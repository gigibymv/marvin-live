"""Runtime smoke test for MARVIN — proves graph.astream actually runs.

Catches sync-vs-async checkpointer divergences and similar runtime bugs that
unit tests miss. MUST pass before any commit touching:
  - marvin_ui/server.py
  - marvin/graph/runner.py
  - marvin/graph/**
  - any checkpointer code

What it does:
  1. Spawns uvicorn on a free port with a temp checkpoint DB
  2. Creates a mission via POST /api/v1/missions
  3. Sends a short brief via POST /api/v1/missions/{id}/chat
  4. Reads first 8s of the SSE stream
  5. Asserts: zero `error` events
  6. Asserts: at least one progress event beyond run_start

Exit 0 = PASS. Exit 1 = FAIL with clear diagnostic.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SMOKE_DURATION = 25  # seconds of SSE we read after sending brief
HEALTH_TIMEOUT = 30
PROGRESS_EVENT_NAMES = {
    "agent_active", "agent_started", "agent_done",
    "milestone", "milestone_persisted",
    "gate_pending", "gate_opened",
    "phase", "phase_changed",
    "finding_persisted", "deliverable_persisted",
    "chat_token", "node_update", "tool_call",
}

BRIEF = (
    "Smoke test brief: assess Mistral AI investment thesis at €6B post-money. "
    "Geography France/EU, sector foundation models, 6-week CDD scope, no data "
    "room available, accept public + interview evidence."
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


def http(method: str, url: str, body: dict | None = None, timeout: int = 10):
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


def stream_sse(url: str, body: dict, duration: float) -> tuple[list[tuple[str, object]], str | None]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    events: list[tuple[str, object]] = []
    err: str | None = None
    start = time.monotonic()
    try:
        resp = urllib.request.urlopen(req, timeout=duration + 5)
        event = None
        buf: list[str] = []
        while time.monotonic() - start < duration:
            line = resp.readline()
            if not line:
                break
            s = line.decode(errors="replace").rstrip("\r\n")
            if s == "":
                if event or buf:
                    payload = "\n".join(buf)
                    try:
                        parsed = json.loads(payload) if payload else None
                    except Exception:
                        parsed = payload
                    events.append((event or "message", parsed))
                event, buf = None, []
            elif s.startswith("event:"):
                event = s[6:].strip()
            elif s.startswith("data:"):
                buf.append(s[5:].lstrip())
        try:
            resp.close()
        except Exception:
            pass
    except Exception as e:
        err = repr(e)
    return events, err


def main() -> int:
    port = find_free_port()
    base = f"http://127.0.0.1:{port}"
    print(f"[smoke] port={port}")

    tmp_db = Path(tempfile.mkdtemp(prefix="marvin-smoke-")) / "checkpoints.db"
    tmp_marvin_db = Path(tempfile.mkdtemp(prefix="marvin-smoke-mdb-")) / "marvin.db"

    env = load_env()
    env["MARVIN_CHECKPOINT_DB"] = str(tmp_db)
    env["MARVIN_DB_PATH"] = str(tmp_marvin_db)

    log_path = Path(tempfile.mkstemp(prefix="marvin-smoke-uvicorn-", suffix=".log")[1])
    print(f"[smoke] uvicorn log: {log_path}")

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
                print(f"[smoke] FAIL — uvicorn died during startup (exit={proc.returncode})")
                print(f"[smoke] last 20 lines of uvicorn log:")
                print("\n".join(log_path.read_text(errors="replace").splitlines()[-20:]))
                return 1
        if not ready:
            print(f"[smoke] FAIL — uvicorn never reached /health within {HEALTH_TIMEOUT}s")
            return 1

        # Create mission
        s, b = http("POST", f"{base}/api/v1/missions", body={
            "client": "Smoke", "target": "smoke-target",
            "ic_question": "smoke", "mission_type": "cdd",
        })
        if s != 200:
            print(f"[smoke] FAIL — POST /missions returned {s}: {b[:200]}")
            return 1
        mid = json.loads(b)["mission_id"]
        print(f"[smoke] mission_id={mid}")

        # Stream chat
        events, err = stream_sse(
            f"{base}/api/v1/missions/{mid}/chat",
            body={"text": BRIEF},
            duration=SMOKE_DURATION,
        )
        print(f"[smoke] received {len(events)} SSE events in {SMOKE_DURATION}s")
        for name, payload in events[:20]:
            preview = json.dumps(payload)[:120] if not isinstance(payload, str) else payload[:120]
            print(f"  - {name}: {preview}")
        if err:
            print(f"[smoke] stream error: {err}")

        # Assertions
        error_events = [(n, p) for n, p in events if n == "error"]
        progress_events = [(n, p) for n, p in events if n in PROGRESS_EVENT_NAMES]

        passed = True
        if error_events:
            passed = False
            print(f"[smoke] FAIL — saw {len(error_events)} `error` event(s):")
            for n, p in error_events[:3]:
                print(f"  ERROR payload: {json.dumps(p)[:400]}")
        if not progress_events:
            passed = False
            print(f"[smoke] FAIL — no progress event observed (run_start alone is not enough)")
            print(f"        Expected one of: {sorted(PROGRESS_EVENT_NAMES)}")

        if passed:
            print(f"[smoke] PASS — {len(progress_events)} progress event(s), 0 errors")
            return 0
        else:
            print(f"[smoke] last 30 lines of uvicorn log:")
            print("\n".join(log_path.read_text(errors="replace").splitlines()[-30:]))
            return 1
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
