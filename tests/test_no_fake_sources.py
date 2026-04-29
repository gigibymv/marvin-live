"""Wiring test for fix B: source_quote with retrieval-failure markers must
not produce a finding or a source row.

Pre-fix: Calculus could submit
  source_url="https://sec.gov/..." +
  source_quote="[missing inputs: tool did not return filing text...]"
and add_finding_to_mission would persist BOTH the source row (with the
failure message stored as the quote) AND the finding (with a fabricated
citation). The result was a fake-evidenced finding.

Post-fix: add_finding_to_mission inspects source_quote against the
absurd-finding patterns BEFORE writing anything. Failure-confession
quotes cause rejection — no source, no finding. The agent must instead
call mark_milestone_blocked or submit a LOW_CONFIDENCE finding with no
source.
"""
from __future__ import annotations

import pytest


def _seed_mission(tmp_path, monkeypatch):
    db_path = tmp_path / "marvin.db"
    monkeypatch.setenv("MARVIN_DB_PATH", str(db_path))

    import importlib
    import marvin.mission.store as store_mod
    importlib.reload(store_mod)
    import marvin.tools.mission_tools as mt
    importlib.reload(mt)

    from marvin.mission.store import MissionStore
    from marvin.mission.schema import (
        Mission as MissionModel,
        Hypothesis,
        Workstream,
        Milestone,
    )

    MID = "m-test-fakesrc"
    store = MissionStore(str(db_path))
    store.save_mission(MissionModel(
        id=MID, client="test", target="test", mission_type="cdd",
        ic_question="?", status="active",
    ))
    store.save_workstream(Workstream(
        id="W2", mission_id=MID, label="Financial",
        assigned_agent="calculus",
    ))
    store.save_hypothesis(Hypothesis(
        id="hyp-test", mission_id=MID, label="H1",
        text="test hypothesis text" * 3, status="active",
    ))
    store.save_milestone(Milestone(
        id="W2.1", mission_id=MID, workstream_id="W2",
        label="Public filings review", status="pending",
    ))
    return MID, store, mt


def test_failure_quote_rejects_finding_and_source(tmp_path, monkeypatch):
    MID, store, mt = _seed_mission(tmp_path, monkeypatch)

    state = {"mission_id": MID}
    result = mt.add_finding_to_mission(
        claim_text="FY2024 net revenue (GAAP) was $3.1B per the 10-K.",
        confidence="LOW_CONFIDENCE",
        agent_id="calculus",
        workstream_id="W2",
        hypothesis_id="hyp-test",
        source_url="https://sec.gov/snowflake-2024",
        source_quote="[missing inputs: tool did not return filing text/line references]",
        state=state,
    )

    assert result["status"] == "rejected"
    assert "retrieval-failure" in result["reason"].lower() or "missing" in result["reason"].lower()

    # No source row should have been written.
    assert len(store.list_sources(MID)) == 0
    # No finding row should have been written.
    assert len(store.list_findings(MID)) == 0


def test_clean_quote_persists_normally(tmp_path, monkeypatch):
    MID, store, mt = _seed_mission(tmp_path, monkeypatch)

    state = {"mission_id": MID}
    result = mt.add_finding_to_mission(
        claim_text="FY2024 net revenue grew approximately 28% per the 10-K MD&A.",
        confidence="REASONED",
        agent_id="calculus",
        workstream_id="W2",
        hypothesis_id="hyp-test",
        source_url="https://sec.gov/snowflake-10k-2024",
        source_quote="Total revenue for fiscal 2024 was $2.81 billion, an increase of 36%.",
        state=state,
    )

    assert result.get("status") != "rejected", result
    assert len(store.list_sources(MID)) == 1
    assert len(store.list_findings(MID)) == 1


def test_mark_milestone_blocked_records_reason(tmp_path, monkeypatch):
    MID, store, mt = _seed_mission(tmp_path, monkeypatch)

    state = {"mission_id": MID}
    out = mt.mark_milestone_blocked(
        milestone_id="W2.1",
        reason="SEC EDGAR returned no filing text for FY2024 10-K",
        state=state,
    )
    assert out["status"] == "blocked"
    assert out["milestone_id"] == "W2.1"

    milestones = store.list_milestones(MID)
    target = next(m for m in milestones if m.id == "W2.1")
    assert target.status == "blocked"
    assert "SEC EDGAR" in (target.result_summary or "")


def test_mark_milestone_blocked_unknown_id(tmp_path, monkeypatch):
    MID, _, mt = _seed_mission(tmp_path, monkeypatch)
    state = {"mission_id": MID}
    out = mt.mark_milestone_blocked(
        milestone_id="W99.99",
        reason="x",
        state=state,
    )
    assert out["status"] == "error"
    assert "unknown" in out["reason"].lower()
