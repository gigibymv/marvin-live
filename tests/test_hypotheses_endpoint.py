"""Chantier 4: tests for GET /api/v1/missions/{id}/hypotheses."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from marvin.mission.schema import Finding, Hypothesis, Mission, Source
from marvin.mission.store import MissionStore
from marvin_ui import server as srv


def _now() -> str:
    return datetime.now(UTC).isoformat()


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(Mission(id="m-h", client="C", target="T", created_at=_now()))
    s.save_hypothesis(Hypothesis(id="hyp-1", mission_id="m-h", label="H1", text="t1", created_at=_now()))
    s.save_hypothesis(Hypothesis(id="hyp-2", mission_id="m-h", label="H2", text="t2", created_at=_now()))
    s.save_source(Source(id="src", mission_id="m-h", url_or_ref="u", retrieved_at=_now()))
    s.save_finding(Finding(
        id="f1", mission_id="m-h", hypothesis_id="hyp-1",
        claim_text="c1", confidence="KNOWN", source_id="src", agent_id="calculus", created_at=_now(),
    ))
    s.save_finding(Finding(
        id="f2", mission_id="m-h", hypothesis_id="hyp-1",
        claim_text="c2", confidence="KNOWN", source_id="src", agent_id="dora", created_at=_now(),
    ))
    monkeypatch.setattr(srv, "get_store", lambda: s)
    yield s
    s.close()


def test_hypotheses_endpoint_returns_computed_status(store: MissionStore) -> None:
    data = asyncio.run(srv.get_mission_hypotheses("m-h"))
    assert data["mission_id"] == "m-h"
    by_id = {h["id"]: h for h in data["hypotheses"]}
    assert by_id["hyp-1"]["computed"]["status"] == "SUPPORTED"
    assert by_id["hyp-1"]["computed"]["known"] == 2
    assert by_id["hyp-1"]["label"] == "H1"
    assert by_id["hyp-2"]["computed"]["status"] == "NOT_STARTED"
    assert by_id["hyp-2"]["computed"]["total"] == 0


def test_hypotheses_endpoint_404_unknown_mission(store: MissionStore) -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(srv.get_mission_hypotheses("m-bogus"))
    assert exc.value.status_code == 404
