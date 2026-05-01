from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from marvin.graph import gates as gate_module
from marvin.graph.gate_material import evaluate_gate_material
from marvin.mission.schema import Finding, Hypothesis, MerlinVerdict, Mission, MissionBrief
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
    store.mark_milestone_delivered("W1.1", "Market research complete", "m-gate")
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-G1")

    material = evaluate_gate_material(store, "m-gate", gate)

    assert material.is_open is True
    assert material.review_payload["findings_total"] == 1
    assert [f["id"] for f in material.review_payload["research_findings"]] == ["f-research"]


def test_missing_material_lists_are_not_aliased(store: MissionStore):
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-hyp-confirm")

    material = evaluate_gate_material(store, "m-gate", gate)

    assert isinstance(material.missing_material, tuple)
    assert isinstance(material.review_payload["missing_material"], list)


def test_final_gate_findings_total_counts_all_findings(store: MissionStore):
    now = datetime.now(UTC).isoformat()
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-gate",
            mission_id="m-gate",
            verdict="SHIP",
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
