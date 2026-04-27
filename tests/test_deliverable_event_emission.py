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
from marvin.mission.schema import Finding, Hypothesis, MerlinVerdict, Mission, MissionBrief
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


def _add_hypothesis(store: MissionStore) -> None:
    store.save_hypothesis(
        Hypothesis(
            id="hyp-dlv",
            mission_id="m-dlv",
            text="Target has a durable edge in a growing market",
            created_at=datetime.now(UTC).isoformat(),
        )
    )


def _add_framing(store: MissionStore) -> None:
    now = datetime.now(UTC).isoformat()
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-dlv",
            raw_brief="Assess durable growth and market position.",
            ic_question="Q?",
            mission_angle="Market position and competitive durability",
            brief_summary="Assess durable growth and market position.",
            workstream_plan_json='[{"id":"W1","label":"Market","focus":"Market evidence"}]',
            created_at=now,
            updated_at=now,
        )
    )


def _add_finding(store: MissionStore, finding_id: str, workstream_id: str) -> None:
    store.save_finding(
        Finding(
            id=finding_id,
            mission_id="m-dlv",
            workstream_id=workstream_id,
            hypothesis_id="hyp-dlv",
            claim_text=f"{workstream_id} has enough evidence for a useful report",
            confidence="REASONED",
            agent_id="dora" if workstream_id == "W1" else "calculus",
            created_at=datetime.now(UTC).isoformat(),
        )
    )


def test_engagement_brief_without_hypotheses_does_not_trigger_listener(store: MissionStore):
    seen: list[dict] = []
    listener = seen.append
    events.register_deliverable_listener("m-dlv", listener)
    try:
        with pytest.raises(ValueError, match="framed hypotheses"):
            papyrus_tools.generate_engagement_brief(state=_state())
    finally:
        events.unregister_deliverable_listener("m-dlv", listener)
    assert seen == []
    assert store.list_deliverables("m-dlv") == []


def test_direct_tool_call_triggers_listener_after_framing_material(store: MissionStore):
    _add_hypothesis(store)
    _add_framing(store)
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
    _add_hypothesis(store)
    _add_finding(store, "f-w1", "W1")
    _add_finding(store, "f-w2", "W2")
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


def test_workstream_report_without_findings_is_not_ready(store: MissionStore):
    seen: list[dict] = []
    listener = seen.append
    events.register_deliverable_listener("m-dlv", listener)
    try:
        result = papyrus_tools._generate_workstream_report_impl("W1", "m-dlv")
    finally:
        events.unregister_deliverable_listener("m-dlv", listener)

    assert result["status"] == "blocked"
    assert seen == []
    assert store.list_deliverables("m-dlv") == []


def test_placeholder_pdf_is_not_marked_ready(store: MissionStore):
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-dlv",
            mission_id="m-dlv",
            verdict="SHIP",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    seen: list[dict] = []
    listener = seen.append
    events.register_deliverable_listener("m-dlv", listener)
    try:
        result = papyrus_tools._generate_report_pdf_impl("m-dlv")
    finally:
        events.unregister_deliverable_listener("m-dlv", listener)

    assert result["status"] == "blocked"
    assert "placeholder" in result["reason"]
    assert seen == []
    assert store.list_deliverables("m-dlv") == []


def test_artifact_validation_allows_legitimate_na_text(store: MissionStore):
    _add_hypothesis(store)
    _add_finding(store, "f-w1", "W1")
    finding = store.list_findings("m-dlv")[0]
    store.save_finding(
        finding.model_copy(update={"claim_text": "Revenue growth is N/A for private comps"})
    )

    result = papyrus_tools._generate_workstream_report_impl("W1", "m-dlv")

    assert result["deliverable_type"] == "workstream_report"
    assert store.list_deliverables("m-dlv")[0].status == "ready"


def test_failed_artifact_validation_removes_orphan_file(store: MissionStore, tmp_path: Path):
    path = tmp_path / "bad_report.md"
    path.write_text("# Bad\n\n- No findings yet\n", encoding="utf-8")

    with pytest.raises(ValueError, match="placeholder"):
        papyrus_tools._save_deliverable(
            store,
            "m-dlv",
            "deliverable-bad",
            "workstream_report",
            path,
        )

    assert not path.exists()
    assert store.list_deliverables("m-dlv") == []


def test_listener_scoped_to_mission_id(store: MissionStore):
    _add_hypothesis(store)
    _add_framing(store)
    seen_other: list[dict] = []
    events.register_deliverable_listener("m-different", seen_other.append)
    try:
        papyrus_tools.generate_engagement_brief(state=_state())
    finally:
        events.unregister_deliverable_listener("m-different", seen_other.append)
    assert seen_other == []


def test_unregister_stops_listener(store: MissionStore):
    _add_hypothesis(store)
    _add_framing(store)
    seen: list[dict] = []
    listener = seen.append
    events.register_deliverable_listener("m-dlv", listener)
    events.unregister_deliverable_listener("m-dlv", listener)
    papyrus_tools.generate_engagement_brief(state=_state())
    assert seen == []
