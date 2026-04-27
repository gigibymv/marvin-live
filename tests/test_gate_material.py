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

    assert result == {"phase": "idle", "pending_gate_id": None}
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
    gate = next(g for g in store.list_gates("m-gate") if g.id == "gate-m-gate-G3")

    material = evaluate_gate_material(store, "m-gate", gate, arbiter_flags=["Check margin bridge"])

    assert material.is_open is True
    assert material.review_payload["findings_total"] == 2
    assert material.review_payload["open_risks"] == ["Red-team challenge"]
    assert material.review_payload["arbiter_flags"] == ["Check margin bridge"]
