"""Scenario C — chat-driven gate approval verification (Chantier 2.7 FIX 3).

Proves that posting `/chat` with text="approved" while the graph is parked at a
manager_review interrupt actually drives the checkpoint forward via
Command(resume=...). The earlier failure mode this guards against:

  - Test asserted DB had a pending G1 row (true from t=0 because gates are
    seeded), then sent "approved", and "graph progressed" was assumed.
  - But the graph wasn't actually at __interrupt__ yet — gates are seeded on
    mission creation, so the DB row tells us nothing about graph position.

This harness instead asserts the LangGraph checkpoint is *actually parked* at
the expected interrupt before sending "approved", by inspecting
`~/.marvin/checkpoints.db` directly. Two precondition signals are required:

  1. Latest checkpoint blob for the thread mentions __interrupt__ (binary marker)
  2. Latest checkpoint blob mentions the expected gate_id (binary marker)

Exit 0 = PASS, evidence printed. Exit non-zero = FAIL with diagnostic.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from queue import Empty, Queue

REPO = Path(__file__).resolve().parent.parent
HEALTH_TIMEOUT = 30
G1_GATE_TYPE = "manager_review"
G3_GATE_TYPE = "final_review"
DATA_GATE_TYPE = "data_availability"
CONFIRMATION_GATE_TYPE = "hypothesis_confirmation"
CLARIFICATION_GATE_TYPE = "clarification_request"
RESUME_AFTER_APPROVE_S = 15
G3_TIMEOUT_S = 360
QA_STREAM_S = 6
APPROVE_STREAM_S = 8
PRE_G1_TIMEOUT_S = 360

BRIEF = (
    "Scenario C brief: evaluate Mistral AI investment opportunity at a €6B "
    "post-money valuation. Mistral AI is a French foundation-model company "
    "based in Paris, sector open-weight LLMs and inference platforms, "
    "Series B stage, with leadership from ex-DeepMind and Meta researchers. "
    "Geography France/EU with US enterprise expansion. The IC question is "
    "whether we should lead a $300M growth round at €6B post-money. Scope: "
    "standard 6-week commercial due diligence covering market positioning, "
    "unit economics, technology moat, and regulatory exposure. Data: no "
    "data room is available; accept public filings, expert interviews, and "
    "product testing only. Generate the framing memo and hypotheses from "
    "this brief — do not invent additional milestones beyond the standard "
    "MARVIN workplan."
)


GENERIC_CLARIFICATION_ANSWER = (
    "Proceed with the brief as written. Use public filings, expert interviews, "
    "and product testing. Accept LOW_CONFIDENCE findings where data is thin. "
    "Default to a 6-week scope and the four workstreams above."
)


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def load_env() -> dict[str, str]:
    env = os.environ.copy()
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    env["PYTHONPATH"] = str(REPO)
    return env


def http(method: str, url: str, body: dict | None = None, timeout: int = 15):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:  # noqa: BLE001
        return 0, repr(e)


# --------------------------------------------------------------------------- #
# SSE consumer thread                                                         #
# --------------------------------------------------------------------------- #


class SSEStream:
    """One persistent SSE connection consumed in a background thread.

    Events land in a thread-safe queue so the main thread can wait on specific
    event types without losing intermediate ones.
    """

    def __init__(self, url: str, body: dict, label: str) -> None:
        self.url = url
        self.body = body
        self.label = label
        self.q: "Queue[tuple[str, object]]" = Queue()
        self._stop = threading.Event()
        self._resp = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            data = json.dumps(self.body).encode()
            req = urllib.request.Request(
                self.url, data=data, method="POST",
                headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            )
            self._resp = urllib.request.urlopen(req, timeout=600)
            event = None
            buf: list[str] = []
            while not self._stop.is_set():
                line = self._resp.readline()
                if not line:
                    break
                s = line.decode(errors="replace").rstrip("\r\n")
                if s == "":
                    if event or buf:
                        payload = "\n".join(buf)
                        try:
                            parsed = json.loads(payload) if payload else None
                        except Exception:  # noqa: BLE001
                            parsed = payload
                        self.q.put((event or "message", parsed))
                    event, buf = None, []
                elif s.startswith("event:"):
                    event = s[6:].strip()
                elif s.startswith("data:"):
                    buf.append(s[5:].lstrip())
        except Exception as e:  # noqa: BLE001
            self.q.put(("__stream_error__", repr(e)))
        finally:
            self.q.put(("__stream_end__", None))

    def wait_for(
        self,
        event_names: set[str],
        timeout: float,
        predicate=None,
    ) -> tuple[str, object] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                name, payload = self.q.get(timeout=remaining)
            except Empty:
                return None
            if name in event_names and (predicate is None or predicate(payload)):
                return name, payload
            if name == "__stream_error__":
                print(f"[{self.label}] stream error: {payload}")
                return None
            if name == "__stream_end__":
                return None
        return None

    def drain_now(self) -> list[tuple[str, object]]:
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except Empty:
                break
        return out

    def stop(self) -> None:
        # Mark stop, then close the underlying socket from a daemon thread so
        # this method never blocks the main thread on a recalcitrant
        # urllib3/SSL close path.
        self._stop.set()
        resp = self._resp
        if resp is None:
            return
        def _force_close():
            try:
                # Closing the underlying fp first is more reliable than .close()
                fp = getattr(resp, "fp", None)
                if fp is not None:
                    try:
                        fp.close()
                    except Exception:  # noqa: BLE001
                        pass
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=_force_close, daemon=True).start()


# --------------------------------------------------------------------------- #
# checkpoint snapshot                                                         #
# --------------------------------------------------------------------------- #


def checkpoint_snapshot(db_path: Path, thread_id: str) -> dict:
    """Inspect latest checkpoint row for `thread_id` and look for interrupt
    markers. Uses binary substring search on the serialized blobs because
    AsyncSqliteSaver writes msgpack and we don't want a hard ormsgpack
    dependency in the harness.
    """
    if not db_path.exists():
        return {"exists": False, "reason": f"checkpoints.db not found at {db_path}"}
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata "
            "FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id DESC LIMIT 1",
            (thread_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"exists": False, "reason": "no rows for thread_id"}
        ckpt_id, parent_id, ckpt_type, ckpt_blob, meta_blob = row
        ckpt_bytes = bytes(ckpt_blob or b"")
        meta_bytes = bytes(meta_blob or b"")
        combined = ckpt_bytes + meta_bytes
        has_interrupt_marker = b"__interrupt__" in combined
        # Also pull any pending writes registered against this checkpoint;
        # interrupts surface as writes with channel "__interrupt__".
        cur.execute(
            "SELECT channel, type FROM writes "
            "WHERE thread_id = ? AND checkpoint_id = ? ORDER BY idx",
            (thread_id, ckpt_id),
        )
        write_channels = [r[0] for r in cur.fetchall()]
        return {
            "exists": True,
            "checkpoint_id": ckpt_id,
            "parent_checkpoint_id": parent_id,
            "type": ckpt_type,
            "has_interrupt_marker": has_interrupt_marker,
            "write_channels": write_channels,
            "ckpt_size": len(ckpt_bytes),
            "meta_size": len(meta_bytes),
            "raw_blob": combined,  # kept for gate-id substring lookup
        }
    finally:
        conn.close()


def assert_at_interrupt(snap: dict, expected_gate_id: str, label: str) -> tuple[bool, str]:
    if not snap.get("exists"):
        return False, f"checkpoint missing: {snap.get('reason')}"
    if not snap.get("has_interrupt_marker"):
        return False, "checkpoint has no __interrupt__ marker (graph not parked)"
    raw = snap.get("raw_blob") or b""
    if expected_gate_id.encode() not in raw:
        return False, f"checkpoint has interrupt marker but not gate_id={expected_gate_id}"
    return True, f"at __interrupt__ for {expected_gate_id}"


# --------------------------------------------------------------------------- #
# DB helpers                                                                  #
# --------------------------------------------------------------------------- #


def gate_row(marvin_db: Path, gate_id: str) -> dict | None:
    if not marvin_db.exists():
        return None
    conn = sqlite3.connect(str(marvin_db))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM gates WHERE id = ?", (gate_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# scenario                                                                    #
# --------------------------------------------------------------------------- #


def reset_state_dirs(checkpoints_db: Path, marvin_db: Path) -> None:
    for p in (checkpoints_db, marvin_db):
        if p.exists():
            p.unlink()


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="marvin-scen-c-"))
    checkpoints_db = workdir / "checkpoints.db"
    marvin_db = workdir / "marvin.db"
    reset_state_dirs(checkpoints_db, marvin_db)

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = load_env()
    env["MARVIN_CHECKPOINT_DB"] = str(checkpoints_db)
    env["MARVIN_DB_PATH"] = str(marvin_db)

    log_path = workdir / "uvicorn.log"
    print(f"[c] port={port} workdir={workdir}")

    proc = subprocess.Popen(
        [str(REPO / ".venv/bin/python"), "-m", "uvicorn",
         "marvin_ui.server:app", "--port", str(port)],
        cwd=str(REPO), env=env,
        stdout=open(log_path, "ab"), stderr=subprocess.STDOUT,
    )

    evidence: dict[str, object] = {
        "checkpoint_at_g1_before_chat": None,
        "chat_approved_response": None,
        "subsequent_sse_events": None,
        "final_db_state_g1": None,
        "graph_reached_g3": None,
    }

    fail_reasons: list[str] = []

    try:
        # ---------- wait for health ---------- #
        deadline = time.monotonic() + HEALTH_TIMEOUT
        ready = False
        while time.monotonic() < deadline:
            time.sleep(0.4)
            s, _ = http("GET", f"{base}/health", timeout=2)
            if s == 200:
                ready = True
                break
            if proc.poll() is not None:
                print(f"[c] uvicorn died exit={proc.returncode}")
                print(log_path.read_text(errors="replace")[-3000:])
                return 1
        if not ready:
            print(f"[c] uvicorn not ready in {HEALTH_TIMEOUT}s")
            return 1

        # ---------- create mission ---------- #
        s, b = http("POST", f"{base}/api/v1/missions", body={
            "client": "ScenC", "target": "mistral-ai",
            "ic_question": "Should we invest at €6B post-money?",
            "mission_type": "cdd",
        })
        if s != 200:
            print(f"[c] FAIL — POST /missions {s}: {b[:300]}")
            return 1
        mid = json.loads(b)["mission_id"]
        print(f"[c] mission_id={mid}")

        # ---------- start brief stream ---------- #
        stream_a = SSEStream(
            f"{base}/api/v1/missions/{mid}/chat",
            {"text": BRIEF},
            label="A:brief",
        )
        stream_a.start()

        # ---------- walk pre-G1 gates: clarification → confirmation → data ---------- #
        # The pipeline can park at several gate types before reaching G1
        # manager_review. Handle each via the standard REST validate path so
        # the chat-driven approval test runs only against the G1 interrupt.
        print("[c] walking pre-G1 gates until manager_review fires …")
        g1_payload: dict | None = None
        deadline_pre_g1 = time.monotonic() + PRE_G1_TIMEOUT_S
        seen_pre_g1: list[str] = []
        while time.monotonic() < deadline_pre_g1:
            evt = stream_a.wait_for(
                {"gate_pending", "error"},
                timeout=max(1.0, deadline_pre_g1 - time.monotonic()),
            )
            if evt is None:
                break
            name, payload = evt
            if name == "error":
                print(f"[c] FAIL — SSE error before G1: {payload}")
                return 1
            if not isinstance(payload, dict):
                continue
            gtype = payload.get("gate_type")
            gid = payload.get("id") or payload.get("gate_id")
            seen_pre_g1.append(f"{gtype}:{gid}")
            print(f"[c]   gate_pending: type={gtype} id={gid}")

            if gtype == G1_GATE_TYPE:
                g1_payload = payload
                break

            if gtype == CLARIFICATION_GATE_TYPE:
                # Number of answers must match number of questions.
                qs = payload.get("questions") or []
                n = max(1, len(qs))
                body = {"answers": [GENERIC_CLARIFICATION_ANSWER] * n}
                s, b = http(
                    "POST",
                    f"{base}/api/v1/missions/{mid}/gates/{gid}/validate",
                    body=body,
                )
                if s != 200:
                    print(f"[c] FAIL — clarification validate {s}: {b[:300]}")
                    return 1
                continue
            if gtype == CONFIRMATION_GATE_TYPE:
                s, b = http(
                    "POST",
                    f"{base}/api/v1/missions/{mid}/gates/{gid}/validate",
                    body={"verdict": "APPROVED", "notes": "auto-approved by scenario_c harness"},
                )
                if s != 200:
                    print(f"[c] FAIL — confirmation validate {s}: {b[:300]}")
                    return 1
                continue
            if gtype == DATA_GATE_TYPE:
                s, b = http(
                    "POST",
                    f"{base}/api/v1/missions/{mid}/gates/{gid}/validate",
                    body={"decision": "proceed_low_confidence"},
                )
                if s != 200:
                    print(f"[c] FAIL — data validate {s}: {b[:300]}")
                    return 1
                continue
            # Unknown gate: validate with APPROVED to keep moving.
            print(f"[c]   unknown gate_type {gtype} — validating APPROVED")
            http(
                "POST",
                f"{base}/api/v1/missions/{mid}/gates/{gid}/validate",
                body={"verdict": "APPROVED"},
            )

        if g1_payload is None:
            print(f"[c] FAIL — never reached manager_review. Saw: {seen_pre_g1}")
            return 1
        g1_id = g1_payload.get("id") or g1_payload.get("gate_id")
        print(f"[c] manager_review G1 id={g1_id}")

        # ---------- close stream A so chat-driven approval can acquire lock ---------- #
        print("[c] closing stream A …", flush=True)
        stream_a.stop()
        time.sleep(1.5)
        print("[c] capturing checkpoint snapshot …", flush=True)

        # ---------- precondition: checkpoint at __interrupt__ for G1 ---------- #
        snap_g1 = checkpoint_snapshot(checkpoints_db, mid)
        ok, reason = assert_at_interrupt(snap_g1, g1_id, "G1")
        evidence["checkpoint_at_g1_before_chat"] = {
            "checkpoint_id": snap_g1.get("checkpoint_id"),
            "parent_checkpoint_id": snap_g1.get("parent_checkpoint_id"),
            "type": snap_g1.get("type"),
            "has_interrupt_marker": snap_g1.get("has_interrupt_marker"),
            "write_channels": snap_g1.get("write_channels"),
            "expected_gate_id": g1_id,
            "precondition_ok": ok,
            "precondition_reason": reason,
        }
        if not ok:
            print(f"[c] ABORT — checkpoint precondition failed: {reason}")
            print(f"[c] harness must be fixed (do NOT interpret as FIX 3 bug)")
            return 2

        print(f"[c] precondition OK — {reason}")

        # ---------- send chat "approved" ---------- #
        stream_b = SSEStream(
            f"{base}/api/v1/missions/{mid}/chat",
            {"text": "approved"},
            label="B:approve",
        )
        stream_b.start()

        # ---------- verify resume happens within window ---------- #
        deadline_b = time.monotonic() + RESUME_AFTER_APPROVE_S
        b_events: list[tuple[str, object]] = []
        saw_phase_or_agent_after_g1 = False
        while time.monotonic() < deadline_b:
            try:
                ev = stream_b.q.get(timeout=0.5)
            except Empty:
                continue
            b_events.append(ev)
            name = ev[0]
            if name in ("phase_changed", "agent_active", "milestone_done", "finding_added", "gate_pending"):
                saw_phase_or_agent_after_g1 = True
        evidence["chat_approved_response"] = [
            {"event": n, "payload": p if isinstance(p, (dict, str, int, float, type(None))) else str(p)}
            for n, p in b_events[:25]
        ]
        evidence["subsequent_sse_events"] = {
            "count": len(b_events),
            "graph_progressed": saw_phase_or_agent_after_g1,
            "window_s": RESUME_AFTER_APPROVE_S,
        }
        if not saw_phase_or_agent_after_g1:
            fail_reasons.append(
                "chat 'approved' did not produce progression events in "
                f"{RESUME_AFTER_APPROVE_S}s — real FIX 3 bug, do NOT commit"
            )

        # ---------- final DB state for G1 ---------- #
        # Note: the gates table encodes verdict as status — "completed" means
        # APPROVED for review_claims-format gates; "failed" means rejected.
        # There is no separate verdict column.
        g1_db = gate_row(marvin_db, g1_id) or {}
        evidence["final_db_state_g1"] = {
            "id": g1_db.get("id"),
            "status": g1_db.get("status"),
            "completion_notes": (g1_db.get("completion_notes") or "")[:120],
        }
        if g1_db.get("status") != "completed":
            fail_reasons.append(f"G1 status not completed (got {g1_db.get('status')!r})")

        # ---------- bonus: confirm graph reached G3 ---------- #
        # Source of truth = checkpoints.db. Polling here proves the post-G1
        # work (adversus → merlin → gate_entry) ran end-to-end after the
        # chat-driven approval. We do NOT exercise the chat-vs-Q&A
        # precedence at G3 here: that path opens a second SSE chat connection
        # while stream B still holds the per-mission lock, which makes the
        # harness brittle. The precedence rule (`_is_approval_text` regex) is
        # covered by unit tests in `tests/test_server_resume.py`.
        print("[c] bonus: polling checkpoints DB for G3 interrupt …")
        g3_id = "gate-" + mid + "-G3"
        deadline_g3 = time.monotonic() + G3_TIMEOUT_S
        snap_g3 = None
        while time.monotonic() < deadline_g3:
            snap = checkpoint_snapshot(checkpoints_db, mid)
            if snap.get("has_interrupt_marker") and (g3_id.encode() in (snap.get("raw_blob") or b"")):
                snap_g3 = snap
                break
            time.sleep(2.0)

        if snap_g3 is None:
            evidence["graph_reached_g3"] = {
                "reached": False,
                "note": f"G3 interrupt not observed in checkpoints DB within {G3_TIMEOUT_S}s",
            }
            fail_reasons.append(
                f"graph did not reach G3 within {G3_TIMEOUT_S}s after chat approval"
            )
        else:
            ok3, reason3 = assert_at_interrupt(snap_g3, g3_id, "G3")
            evidence["graph_reached_g3"] = {
                "reached": True,
                "g3_id": g3_id,
                "checkpoint_id": snap_g3.get("checkpoint_id"),
                "checkpoint_precondition_ok": ok3,
                "checkpoint_precondition_reason": reason3,
            }
            if not ok3:
                fail_reasons.append(f"G3 checkpoint marker mismatch: {reason3}")

        # Tear down stream B before evidence print so cleanup is bounded.
        stream_b.stop()

        # ---------- print evidence table ---------- #
        print()
        print("=" * 78)
        print("Scenario C — Evidence")
        print("=" * 78)
        for k, v in evidence.items():
            print(f"\n## {k}")
            print(json.dumps(v, indent=2, default=str)[:2000])
        print()
        print("=" * 78)
        if fail_reasons:
            print("Verdict: FAIL")
            for r in fail_reasons:
                print(f"  ✗ {r}")
            return 1
        print("Verdict: PASS")
        print("  ✓ checkpoint precondition was at __interrupt__ for G1")
        print("  ✓ chat 'approved' produced progression events within window")
        print("  ✓ DB G1 completed with APPROVED")
        if isinstance(evidence.get("graph_reached_g3"), dict) and evidence["graph_reached_g3"].get("reached"):
            print("  ✓ graph progressed end-to-end through redteam/merlin to G3")
        return 0

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        # Keep workdir on failure for forensics; clean only on success-ish exits.
        # (Caller can inspect log_path if needed.)


if __name__ == "__main__":
    sys.exit(main())
