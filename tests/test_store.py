from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from marvin.mission.schema import Deliverable, Finding, Gate, Hypothesis, MerlinVerdict, Mission, MissionBrief, Source
from marvin.mission.store import MissionStore, _seed_standard_workplan


def _mission() -> Mission:
    return Mission(
        id="m-test",
        client="Test Client",
        target="TargetCo",
        status="active",
        created_at=datetime.now(UTC).isoformat(),
    )


def test_schema_mission_defaults():
    mission = Mission(id="m-1", client="Client", target="Target")
    assert mission.mission_type == "cdd"
    assert mission.status == "active"


def test_schema_finding_requires_source_for_known():
    with pytest.raises(ValueError, match="source_id required for KNOWN findings"):
        Finding(
            id="f-1",
            mission_id="m-1",
            claim_text="Known fact",
            confidence="KNOWN",
        )


def test_schema_deliverable_requires_absolute_path():
    with pytest.raises(ValueError, match="file_path must be absolute"):
        Deliverable(
            id="d-1",
            mission_id="m-1",
            deliverable_type="brief",
            file_path="relative/path.md",
        )


def test_store_initializes_temp_db_file(tmp_path: Path):
    db_path = tmp_path / "marvin.db"
    store = MissionStore(db_path)
    assert db_path.exists()
    tables = {
        row["name"]
        for row in store._execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert "missions" in tables
    assert "mission_briefs" in tables
    assert "merlin_verdicts" in tables
    store.close()


def test_store_initializes_in_memory():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    assert store.get_mission("m-test").target == "TargetCo"
    store.close()


def test_save_and_get_mission():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    mission = store.get_mission("m-test")
    assert mission.client == "Test Client"
    store.close()


def test_list_missions_returns_multiple_rows():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_mission(
        Mission(
            id="m-second",
            client="Client 2",
            target="Target 2",
            created_at=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        )
    )
    assert [mission.id for mission in store.list_missions()] == ["m-test", "m-second"]
    store.close()


def test_save_and_get_mission_brief_updates_ic_question():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    now = datetime.now(UTC).isoformat()
    brief = MissionBrief(
        mission_id="m-test",
        raw_brief="We need to assess whether TargetCo can defend growth.",
        ic_question="Can TargetCo defend growth?",
        mission_angle="Growth durability",
        brief_summary="Assess growth durability and risks.",
        workstream_plan_json='[{"id":"W1","focus":"Market"}]',
        created_at=now,
        updated_at=now,
    )

    saved = store.save_mission_brief(brief)

    assert saved.ic_question == "Can TargetCo defend growth?"
    assert store.get_mission_brief("m-test") == brief
    assert store.get_mission("m-test").ic_question == "Can TargetCo defend growth?"
    store.close()


def test_save_mission_brief_rolls_back_when_mission_missing():
    store = MissionStore(":memory:")
    now = datetime.now(UTC).isoformat()
    brief = MissionBrief(
        mission_id="missing",
        raw_brief="Brief",
        ic_question="Question?",
        mission_angle="Angle",
        brief_summary="Summary",
        workstream_plan_json="[]",
        created_at=now,
        updated_at=now,
    )

    with pytest.raises(KeyError, match="mission not found"):
        store.save_mission_brief(brief)

    assert store.get_mission_brief("missing") is None
    store.close()


def test_get_mission_raises_for_missing_row():
    store = MissionStore(":memory:")
    with pytest.raises(KeyError, match="mission not found"):
        store.get_mission("missing")
    store.close()


def test_save_and_filter_hypotheses():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_hypothesis(Hypothesis(id="h-1", mission_id="m-test", text="Grow faster"))
    store.save_hypothesis(Hypothesis(id="h-2", mission_id="m-test", text="Expand margins", status="validated"))
    assert [hypothesis.id for hypothesis in store.list_hypotheses("m-test")] == ["h-1", "h-2"]
    assert [hypothesis.id for hypothesis in store.list_hypotheses("m-test", status="validated")] == ["h-2"]
    store.close()


def test_update_hypothesis_status_and_reason():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_hypothesis(Hypothesis(id="h-1", mission_id="m-test", text="Hypothesis"))
    hypothesis = store.update_hypothesis("h-1", "abandoned", "No evidence")
    assert hypothesis.status == "abandoned"
    assert hypothesis.abandon_reason == "No evidence"
    store.close()


def test_update_hypothesis_raises_when_missing():
    store = MissionStore(":memory:")
    with pytest.raises(KeyError, match="hypothesis not found"):
        store.update_hypothesis("missing", "validated")
    store.close()


def test_save_and_list_workstreams():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    _seed_standard_workplan("m-test", store)
    workstreams = store.list_workstreams("m-test")
    assert len(workstreams) == 4
    assert workstreams[0].id == "W1"
    store.close()


def test_mark_workstream_delivered():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    _seed_standard_workplan("m-test", store)
    workstream = store.mark_workstream_delivered("m-test", "W2")
    assert workstream.status == "delivered"
    store.close()


def test_save_list_and_mark_milestone_delivered():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    _seed_standard_workplan("m-test", store)
    milestones = store.list_milestones("m-test")
    assert any(milestone.id == "W1.1" for milestone in milestones)
    delivered = store.mark_milestone_delivered("W1.1", "Completed market sizing", mission_id="m-test")
    assert delivered.status == "delivered"
    assert delivered.result_summary == "Completed market sizing"
    store.close()


def test_save_and_list_finding():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    finding = Finding(
        id="f-1",
        mission_id="m-test",
        claim_text="TAM exceeds $1B",
        confidence="REASONED",
        agent_id="dora",
        created_at=datetime.now(UTC).isoformat(),
    )
    store.save_finding(finding)
    findings = store.list_findings("m-test")
    assert len(findings) == 1
    assert findings[0].claim_text == "TAM exceeds $1B"
    store.close()


def test_save_finding_rejects_known_without_source():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    with pytest.raises(ValueError, match="source_id required for KNOWN findings"):
        store.save_finding(
            Finding(
                id="f-1",
                mission_id="m-test",
                claim_text="Known claim",
                confidence="KNOWN",
                source_id=None,
            )
        )
    store.close()


def test_save_finding_allows_reasoned_without_source():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_finding(
        Finding(
            id="f-1",
            mission_id="m-test",
            claim_text="Reasoned claim",
            confidence="REASONED",
        )
    )
    assert len(store.list_findings("m-test")) == 1
    store.close()


def test_save_finding_allows_low_confidence_without_source():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_finding(
        Finding(
            id="f-1",
            mission_id="m-test",
            claim_text="Tentative claim",
            confidence="LOW_CONFIDENCE",
        )
    )
    assert store.list_findings("m-test")[0].confidence == "LOW_CONFIDENCE"
    store.close()


def test_save_and_list_sources():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_source(
        Source(
            id="s-1",
            mission_id="m-test",
            url_or_ref="https://example.com",
            quote="Quoted source",
            retrieved_at=datetime.now(UTC).isoformat(),
        )
    )
    sources = store.list_sources("m-test")
    assert len(sources) == 1
    assert sources[0].url_or_ref == "https://example.com"
    store.close()


def test_save_list_and_update_gate_status():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    gate = Gate(
        id="gate-1",
        mission_id="m-test",
        gate_type="hypothesis_confirmation",
        scheduled_day=0,
    )
    store.save_gate(gate)
    gates = store.list_gates("m-test")
    assert len(gates) == 1
    updated = store.update_gate_status("gate-1", "completed", notes="Approved")
    assert updated.status == "completed"
    assert updated.completion_notes == "Approved"
    store.close()


def test_save_and_list_deliverables():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    deliverable = Deliverable(
        id="d-1",
        mission_id="m-test",
        deliverable_type="engagement_brief",
        file_path="/tmp/engagement_brief.md",
        file_size_bytes=128,
        created_at=datetime.now(UTC).isoformat(),
    )
    store.save_deliverable(deliverable)
    deliverables = store.list_deliverables("m-test")
    assert len(deliverables) == 1
    assert deliverables[0].file_path == "/tmp/engagement_brief.md"
    store.close()


def test_save_and_get_latest_merlin_verdict():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-1",
            mission_id="m-test",
            verdict="MINOR_FIXES",
            created_at="2026-01-01T00:00:00",
        )
    )
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-2",
            mission_id="m-test",
            verdict="SHIP",
            created_at="2026-01-02T00:00:00",
        )
    )
    latest = store.get_latest_merlin_verdict("m-test")
    assert latest is not None
    assert latest.verdict == "SHIP"
    store.close()


def test_seed_standard_workplan():
    store = MissionStore(":memory:")
    store.save_mission(
        Mission(
            id="m-test",
            client="Test",
            target="Target",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-test", store)

    workstreams = store.list_workstreams("m-test")
    assert len(workstreams) == 4
    assert any(workstream.id == "W1" for workstream in workstreams)

    gates = store.list_gates("m-test")
    assert len(gates) == 3
    assert any(gate.gate_type == "hypothesis_confirmation" for gate in gates)
    assert any(gate.scheduled_day == 3 for gate in gates)
    assert any(gate.scheduled_day == 10 for gate in gates)
    store.close()


def test_seed_standard_workplan_is_idempotent():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    _seed_standard_workplan("m-test", store)
    _seed_standard_workplan("m-test", store)
    assert len(store.list_workstreams("m-test")) == 4
    assert len(store.list_milestones("m-test")) == 10
    assert len(store.list_gates("m-test")) == 3
    store.close()
