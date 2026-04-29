"""C12 fresh-mission verifier: pure SSE event-driven, no DB polling for gates.

Architecture:
    1. POST /api/v1/missions → mission_id
    2. POST /api/v1/missions/{id}/chat with brief → SSE stream
    3. Read SSE events line-by-line. When gate_pending arrives:
         a. record gate_id, gate_type
         b. POST /api/v1/missions/{id}/gates/{gate_id}/validate from a side
            thread (validate must run while the SSE consumer is still alive
            so _deliver_resume can hand the payload off)
    4. When current SSE stream emits run_end (graph parked again), open a
       new /resume to drain next batch.
    5. Stop when mission status=complete or hard timeout.

Gates: G0 → APPROVE, data_availability → proceed_low_confidence,
       G1 (first fire) → REJECT, G1 (retry) → APPROVE,
       G3 → APPROVE, clarifications → answer.
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
agent_active_after_reject_s: list[float] = []
reject_time: list[float] = []
g1_rejected_once = [False]
mission_id_holder = [""]


def post_json(path: str, body: dict, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def db_mission_status(mid: str) -> str:
    con = sqlite3.connect(DB)
    r = con.execute("SELECT status FROM missions WHERE id=?", (mid,)).fetchone()
    con.close()
    return r[0] if r else "?"


def gate_type_for(gate_id: str) -> str:
    con = sqlite3.connect(DB)
    r = con.execute("SELECT gate_type FROM gates WHERE id=?", (gate_id,)).fetchone()
    con.close()
    return r[0] if r else "?"


def validate_gate(mid: str, gate_id: str, gate_type: str) -> None:
    body: dict
    if gate_type == "hypothesis_confirmation":
        body = {"verdict": "APPROVED", "notes": "c12 G0"}
    elif gate_type == "manager_review":
        if not g1_rejected_once[0]:
            body = {"verdict": "REJECTED", "notes": "c12 G1 reject"}
            g1_rejected_once[0] = True
            reject_time.append(time.time())
        else:
            body = {"verdict": "APPROVED", "notes": "c12 G1 retry"}
    elif gate_type == "final_review":
        body = {"verdict": "APPROVED", "notes": "c12 G3"}
    elif gate_type == "data_availability" or "data" in gate_type:
        body = {"decision": "proceed_low_confidence"}
    elif gate_type == "clarification_questions":
        body = {"answers": ["proceed with available data"]}
    else:
        body = {"verdict": "APPROVED"}

    # tiny wait so the parked stream is genuinely waiting on resume payload
    time.sleep(1.5)
    try:
        res = post_json(
            f"/api/v1/missions/{mid}/gates/{gate_id}/validate", body, timeout=15,
        )
        print(f"[c12] validate {gate_id} body={body} → {res.get('status')}", flush=True)
    except Exception as e:
        print(f"[c12] validate err {gate_id}: {e}", flush=True)


def consume(proc, mid: str) -> str:
    """Drain one SSE stream, return reason: 'run_end' | 'mission_complete' | 'timeout'."""
    current = None
    deadline = time.time() + 60 * 18
    for raw in proc.stdout:
        if time.time() > deadline:
            print("[c12] stream timeout", flush=True)
            proc.kill()
            return "timeout"
        line = raw.rstrip("\n")
        if line.startswith("event: "):
            current = line[7:].strip()
        elif line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except Exception:
                payload = {"raw": line[6:]}
            evt = {"type": current, "data": payload, "ts": time.time()}
            events.append(evt)
            et = evt["type"]
            if et == "agent_active":
                agent = evt["data"].get("agent", "")
                if g1_rejected_once[0] and reject_time and not agent_active_after_reject_s:
                    elapsed = time.time() - reject_time[0]
                    agent_active_after_reject_s.append(elapsed)
                    print(f"[c12] post-reject agent_active={agent} after {elapsed:.1f}s", flush=True)
            elif et == "gate_pending":
                gid = evt["data"].get("gate_id") or evt["data"].get("id") or "?"
                gtype = evt["data"].get("gate_type") or gate_type_for(gid)
                gate_pending_count[gid] = gate_pending_count.get(gid, 0) + 1
                print(f"[c12] gate_pending {gid} type={gtype}", flush=True)
                threading.Thread(
                    target=validate_gate, args=(mid, gid, gtype), daemon=True
                ).start()
            elif et == "run_end":
                proc.terminate()
                if db_mission_status(mid) == "complete":
                    return "mission_complete"
                return "run_end"
    proc.wait(timeout=5)
    return "run_end"


def open_chat(mid: str, text: str):
    return subprocess.Popen(
        [
            "/usr/bin/curl", "-sN", "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"text": text}),
            f"{BASE}/api/v1/missions/{mid}/chat",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def open_resume(mid: str):
    return subprocess.Popen(
        ["/usr/bin/curl", "-sN", "-X", "POST", f"{BASE}/api/v1/missions/{mid}/resume"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def main() -> int:
    print("[c12] creating fresh mission", flush=True)
    res = post_json(
        "/api/v1/missions",
        {
            "client": "C12 Fresh",
            "target": "Doctolib",
            "ic_question": "Should we invest in Doctolib at the proposed valuation?",
            "mission_type": "cdd",
        },
    )
    mid = res["mission_id"]
    mission_id_holder[0] = mid
    print(f"[c12] mission_id={mid}", flush=True)

    # 1. Initial /chat — flows until first park (G0).
    proc = open_chat(mid, BRIEF)
    reason = consume(proc, mid)
    print(f"[c12] first stream ended: {reason}", flush=True)

    # 2. Loop: as long as mission is active, /resume to pump next stage.
    overall_deadline = time.time() + 60 * 22
    while reason != "mission_complete" and time.time() < overall_deadline:
        if db_mission_status(mid) == "complete":
            reason = "mission_complete"
            break
        time.sleep(1.0)
        rp = open_resume(mid)
        reason = consume(rp, mid)
        print(f"[c12] resume stream ended: {reason} status={db_mission_status(mid)}", flush=True)
        # Backstop: if /resume returns immediately with run_end + status still
        # active, the checkpoint is terminal and we're stuck — bail out.
        if reason == "run_end" and not gate_pending_count:
            time.sleep(2.0)

    # ---- ASSERTIONS ----
    print(f"\n[c12] events captured: {len(events)}", flush=True)
    Path("/tmp/c12_events.json").write_text(json.dumps(events, indent=2, default=str))
    print("\n========== C12 ASSERTIONS ==========\n", flush=True)

    # 1. Mission complete msg in SSE.
    chat_complete = [
        e for e in events
        if (e["type"] in ("text", "agent_message", "narration"))
        and "Mission complete" in json.dumps(e["data"])
    ]
    a1 = bool(chat_complete)
    print(f"1. Mission complete msg in SSE: {'PASS' if a1 else 'FAIL'} ({len(chat_complete)} matches)")

    # 2. DB status complete.
    a2_status = db_mission_status(mid)
    a2 = a2_status == "complete"
    print(f"2. Mission status=complete: {'PASS' if a2 else 'FAIL'} (got {a2_status!r})")

    # 3. No internal IDs in deliverables.
    a3 = True
    a3_hits: list[str] = []
    out_dir = Path(f"/Users/mv/Desktop/AI/PROJECTS/marvin/output/{mid}")
    if out_dir.exists():
        grep = subprocess.run(
            ["grep", "-rEn",
             r"Finding ID: f-|Hypothesis ID: hyp-|Source ID: unassigned",
             str(out_dir)],
            capture_output=True, text=True,
        )
        if grep.stdout.strip():
            a3 = False
            a3_hits = grep.stdout.strip().splitlines()[:5]
    print(f"3. No internal IDs in deliverables: {'PASS' if a3 else 'FAIL'}")
    for h in a3_hits[:5]:
        print(f"     hit: {h}")

    # 4. Each gate_pending fires once per gate_id.
    a4 = bool(gate_pending_count) and all(c == 1 for c in gate_pending_count.values())
    print(f"4. Gate pending fires once per gate_id: {'PASS' if a4 else 'FAIL'}")
    for gid, c in gate_pending_count.items():
        print(f"     {gid}: {c}")

    # 5. G1 reject re-runs Dora ≤15s.
    a5 = (
        bool(g1_rejected_once[0])
        and bool(agent_active_after_reject_s)
        and agent_active_after_reject_s[0] <= 15.0
    )
    a5_detail = (
        f"rejected={g1_rejected_once[0]} "
        f"first_active_after_reject={agent_active_after_reject_s[:1]}"
    )
    print(f"5. G1 reject re-runs Dora ≤15s: {'PASS' if a5 else 'FAIL'} ({a5_detail})")

    # 6. Brief preserved.
    con = sqlite3.connect(DB)
    r = con.execute(
        "SELECT raw_brief FROM mission_briefs WHERE mission_id=?", (mid,)
    ).fetchone()
    con.close()
    stored = r[0] if r else ""
    a6 = (BRIEF.strip() in (stored or "")) or (stored.strip() == BRIEF.strip())
    print(f"6. Raw brief preserved: {'PASS' if a6 else 'FAIL'} (stored_len={len(stored)} brief_len={len(BRIEF)})")

    all_pass = all([a1, a2, a3, a4, a5, a6])
    print(f"\n========== {'ALL PASS — OK TO PUSH' if all_pass else 'FAILURES — DO NOT PUSH'} ==========\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
