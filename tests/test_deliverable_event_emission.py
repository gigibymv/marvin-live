"""Reference-integrity tests for deliverable_ready emission.

Proves:
1. A direct call to a papyrus tool triggers the registered listener exactly once.
2. The runner's internal Python call to `_generate_workstream_report_impl`
   ALSO triggers the listener — this is the central guarantee, since
   `marvin.graph.runner.research_join` calls the impl as a function (no
   ToolMessage), the SSE mapper would never see it. Event ownership at the
   persistence chokepoint closes that gap.
3. Listeners scoped to a different mission_id never fire.
4. Unregistering removes the listener cleanly.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin import events
from marvin.mission.schema import Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import papyrus_tools


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-dlv",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-dlv", s)
    monkeypatch.setattr(papyrus_tools, "_STORE_FACTORY", lambda: s)
    monkeypatch.setattr(papyrus_tools, "PROJECT_ROOT", tmp_path)
    yield s
    s.close()


def _state() -> dict:
    return {"mission_id": "m-dlv"}


def test_direct_tool_call_triggers_listener(store: MissionStore):
    seen: list[dict] = []
    listener = seen.append
    events.register_deliverable_listener("m-dlv", listener)
    try:
        papyrus_tools.generate_engagement_brief(state=_state())
    finally:
        events.unregister_deliverable_listener("m-dlv", listener)
    assert len(seen) == 1
    assert seen[0]["deliverable_type"] == "engagement_brief"
    assert seen[0]["deliverable_id"] == "deliverable-m-dlv-engagement-brief"
    assert seen[0]["file_path"]


def test_runner_internal_impl_triggers_listener(store: MissionStore):
    """runner.research_join calls _generate_workstream_report_impl as Python.
    The listener must still fire — that is the whole point of moving event
    ownership to the persistence chokepoint."""
    seen: list[dict] = []
    listener = seen.append
    events.register_deliverable_listener("m-dlv", listener)
    try:
        papyrus_tools._generate_workstream_report_impl("W1", "m-dlv")
        papyrus_tools._generate_workstream_report_impl("W2", "m-dlv")
    finally:
        events.unregister_deliverable_listener("m-dlv", listener)
    assert len(seen) == 2
    assert {p["deliverable_type"] for p in seen} == {"workstream_report"}
    assert {p["deliverable_id"] for p in seen} == {
        "deliverable-m-dlv-w1-report",
        "deliverable-m-dlv-w2-report",
    }


def test_listener_scoped_to_mission_id(store: MissionStore):
    seen_other: list[dict] = []
    events.register_deliverable_listener("m-different", seen_other.append)
    try:
        papyrus_tools.generate_engagement_brief(state=_state())
    finally:
        events.unregister_deliverable_listener("m-different", seen_other.append)
    assert seen_other == []


def test_unregister_stops_listener(store: MissionStore):
    seen: list[dict] = []
    listener = seen.append
    events.register_deliverable_listener("m-dlv", listener)
    events.unregister_deliverable_listener("m-dlv", listener)
    papyrus_tools.generate_engagement_brief(state=_state())
    assert seen == []
