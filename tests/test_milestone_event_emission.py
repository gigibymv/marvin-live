"""Reference-integrity tests for milestone_done emission.

Proves:
1. A direct call to the mission_tools.mark_milestone_delivered tool fires the
   listener exactly once.
2. The runner's deterministic graph code (research_join) ALSO fires the
   listener — twice, once for W1.1 and once for W2.1. This is the central
   guarantee, since the runner calls store.mark_milestone_delivered as Python
   (no ToolMessage), the SSE mapper would never see it. Event ownership at
   the persistence chokepoint closes that gap.
3. Listeners scoped to a different mission_id never fire.
4. Unregistering removes the listener cleanly.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin import events
from marvin.graph import runner
from marvin.mission.schema import Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools, papyrus_tools


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-mile",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-mile", s)
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: s)
    monkeypatch.setattr(papyrus_tools, "_STORE_FACTORY", lambda: s)
    monkeypatch.setattr(papyrus_tools, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "MissionStore", lambda *a, **kw: s)
    yield s
    s.close()


def _state() -> dict:
    return {"mission_id": "m-mile"}


def test_direct_tool_call_triggers_listener(store: MissionStore):
    seen: list[dict] = []
    listener = seen.append
    events.register_milestone_listener("m-mile", listener)
    try:
        mission_tools.mark_milestone_delivered("W1.1", "done", _state())
    finally:
        events.unregister_milestone_listener("m-mile", listener)
    assert len(seen) == 1
    assert seen[0]["milestone_id"] == "W1.1"
    assert seen[0]["status"] == "delivered"
    assert seen[0]["label"]


def test_runner_research_join_triggers_listener_twice(store: MissionStore):
    """runner.research_join calls store.mark_milestone_delivered as Python for
    both W1.1 and W2.1. The listener must fire twice — that is the whole point
    of moving event ownership to the persistence chokepoint."""
    seen: list[dict] = []
    listener = seen.append
    events.register_milestone_listener("m-mile", listener)
    try:
        runner.research_join({"mission_id": "m-mile", "phase": "confirmed"})
    finally:
        events.unregister_milestone_listener("m-mile", listener)
    milestone_ids = sorted(p["milestone_id"] for p in seen)
    assert milestone_ids == ["W1.1", "W2.1"]
    assert all(p["status"] == "delivered" for p in seen)


def test_listener_scoped_to_mission_id(store: MissionStore):
    seen_other: list[dict] = []
    events.register_milestone_listener("m-different", seen_other.append)
    try:
        mission_tools.mark_milestone_delivered("W1.1", "done", _state())
    finally:
        events.unregister_milestone_listener("m-different", seen_other.append)
    assert seen_other == []


def test_repeated_marks_emit_only_once(store: MissionStore):
    """A milestone can be marked delivered by both the LLM tool path AND the
    deterministic research_join safety net. The chokepoint must be idempotent:
    the second call returns the already-delivered row WITHOUT firing a second
    listener event. Otherwise the SSE stream double-signals a single business
    transition (pending → delivered)."""
    seen: list[dict] = []
    listener = seen.append
    events.register_milestone_listener("m-mile", listener)
    try:
        first = mission_tools.mark_milestone_delivered("W1.1", "first", _state())
        second = mission_tools.mark_milestone_delivered("W1.1", "second", _state())
    finally:
        events.unregister_milestone_listener("m-mile", listener)
    assert first["status"] == "delivered"
    assert second["status"] == "delivered"
    assert len(seen) == 1
    assert seen[0]["milestone_id"] == "W1.1"


def test_unregister_stops_listener(store: MissionStore):
    seen: list[dict] = []
    listener = seen.append
    events.register_milestone_listener("m-mile", listener)
    events.unregister_milestone_listener("m-mile", listener)
    mission_tools.mark_milestone_delivered("W1.1", "done", _state())
    assert seen == []
