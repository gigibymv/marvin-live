"""Bug 1 (chantier 2.6) regression tests: quality validator on findings.

The system must reject absurd findings (math on missing data) marked
KNOWN/REASONED, and downgrade soft cases to LOW_CONFIDENCE before persist.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marvin.mission.schema import Hypothesis, Mission, Source
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools
from marvin.tools.mission_tools import validate_finding_quality


@pytest.fixture
def graph_store(monkeypatch):
    store = MissionStore(":memory:")
    store.save_mission(
        Mission(
            id="m-test",
            client="Client",
            target="Target",
            ic_question="Is this attractive?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-test", store)
    store.save_hypothesis(
        Hypothesis(
            id="hyp-1",
            mission_id="m-test",
            text="Moat is defensible.",
            label="H1",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    store.save_source(
        Source(
            id="s-1",
            mission_id="m-test",
            url_or_ref="https://example.com",
            quote="evidence",
            retrieved_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: store)
    yield store
    store.close()


# --- pure validator -------------------------------------------------------

def test_validator_rejects_short_claim():
    ok, suggested, reason = validate_finding_quality("too short", "REASONED")
    assert ok is False
    assert "short" in reason.lower()


def test_validator_rejects_multi_pattern_reasoned():
    ok, suggested, reason = validate_finding_quality(
        "Adjusted EBITDA is 0.00 (revenue 0.0, cogs 0.0, opex 0.0) "
        "[missing inputs: revenue, cogs, opex, add_backs]",
        "REASONED",
    )
    assert ok is False
    assert "REASONED" in reason or "missing" in reason.lower()


def test_validator_downgrades_single_pattern_reasoned():
    ok, suggested, reason = validate_finding_quality(
        "Mistral revenue cannot be verified from public filings as of Q3 2024.",
        "REASONED",
    )
    assert ok is True
    assert suggested == "LOW_CONFIDENCE"


def test_validator_passes_legitimate_claim():
    ok, suggested, reason = validate_finding_quality(
        "Mistral's enterprise contracts show 12-month minimum commitments "
        "with 87% renewal rate based on Q3 2024 investor disclosure.",
        "REASONED",
    )
    assert ok is True
    assert suggested is None
    assert reason is None


def test_validator_lets_low_confidence_through():
    """LOW_CONFIDENCE findings are allowed to mention missing data."""
    ok, suggested, reason = validate_finding_quality(
        "EBITDA cannot be verified — Mistral private, [missing inputs: revenue].",
        "LOW_CONFIDENCE",
    )
    assert ok is True
    assert suggested is None


# --- integration with add_finding_to_mission -----------------------------

def test_absurd_finding_rejected_when_reasoned(graph_store):
    result = mission_tools.add_finding_to_mission(
        claim_text=(
            "Adjusted EBITDA is 0.00 (revenue 0.0, cogs 0.0) "
            "[missing inputs: revenue, cogs]"
        ),
        confidence="REASONED",
        hypothesis_id="hyp-1",
        agent_id="calculus",
        workstream_id="W2",
        state={"mission_id": "m-test"},
    )
    assert result["status"] == "rejected"
    assert "guidance" in result
    assert graph_store.list_findings("m-test") == []


def test_partial_zero_finding_downgraded_to_low_confidence(graph_store):
    result = mission_tools.add_finding_to_mission(
        claim_text="Mistral revenue cannot be verified from public filings as of Q3 2024.",
        confidence="REASONED",
        hypothesis_id="hyp-1",
        agent_id="calculus",
        workstream_id="W2",
        state={"mission_id": "m-test"},
    )
    assert result["status"] == "saved"
    assert result["confidence"] == "LOW_CONFIDENCE"
    rows = graph_store.list_findings("m-test")
    assert len(rows) == 1
    assert rows[0].confidence == "LOW_CONFIDENCE"
    assert "auto-adjusted" in rows[0].claim_text


def test_legitimate_finding_passes(graph_store):
    result = mission_tools.add_finding_to_mission(
        claim_text=(
            "Mistral's enterprise contracts show 12-month minimum commitments "
            "with 87% renewal rate based on Q3 2024 investor disclosure."
        ),
        confidence="REASONED",
        hypothesis_id="hyp-1",
        agent_id="calculus",
        workstream_id="W2",
        state={"mission_id": "m-test"},
    )
    assert result["status"] == "saved"
    assert result["confidence"] == "REASONED"


def test_short_claim_rejected(graph_store):
    result = mission_tools.add_finding_to_mission(
        claim_text="too short",
        confidence="KNOWN",
        hypothesis_id="hyp-1",
        agent_id="calculus",
        workstream_id="W2",
        source_id="s-1",
        state={"mission_id": "m-test"},
    )
    assert result["status"] == "rejected"
    assert "short" in result["reason"].lower()
