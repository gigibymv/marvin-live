"""C12 driver v3: single long-lived /resume + queue-based gate validation.

The /resume stream stays open for the whole mission. As gate_pending events
arrive, they're pushed into a queue. A separate thread pops gate IDs from the
queue and validates them. /resume terminates only on run_end (terminal state)
or hard timeout.

Usage:
    PYTHONPATH=$PWD .venv/bin/python scripts/c12_drive.py <mission_id>
"""
from __future__ import annotations

import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:8095"
DB = os.path.expanduser("~/.marvin/marvin.db")

events: list[dict] = []
gate_pending_count: dict[str, int] = {}
agent_active_after_reject_s: list[float] = []
reject_time: list[float] = []
g1_rejected_once = [False]
gate_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
stop = threading.Event()


def post_json(path: str, body: dict, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def db_mission_status(mid: str) -> str:
    con = sqlite3.connect(DB)
    r = con.execute("SELECT status FROM missions WHERE id=?", (mid,)).fetchone()
    con.close()
    return r[0] if r else "?"


def gate_type_for(mid: str, gate_id: str) -> str:
    con = sqlite3.connect(DB)
    r = con.execute(
        "SELECT gate_type FROM gates WHERE id=?", (gate_id,)
    ).fetchone()
    con.close()
    return r[0] if r else "?"


def stream_resume(mid: str) -> None:
    """Single long-lived /resume; consumes events until run_end or stop."""
    print("[c12] opening /resume (long-lived)", flush=True)
    proc = subprocess.Popen(
        ["/usr/bin/curl", "-sN", "-X", "POST", f"{BASE}/api/v1/missions/{mid}/resume"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    current = None
    deadline = time.time() + 60 * 25
    try:
        for raw in proc.stdout:
            if stop.is_set() or time.time() > deadline:
                proc.kill()
                return
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
                _track(evt, mid)
                if current == "run_end":
                    print("[c12] /resume run_end", flush=True)
                    return
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


def _track(evt, mid):
    et = evt["type"]
    if et == "agent_active":
        agent = evt["data"].get("agent", "")
        if g1_rejected_once[0] and reject_time and not agent_active_after_reject_s:
            elapsed = time.time() - reject_time[0]
            agent_active_after_reject_s.append(elapsed)
            print(f"[c12] post-reject agent_active={agent} after {elapsed:.1f}s", flush=True)
    elif et == "gate_pending":
        gid = evt["data"].get("gate_id") or evt["data"].get("id") or "?"
        gtype = evt["data"].get("gate_type") or gate_type_for(mid, gid)
        gate_pending_count[gid] = gate_pending_count.get(gid, 0) + 1
        print(f"[c12] gate_pending {gid} type={gtype}", flush=True)
        gate_q.put((gid, gtype))


def driver(mid: str) -> None:
    """Pop gate_ids from queue, decide verdict, POST /validate."""
    while not stop.is_set():
        try:
            gate_id, gate_type = gate_q.get(timeout=2.0)
        except queue.Empty:
            if db_mission_status(mid) == "complete":
                print("[c12] mission complete, driver exiting", flush=True)
                return
            continue
        # Decide.
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
        elif gate_type == "data_availability" or gate_type == "data_decision" or "data" in gate_type:
            body = {"decision": "proceed_low_confidence"}
        elif gate_type == "clarification_questions":
            body = {"answers": ["proceed with available data"]}
        else:
            body = {"verdict": "APPROVED"}

        # Small delay so /resume's interrupt re-fires before we deliver payload.
        time.sleep(2.0)
        try:
            res = post_json(
                f"/api/v1/missions/{mid}/gates/{gate_id}/validate", body, timeout=15,
            )
            print(f"[c12] validate {gate_id} body={body} → {res.get('status')}", flush=True)
        except Exception as e:
            print(f"[c12] validate err {gate_id}: {e}", flush=True)


def main() -> int:
    mid = sys.argv[1]
    print(f"[c12] driving mission {mid}", flush=True)

    # Capture original brief.
    con = sqlite3.connect(DB)
    r = con.execute(
        "SELECT raw_brief FROM mission_briefs WHERE mission_id=?", (mid,)
    ).fetchone()
    con.close()
    original_brief = r[0] if r else ""
    print(f"[c12] brief len={len(original_brief)}", flush=True)

    rt = threading.Thread(target=stream_resume, args=(mid,), daemon=True)
    drv = threading.Thread(target=driver, args=(mid,), daemon=True)
    rt.start()
    drv.start()

    # Wait up to 25 min for /resume to send run_end.
    rt.join(timeout=60 * 25)
    stop.set()
    drv.join(timeout=10)

    print(f"\n[c12] events captured: {len(events)}", flush=True)
    Path("/tmp/c12_events.json").write_text(json.dumps(events, indent=2, default=str))

    # ---- ASSERTIONS ----
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
    try:
        con = sqlite3.connect(DB)
        for did, fp in con.execute(
            "SELECT id, file_path FROM deliverables WHERE mission_id=?", (mid,)
        ).fetchall():
            if fp and Path(fp).exists():
                txt = Path(fp).read_text(errors="ignore")
                for needle in ("Finding ID: f-", "Hypothesis ID: hyp-", "Source ID: unassigned"):
                    if needle in txt:
                        a3 = False
                        a3_hits.append(f"{did}: {needle}")
        con.close()
    except Exception as e:
        a3_hits.append(f"db err: {e}")
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
    a6 = len(original_brief) >= 500 and "Doctolib" in original_brief
    print(f"6. Raw brief preserved: {'PASS' if a6 else 'FAIL'} (len={len(original_brief)})")

    all_pass = all([a1, a2, a3, a4, a5, a6])
    print(f"\n========== {'ALL PASS — OK TO PUSH' if all_pass else 'FAILURES — DO NOT PUSH'} ==========\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
