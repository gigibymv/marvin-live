"""Reference-integrity tests for add_finding_to_mission.

Proves:
1. A finding with a valid hypothesis_id and valid workstream_id persists.
2. An unknown hypothesis_id is rejected with a clear ValueError BEFORE the
   INSERT (so the LLM tool-loop sees a corrective message instead of an
   opaque SQLite FOREIGN KEY error).
3. An unknown workstream_id is rejected the same way.
4. Omitting hypothesis_id (None) is allowed — findings can stand on their own.

The validation lives at the tool boundary, so the FK constraint is preserved;
this test exercises that boundary directly without going through the LLM.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin.mission.schema import Hypothesis, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-fv",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-fv", s)
    s.save_hypothesis(
        Hypothesis(
            id="hyp-real-1",
            mission_id="m-fv",
            text="Market is large",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: s)
    yield s
    s.close()


def _state() -> dict:
    return {"mission_id": "m-fv"}


def test_valid_hypothesis_and_workstream_persists(store: MissionStore):
    result = mission_tools.add_finding_to_mission(
        claim_text="Real claim with sustained sourced evidence.",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-real-1",
        state=_state(),
    )
    assert "finding_id" in result
    findings = store.list_findings("m-fv")
    assert len(findings) == 1
    assert findings[0].hypothesis_id == "hyp-real-1"
    assert findings[0].workstream_id == "W1"
    assert result["status"] == "saved"


def test_milestone_shaped_workstream_id_is_normalized(store: MissionStore):
    result = mission_tools.add_finding_to_mission(
        claim_text="Milestone-shaped workstream ref is recoverable",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1.1",
        hypothesis_id="hyp-real-1",
        state=_state(),
    )

    findings = store.list_findings("m-fv")
    assert result["status"] == "saved"
    assert findings[0].workstream_id == "W1"


def test_invalid_hypothesis_id_rejected_before_insert(store: MissionStore):
    with pytest.raises(ValueError, match="hypothesis_id 'hyp-fake' is not a valid"):
        mission_tools.add_finding_to_mission(
            claim_text="Bad claim with realistic length for validator.",
            confidence="REASONED",
            agent_id="dora",
            workstream_id="W1",
            hypothesis_id="hyp-fake",
            state=_state(),
        )
    # Nothing persisted.
    assert store.list_findings("m-fv") == []


def test_invalid_workstream_id_rejected_before_insert(store: MissionStore):
    with pytest.raises(ValueError, match="workstream_id 'W99' is not a valid"):
        mission_tools.add_finding_to_mission(
            claim_text="Bad claim with realistic length for validator.",
            confidence="REASONED",
            agent_id="dora",
            workstream_id="W99",
            hypothesis_id="hyp-real-1",
            state=_state(),
        )
    assert store.list_findings("m-fv") == []


def test_no_hypothesis_id_is_allowed(store: MissionStore):
    result = mission_tools.add_finding_to_mission(
        claim_text="Standalone claim with sustained content.",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id=None,
        state=_state(),
    )
    assert "finding_id" in result
    findings = store.list_findings("m-fv")
    assert len(findings) == 1
    assert findings[0].hypothesis_id is None


def test_duplicate_finding_returns_existing_id_without_second_insert(store: MissionStore):
    first = mission_tools.add_finding_to_mission(
        claim_text="Retention is durable.",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-real-1",
        state=_state(),
    )
    second = mission_tools.add_finding_to_mission(
        claim_text="retention   is durable",
        confidence="LOW_CONFIDENCE",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-real-1",
        state=_state(),
    )

    findings = store.list_findings("m-fv")
    assert len(findings) == 1
    assert second["status"] == "duplicate"
    assert second["finding_id"] == first["finding_id"]


def test_duplicate_finding_is_suppressed_across_hypotheses_in_same_workstream(store: MissionStore):
    first = mission_tools.add_finding_to_mission(
        claim_text="Premium pricing rests on regulated workflow lock-in",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-real-1",
        state=_state(),
    )
    second = mission_tools.add_finding_to_mission(
        claim_text="Premium pricing rests on regulated workflow lock-in",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id=None,
        state=_state(),
    )

    assert len(store.list_findings("m-fv")) == 1
    assert second["status"] == "duplicate"
    assert second["finding_id"] == first["finding_id"]


def test_duplicate_finding_is_suppressed_without_workstream(store: MissionStore):
    first = mission_tools.add_finding_to_mission(
        claim_text="Source evidence remains incomplete!",
        confidence="LOW_CONFIDENCE",
        agent_id="dora",
        workstream_id=None,
        state=_state(),
    )
    second = mission_tools.add_finding_to_mission(
        claim_text="source evidence remains incomplete",
        confidence="LOW_CONFIDENCE",
        agent_id="dora",
        workstream_id=None,
        state=_state(),
    )

    assert len(store.list_findings("m-fv")) == 1
    assert second["status"] == "duplicate"
    assert second["finding_id"] == first["finding_id"]


def test_same_claim_can_exist_in_different_workstreams(store: MissionStore):
    mission_tools.add_finding_to_mission(
        claim_text="Evidence quality is mixed",
        confidence="REASONED",
        agent_id="dora",
        workstream_id="W1",
        state=_state(),
    )
    mission_tools.add_finding_to_mission(
        claim_text="Evidence quality is mixed",
        confidence="REASONED",
        agent_id="calculus",
        workstream_id="W2",
        state=_state(),
    )

    assert len(store.list_findings("m-fv")) == 2


def test_hallucinated_agent_id_falls_back_to_workstream_map(store: MissionStore):
    """LLM passing a manager name (e.g. 'MV' from 'Manager: MV.' in the brief)
    must NOT be persisted; agent_id must resolve to the workstream's owner."""
    result = mission_tools.add_finding_to_mission(
        claim_text="Some W1 claim from a confused agent",
        confidence="REASONED",
        agent_id="MV",
        workstream_id="W1",
        hypothesis_id="hyp-real-1",
        state=_state(),
    )
    assert result["status"] == "saved"
    findings = store.list_findings("m-fv")
    assert findings[0].agent_id == "dora"


