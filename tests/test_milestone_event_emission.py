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
from marvin.mission.schema import Finding, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools, papyrus_tools


def _seed_finding(store: MissionStore, fid: str, workstream_id: str) -> str:
    """Helper: persist a minimal finding so mark_milestone_delivered can
    anchor against it. Phase 3 (Fix D) requires finding_id to deliver."""
    store.save_finding(
        Finding(
            id=fid,
            mission_id="m-mile",
            workstream_id=workstream_id,
            hypothesis_id=None,
            claim_text=f"seeded finding for {workstream_id}",
            confidence="REASONED",
            agent_id="dora",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    return fid


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
    fid = _seed_finding(store, "f-1", "W1")
    seen: list[dict] = []
    listener = seen.append
    events.register_milestone_listener("m-mile", listener)
    try:
        mission_tools.mark_milestone_delivered("W1.1", "done", fid, _state())
    finally:
        events.unregister_milestone_listener("m-mile", listener)
    assert len(seen) == 1
    assert seen[0]["milestone_id"] == "W1.1"
    assert seen[0]["status"] == "delivered"
    assert seen[0]["label"]


def test_runner_research_join_triggers_listener_twice(store: MissionStore):
    """Phase 3 (Fix D): research_join now gates milestone delivery on findings
    count. With ≥1 finding per workstream, both milestones flip to delivered
    and the listener fires twice."""
    _seed_finding(store, "f-w1", "W1")
    _seed_finding(store, "f-w2", "W2")
    seen: list[dict] = []
    listener = seen.append
    events.register_milestone_listener("m-mile", listener)
    try:
        runner.research_join({"mission_id": "m-mile", "phase": "confirmed"})
    finally:
        events.unregister_milestone_listener("m-mile", listener)
    by_id = {p["milestone_id"]: p["status"] for p in seen}
    assert by_id["W1.1"] == "delivered"
    assert by_id["W2.1"] == "delivered"
    # Sibling milestones (W1.2/W1.3/W2.2/W2.3) resolve to a terminal status
    # (blocked when no finding was tagged to them) so the UI tab can flip ✓.
    for sibling in ("W1.2", "W1.3", "W2.2", "W2.3"):
        assert by_id.get(sibling) in ("delivered", "blocked")


def test_research_join_blocks_when_no_findings(store: MissionStore):
    """Phase 3 (Fix D): with zero findings for W2, research_join must mark
    W2.1 as blocked (not delivered) — the original silent-delivered bug."""
    _seed_finding(store, "f-w1-only", "W1")
    seen: list[dict] = []
    events.register_milestone_listener("m-mile", seen.append)
    try:
        runner.research_join({"mission_id": "m-mile", "phase": "confirmed"})
    finally:
        events.unregister_milestone_listener("m-mile", seen.append)
    by_id = {p["milestone_id"]: p["status"] for p in seen}
    assert by_id["W1.1"] == "delivered"
    assert by_id["W2.1"] == "blocked"


def test_listener_scoped_to_mission_id(store: MissionStore):
    fid = _seed_finding(store, "f-2", "W1")
    seen_other: list[dict] = []
    events.register_milestone_listener("m-different", seen_other.append)
    try:
        mission_tools.mark_milestone_delivered("W1.1", "done", fid, _state())
    finally:
        events.unregister_milestone_listener("m-different", seen_other.append)
    assert seen_other == []


def test_repeated_marks_emit_only_once(store: MissionStore):
    """A milestone can be marked delivered by both the LLM tool path AND the
    deterministic research_join safety net. The chokepoint must be idempotent:
    the second call returns the already-delivered row WITHOUT firing a second
    listener event. Otherwise the SSE stream double-signals a single business
    transition (pending → delivered)."""
    fid = _seed_finding(store, "f-3", "W1")
    seen: list[dict] = []
    listener = seen.append
    events.register_milestone_listener("m-mile", listener)
    try:
        first = mission_tools.mark_milestone_delivered("W1.1", "first", fid, _state())
        second = mission_tools.mark_milestone_delivered("W1.1", "second", fid, _state())
    finally:
        events.unregister_milestone_listener("m-mile", listener)
    assert first["status"] == "delivered"
    assert second["status"] == "delivered"
    assert len(seen) == 1
    assert seen[0]["milestone_id"] == "W1.1"


def test_unregister_stops_listener(store: MissionStore):
    fid = _seed_finding(store, "f-4", "W1")
    seen: list[dict] = []
    listener = seen.append
    events.register_milestone_listener("m-mile", listener)
    events.unregister_milestone_listener("m-mile", listener)
    mission_tools.mark_milestone_delivered("W1.1", "done", fid, _state())
    assert seen == []


def test_tool_rejects_missing_finding_id(store: MissionStore):
    """Phase 3 (Fix D): mark_milestone_delivered without a finding_id must
    surface a structured error and NOT write the row."""
    result = mission_tools.mark_milestone_delivered("W1.1", "done", None, _state())
    assert result["status"] == "error"
    assert "finding_id" in result["reason"]
    # Row stayed pending
    m = next(m for m in store.list_milestones("m-mile") if m.id == "W1.1")
    assert m.status == "pending"


def test_tool_rejects_workstream_mismatch(store: MissionStore):
    """A finding from W2 cannot deliver a W1 milestone."""
    fid = _seed_finding(store, "f-w2-mismatch", "W2")
    result = mission_tools.mark_milestone_delivered("W1.1", "done", fid, _state())
    assert result["status"] == "error"
    assert "workstream" in result["reason"]
    m = next(m for m in store.list_milestones("m-mile") if m.id == "W1.1")
    assert m.status == "pending"
