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
        claim_text="Real claim",
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


def test_invalid_hypothesis_id_rejected_before_insert(store: MissionStore):
    with pytest.raises(ValueError, match="hypothesis_id 'hyp-fake' is not a valid"):
        mission_tools.add_finding_to_mission(
            claim_text="Bad claim",
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
            claim_text="Bad claim",
            confidence="REASONED",
            agent_id="dora",
            workstream_id="W99",
            hypothesis_id="hyp-real-1",
            state=_state(),
        )
    assert store.list_findings("m-fv") == []


def test_no_hypothesis_id_is_allowed(store: MissionStore):
    result = mission_tools.add_finding_to_mission(
        claim_text="Standalone claim",
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
