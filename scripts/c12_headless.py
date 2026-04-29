"""C12 headless verification orchestrator.

Runs a fresh Doctolib mission end-to-end via the API, drives gate validations
(approve G0, REJECT G1 first time, approve G1 retry, approve G3), captures the
SSE stream, and asserts the 6 acceptance criteria.

Usage:
    PYTHONPATH=$PWD .venv/bin/python scripts/c12_headless.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:8095"
DB = os.path.expanduser("~/.marvin/marvin.db")
MISSION_DIR = Path(os.path.expanduser("~/.marvin/missions"))

BRIEF = (
    "We are evaluating a potential investment in Doctolib, the European "
    "doctor-appointment booking platform. Sponsor target close in 4 weeks. "
    "Key questions: (1) Is the European telehealth + booking TAM still "
    "expanding through 2030, or is penetration plateauing? (2) Can Doctolib "
    "defend its lead against Practo / Zocdoc style entrants and against "
    "vertical EMR competitors? (3) Is the unit economics story (LTV/CAC, net "
    "revenue retention on practitioner subscriptions) durable enough to "
    "underwrite a 3x exit. The sponsor has access to a 6-month-old data room "
    "with KPIs through Q4 2025. Recommend GO / NO-GO."
)

events: list[dict] = []
gate_pending_count: dict[str, int] = {}
agent_active_after_reject: list[float] = []
reject_time: list[float] = []
g1_rejected_once = [False]
done = threading.Event()
mission_id_holder: list[str] = [""]


def post_json(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def stream_chat(mission_id: str, text: str) -> None:
    """Stream /chat SSE; queue gate validations as we see gate_pending."""
    proc = subprocess.Popen(
        [
            "/usr/bin/curl", "-sN", "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"text": text}),
            f"{BASE}/api/v1/missions/{mission_id}/chat",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    _consume_stream(proc, mission_id)


def stream_resume(mission_id: str) -> None:
    proc = subprocess.Popen(
        [
            "/usr/bin/curl", "-sN", "-X", "POST",
            f"{BASE}/api/v1/missions/{mission_id}/resume",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    _consume_stream(proc, mission_id)


def _consume_stream(proc, mission_id: str) -> None:
    current_event = None
    deadline = time.time() + 60 * 30  # 30 min cap
    for raw in proc.stdout:
        if time.time() > deadline:
            print("[c12] HARD TIMEOUT 30min", flush=True)
            proc.kill()
            done.set()
            return
        line = raw.rstrip("\n")
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            data = line[6:]
            try:
                payload = json.loads(data)
            except Exception:
                payload = {"raw": data}
            evt = {"type": current_event, "data": payload, "ts": time.time()}
            events.append(evt)
            _handle(evt, mission_id, proc)
            if current_event == "run_end":
                print("[c12] run_end received", flush=True)
                done.set()
                return
        elif line == "":
            current_event = None


def _handle(evt, mission_id, proc):
    et = evt["type"]
    if et == "agent_active":
        agent = evt["data"].get("agent", "")
        if g1_rejected_once[0] and reject_time and not agent_active_after_reject:
            elapsed = time.time() - reject_time[0]
            print(f"[c12] agent_active={agent} {elapsed:.1f}s after G1 reject", flush=True)
            agent_active_after_reject.append(elapsed)
    elif et == "gate_pending":
        gate_id = evt["data"].get("gate_id") or evt["data"].get("id")
        gate_type = evt["data"].get("gate_type")
        gate_pending_count[gate_id or "?"] = gate_pending_count.get(gate_id or "?", 0) + 1
        print(f"[c12] gate_pending gate_id={gate_id} type={gate_type}", flush=True)
        # Decide action
        threading.Thread(
            target=_drive_gate,
            args=(mission_id, gate_id, gate_type, proc),
            daemon=True,
        ).start()


def _drive_gate(mission_id, gate_id, gate_type, proc):
    time.sleep(2.0)
    if gate_type == "hypothesis_confirmation":
        verdict = "APPROVED"
    elif gate_type == "manager_review":
        if not g1_rejected_once[0]:
            verdict = "REJECTED"
            g1_rejected_once[0] = True
        else:
            verdict = "APPROVED"
    elif gate_type == "final_review":
        verdict = "APPROVED"
    else:
        # data_decision or clarification — handle generically
        if gate_type == "data_decision":
            try:
                post_json(
                    f"/api/v1/missions/{mission_id}/gates/{gate_id}/validate",
                    {"decision": "proceed_low_confidence"},
                )
                print(f"[c12] gate {gate_id} decided=proceed_low_confidence", flush=True)
            except Exception as e:
                print(f"[c12] gate {gate_id} decision err: {e}", flush=True)
            return
        if gate_type == "clarification_questions":
            try:
                post_json(
                    f"/api/v1/missions/{mission_id}/gates/{gate_id}/validate",
                    {"answers": ["proceed with available data"]},
                )
                print(f"[c12] gate {gate_id} clarification answered", flush=True)
            except Exception as e:
                print(f"[c12] gate {gate_id} clarif err: {e}", flush=True)
            return
        verdict = "APPROVED"
    try:
        if verdict == "REJECTED":
            reject_time.append(time.time())
        post_json(
            f"/api/v1/missions/{mission_id}/gates/{gate_id}/validate",
            {"verdict": verdict, "notes": f"c12 auto-{verdict.lower()}"},
        )
        print(f"[c12] gate {gate_id} verdict={verdict}", flush=True)
        # If REJECTED, kill current SSE; backend resets to a phase that needs
        # the chat loop to re-pick-up via /resume.
        if verdict == "REJECTED":
            time.sleep(1.0)
            proc.kill()
            print("[c12] killed chat stream after reject; reattaching via /resume", flush=True)
            threading.Thread(
                target=stream_resume, args=(mission_id,), daemon=True,
            ).start()
    except Exception as e:
        print(f"[c12] gate {gate_id} validate err: {e}", flush=True)


def main() -> int:
    print(f"[c12] creating mission", flush=True)
    res = post_json(
        "/api/v1/missions",
        {
            "client": "C12 Headless",
            "target": "Doctolib",
            "ic_question": "Should we invest in Doctolib at the proposed valuation?",
            "mission_type": "cdd",
        },
    )
    mid = res["mission_id"]
    mission_id_holder[0] = mid
    print(f"[c12] mission_id={mid}", flush=True)

    t = threading.Thread(target=stream_chat, args=(mid, BRIEF), daemon=True)
    t.start()

    # Wait up to 25 minutes for run_end.
    finished = done.wait(timeout=60 * 25)
    if not finished:
        print("[c12] FAIL: timed out waiting for run_end", flush=True)
    print(f"[c12] events captured: {len(events)}", flush=True)

    # ---- ASSERTIONS ----
    print("\n========== C12 ASSERTIONS ==========\n", flush=True)

    # 1. Mission complete message in SSE.
    chat_complete = [
        e for e in events
        if (e["type"] in ("text", "agent_message", "narration"))
        and "Mission complete" in (json.dumps(e["data"]))
    ]
    a1_pass = bool(chat_complete)
    print(f"1. Mission complete msg in SSE: {'PASS' if a1_pass else 'FAIL'} ({len(chat_complete)} matches)")

    # 2. Mission status complete in DB.
    a2_pass = False
    a2_status = "?"
    try:
        con = sqlite3.connect(DB)
        cur = con.execute("SELECT status FROM missions WHERE id=?", (mid,))
        row = cur.fetchone()
        a2_status = row[0] if row else "no-row"
        a2_pass = a2_status == "complete"
        con.close()
    except Exception as e:
        a2_status = f"err:{e}"
    print(f"2. Mission status=complete: {'PASS' if a2_pass else 'FAIL'} (got {a2_status!r})")

    # 3. No Finding/Hypothesis IDs in deliverables.
    a3_pass = True
    a3_hits: list[str] = []
    mdir = MISSION_DIR / mid
    if mdir.exists():
        try:
            grep = subprocess.run(
                ["grep", "-rn", "-E",
                 r"Finding ID: f-|Hypothesis ID: hyp-|Source ID: unassigned",
                 str(mdir)],
                capture_output=True, text=True,
            )
            if grep.stdout.strip():
                a3_pass = False
                a3_hits = grep.stdout.strip().splitlines()[:5]
        except Exception as e:
            a3_pass = False
            a3_hits = [f"grep err: {e}"]
    else:
        # deliverables may also live in DB
        try:
            con = sqlite3.connect(DB)
            cur = con.execute(
                "SELECT id, content FROM deliverables WHERE mission_id=?", (mid,)
            )
            for did, content in cur.fetchall():
                for needle in ("Finding ID: f-", "Hypothesis ID: hyp-", "Source ID: unassigned"):
                    if needle in (content or ""):
                        a3_pass = False
                        a3_hits.append(f"{did}: {needle}")
            con.close()
        except Exception as e:
            a3_hits.append(f"db err: {e}")
    print(f"3. No internal IDs in deliverables: {'PASS' if a3_pass else 'FAIL'}")
    for h in a3_hits[:5]:
        print(f"     hit: {h}")

    # 4. Gate event dedup. Each gate_pending should fire once per fire-attempt.
    # Original G1 fires once, retry G1 fires once. So per gate_id == 1 always.
    a4_pass = all(c == 1 for c in gate_pending_count.values())
    print(f"4. Gate pending fires once per gate_id: {'PASS' if a4_pass else 'FAIL'}")
    for gid, c in gate_pending_count.items():
        print(f"     {gid}: {c}")

    # 5. G1 reject re-fan-out: agent_active within 15s of reject.
    a5_pass = (
        bool(g1_rejected_once[0])
        and bool(agent_active_after_reject)
        and agent_active_after_reject[0] <= 15.0
    )
    g1_retry_fires = sum(1 for gid in gate_pending_count if "retry" in gid.lower() or "G1" in gid)
    a5_detail = (
        f"rejected={g1_rejected_once[0]} "
        f"agent_active_after_reject={agent_active_after_reject[:1]} "
        f"g1_retry_fires={g1_retry_fires}"
    )
    print(f"5. G1 reject re-runs Dora: {'PASS' if a5_pass else 'FAIL'} ({a5_detail})")

    # 6. Brief not truncated. Read framing memo from DB or filesystem.
    a6_pass = False
    a6_detail = "?"
    try:
        con = sqlite3.connect(DB)
        cur = con.execute(
            "SELECT raw_brief FROM mission_briefs WHERE mission_id=?", (mid,)
        )
        row = cur.fetchone()
        if row and row[0]:
            stored = row[0]
            a6_pass = BRIEF.strip() in stored or stored.strip() == BRIEF.strip()
            a6_detail = f"stored_len={len(stored)} brief_len={len(BRIEF)}"
        else:
            a6_detail = "no mission_briefs row"
        con.close()
    except Exception as e:
        a6_detail = f"err:{e}"
    print(f"6. Raw brief preserved: {'PASS' if a6_pass else 'FAIL'} ({a6_detail})")

    all_pass = all([a1_pass, a2_pass, a3_pass, a4_pass, a5_pass, a6_pass])
    print(f"\n========== {'ALL PASS — OK TO PUSH' if all_pass else 'FAILURES — DO NOT PUSH'} ==========\n")

    # Persist evidence.
    Path("/tmp/c12_events.json").write_text(json.dumps(events, indent=2, default=str))
    print(f"[c12] events log: /tmp/c12_events.json")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
