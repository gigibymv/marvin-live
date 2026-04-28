"""Chantier 2.7 FIX 2: /api/v1/missions/{id}/resume stream tests.

Drives _stream_resume directly (avoids TestClient SQLite threading issue,
mirroring tests/test_deliverable_preview.py).
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from marvin.mission.schema import Mission
from marvin.mission.store import MissionStore
from marvin_ui import server as srv


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _drain(gen) -> list[str]:
    out = []
    async for chunk in gen:
        out.append(chunk)
    return out


def _parse_events(chunks: list[str]) -> list[tuple[str, dict]]:
    events = []
    for raw in chunks:
        if not raw.strip() or raw.startswith(":"):
            continue
        evt_type = "message"
        data = ""
        for line in raw.splitlines():
            if line.startswith("event:"):
                evt_type = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        payload: dict = {}
        if data:
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                payload = {"text": data}
        events.append((evt_type, payload))
    return events


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch):
    s = MissionStore(":memory:")
    monkeypatch.setattr(srv, "get_store", lambda: s)
    yield s
    s.close()


def test_resume_unknown_mission_emits_error(store: MissionStore) -> None:
    chunks = asyncio.run(_drain(srv._stream_resume("m-bogus")))
    events = _parse_events(chunks)
    assert any(t == "error" for t, _ in events), f"expected error, got {events}"


def test_resume_terminal_mission_emits_run_end(store: MissionStore) -> None:
    """A non-active mission needs no live stream — emit run_end and exit."""
    store.save_mission(Mission(
        id="m-done", client="C", target="T", created_at=_now(), status="completed",
    ))
    chunks = asyncio.run(_drain(srv._stream_resume("m-done")))
    events = _parse_events(chunks)
    assert any(t == "run_end" for t, _ in events), f"expected run_end, got {events}"


def test_resume_active_no_checkpoint_emits_run_end(monkeypatch, store: MissionStore) -> None:
    """Active mission with no checkpoint (e.g. pre-brief) closes cleanly."""
    monkeypatch.setenv("MARVIN_CHECKPOINT_BACKEND", "memory")
    # Force a fresh graph so the test's MemorySaver is fresh.
    monkeypatch.setattr(srv, "_graph", None)
    store.save_mission(Mission(
        id="m-fresh", client="C", target="T", created_at=_now(), status="active",
    ))
    chunks = asyncio.run(_drain(srv._stream_resume("m-fresh")))
    events = _parse_events(chunks)
    types = [t for t, _ in events]
    assert "run_end" in types, f"expected run_end, got {types}"
    assert "error" not in types, f"unexpected error in {events}"


def test_resume_endpoint_registered() -> None:
    paths = [getattr(r, "path", "") for r in srv.app.routes]
    assert "/api/v1/missions/{mission_id}/resume" in paths
