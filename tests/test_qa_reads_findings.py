"""Bug 5 (chantier 2.6) regression tests: Q&A must read findings from DB
and attribute them to the correct agent. MARVIN must never say "Merlin
logged findings" since Merlin issues verdicts only.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from marvin.graph.subgraphs import orchestrator_qa
from marvin.mission.schema import Finding, Hypothesis, Mission, Source
from marvin.mission.store import MissionStore, _seed_standard_workplan


@pytest.fixture
def mission_store(monkeypatch, tmp_path):
    db_path = tmp_path / "qa.db"
    store = MissionStore(str(db_path))
    mid = "m-qa-find"
    store.save_mission(
        Mission(
            id=mid,
            client="C",
            target="Mistral AI",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan(mid, store)
    store.save_hypothesis(
        Hypothesis(
            id="hyp-1",
            mission_id=mid,
            text="Moat is defensible.",
            label="H1",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    # Two LOW_CONFIDENCE findings from Calculus, none from Merlin.
    store.save_finding(
        Finding(
            id="f-1",
            mission_id=mid,
            workstream_id="W2",
            hypothesis_id="hyp-1",
            claim_text="LTV/CAC cannot be computed; missing inputs.",
            confidence="LOW_CONFIDENCE",
            agent_id="calculus",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    store.save_finding(
        Finding(
            id="f-2",
            mission_id=mid,
            workstream_id="W2",
            hypothesis_id="hyp-1",
            claim_text="Adjusted EBITDA cannot be computed; missing inputs.",
            confidence="LOW_CONFIDENCE",
            agent_id="calculus",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(orchestrator_qa, "MissionStore", lambda: MissionStore(str(db_path)))
    yield mid, store
    store.close()


def test_summarize_state_includes_findings_text_and_attribution(mission_store):
    mid, _ = mission_store
    state = orchestrator_qa._summarize_state(mid)
    assert state["findings_count"] == 2
    assert "findings" in state and len(state["findings"]) == 2
    assert all(f["agent_id"] == "calculus" for f in state["findings"])
    assert "calculus" in state["findings_by_agent"]
    assert "merlin" not in state["findings_by_agent"]


def test_qa_response_cites_calculus_not_merlin_for_weak_claims(mission_store):
    mid, _ = mission_store
    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "why are the claims poor?"))
    assert "Calculus" in reply
    assert "Merlin logged" not in reply
    assert "Merlin has logged" not in reply


def test_qa_response_attributes_findings_correctly(mission_store):
    mid, _ = mission_store
    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "who logged the findings?"))
    assert "Calculus" in reply
    assert "Merlin logged" not in reply


def test_qa_response_mentions_low_confidence_when_present(mission_store):
    mid, _ = mission_store
    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "why are claims weak?"))
    # Either explicit LOW_CONFIDENCE flag or the finding excerpt itself
    assert (
        "LOW_CONFIDENCE" in reply
        or "missing" in reply.lower()
        or "cannot" in reply.lower()
    )


def test_qa_handles_empty_findings_gracefully(monkeypatch, tmp_path):
    db_path = tmp_path / "qa-empty.db"
    store = MissionStore(str(db_path))
    mid = "m-qa-empty"
    store.save_mission(
        Mission(
            id=mid, client="C", target="T", ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan(mid, store)
    monkeypatch.setattr(orchestrator_qa, "MissionStore", lambda: MissionStore(str(db_path)))
    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "what findings do we have?"))
    lower = reply.lower()
    assert "no" in lower and ("finding" in lower or "claim" in lower)
    assert "Merlin logged" not in reply
    store.close()
