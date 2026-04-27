"""Bug 2 (chantier 2.6) regression tests: hypothesis linking is mandatory.

Every finding must reference an active hypothesis. Orphan or stale-hypothesis
findings are rejected at the tool boundary so the LLM tool-loop receives a
corrective message instead of polluting the DB.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marvin.mission.schema import Hypothesis, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools


@pytest.fixture
def store(monkeypatch):
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-link",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-link", s)
    s.save_hypothesis(
        Hypothesis(
            id="hyp-active",
            mission_id="m-link",
            text="Active hypothesis under test.",
            label="H1",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    s.save_hypothesis(
        Hypothesis(
            id="hyp-abandoned",
            mission_id="m-link",
            text="Abandoned hypothesis after pivot.",
            label="H2",
            status="abandoned",
            abandon_reason="pivot",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: s)
    yield s
    s.close()


def test_finding_without_hypothesis_rejected(store):
    result = mission_tools.add_finding_to_mission(
        claim_text="Some legitimate claim with real data and sourcing.",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id=None,
        state={"mission_id": "m-link"},
    )
    assert result["status"] == "rejected"
    assert "hypothesis_id" in result["reason"]
    assert "guidance" in result
    assert store.list_findings("m-link") == []


def test_finding_with_invalid_hypothesis_rejected(store):
    result = mission_tools.add_finding_to_mission(
        claim_text="Real claim about real data with sourcing.",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-doesnotexist",
        state={"mission_id": "m-link"},
    )
    assert result["status"] == "rejected"
    assert "not a valid" in result["reason"]
    assert store.list_findings("m-link") == []


def test_finding_with_abandoned_hypothesis_rejected(store):
    result = mission_tools.add_finding_to_mission(
        claim_text="Real claim that targets a stale hypothesis.",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-abandoned",
        state={"mission_id": "m-link"},
    )
    assert result["status"] == "rejected"
    assert "abandoned" in result["reason"]
    assert store.list_findings("m-link") == []


def test_finding_with_active_hypothesis_persists(store):
    result = mission_tools.add_finding_to_mission(
        claim_text="Real claim about real data with sourcing.",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-active",
        state={"mission_id": "m-link"},
    )
    assert result["status"] == "saved"
    assert len(store.list_findings("m-link")) == 1
