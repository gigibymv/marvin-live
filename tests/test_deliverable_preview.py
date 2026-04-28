"""Chantier 4 CP3: GET /api/v1/deliverables/{id}/preview tests."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException

from marvin.mission.schema import Deliverable, Finding, Hypothesis, Mission, Source
from marvin.mission.store import MissionStore
from marvin_ui import server as srv


def _now() -> str:
    return datetime.now(UTC).isoformat()


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    monkeypatch.setattr(srv, "PROJECT_ROOT", tmp_path)

    md_path = out_dir / "framing_memo.md"
    md_path.write_text("# Framing memo\n\nHello world.", encoding="utf-8")

    s = MissionStore(":memory:")
    s.save_mission(Mission(id="m-d", client="C", target="T", created_at=_now()))
    s.save_hypothesis(Hypothesis(id="hyp-1", mission_id="m-d", label="H1", text="t", created_at=_now()))
    s.save_source(Source(id="src", mission_id="m-d", url_or_ref="u", retrieved_at=_now()))
    s.save_finding(Finding(
        id="f1", mission_id="m-d", hypothesis_id="hyp-1",
        claim_text="Critical claim", confidence="KNOWN",
        source_id="src", agent_id="calculus", created_at=_now(), impact="load_bearing",
    ))
    s.save_deliverable(Deliverable(
        id="d-md", mission_id="m-d", deliverable_type="framing_memo",
        status="ready", file_path=str(md_path.resolve()),
        file_size_bytes=md_path.stat().st_size, created_at=_now(),
    ))
    monkeypatch.setattr(srv, "get_store", lambda: s)
    yield s
    s.close()


def test_preview_returns_markdown_content(setup) -> None:
    data = asyncio.run(srv.get_deliverable_preview("d-md"))
    assert data["content_type"] == "markdown"
    assert "Framing memo" in data["content"]
    assert data["mission_id"] == "m-d"
    assert len(data["linked_findings"]) == 1
    assert data["linked_findings"][0]["hypothesis_label"] == "H1"
    assert data["linked_findings"][0]["impact"] == "load_bearing"


def test_preview_404_unknown_id(setup) -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(srv.get_deliverable_preview("d-bogus"))
    assert exc.value.status_code == 404
