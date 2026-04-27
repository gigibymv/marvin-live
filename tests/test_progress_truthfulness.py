from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin.mission.schema import Deliverable, Finding, Hypothesis, MerlinVerdict, Mission, MissionBrief
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin_ui import server as srv
from fastapi import HTTPException


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    srv._gate_decisions_in_flight.clear()
    srv._gate_decision_by_mission.clear()
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-progress",
            client="Client",
            target="Target",
            ic_question="Should IC invest?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-progress", s)
    monkeypatch.setattr(srv, "get_store", lambda: s)
    yield s
    srv._gate_decisions_in_flight.clear()
    srv._gate_decision_by_mission.clear()
    s.close()


def test_empty_mission_has_scheduled_gates_but_none_open(store: MissionStore):
    payload = asyncio.run(srv.get_mission_progress("m-progress"))

    assert payload["deliverables"] == []
    assert payload["gates"]
    assert {gate["lifecycle_status"] for gate in payload["gates"]} == {"scheduled"}
    assert all(gate["is_open"] is False for gate in payload["gates"])


def test_hypothesis_gate_opens_only_after_hypotheses_exist(store: MissionStore):
    store.save_hypothesis(
        Hypothesis(
            id="hyp-progress",
            mission_id="m-progress",
            text="Target can sustain a differentiated market position",
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["hypothesis_confirmation"]["lifecycle_status"] == "scheduled"

    now = datetime.now(UTC).isoformat()
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-progress",
            raw_brief="Assess whether Target can sustain differentiated growth.",
            ic_question="Should IC invest?",
            mission_angle="Market position and competitive durability",
            brief_summary="Assess differentiated growth.",
            workstream_plan_json='[{"id":"W1","label":"Market","focus":"Market"}]',
            created_at=now,
            updated_at=now,
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["hypothesis_confirmation"]["lifecycle_status"] == "open"
    assert gates["hypothesis_confirmation"]["is_open"] is True
    assert gates["hypothesis_confirmation"]["review_payload"]["framing"]["brief_summary"] == "Assess differentiated growth."
    assert gates["hypothesis_confirmation"]["review_payload"]["hypotheses"][0]["id"] == "hyp-progress"
    assert gates["manager_review"]["lifecycle_status"] == "scheduled"
    assert gates["final_review"]["lifecycle_status"] == "scheduled"


def test_progress_never_marks_placeholder_artifact_ready(store: MissionStore, tmp_path: Path):
    path = tmp_path / "engagement_brief.md"
    path.write_text(
        "# Engagement Brief\n\n"
        "Hypothesis ID: hyp-placeholder\n\n"
        "This file is deliberately long enough to pass the minimum length check, "
        "so the regression proves placeholder detection still blocks readiness "
        "instead of accidentally passing because another validation rule fired first. "
        "The rest of this sentence is padding for the artifact quality threshold.\n\n"
        "- No hypotheses yet\n",
        encoding="utf-8",
    )
    store.save_deliverable(
        Deliverable(
            id="deliverable-placeholder",
            mission_id="m-progress",
            deliverable_type="engagement_brief",
            status="ready",
            file_path=str(path.resolve()),
            file_size_bytes=path.stat().st_size,
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))

    assert payload["deliverables"] == [
        {
            "id": "deliverable-placeholder",
            "deliverable_type": "engagement_brief",
            "status": "pending",
            "file_path": None,
            "created_at": payload["deliverables"][0]["created_at"],
        }
    ]


def test_progress_never_marks_short_artifact_ready(store: MissionStore, tmp_path: Path):
    path = tmp_path / "workstream_report.md"
    path.write_text("Finding ID: f-1. Too short.\n", encoding="utf-8")
    store.save_deliverable(
        Deliverable(
            id="deliverable-short",
            mission_id="m-progress",
            deliverable_type="workstream_report",
            status="ready",
            file_path=str(path.resolve()),
            file_size_bytes=path.stat().st_size,
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))

    assert payload["deliverables"][0]["id"] == "deliverable-short"
    assert payload["deliverables"][0]["status"] == "pending"
    assert payload["deliverables"][0]["file_path"] is None


def test_manager_review_opens_after_research_finding(store: MissionStore):
    store.save_finding(
        Finding(
            id="f-research",
            mission_id="m-progress",
            workstream_id="W1",
            claim_text="Market evidence is ready for manager review",
            confidence="REASONED",
            agent_id="dora",
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["manager_review"]["lifecycle_status"] == "open"
    assert gates["manager_review"]["is_open"] is True
    assert gates["manager_review"]["review_payload"]["coverage"]["findings_total"] == 1
    assert gates["manager_review"]["review_payload"]["research_findings"][0]["id"] == "f-research"
    assert gates["final_review"]["lifecycle_status"] == "scheduled"


def test_final_review_opens_after_merlin_verdict_and_redteam_finding(store: MissionStore):
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-progress",
            mission_id="m-progress",
            verdict="SHIP",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    store.save_finding(
        Finding(
            id="f-redteam",
            mission_id="m-progress",
            workstream_id="W4",
            claim_text="Adversus identified and bounded the weakest link",
            confidence="REASONED",
            agent_id="adversus",
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["final_review"]["lifecycle_status"] == "open"
    assert gates["final_review"]["is_open"] is True
    assert gates["final_review"]["review_payload"]["merlin_verdict"]["verdict"] == "SHIP"
    assert gates["final_review"]["review_payload"]["redteam_findings"][0]["id"] == "f-redteam"


def test_validate_gate_rejects_scheduled_gate_without_material(store: MissionStore):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            srv.validate_gate(
                "m-progress",
                "gate-m-progress-hyp-confirm",
                srv.GateValidateRequest(verdict="APPROVED", notes="too early"),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["lifecycle_status"] == "scheduled"
    assert set(exc_info.value.detail["missing_material"]) == {"framing_summary", "hypotheses"}


def test_validate_gate_rejects_opposite_verdict_after_gate_closed(store: MissionStore):
    store.update_gate_status("gate-m-progress-G1", "failed", notes="Needs more work")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            srv.validate_gate(
                "m-progress",
                "gate-m-progress-G1",
                srv.GateValidateRequest(verdict="APPROVED", notes="changed mind"),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["lifecycle_status"] == "failed"
    assert "already been decided" in exc_info.value.detail["message"]


def test_validate_gate_does_not_preclose_gate_when_stream_resumes(
    store: MissionStore,
    monkeypatch: pytest.MonkeyPatch,
):
    now = datetime.now(UTC).isoformat()
    store.save_hypothesis(
        Hypothesis(
            id="hyp-resume",
            mission_id="m-progress",
            text="Resume path hypothesis",
            created_at=now,
        )
    )
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-progress",
            raw_brief="Assess whether Target can sustain growth.",
            ic_question="Should IC invest?",
            mission_angle="Growth durability",
            brief_summary="Assess growth durability.",
            workstream_plan_json='[{"id":"W1","label":"Market","focus":"Market"}]',
            created_at=now,
            updated_at=now,
        )
    )
    delivered_payloads: list[dict] = []

    def deliver_resume(mission_id: str, payload: dict) -> bool:
        delivered_payloads.append(payload)
        return True

    monkeypatch.setattr(srv, "_deliver_resume", deliver_resume)

    response = asyncio.run(
        srv.validate_gate(
            "m-progress",
            "gate-m-progress-hyp-confirm",
            srv.GateValidateRequest(verdict="APPROVED", notes="approve"),
        )
    )

    gate = next(g for g in store.list_gates("m-progress") if g.id == "gate-m-progress-hyp-confirm")
    assert response.status == "resumed"
    assert gate.status == "pending"
    assert delivered_payloads == [
        {
            "approved": True,
            "verdict": "APPROVED",
            "notes": "approve",
            "gate_id": "gate-m-progress-hyp-confirm",
        }
    ]


def test_validate_gate_rejects_conflicting_decision_while_resume_in_flight(
    store: MissionStore,
    monkeypatch: pytest.MonkeyPatch,
):
    now = datetime.now(UTC).isoformat()
    store.save_hypothesis(
        Hypothesis(
            id="hyp-resume",
            mission_id="m-progress",
            text="Resume path hypothesis",
            created_at=now,
        )
    )
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-progress",
            raw_brief="Assess whether Target can sustain growth.",
            ic_question="Should IC invest?",
            mission_angle="Growth durability",
            brief_summary="Assess growth durability.",
            workstream_plan_json='[{"id":"W1","label":"Market","focus":"Market"}]',
            created_at=now,
            updated_at=now,
        )
    )
    monkeypatch.setattr(srv, "_deliver_resume", lambda mission_id, payload: True)

    first = asyncio.run(
        srv.validate_gate(
            "m-progress",
            "gate-m-progress-hyp-confirm",
            srv.GateValidateRequest(verdict="APPROVED", notes="approve"),
        )
    )
    same = asyncio.run(
        srv.validate_gate(
            "m-progress",
            "gate-m-progress-hyp-confirm",
            srv.GateValidateRequest(verdict="APPROVED", notes="approve again"),
        )
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            srv.validate_gate(
                "m-progress",
                "gate-m-progress-hyp-confirm",
                srv.GateValidateRequest(verdict="REJECTED", notes="reject"),
            )
        )

    gate = next(g for g in store.list_gates("m-progress") if g.id == "gate-m-progress-hyp-confirm")
    assert first.status == "resumed"
    assert same.status == "resume_pending"
    assert gate.status == "pending"
    assert srv._gate_decision_by_mission == {"m-progress": "gate-m-progress-hyp-confirm"}
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["lifecycle_status"] == "resuming"


def test_validate_gate_persists_decision_without_active_stream(
    store: MissionStore,
    monkeypatch: pytest.MonkeyPatch,
):
    now = datetime.now(UTC).isoformat()
    store.save_hypothesis(
        Hypothesis(
            id="hyp-no-stream",
            mission_id="m-progress",
            text="No stream hypothesis",
            created_at=now,
        )
    )
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-progress",
            raw_brief="Assess whether Target can sustain growth.",
            ic_question="Should IC invest?",
            mission_angle="Growth durability",
            brief_summary="Assess growth durability.",
            workstream_plan_json='[{"id":"W1","label":"Market","focus":"Market"}]',
            created_at=now,
            updated_at=now,
        )
    )
    monkeypatch.setattr(srv, "_deliver_resume", lambda mission_id, payload: False)

    response = asyncio.run(
        srv.validate_gate(
            "m-progress",
            "gate-m-progress-hyp-confirm",
            srv.GateValidateRequest(verdict="APPROVED", notes="approve without stream"),
        )
    )

    gate = next(g for g in store.list_gates("m-progress") if g.id == "gate-m-progress-hyp-confirm")
    assert response.status == "validated_no_stream"
    assert gate.status == "completed"
    assert gate.completion_notes == "approve without stream"
    assert srv._gate_decisions_in_flight == {}
    assert srv._gate_decision_by_mission == {}
