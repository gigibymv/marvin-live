"""Regression: G1 gate must not loop forever when Papyrus failed to write
the workstream reports during research_join.

Setup mirrors the Render incident on m-netflix-20260504-x-5922d6e1: research
findings exist, milestones marked delivered, but no workstream_report
deliverable was persisted (Papyrus LLM call silently failed). gate_node must
route to papyrus_recover_workstreams once, then surface phase_blocked with
phase=blocked_terminal on the second failure rather than loop.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from marvin.graph import gates as gate_module
from marvin.mission.schema import Finding, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-recover",
            client="Client",
            target="Target",
            ic_question="Should IC invest?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-recover", s)
    monkeypatch.setattr(gate_module, "MissionStore", lambda *a, **kw: s)
    monkeypatch.setattr(gate_module, "check_internal_consistency", lambda mid: {})
    yield s
    s.close()


def _seed_research_state_without_reports(store: MissionStore) -> None:
    """Findings + delivered milestones, but no workstream_report deliverables.
    This is exactly the state research_join leaves behind when Papyrus fails."""
    now = datetime.now(UTC).isoformat()
    for i, ws in enumerate(("W1", "W2"), start=1):
        store.save_finding(
            Finding(
                id=f"f-{i}",
                mission_id="m-recover",
                workstream_id=ws,
                claim_text=f"{ws} claim",
                confidence="REASONED",
                agent_id="dora" if ws == "W1" else "calculus",
                created_at=now,
            )
        )
    for milestone_id, label in (
        ("W1.1", "Market research"),
        ("W2.1", "Unit economics"),
    ):
        store.mark_milestone_delivered(milestone_id, label, "m-recover")


def test_g1_first_failure_routes_to_papyrus_recovery(store: MissionStore):
    _seed_research_state_without_reports(store)

    result = asyncio.run(
        gate_module.gate_node(
            {
                "mission_id": "m-recover",
                "pending_gate_id": "gate-m-recover-G1",
                "papyrus_recovery_attempts": 0,
            }
        )
    )

    assert result["phase"] == "papyrus_recover_workstreams"
    assert result["pending_gate_id"] == "gate-m-recover-G1"
    assert result["papyrus_recovery_attempts"] == 1


def test_g1_second_failure_terminates_with_phase_blocked(store: MissionStore):
    _seed_research_state_without_reports(store)

    result = asyncio.run(
        gate_module.gate_node(
            {
                "mission_id": "m-recover",
                "pending_gate_id": "gate-m-recover-G1",
                "papyrus_recovery_attempts": 1,
            }
        )
    )

    assert result["phase"] == "blocked_terminal"
    assert result["pending_gate_id"] is None
    blocked = result["phase_blocked"]
    assert blocked["terminal"] is True
    assert "deliverable_writing_in_progress" in blocked["missing_material"]