def test_w3_workstream_maps_to_merlin_and_hits_zero_cap(store: MissionStore):
    """Merlin synthesizes, never persists findings — its cap is 0. A W3 save
    attempt must resolve agent_id to 'merlin' and hit the cap immediately."""
    result = mission_tools.add_finding_to_mission(
        claim_text="W3 synthesis claim with sufficient body length.",
        confidence="REASONED",
        agent_id=None,
        workstream_id="W3",
        state=_state(),
    )
    assert result["status"] == "cap_reached"
    assert result["agent_id"] == "merlin"
    assert store.list_findings("m-fv") == []


def test_finding_cap_blocks_overage_per_agent(store: MissionStore):
    """Adversus has a 12-finding cap. The 13th call must raise with a
    cap-reached message instead of silently piling on."""
    cap = mission_tools.MAX_FINDINGS_PER_AGENT_PER_MISSION["adversus"]
    for i in range(cap):
        mission_tools.add_finding_to_mission(
            claim_text=f"Adversus attack #{i} — distinct counter-argument body",
            confidence="REASONED",
            agent_id="adversus",
            workstream_id="W4",
            state=_state(),
        )
    assert len(
        [f for f in store.list_findings("m-fv") if f.agent_id == "adversus"]
    ) == cap

    overflow = mission_tools.add_finding_to_mission(
        claim_text="One attack too many — overflow check beyond cap.",
        confidence="REASONED",
        agent_id="adversus",
        workstream_id="W4",
        state=_state(),
    )
    assert overflow["status"] == "cap_reached"
    assert overflow["agent_id"] == "adversus"
    assert overflow["existing"] == cap
    # Cap blocks the insert: still exactly `cap` findings for adversus.
    assert len(
        [f for f in store.list_findings("m-fv") if f.agent_id == "adversus"]
    ) == cap
