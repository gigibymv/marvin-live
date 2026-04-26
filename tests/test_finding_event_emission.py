"""Reference-integrity tests for finding_added emission.

Proves:
1. A direct call to `add_finding_to_mission` triggers the registered listener
   exactly once.
2. A wrapper tool that internally calls `add_finding_to_mission` (e.g.
   `moat_analysis`) ALSO triggers the listener — no LLM tool-selection
   sensitivity. This is the central guarantee of this slice.
3. Listeners scoped to a different mission_id never fire.
4. Unregistering removes the listener cleanly.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin import events
from marvin.mission.schema import Hypothesis, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import dora_tools, mission_tools


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-evt",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-evt", s)
    s.save_hypothesis(
        Hypothesis(
            id="hyp-evt-1",
            mission_id="m-evt",
            text="x",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: s)
    yield s
    s.close()


def _state() -> dict:
    return {"mission_id": "m-evt"}


def test_direct_call_triggers_listener(store: MissionStore):
    seen: list[dict] = []
    listener = seen.append
    events.register_finding_listener("m-evt", listener)
    try:
        mission_tools.add_finding_to_mission(
            claim_text="Direct claim",
            confidence="REASONED",
            agent_id="dora",
            workstream_id="W1",
            hypothesis_id="hyp-evt-1",
            state=_state(),
        )
    finally:
        events.unregister_finding_listener("m-evt", listener)
    assert len(seen) == 1
    assert seen[0]["claim_text"] == "Direct claim"
    assert seen[0]["confidence"] == "REASONED"
    assert seen[0]["hypothesis_id"] == "hyp-evt-1"
    assert seen[0]["finding_id"]


def test_wrapper_tool_triggers_listener(store: MissionStore):
    """moat_analysis calls add_finding_to_mission internally as Python.
    The listener must still fire — that is the whole point of moving event
    ownership to the persistence chokepoint."""
    seen: list[dict] = []
    listener = seen.append
    events.register_finding_listener("m-evt", listener)
    try:
        dora_tools.moat_analysis(
            company_name="Acme",
            hypothesis_id="hyp-evt-1",
            state=_state(),
        )
    finally:
        events.unregister_finding_listener("m-evt", listener)
    assert len(seen) == 1, "wrapper tool must produce exactly one finding event"
    assert "moat" in seen[0]["claim_text"].lower()
    assert seen[0]["hypothesis_id"] == "hyp-evt-1"


def test_listener_scoped_to_mission_id(store: MissionStore):
    seen_other: list[dict] = []
    events.register_finding_listener("m-different", seen_other.append)
    try:
        mission_tools.add_finding_to_mission(
            claim_text="Should not reach m-different listener",
            confidence="REASONED",
            workstream_id="W1",
            state=_state(),
        )
    finally:
        events.unregister_finding_listener("m-different", seen_other.append)
    assert seen_other == []


def test_unregister_stops_listener(store: MissionStore):
    seen: list[dict] = []
    listener = seen.append
    events.register_finding_listener("m-evt", listener)
    events.unregister_finding_listener("m-evt", listener)
    mission_tools.add_finding_to_mission(
        claim_text="After unregister",
        confidence="REASONED",
        workstream_id="W1",
        state=_state(),
    )
    assert seen == []
