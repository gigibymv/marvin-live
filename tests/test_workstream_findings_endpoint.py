"""Bug 6 (chantier 2.6) regression: per-workstream findings endpoint.

Workstream tabs in the UI must render findings from DB (content), not
the live SSE meta-event stream (process). This endpoint is the data
source for that.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin.mission.schema import Finding, Hypothesis, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin_ui import server as srv


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-ws",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-ws", s)
    s.save_hypothesis(
        Hypothesis(
            id="hyp-1",
            mission_id="m-ws",
            text="x",
            label="H1",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(srv, "get_store", lambda: s)
    yield s
    s.close()


def _save(store: MissionStore, agent_id: str, claim: str, ws: str | None = None) -> None:
    fid = f"f-{agent_id}-{abs(hash(claim)) % 10000}"
    store.save_finding(
        Finding(
            id=fid,
            mission_id="m-ws",
            workstream_id=ws,
            hypothesis_id="hyp-1",
            claim_text=claim,
            confidence="REASONED",
            agent_id=agent_id,
            created_at=datetime.now(UTC).isoformat(),
        )
    )


def test_endpoint_returns_dora_findings_for_w1(store: MissionStore):
    _save(store, "dora", "Market is large and growing in priority segments.", ws="W1")
    _save(store, "calculus", "Adjusted EBITDA cannot be computed; missing inputs.", ws="W2")

    response = asyncio.run(srv.get_workstream_findings("m-ws", "W1"))

    assert response["workstream_id"] == "W1"
    assert response["count"] == 1
    assert response["findings"][0]["agent_id"] == "dora"
    assert response["findings"][0]["hypothesis_label"] == "H1"


def test_endpoint_returns_calculus_findings_for_w2(store: MissionStore):
    _save(store, "dora", "Market claim with sourced evidence.", ws="W1")
    _save(store, "calculus", "EBITDA cannot be computed; missing inputs.", ws="W2")

    response = asyncio.run(srv.get_workstream_findings("m-ws", "W2"))
    assert response["count"] == 1
    assert response["findings"][0]["agent_id"] == "calculus"


def test_empty_workstream_returns_empty_list(store: MissionStore):
    response = asyncio.run(srv.get_workstream_findings("m-ws", "W1"))
    assert response["count"] == 0
    assert response["findings"] == []


def test_endpoint_404_for_unknown_mission():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(srv.get_workstream_findings("m-nope", "W1"))
    assert exc.value.status_code == 404


def test_findings_attributed_by_agent_when_workstream_id_missing(store: MissionStore):
    """Even if a finding row has workstream_id=None, the agent → workstream
    map ensures the W1 tab still surfaces Dora's findings."""
    _save(store, "dora", "Market claim without explicit workstream tag.", ws=None)
    response = asyncio.run(srv.get_workstream_findings("m-ws", "W1"))
    assert response["count"] == 1
