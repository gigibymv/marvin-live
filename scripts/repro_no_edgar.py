"""Reproduction script: W2 tab stays in_progress + duplicate "Mission complete" for fictive target.

Scenario: CDD mission against a fictive company with no SEC EDGAR data.
Calculus should mark W2 milestones as `blocked`. Bug under investigation:
  1. W2 tab spins forever on in_progress
  2. "Mission complete" appears multiple times in the SSE chat

What it does:
  1. Boots uvicorn on a free port with temp DBs
  2. Creates a mission targeting "AcmeFin Holdings" (fictive, no EDGAR)
  3. Streams /chat, auto-approving gates when gate_pending fires
  4. Captures full SSE until run_end or 60s timeout
  5. Writes raw stream to /tmp/marvin_repro_sse.log
  6. Queries SQLite for W2 milestone statuses and W2 deliverables
  7. Simulates frontend tabCompletedReady for W2

Exit 0 always (repro output regardless); findings in stdout.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import threading
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STREAM_TIMEOUT = 90  # seconds total for the full mission run
HEALTH_TIMEOUT = 30
LOG_PATH = Path("/tmp/marvin_repro_sse.log")

BRIEF = (
    "CDD brief: assess acquisition of AcmeFin Holdings (a fictive mid-market "
    "specialty finance company). Client: TestPE. IC question: should we acquire "
    "AcmeFin Holdings? No SEC EDGAR ticker available — rely on public press "
    "coverage and management interviews only. Budget: 6-week scope."
)


def find_free_port() -> int:
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
    except Exception as e:
        return 0, str(e)


def stream_sse_with_gate_handler(
    base: str,
    mission_id: str,
    body: dict,
    timeout: float,
) -> tuple[list[tuple[str, object]], str | None, int]:
    """Stream SSE and auto-approve gates.

    Returns: (events, error_or_None, gate_approval_count)
    """
    url = f"{base}/api/v1/missions/{mission_id}/chat"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )

    events: list[tuple[str, object]] = []
    err: str | None = None
    gates_approved = 0
    raw_lines: list[str] = []

    start = time.monotonic()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout + 5)
        event_type = None
        buf: list[str] = []

        while time.monotonic() - start < timeout:
            line = resp.readline()
            if not line:
                break
            s = line.decode(errors="replace").rstrip("\r\n")
            raw_lines.append(s)

            if s == "":
                if event_type or buf:
                    payload_str = "\n".join(buf)
                    try:
                        parsed = json.loads(payload_str) if payload_str else None
                    except Exception:
                        parsed = payload_str
                    events.append((event_type or "message", parsed))

                    # Auto-approve gates
                    if event_type == "gate_pending":
                        gate_id = None
                        if isinstance(parsed, dict):
                            gate_id = parsed.get("gate_id") or parsed.get("id")
                        if gate_id:
                            _approve_gate(base, mission_id, gate_id)
                            gates_approved += 1
                        else:
                            print(f"[repro] gate_pending but no gate_id in: {parsed}")

                    # Stop on run_end
                    if event_type == "run_end":
                        break

                event_type, buf = None, []
            elif s.startswith("event:"):
                event_type = s[6:].strip()
            elif s.startswith("data:"):
                buf.append(s[5:].lstrip())

        try:
            resp.close()
        except Exception:
            pass
    except Exception as e:
        err = repr(e)

    # Write raw stream to log
    LOG_PATH.write_text("\n".join(raw_lines), encoding="utf-8")

    return events, err, gates_approved


def _approve_gate(base: str, mission_id: str, gate_id: str) -> None:
    """POST a generic approval verdict for a gate."""
    print(f"[repro] auto-approving gate {gate_id}...")
    url = f"{base}/api/v1/missions/{mission_id}/gates/{gate_id}/validate"
    # Try a generic proceed_low_confidence verdict first (works for data_decision gates)
    # For clarification gates, send answers=[]
    # We'll try both and see which succeeds
    for body in [
        {"verdict": "proceed_low_confidence", "comment": "repro auto-approve"},
        {"verdict": "approved", "comment": "repro auto-approve"},
        {"answers": [], "verdict": "approved"},
        {"answers": ["repro answer"], "verdict": "approved"},
    ]:
        status, resp_body = http("POST", url, body=body, timeout=10)
        if status == 200:
            print(f"[repro]   gate {gate_id} approved (body={body}, status=200)")
            return
        # 422 = wrong format, try next; 404 = already resolved, stop
        if status == 404:
            print(f"[repro]   gate {gate_id} already resolved (404)")
            return
    print(f"[repro]   WARNING: could not approve gate {gate_id} (last status={status})")


def query_db(db_path: str, mission_id: str) -> dict:
    """Query SQLite for W2 milestones, deliverables, and mission status."""
    if not Path(db_path).exists():
        return {"error": f"DB not found: {db_path}"}

    result: dict = {}
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row

        # Mission status
        row = con.execute(
            "SELECT id, status, target, client FROM missions WHERE id=?", (mission_id,)
        ).fetchone()
        if row:
            result["mission"] = dict(row)
        else:
            result["mission"] = None

        # W2 milestones (workstream_id = 'W2')
        rows = con.execute(
            "SELECT id, title, status, workstream_id, agent_id FROM milestones "
            "WHERE mission_id=? AND workstream_id='W2'",
            (mission_id,),
        ).fetchall()
        result["w2_milestones"] = [dict(r) for r in rows]

        # All milestones for reference
        rows_all = con.execute(
            "SELECT id, title, status, workstream_id, agent_id FROM milestones "
            "WHERE mission_id=?",
            (mission_id,),
        ).fetchall()
        result["all_milestones"] = [dict(r) for r in rows_all]

        # W2 deliverables (by workstream_id column or matching file_path pattern)
        # Try workstream_id column first, fall back to agent_id
        try:
            rows_d = con.execute(
                "SELECT id, deliverable_type, status, workstream_id, agent_id, file_path "
                "FROM deliverables WHERE mission_id=? AND workstream_id='W2'",
                (mission_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            # workstream_id column may not exist on older schema
            rows_d = con.execute(
                "SELECT id, deliverable_type, status, agent_id, file_path "
                "FROM deliverables WHERE mission_id=? AND agent_id='calculus'",
                (mission_id,),
            ).fetchall()
        result["w2_deliverables"] = [dict(r) for r in rows_d]

        # All deliverables for reference
        try:
            rows_dall = con.execute(
                "SELECT id, deliverable_type, status, workstream_id, agent_id FROM deliverables "
                "WHERE mission_id=?",
                (mission_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows_dall = con.execute(
                "SELECT id, deliverable_type, status, agent_id FROM deliverables "
                "WHERE mission_id=?",
                (mission_id,),
            ).fetchall()
        result["all_deliverables"] = [dict(r) for r in rows_dall]

        con.close()
    except Exception as e:
        result["db_error"] = repr(e)

    return result


def analyze_mission_complete(events: list[tuple[str, object]]) -> dict:
    """Find all 'Mission complete' text emissions in the SSE stream."""
    count = 0
    sources: list[str] = []
    MISSION_COMPLETE_NEEDLE = "Mission complete"

    for ev_type, payload in events:
        text = None
        source = None
        if isinstance(payload, dict):
            text = payload.get("text") or payload.get("content") or payload.get("message") or ""
            source = payload.get("agent") or payload.get("source") or payload.get("node") or ev_type
        elif isinstance(payload, str):
            text = payload
            source = ev_type

        if text and MISSION_COMPLETE_NEEDLE in str(text):
            count += 1
            sources.append(str(source))

    return {"count": count, "sources": sources}


def simulate_tab_completed_ready_w2(db_data: dict, events: list[tuple[str, object]]) -> str:
    """Simulate the frontend tabCompletedReady logic for W2.

    From MissionControl.tsx lines 2014-2047:
      tabCompletedReady = missionCompleted
        || (allMilestonesDone && wsHasReadyDeliverable)
        || synthesisDone (W3 only)
        || agentDoneWithDeliverable

    Notes:
      - missionCompleted: mission.status === "completed" (frontend uses "completed")
      - allMilestonesDone: all W2 milestones are in ["delivered","skipped","blocked"]
      - wsHasReadyDeliverable: any deliverable for W2 with status=="ready"
      - agentDoneWithDeliverable: agent status "done" AND wsHasReadyDeliverable
      - synthesisDone: W3 only, irrelevant here
    """
    reasoning: list[str] = []

    mission = db_data.get("mission") or {}
    # Frontend checks mission.status === "completed"; DB may store "complete" or "completed"
    db_mission_status = mission.get("status", "unknown")
    mission_completed_db = db_mission_status in ("completed", "complete")
    reasoning.append(f"DB mission status: '{db_mission_status}' → missionCompleted={mission_completed_db}")

    w2_milestones = db_data.get("w2_milestones", [])
    if not w2_milestones:
        reasoning.append("W2 milestones: NONE in DB → allMilestonesDone=False (no milestones = False)")
        all_milestones_done = False
    else:
        terminal_statuses = {"delivered", "skipped", "blocked"}
        terminal = [m for m in w2_milestones if m.get("status") in terminal_statuses]
        all_milestones_done = len(terminal) == len(w2_milestones)
        reasoning.append(
            f"W2 milestones: {len(w2_milestones)} total, "
            f"{len(terminal)} terminal (delivered/skipped/blocked) → allMilestonesDone={all_milestones_done}"
        )
        for m in w2_milestones:
            reasoning.append(f"  - {m.get('id')} '{m.get('title','?')}': status={m.get('status')}")

    w2_deliverables = db_data.get("w2_deliverables", [])
    ws_has_ready_deliverable = any(d.get("status") == "ready" for d in w2_deliverables)
    reasoning.append(f"W2 deliverables: {len(w2_deliverables)} total, hasReady={ws_has_ready_deliverable}")

    # agent status from SSE: look for agent_done events for calculus
    calculus_done = False
    for ev_type, payload in events:
        if ev_type == "agent_done" and isinstance(payload, dict):
            agent = (payload.get("agent") or "").lower()
            if agent == "calculus":
                calculus_done = True
        # Also check node_update / phase events
        if ev_type == "phase_changed" and isinstance(payload, dict):
            pass  # not directly useful for agent status

    agent_done_with_deliverable = calculus_done and ws_has_ready_deliverable
    reasoning.append(f"calculus agent_done SSE seen: {calculus_done} → agentDoneWithDeliverable={agent_done_with_deliverable}")

    synthesis_done = False  # W3 only

    tab_completed_ready = (
        mission_completed_db
        or (all_milestones_done and ws_has_ready_deliverable)
        or synthesis_done
        or agent_done_with_deliverable
    )
    reasoning.append(
        f"\ntabCompletedReady = {mission_completed_db} (missionCompleted) "
        f"|| ({all_milestones_done} && {ws_has_ready_deliverable}) (allDone&&hasDeliverable) "
        f"|| False (synthesisDone W3) "
        f"|| {agent_done_with_deliverable} (agentDone+deliverable)"
        f" = {tab_completed_ready}"
    )

    # Key bug analysis
    if not tab_completed_ready and all_milestones_done:
        reasoning.append(
            "BUG CONFIRMED: allMilestonesDone=True but wsHasReadyDeliverable=False → "
            "tab stays 'in_progress' (line 2055-2056 fallthrough) even though all milestones are terminal."
        )

    return "\n".join(reasoning)


def main() -> int:
    # Check API key before doing anything
    env = load_env()
    if not env.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set in .env — repro meaningless without real LLM. STOP.")
        return 1

    port = find_free_port()
    base = f"http://127.0.0.1:{port}"
    print(f"[repro] port={port}")

    tmp_db = Path(tempfile.mkdtemp(prefix="marvin-repro-")) / "checkpoints.db"
    tmp_marvin_db = Path(tempfile.mkdtemp(prefix="marvin-repro-mdb-")) / "marvin.db"
    print(f"[repro] marvin DB: {tmp_marvin_db}")

    env["MARVIN_CHECKPOINT_DB"] = str(tmp_db)
    env["MARVIN_DB_PATH"] = str(tmp_marvin_db)

    log_path = Path(tempfile.mkstemp(prefix="marvin-repro-uvicorn-", suffix=".log")[1])
    print(f"[repro] uvicorn log: {log_path}")

    proc = subprocess.Popen(
        [str(REPO / ".venv/bin/python"), "-m", "uvicorn",
         "marvin_ui.server:app", "--port", str(port)],
        cwd=str(REPO), env=env,
        stdout=open(log_path, "ab"),
        stderr=subprocess.STDOUT,
    )

    try:
        # Wait for health
        deadline = time.monotonic() + HEALTH_TIMEOUT
        ready = False
        while time.monotonic() < deadline:
            time.sleep(0.5)
            s, _ = http("GET", f"{base}/health", timeout=2)
            if s == 200:
                ready = True
                break
            if proc.poll() is not None:
                print(f"[repro] FAIL — uvicorn died during startup (exit={proc.returncode})")
                print("\n".join(log_path.read_text(errors="replace").splitlines()[-20:]))
                return 1
        if not ready:
            print(f"[repro] FAIL — uvicorn never reached /health in {HEALTH_TIMEOUT}s")
            return 1
        print("[repro] server boot: PASS")

        # Create mission
        s, b = http("POST", f"{base}/api/v1/missions", body={
            "client": "TestPE",
            "target": "AcmeFin Holdings",
            "ic_question": "should we acquire AcmeFin Holdings?",
            "mission_type": "cdd",
        })
        if s != 200:
            print(f"[repro] FAIL — POST /missions returned {s}: {b[:400]}")
            return 1
        mission_id = json.loads(b)["mission_id"]
        print(f"[repro] mission_id={mission_id}")

        # Stream chat with gate auto-approval
        print(f"[repro] streaming /chat (timeout={STREAM_TIMEOUT}s, gates auto-approved)...")
        t0 = time.monotonic()
        events, err, gates_approved = stream_sse_with_gate_handler(
            base=base,
            mission_id=mission_id,
            body={"text": BRIEF},
            timeout=STREAM_TIMEOUT,
        )
        elapsed = time.monotonic() - t0

        # Determine stream end condition
        has_run_end = any(ev[0] == "run_end" for ev in events)
        stream_end_status = "PASS (run_end)" if has_run_end else f"TIMEOUT ({elapsed:.0f}s)"
        print(f"[repro] stream done: {stream_end_status} — {len(events)} events, {elapsed:.1f}s")
        if err:
            print(f"[repro] stream error: {err}")

        # Write raw log
        print(f"[repro] raw SSE written to: {LOG_PATH}")

        # Analysis: Mission complete count
        mc = analyze_mission_complete(events)

        # DB query
        db_data = query_db(str(tmp_marvin_db), mission_id)

        # Frontend simulation
        tab_sim = simulate_tab_completed_ready_w2(db_data, events)

        # Print event type summary
        event_type_counts: dict[str, int] = {}
        for ev_type, _ in events:
            event_type_counts[ev_type] = event_type_counts.get(ev_type, 0) + 1

        print("\n" + "=" * 60)
        print("## Repro outcome")
        print(f"- Server boot: PASS")
        print(f"- Mission created: {mission_id}")
        print(f"- Gates auto-approved: {gates_approved}")
        print(f"- Stream ended: {stream_end_status}")
        print(f"- Total SSE events: {len(events)}")
        print(f"- Event type counts: {json.dumps(event_type_counts, indent=2)}")
        print(f"- \"Mission complete\" SSE count: {mc['count']}")
        print(f"- Sources of mission-complete events: {mc['sources']}")

        print("\n### W2 milestone DB statuses:")
        w2m = db_data.get("w2_milestones", [])
        if w2m:
            for m in w2m:
                print(f"  - {m.get('id')} | {m.get('title','?')[:50]} | status={m.get('status')}")
        else:
            print("  (none found)")

        print(f"\n### W2 deliverables count: {len(db_data.get('w2_deliverables', []))}")
        for d in db_data.get("w2_deliverables", []):
            print(f"  - {d.get('id')} | {d.get('deliverable_type','?')} | status={d.get('status')}")

        print("\n### All milestones (for context):")
        for m in db_data.get("all_milestones", []):
            print(f"  - ws={m.get('workstream_id')} | {m.get('id')} | {m.get('title','?')[:40]} | {m.get('status')}")

        print("\n### Mission DB status:")
        print(f"  {db_data.get('mission')}")

        print("\n### Frontend tabCompletedReady simulation (W2):")
        print(tab_sim)

        if db_data.get("db_error"):
            print(f"\n### DB error: {db_data['db_error']}")

        # Surprises section
        print("\n## Surprises")
        surprises = []
        if mc["count"] > 1:
            surprises.append(
                f"'Mission complete' appeared {mc['count']} times (sources: {set(mc['sources'])}). "
                "Likely both _maybe_emit_mission_complete (line 1565) and phase='done' path both emit."
            )
        if not w2m:
            surprises.append(
                "No W2 milestones recorded in DB — Calculus may not have run or milestone "
                "creation failed silently."
            )
        blocked = [m for m in w2m if m.get("status") == "blocked"]
        if blocked and not any(d.get("status") == "ready" for d in db_data.get("w2_deliverables", [])):
            surprises.append(
                f"{len(blocked)} W2 milestone(s) correctly marked 'blocked' by Calculus, "
                "but no ready W2 deliverable → allMilestonesDone=True but wsHasReadyDeliverable=False "
                "→ tabCompletedReady stays False → tab spins on in_progress."
            )
        if not surprises:
            surprises.append("(none beyond expected behavior)")
        for s_item in surprises:
            print(f"- {s_item}")

        print("\n## Obstacles")
        obstacles = []
        if err:
            obstacles.append(f"SSE stream error: {err}")
        if not has_run_end:
            obstacles.append(f"Stream timed out after {STREAM_TIMEOUT}s — mission may not have completed")
        if not obstacles:
            obstacles.append("(none)")
        for o in obstacles:
            print(f"- {o}")

        print(f"\n[repro] uvicorn log: {log_path}")
        print(f"[repro] raw SSE log: {LOG_PATH}")
        return 0

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
