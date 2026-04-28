"""Chantier 4: tests for findings.impact field.

Validates:
1. Impact field persists round-trip through MissionStore.
2. load_bearing + LOW_CONFIDENCE is rejected at validation.
3. None impact remains valid (backward-compatible default).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marvin.mission.schema import Finding, Hypothesis, Mission, Source
from marvin.mission.store import MissionStore


def _now() -> str:
    return datetime.now(UTC).isoformat()


@pytest.fixture
def store() -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(Mission(id="m-i", client="C", target="T", created_at=_now()))
    s.save_hypothesis(Hypothesis(id="hyp-1", mission_id="m-i", text="H", created_at=_now()))
    s.save_source(Source(id="src-1", mission_id="m-i", url_or_ref="ref", retrieved_at=_now()))
    yield s
    s.close()


def test_impact_persists_round_trip(store: MissionStore) -> None:
    f = Finding(
        id="f-lb",
        mission_id="m-i",
        hypothesis_id="hyp-1",
        claim_text="Load-bearing claim",
        confidence="KNOWN",
        source_id="src-1",
        agent_id="calculus",
        created_at=_now(),
        impact="load_bearing",
    )
    store.save_finding(f)
    rows = store.list_findings("m-i")
    assert len(rows) == 1
    assert rows[0].impact == "load_bearing"


def test_impact_none_is_valid(store: MissionStore) -> None:
    f = Finding(
        id="f-none",
        mission_id="m-i",
        claim_text="Plain claim",
        confidence="REASONED",
        agent_id="dora",
        created_at=_now(),
    )
    store.save_finding(f)
    assert store.list_findings("m-i")[0].impact is None


def test_load_bearing_low_confidence_rejected() -> None:
    with pytest.raises(ValueError, match="load_bearing"):
        Finding(
            id="f-bad",
            mission_id="m-i",
            claim_text="Weak claim",
            confidence="LOW_CONFIDENCE",
            agent_id="adversus",
            created_at=_now(),
            impact="load_bearing",
        )


def test_supporting_low_confidence_allowed() -> None:
    f = Finding(
        id="f-sup",
        mission_id="m-i",
        claim_text="Soft signal",
        confidence="LOW_CONFIDENCE",
        agent_id="adversus",
        created_at=_now(),
        impact="supporting",
    )
    assert f.impact == "supporting"
