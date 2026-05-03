from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from marvin.graph import gates as gate_module
from marvin.graph.gate_material import evaluate_gate_material
from marvin.mission.schema import Deliverable, Finding, Hypothesis, MerlinVerdict, Mission, MissionBrief
from marvin.mission.store import MissionStore, _seed_standard_workplan


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-gate",
            client="Client",
            target="Target",
            ic_question="Should IC invest?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-gate", s)
    monkeypatch.setattr(gate_module, "MissionStore", lambda *a, **kw: s)
    monkeypatch.setattr(gate_module, "check_internal_consistency", lambda mission_id: {})
    yield s
    s.close()


def test_gate_node_does_not_interrupt_without_required_material(store: MissionStore):
    result = asyncio.run(
        gate_module.gate_node(
            {
                "mission_id": "m-gate",
                "pending_gate_id": "gate-m-gate-hyp-confirm",
            }
        )
    )

    assert result["phase"] == "idle"
    assert result["pending_gate_id"] is None
    blocked = result["phase_blocked"]
    assert blocked["gate_id"] == "gate-m-gate-hyp-confirm"
    assert blocked["gate_type"] == "hypothesis_confirmation"
    assert blocked["missing_material"]
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-hyp-confirm")
    assert gate.status == "pending"


def test_hypothesis_gate_material_requires_framing_and_hypotheses(store: MissionStore):
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-hyp-confirm")
    now = datetime.now(UTC).isoformat()
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-gate",
            raw_brief="Assess Target.",
            ic_question="Should IC invest?",
            mission_angle="Market attractiveness",
            brief_summary="Assess Target's market attractiveness.",
            workstream_plan_json="[]",
            created_at=now,
            updated_at=now,
        )
    )
    store.save_hypothesis(
        Hypothesis(
            id="hyp-gate",
            mission_id="m-gate",
            text="Target can sustain growth.",
            created_at=now,
        )
    )

    material = evaluate_gate_material(store, "m-gate", gate)

    assert material.is_open is True
    assert material.missing_material == ()
    assert material.review_payload["framing"]["brief_summary"] == "Assess Target's market attractiveness."


