from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin.mission.schema import (
    Deliverable,
    Finding,
    Hypothesis,
    MerlinVerdict,
    Mission,
    MissionBrief,
    MissionChatMessage,
)
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


def test_chat_messages_endpoint_returns_persisted_history(store: MissionStore):
    store.save_chat_message(
        MissionChatMessage(
            id="chat-user",
            mission_id="m-progress",
            role="user",
            text="What is blocked?",
            seq=1,
            created_at="2026-01-01T00:00:01+00:00",
        )
    )
    store.save_chat_message(
        MissionChatMessage(
            id="chat-marvin",
            mission_id="m-progress",
            role="marvin",
            text="Deliverable writing in progress.",
            seq=2,
            created_at="2026-01-01T00:00:02+00:00",
        )
    )

    payload = asyncio.run(srv.get_chat_messages("m-progress"))

    assert [message["id"] for message in payload["messages"]] == ["chat-user", "chat-marvin"]
    assert payload["messages"][0]["from"] == "u"
    assert payload["messages"][1]["from"] == "m"


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
            "milestone_id": None,
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


def test_manager_review_opens_after_research_finding(store: MissionStore, tmp_path: Path):
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
    # Gate requires ALL W1+W2 milestones in a terminal state. Seed all six so
    # the test reflects "research is complete" under the stricter rule.
    store.mark_milestone_delivered("W1.1", "Market research complete", "m-progress")
    store.mark_milestone_delivered("W1.2", "Competitive mapping complete", "m-progress")
    store.mark_milestone_delivered("W1.3", "Moat assessment complete", "m-progress")
    store.mark_milestone_delivered("W2.1", "Unit economics complete", "m-progress")
    store.mark_milestone_delivered("W2.2", "Public filings review complete", "m-progress")
    store.mark_milestone_delivered("W2.3", "Anomaly detection complete", "m-progress")
    # Gate also requires at least one `ready` deliverable per research workstream
    # (W1 and W2) — Papyrus must have finished compiling before the gate opens.
    w1_report = tmp_path / "w1_report.md"
    w1_report.write_text("W1 workstream report content — market and competitive analysis.\n" * 20, encoding="utf-8")
    store.save_deliverable(
        Deliverable(
            id="d-w1-report",
            mission_id="m-progress",
            deliverable_type="workstream_report",
            status="ready",
            workstream_id="W1",
            file_path=str(w1_report.resolve()),
            file_size_bytes=w1_report.stat().st_size,
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    w2_report = tmp_path / "w2_report.md"
    w2_report.write_text("W2 workstream report content — financial analysis.\n" * 20, encoding="utf-8")
    store.save_deliverable(
        Deliverable(
            id="d-w2-report",
            mission_id="m-progress",
            deliverable_type="workstream_report",
            status="ready",
            workstream_id="W2",
            file_path=str(w2_report.resolve()),
            file_size_bytes=w2_report.stat().st_size,
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    for milestone_id, ws_id in (
        ("W1.1", "W1"),
        ("W1.2", "W1"),
        ("W1.3", "W1"),
        ("W2.1", "W2"),
        ("W2.2", "W2"),
        ("W2.3", "W2"),
    ):
        milestone_report = tmp_path / f"{milestone_id}_report.md"
        milestone_report.write_text(
            f"{milestone_id} milestone report content.\n" * 20,
            encoding="utf-8",
        )
        store.save_deliverable(
            Deliverable(
                id=f"d-{milestone_id}",
                mission_id="m-progress",
                deliverable_type="milestone_report",
                status="ready",
                milestone_id=milestone_id,
                workstream_id=ws_id,
                file_path=str(milestone_report.resolve()),
                file_size_bytes=milestone_report.stat().st_size,
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


def test_final_review_opens_only_after_synthesis_complete(store: MissionStore):
    store.update_mission_synthesis_state("m-progress", "complete", datetime.now(UTC).isoformat())
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-progress",
            mission_id="m-progress",
            verdict="SHIP",
            synthesis_complete_at=datetime.now(UTC).isoformat(),
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
    g2 = next(g for g in store.list_gates("m-progress") if g.gate_type == "manager_review")
    store.update_gate_status(g2.id, "completed", "approved-for-test")

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["final_review"]["lifecycle_status"] == "open"
    assert gates["final_review"]["is_open"] is True
    assert gates["final_review"]["review_payload"]["merlin_verdict"]["verdict"] == "SHIP"
    assert gates["final_review"]["review_payload"]["redteam_findings"][0]["id"] == "f-redteam"


def test_final_review_stays_scheduled_while_synthesis_running(store: MissionStore):
    store.update_mission_synthesis_state("m-progress", "running", None)
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-progress-running",
            mission_id="m-progress",
            verdict="SHIP",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    store.save_finding(
        Finding(
            id="f-redteam-running",
            mission_id="m-progress",
            workstream_id="W4",
            claim_text="Adversus challenge still being synthesized",
            confidence="REASONED",
            agent_id="adversus",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    g2 = next(g for g in store.list_gates("m-progress") if g.gate_type == "manager_review")
    store.update_gate_status(g2.id, "completed", "approved-for-test")

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["final_review"]["lifecycle_status"] == "scheduled"
    assert "synthesis_incomplete" in gates["final_review"]["missing_material"]


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
    """Bug 4 (chantier 2.6): mismatched-verdict on a finalised gate returns
    a structured 200 conflict, not a 409 server error."""
    store.update_gate_status("gate-m-progress-G1", "failed", notes="Needs more work")

    response = asyncio.run(
        srv.validate_gate(
            "m-progress",
            "gate-m-progress-G1",
            srv.GateValidateRequest(verdict="APPROVED", notes="changed mind"),
        )
    )

    assert response.status == "conflict"
    assert response.conflict is True
    assert "already completed" in response.message


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
    spawned: list[tuple[str, dict]] = []

    def _fake_spawn(mission_id: str, payload: dict) -> str:
        spawned.append((mission_id, payload))
        return "spawned"

    monkeypatch.setattr(srv, "_spawn_detached_resume", _fake_spawn)

    response = asyncio.run(
        srv.validate_gate(
            "m-progress",
            "gate-m-progress-hyp-confirm",
            srv.GateValidateRequest(verdict="APPROVED", notes="approve without stream"),
        )
    )

    gate = next(g for g in store.list_gates("m-progress") if g.id == "gate-m-progress-hyp-confirm")
    # No parked stream → detached driver spawned. Per commit 38bda2e
    # (race fix), validate_gate must NOT pre-write gate.status='completed'
    # for the standard verdict path: gate_node owns that write at
    # gates.py:141, AFTER interrupt() returns the verdict. Pre-writing
    # caused gate_node's replay to take the missing-material early-exit
    # branch and terminate the graph. Status remains 'pending' here;
    # gate_node flips it to 'completed' once the detached driver replays.
    assert response.status == "resumed_detached"
    assert spawned == [
        (
            "m-progress",
            {
                "approved": True,
                "verdict": "APPROVED",
                "notes": "approve without stream",
                "gate_id": "gate-m-progress-hyp-confirm",
            },
        )
    ]
    assert gate.status == "pending"
    assert gate.completion_notes is None or gate.completion_notes == ""
    assert srv._gate_decisions_in_flight == {}
    assert srv._gate_decision_by_mission == {}
