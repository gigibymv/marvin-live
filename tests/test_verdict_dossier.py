from __future__ import annotations

from datetime import UTC, datetime

from marvin.graph.verdict_dossier import build_verdict_dossier
from marvin.mission.schema import Deliverable, Finding, Hypothesis, Mission, Source
from marvin.mission.store import MissionStore, _seed_standard_workplan


def _seed(store: MissionStore, mission_id: str = "m-dossier") -> None:
    now = datetime.now(UTC).isoformat()
    store.save_hypothesis(
        Hypothesis(id="hyp-1", mission_id=mission_id, label="H1", text="Core claim", created_at=now)
    )
    store.save_hypothesis(
        Hypothesis(id="hyp-2", mission_id=mission_id, label="H2", text="Open claim", created_at=now)
    )
    store.save_source(
        Source(
            id="s-1",
            mission_id=mission_id,
            url_or_ref="https://example.com/primary",
            quote="Primary quote supporting the core claim.",
            source_type="web",
            retrieved_at=now,
        )
    )
    store.save_finding(
        Finding(
            id="f-support-1",
            mission_id=mission_id,
            workstream_id="W1",
            hypothesis_id="hyp-1",
            claim_text="Primary source support",
            confidence="KNOWN",
            source_id="s-1",
            agent_id="dora",
            created_at=now,
        )
    )
    store.save_finding(
        Finding(
            id="f-contradict-1",
            mission_id=mission_id,
            workstream_id="W4",
            hypothesis_id="hyp-1",
            claim_text="Red-team contradiction",
            confidence="REASONED",
            agent_id="adversus",
            stance="contradicts",
            implication="This makes the original thesis conditional on a rebuttal.",
            created_at=now,
        )
    )
    store.save_deliverable(
        Deliverable(
            id="del-w1",
            mission_id=mission_id,
            deliverable_type="workstream_report",
            status="ready",
            file_path="/tmp/market-report.txt",
            workstream_id="W1",
            created_at=now,
        )
    )


def test_verdict_dossier_is_deterministic_and_flags_gaps(tmp_path):
    store = MissionStore(db_path=tmp_path / "marvin.db")
    mission = Mission(id="m-dossier", client="Client", target="Target", mission_type="cdd")
    store.save_mission(mission)
    _seed_standard_workplan(mission.id, store)
    _seed(store, mission.id)

    first = build_verdict_dossier(store, mission.id)
    second = build_verdict_dossier(store, mission.id)

    assert first == second
    assert first["python_signal"] == "high"
    assert first["decision_guidance"]["insufficient_evidence_allowed"] is False
    assert (
        first["decision_guidance"]["suggested_decision_family"]
        == "investment_decision_with_conditions_or_decline"
    )
    assert any("H1 has unresolved red-team contradiction" in gap for gap in first["gaps"])
    assert any("H2 has no linked evidence yet." in gap for gap in first["gaps"])
    assert any("H1 has unresolved red-team contradiction" in risk for risk in first["investment_risks"])
    assert any("H2 has no linked evidence yet." in gap for gap in first["evidence_gaps"])
    by_label = {row["label"]: row for row in first["hypotheses"]}
    assert by_label["H1"]["primary_sourced_count"] == 1
    assert by_label["H1"]["supporting"][0]["finding_role"] == "supports"
    assert by_label["H1"]["supporting"][0]["source"]["quote"] == "Primary quote supporting the core claim."
    assert by_label["H1"]["supporting"][0]["evidence_packet"]["source_url_or_ref"] == "https://example.com/primary"
    assert len(by_label["H1"]["attacks"]) == 1
    assert by_label["H1"]["attacks"][0]["evidence_packet"]["claim"] == "Red-team contradiction"
    assert by_label["H1"]["attacks"][0]["evidence_packet"]["stance"] == "contradicts"
    assert (
        by_label["H1"]["attacks"][0]["evidence_packet"]["implication"]
        == "This makes the original thesis conditional on a rebuttal."
    )
    assert by_label["H2"]["status"] == "NOT_STARTED"