def test_manager_gate_findings_total_counts_only_research_findings(store: MissionStore):
    now = datetime.now(UTC).isoformat()
    store.save_finding(
        Finding(
            id="f-research",
            mission_id="m-gate",
            workstream_id="W1",
            claim_text="Research claim",
            confidence="REASONED",
            agent_id="dora",
            created_at=now,
        )
    )
    store.save_finding(
        Finding(
            id="f-redteam",
            mission_id="m-gate",
            workstream_id="W4",
            claim_text="Red-team challenge",
            confidence="REASONED",
            agent_id="adversus",
            created_at=now,
        )
    )
    # Gate requires ALL W1+W2 milestones terminal; seed all six to reflect
    # "research complete" under the stricter rule (intent unchanged).
    store.mark_milestone_delivered("W1.1", "Market research complete", "m-gate")
    store.mark_milestone_delivered("W1.2", "Competitive mapping complete", "m-gate")
    store.mark_milestone_delivered("W1.3", "Moat assessment complete", "m-gate")
    store.mark_milestone_delivered("W2.1", "Unit economics complete", "m-gate")
    store.mark_milestone_delivered("W2.2", "Public filings review complete", "m-gate")
    store.mark_milestone_delivered("W2.3", "Anomaly detection complete", "m-gate")
    # Gate also requires a `ready` deliverable per research workstream (P16 fix).
    store.save_deliverable(
        Deliverable(
            id="d-w1",
            mission_id="m-gate",
            deliverable_type="workstream_report",
            status="ready",
            workstream_id="W1",
            created_at=now,
        )
    )
    store.save_deliverable(
        Deliverable(
            id="d-w2",
            mission_id="m-gate",
            deliverable_type="workstream_report",
            status="ready",
            workstream_id="W2",
            created_at=now,
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
        store.save_deliverable(
            Deliverable(
                id=f"d-{milestone_id}",
                mission_id="m-gate",
                deliverable_type="milestone_report",
                status="ready",
                milestone_id=milestone_id,
                workstream_id=ws_id,
                created_at=now,
            )
        )
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-G1")

    material = evaluate_gate_material(store, "m-gate", gate)

    assert material.is_open is True
    assert material.review_payload["findings_total"] == 1
    assert [f["id"] for f in material.review_payload["research_findings"]] == ["f-research"]


def test_manager_gate_waits_for_delivered_milestone_reports(store: MissionStore):
    now = datetime.now(UTC).isoformat()
    store.save_finding(
        Finding(
            id="f-research",
            mission_id="m-gate",
            workstream_id="W1",
            claim_text="Research claim",
            confidence="REASONED",
            agent_id="dora",
            created_at=now,
        )
    )
    for milestone_id, label in (
        ("W1.1", "Market research complete"),
        ("W1.2", "Competitive mapping complete"),
        ("W1.3", "Moat assessment complete"),
        ("W2.1", "Unit economics complete"),
        ("W2.2", "Public filings review complete"),
        ("W2.3", "Anomaly detection complete"),
    ):
        store.mark_milestone_delivered(milestone_id, label, "m-gate")
    for ws_id in ("W1", "W2"):
        store.save_deliverable(
            Deliverable(
                id=f"d-{ws_id}",
                mission_id="m-gate",
                deliverable_type="workstream_report",
                status="ready",
                workstream_id=ws_id,
                created_at=now,
            )
        )
    # W2.3 is intentionally missing: if the backend delivered that milestone,
    # the manager gate must wait until Papyrus has produced its report.
    for milestone_id, ws_id in (
        ("W1.1", "W1"),
        ("W1.2", "W1"),
        ("W1.3", "W1"),
        ("W2.1", "W2"),
        ("W2.2", "W2"),
    ):
        store.save_deliverable(
            Deliverable(
                id=f"d-{milestone_id}",
                mission_id="m-gate",
                deliverable_type="milestone_report",
                status="ready",
                milestone_id=milestone_id,
                workstream_id=ws_id,
                created_at=now,
            )
        )
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-G1")

    material = evaluate_gate_material(store, "m-gate", gate)

    assert material.is_open is False
    assert "deliverable_writing_in_progress" in material.missing_material


def test_manager_gate_allows_blocked_optional_financial_milestones_without_reports(store: MissionStore):
    now = datetime.now(UTC).isoformat()
    store.save_finding(
        Finding(
            id="f-research",
            mission_id="m-gate",
            workstream_id="W1",
            claim_text="Research claim",
            confidence="REASONED",
            agent_id="dora",
            created_at=now,
        )
    )
    for milestone_id, label in (
        ("W1.1", "Market research complete"),
        ("W1.2", "Competitive mapping complete"),
        ("W1.3", "Moat assessment complete"),
        ("W2.1", "Unit economics complete"),
    ):
        store.mark_milestone_delivered(milestone_id, label, "m-gate")
    store.mark_milestone_blocked("W2.2", "optional public filings review not required", "m-gate")
    store.mark_milestone_blocked("W2.3", "optional anomaly detection not required", "m-gate")
    for ws_id in ("W1", "W2"):
        store.save_deliverable(
            Deliverable(
                id=f"d-{ws_id}",
                mission_id="m-gate",
                deliverable_type="workstream_report",
                status="ready",
                workstream_id=ws_id,
                created_at=now,
            )
        )
    for milestone_id, ws_id in (
        ("W1.1", "W1"),
        ("W1.2", "W1"),
        ("W1.3", "W1"),
        ("W2.1", "W2"),
    ):
        store.save_deliverable(
            Deliverable(
                id=f"d-{milestone_id}",
                mission_id="m-gate",
                deliverable_type="milestone_report",
                status="ready",
                milestone_id=milestone_id,
                workstream_id=ws_id,
                created_at=now,
            )
        )
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-G1")

    material = evaluate_gate_material(store, "m-gate", gate)

    assert material.is_open is True


def test_manager_gate_does_not_treat_blocked_visible_workstream_as_complete(store: MissionStore):
    now = datetime.now(UTC).isoformat()
    store.save_finding(
        Finding(
            id="f-research",
            mission_id="m-gate",
            workstream_id="W1",
            claim_text="Research claim",
            confidence="REASONED",
            agent_id="dora",
            created_at=now,
        )
    )
    for milestone_id, label in (
        ("W1.1", "Market research complete"),
        ("W1.2", "Competitive mapping complete"),
        ("W1.3", "Moat assessment complete"),
    ):
        store.mark_milestone_delivered(milestone_id, label, "m-gate")
    store.mark_milestone_blocked("W2.1", "Financial analysis could not complete", "m-gate")
    for ws_id in ("W1",):
        store.save_deliverable(
            Deliverable(
                id=f"d-{ws_id}",
                mission_id="m-gate",
                deliverable_type="workstream_report",
                status="ready",
                workstream_id=ws_id,
                created_at=now,
            )
        )
    for milestone_id in ("W1.1", "W1.2", "W1.3"):
        store.save_deliverable(
            Deliverable(
                id=f"d-{milestone_id}",
                mission_id="m-gate",
                deliverable_type="milestone_report",
                status="ready",
                milestone_id=milestone_id,
                workstream_id="W1",
                created_at=now,
            )
        )
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-G1")

    material = evaluate_gate_material(store, "m-gate", gate)

    assert material.is_open is False
    assert "deliverable_writing_in_progress" in material.missing_material


def test_missing_material_lists_are_not_aliased(store: MissionStore):
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-hyp-confirm")

    material = evaluate_gate_material(store, "m-gate", gate)

    assert isinstance(material.missing_material, tuple)
    assert isinstance(material.review_payload["missing_material"], list)


def test_final_gate_findings_total_counts_all_findings(store: MissionStore):
    now = datetime.now(UTC).isoformat()
    store.update_mission_synthesis_state("m-gate", "complete", now)
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-gate",
            mission_id="m-gate",
            verdict="SHIP",
            synthesis_complete_at=now,
            created_at=now,
        )
    )
    store.save_finding(
        Finding(
            id="f-research-final",
            mission_id="m-gate",
            workstream_id="W1",
            claim_text="Research claim",
            confidence="REASONED",
            agent_id="dora",
            created_at=now,
        )
    )
    store.save_finding(
        Finding(
            id="f-redteam-final",
            mission_id="m-gate",
            workstream_id="W4",
            claim_text="Red-team challenge",
            confidence="LOW_CONFIDENCE",
            agent_id="adversus",
            created_at=now,
        )
    )
    # G3 only opens once G2 (manager_review) is completed; without this
    # gate ordering, an interim merlin verdict would open G3 mid-Adversus.
    g2 = next(g for g in store.list_gates("m-gate") if g.gate_type == "manager_review")
    store.update_gate_status(g2.id, "completed", "approved-for-test")
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-G3")

    material = evaluate_gate_material(store, "m-gate", gate, arbiter_flags=["Check margin bridge"])

    assert material.is_open is True
    assert material.review_payload["findings_total"] == 2
    assert material.review_payload["open_risks"] == ["Red-team challenge"]
    assert material.review_payload["arbiter_flags"] == ["Check margin bridge"]


def test_final_gate_blocked_while_manager_gate_pending(store: MissionStore):
    """G3 must NOT open until G2 is completed, even when Merlin has saved
    an interim verdict and Adversus has produced findings (synthesis_retry
    loop). Regression for #3 — IC sign-off banner appearing at ~42% during
    Adversus."""
    now = datetime.now(UTC).isoformat()
    store.save_merlin_verdict(
        MerlinVerdict(id="mv-interim", mission_id="m-gate", verdict="MINOR_FIXES", created_at=now)
    )
    store.save_finding(
        Finding(
            id="f-redteam-interim",
            mission_id="m-gate",
            workstream_id="W4",
            claim_text="Red-team interim claim",
            confidence="REASONED",
            agent_id="adversus",
            created_at=now,
        )
    )
    g3 = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-G3")

    material = evaluate_gate_material(store, "m-gate", g3)

    assert material.is_open is False
    assert "prior_gate_pending" in material.missing_material
