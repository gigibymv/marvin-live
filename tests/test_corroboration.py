"""Wiring tests for C4 — source corroboration gate.

Covers:
  - extract_domain handles http/https + special schemes (data_room://, transcript://)
  - independent_source_count groups by (domain, source_type)
  - evaluate_corroboration downgrades KNOWN with <2 independent sources
  - add_source_to_finding tool: persists, updates corroboration, downgrades
  - recompute_mission_corroboration: scans all findings, updates statuses
"""
from __future__ import annotations

import importlib

import pytest


def test_extract_domain_strips_www():
    from marvin.quality.corroboration import extract_domain
    assert extract_domain("https://www.cnbc.com/article/foo") == "cnbc.com"
    assert extract_domain("https://sec.gov/path") == "sec.gov"
    assert extract_domain("http://example.org") == "example.org"


def test_extract_domain_special_schemes():
    from marvin.quality.corroboration import extract_domain
    assert extract_domain("data_room://dr-abc#L42") == "data_room"
    assert extract_domain("transcript://tx-xyz:1-3") == "transcript"


def test_independent_count_groups_by_domain_and_type():
    from marvin.mission.schema import Source
    from marvin.quality.corroboration import independent_source_count

    s1 = Source(id="s1", mission_id="m1",
                url_or_ref="https://sec.gov/a", source_type="sec_filing")
    s2 = Source(id="s2", mission_id="m1",
                url_or_ref="https://sec.gov/b", source_type="sec_filing")
    s3 = Source(id="s3", mission_id="m1",
                url_or_ref="https://www.cnbc.com/x", source_type="web")
    # s1 + s2: same (sec.gov, sec_filing) → 1 group
    assert independent_source_count([s1, s2]) == 1
    # s1 + s3: distinct (sec.gov, sec_filing) and (cnbc.com, web) → 2 groups
    assert independent_source_count([s1, s3]) == 2
    # all three → still 2 groups
    assert independent_source_count([s1, s2, s3]) == 2


def test_evaluate_known_with_single_source_downgrades():
    from marvin.mission.schema import Source
    from marvin.quality.corroboration import evaluate_corroboration
    s = Source(id="s1", mission_id="m1",
               url_or_ref="https://sec.gov/a", source_type="sec_filing")
    out = evaluate_corroboration("KNOWN", [s])
    assert out.final_confidence == "REASONED"
    assert out.status == "downgraded"
    assert out.independent_count == 1


def test_evaluate_known_with_two_independent_keeps_known():
    from marvin.mission.schema import Source
    from marvin.quality.corroboration import evaluate_corroboration
    s1 = Source(id="s1", mission_id="m1",
                url_or_ref="https://sec.gov/a", source_type="sec_filing")
    s2 = Source(id="s2", mission_id="m1",
                url_or_ref="https://www.cnbc.com/b", source_type="web")
    out = evaluate_corroboration("KNOWN", [s1, s2])
    assert out.final_confidence == "KNOWN"
    assert out.status == "corroborated"
    assert out.independent_count == 2


def test_evaluate_reasoned_unchanged():
    from marvin.mission.schema import Source
    from marvin.quality.corroboration import evaluate_corroboration
    s = Source(id="s1", mission_id="m1",
               url_or_ref="https://x.com/a", source_type="web")
    out = evaluate_corroboration("REASONED", [s])
    assert out.final_confidence == "REASONED"
    assert out.status == "single_source"


def _seed(tmp_path, monkeypatch):
    monkeypatch.setenv("MARVIN_DB_PATH", str(tmp_path / "marvin.db"))
    import marvin.mission.store as store_mod
    importlib.reload(store_mod)
    import marvin.tools.mission_tools as mt
    importlib.reload(mt)
    from marvin.mission.schema import (
        Mission as MissionModel, Hypothesis, Workstream, Milestone,
    )
    store = store_mod.MissionStore(str(tmp_path / "marvin.db"))
    store.save_mission(MissionModel(id="m1", client="c", target="t", mission_type="cdd"))
    store.save_workstream(Workstream(id="W2", mission_id="m1", label="Financial",
                                     assigned_agent="calculus"))
    store.save_hypothesis(Hypothesis(id="hyp-1", mission_id="m1", label="H1",
                                     text="hypothesis text long enough" * 3,
                                     status="active"))
    store.save_milestone(Milestone(id="W2.1", mission_id="m1", workstream_id="W2",
                                   label="Public filings review", status="pending"))
    return store, mt


def test_add_finding_then_corroborate_keeps_known(tmp_path, monkeypatch):
    store, mt = _seed(tmp_path, monkeypatch)
    state = {"mission_id": "m1"}
    r = mt.add_finding_to_mission(
        claim_text="Snowflake FY2024 GAAP revenue was $2.81B per the 10-K MD&A.",
        confidence="KNOWN", agent_id="calculus",
        workstream_id="W2", hypothesis_id="hyp-1",
        source_url="https://www.sec.gov/Archives/edgar/data/1640147/abc/snow.htm",
        source_quote="Total revenue for fiscal 2024 was $2.81 billion.",
        state=state,
    )
    assert r["status"] == "saved"
    assert r["corroboration_warning"] is not None
    fid = r["finding_id"]

    r2 = mt.add_source_to_finding(
        finding_id=fid,
        source_url="https://www.cnbc.com/snowflake-earnings",
        source_quote="Snowflake's fiscal 2024 revenue grew 36% to $2.81B.",
        state=state,
    )
    assert r2["status"] == "saved"
    assert r2["corroboration_status"] == "corroborated"
    assert r2["final_confidence"] == "KNOWN"
    assert r2["downgrade_reason"] is None


def test_add_finding_known_with_no_corroboration_recomputed_to_reasoned(
    tmp_path, monkeypatch
):
    store, mt = _seed(tmp_path, monkeypatch)
    state = {"mission_id": "m1"}
    r = mt.add_finding_to_mission(
        claim_text="Snowflake FY2024 revenue $2.81B (10-K consolidated statements).",
        confidence="KNOWN", agent_id="calculus",
        workstream_id="W2", hypothesis_id="hyp-1",
        source_url="https://www.sec.gov/Archives/edgar/data/1640147/abc/snow.htm",
        source_quote="Total revenue for fiscal 2024 was $2.81 billion.",
        state=state,
    )
    assert r["status"] == "saved"
    fid = r["finding_id"]

    out = mt.recompute_mission_corroboration(state=state)
    assert out["downgraded"] == 1
    assert fid in out["downgraded_finding_ids"]

    after = store.get_finding(fid)
    assert after.confidence == "REASONED"
    assert after.corroboration_status == "downgraded"


def test_add_source_rejects_failure_quote(tmp_path, monkeypatch):
    store, mt = _seed(tmp_path, monkeypatch)
    state = {"mission_id": "m1"}
    r = mt.add_finding_to_mission(
        claim_text="Snowflake FY2024 revenue $2.81B per the 10-K.",
        confidence="REASONED", agent_id="calculus",
        workstream_id="W2", hypothesis_id="hyp-1",
        source_url="https://www.sec.gov/Archives/edgar/data/1640147/abc/snow.htm",
        source_quote="Total revenue for fiscal 2024 was $2.81 billion.",
        state=state,
    )
    fid = r["finding_id"]

    bad = mt.add_source_to_finding(
        finding_id=fid,
        source_url="https://example.com/x",
        source_quote="[missing inputs: tool did not return filing text]",
        state=state,
    )
    assert bad["status"] == "rejected"
    assert "retrieval-failure" in bad["reason"].lower()
