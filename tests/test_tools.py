from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from marvin.mission.schema import Finding, Gate, Hypothesis, MerlinVerdict, Mission, MissionBrief, Source
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import adversus_tools, arbiter_tools, calculus_tools, dora_tools, merlin_tools, mission_tools, papyrus_tools


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    store = MissionStore(":memory:")
    mission = Mission(
        id="m-test",
        client="Client",
        target="Target",
        ic_question="Is this attractive?",
        status="active",
        created_at=datetime.now(UTC).isoformat(),
    )
    store.save_mission(mission)
    _seed_standard_workplan("m-test", store)
    store.save_hypothesis(Hypothesis(id="h-1", mission_id="m-test", text="Core category is resilient", created_at=datetime.now(UTC).isoformat()))
    store.save_hypothesis(Hypothesis(id="h-2", mission_id="m-test", text="Expansion supports valuation", created_at=datetime.now(UTC).isoformat()))
    now = datetime.now(UTC).isoformat()
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-test",
            raw_brief="Assess market resilience and expansion upside.",
            ic_question="Is this attractive?",
            mission_angle="Market position and competitive durability",
            brief_summary="Assess market resilience and expansion upside.",
            workstream_plan_json='[{"id":"W1","label":"Market","focus":"Market resilience"}]',
            created_at=now,
            updated_at=now,
        )
    )

    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: store)
    monkeypatch.setattr(dora_tools, "_STORE_FACTORY", lambda: store)
    monkeypatch.setattr(adversus_tools, "_STORE_FACTORY", lambda: store)
    monkeypatch.setattr(merlin_tools, "_STORE_FACTORY", lambda: store)
    monkeypatch.setattr(papyrus_tools, "_STORE_FACTORY", lambda: store)
    monkeypatch.setattr(arbiter_tools, "_STORE_FACTORY", lambda: store)
    monkeypatch.setattr(papyrus_tools, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(papyrus_tools, "_papyrus_llm_generate", _stub_papyrus_llm_generate)
    yield store
    store.close()


def _stub_papyrus_llm_generate(
    deliverable_type, mission, hypotheses, findings, mission_brief=None, extra=None,
):
    """Test stub for the Papyrus LLM helper. Returns a deterministic body
    that satisfies new-mode validation (structural markers, no internal IDs)."""
    if deliverable_type == "engagement_brief":
        hyp_block = "\n\n".join(
            f"**H{i + 1} — {h.text[:48].rstrip('.')}**.\n\n{h.text}"
            for i, h in enumerate(hypotheses)
        )
        return (
            f"# Engagement Brief — {mission.target}\n\n"
            f"**Client:** {mission.client}\n"
            f"**Target:** {mission.target}\n"
            f"**Date:** 2026-04-28\n\n"
            f"## IC Question\n\n{mission.ic_question}\n\n"
            f"## Context\n\n"
            "This diligence frames the binding constraints on the investment thesis "
            "and sets the testable hypotheses ahead of any field research.\n\n"
            f"## Hypotheses to Test\n\n{hyp_block}\n\n"
            "## Workstream Plan\n\n"
            "- **W1 Market analysis** — Tests H1 through market evidence.\n\n"
            "## Validation Focus\n\n"
            "Gate G1 should validate that these hypotheses capture the binding "
            "risks before research begins.\n"
        )
    if deliverable_type == "exec_summary":
        verdict = (extra or {}).get("verdict")
        verdict_label = verdict.verdict if verdict else "MINOR_FIXES"
        finding_block = "\n\n".join(
            f"**{i + 1}. {f.claim_text[:64].rstrip('.')}.**\n\n"
            f"{f.claim_text} Confidence: {f.confidence}."
            for i, f in enumerate(findings[:5])
        ) or "No findings provided in context."
        body = (
            f"# Executive Summary — {mission.target}\n\n"
            f"**Mission:** {mission.client} — {mission.target}\n"
            f"**Verdict:** {verdict_label}\n"
            f"**Date:** 2026-04-28\n\n"
            "## Headline\n\n"
            f"Verdict {verdict_label}. The diligence dossier reflects the "
            "current evidence base.\n\n"
            f"## Key Findings\n\n{finding_block}\n\n"
            "## Verdict Reasoning\n\n"
            "Synthesis of the evidence and weakest-link analysis above.\n\n"
            "## Recommendation\n\nProceed to next gate.\n"
        )
        return body
    if deliverable_type == "data_book":
        n = len(hypotheses) or 1
        hyp_sections = "\n\n".join(
            f"## H{i + 1} — {h.text[:48].rstrip('.')}\n\n"
            "| Claim | Confidence | Source | Workstream |\n"
            "|-------|-----------|--------|------------|\n"
            + "\n".join(
                f"| {f.claim_text[:60]}. | {f.confidence} | inference | {f.workstream_id or 'W1'} |"
                for f in findings
                if (f.hypothesis_id or "") == h.id
            )
            + ("\n| No findings for this hypothesis. | — | — | — |" if not any((f.hypothesis_id or "") == h.id for f in findings) else "")
            + f"\n\n**Coverage gap:** Primary evidence not yet sourced for H{i + 1}."
            for i, h in enumerate(hypotheses)
        ) or (
            "## H1 — Evidence\n\n"
            "| Claim | Confidence | Source | Workstream |\n"
            "|-------|-----------|--------|------------|\n"
            "| Sample finding. | REASONED | inference | W1 |\n\n"
            "**Coverage gap:** No hypotheses registered.\n"
        )
        return (
            f"# Data Book — {mission.client} CDD\n\n"
            f"**Mission:** {mission.client} — {mission.target}\n"
            f"**Date:** 2026-04-28\n"
            f"**Status:** Evidence registered for hypotheses H1 through H{n}. "
            "Primary-source coverage gaps flagged below.\n\n"
            f"{hyp_sections}\n\n"
            "## Evidence Quality Summary\n\n"
            f"- Total findings: {len(findings)}\n"
            "- KNOWN (primary-sourced): 0\n"
            f"- REASONED (logical inference): {len(findings)}\n"
            "- LOW_CONFIDENCE (estimates): 0\n"
            "- Adversus red-team challenges: 0\n\n"
            "Evidence is predominantly inference-based. IC defensibility is limited "
            "without primary data.\n"
        )
    if deliverable_type == "workstream_report":
        ws_id = (extra or {}).get("workstream_id", "W?")
        hyp_labels = ", ".join(
            f"H{i + 1}"
            for i, h in enumerate(hypotheses)
            if any((f.hypothesis_id or "") == h.id for f in findings)
        ) or "H1"
        finding_paras = "\n\n".join(
            f"### {f.claim_text[:52].rstrip('.')} (testing {hyp_labels})\n\n"
            f"{f.claim_text} Confidence: {f.confidence}."
            for f in findings[:4]
        ) or "No findings available for this workstream."
        return (
            f"# Workstream Report — {ws_id}\n\n"
            f"**Mission:** {mission.client} — {mission.target}\n"
            f"**Workstream:** {ws_id}\n"
            f"**Hypotheses tested:** {hyp_labels}\n"
            f"**Date:** 2026-04-28\n\n"
            "## Scope\n\n"
            f"This workstream tests {hyp_labels} through evidence gathered in {ws_id}.\n\n"
            f"## Findings\n\n{finding_paras}\n\n"
            "## Coverage Gaps\n\n"
            "No primary-source data has been secured. Further evidence required.\n\n"
            "## Manager Review Note\n\n"
            "Review the findings above before advancing to the next gate.\n"
        )
    raise NotImplementedError(f"stub does not yet handle {deliverable_type}")


@pytest.fixture
def state() -> dict[str, str]:
    return {"mission_id": "m-test"}


def test_create_cdd_mission_creates_mission_and_seed(monkeypatch: pytest.MonkeyPatch):
    store = MissionStore(":memory:")
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: store)
    result = mission_tools.create_cdd_mission("Client", "Target Co", "Why now?")
    mission_id = result.update["mission_id"]
    assert mission_id.startswith("m-target-co-")
    assert len(store.list_workstreams(mission_id)) == 4
    assert len(store.list_gates(mission_id)) == 3
    store.close()


def test_get_workplan_for_mission_returns_seeded_rows(store: MissionStore, state: dict[str, str]):
    result = mission_tools.get_workplan_for_mission(state)
    assert len(result["workstreams"]) == 4
    assert len(result["gates"]) == 3


def test_persist_framing_from_brief_records_brief_and_ic_question(monkeypatch: pytest.MonkeyPatch):
    store = MissionStore(":memory:")
    store.save_mission(Mission(id="m-blank", client="Client", target="Target", ic_question=""))
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: store)
    brief = mission_tools.persist_framing_from_brief(
        "m-blank",
        "Can Target sustain pricing power? Focus on retention, moat, and concentration.",
    )

    assert brief.ic_question == "Can Target sustain pricing power?"
    assert "retention" in brief.raw_brief
    assert store.get_mission("m-blank").ic_question == "Can Target sustain pricing power?"
    store.close()


def test_structured_brief_uses_investment_question_section(monkeypatch: pytest.MonkeyPatch):
    store = MissionStore(":memory:")
    store.save_mission(Mission(id="m-structured", client="CDD", target="Nvidia", ic_question=""))
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: store)

    brief = mission_tools.persist_framing_from_brief(
        "m-structured",
        """
        [1] CLIENT AND CONTEXT
        "CDD"
        [2] TARGET
        "Target: Nvidia, semiconductors / AI infrastructure, global"
        [3] DEAL ECONOMICS
        "EUR1.5-2Tn implied valuation, ~$60Bn revenue FY2024, ~45-50% net margin"
        [4] COMPETITIVE LANDSCAPE
        "Main competitors: AMD, Intel, Google (TPUs), custom AI chips"
        [5] INVESTMENT QUESTION
        "IC question: Is Nvidia's dominance in AI infrastructure sustainable, or will hyperscalers vertically integrate and erode its moat?"
        """,
    )

    assert brief.ic_question == (
        "Is Nvidia's dominance in AI infrastructure sustainable, or will "
        "hyperscalers vertically integrate and erode its moat?"
    )
    assert "Main competitors" not in brief.ic_question
    assert store.get_mission("m-structured").ic_question == brief.ic_question
    store.close()


def test_get_hypotheses_returns_current_hypotheses(store: MissionStore, state: dict[str, str]):
    result = mission_tools.get_hypotheses(state)
    assert len(result["hypotheses"]) == 2
    assert result["hypotheses"][0]["id"] == "h-1"


def test_add_hypothesis_to_mission_writes_to_store(store: MissionStore, state: dict[str, str]):
    result = mission_tools.add_hypothesis_to_mission("Unit economics improve with scale", state)
    assert result["status"] == "saved"
    assert len(store.list_hypotheses("m-test")) == 3


def test_update_hypothesis_changes_status(store: MissionStore, state: dict[str, str]):
    result = mission_tools.update_hypothesis("h-1", "validated", state=state)
    assert result["status"] == "validated"
    assert store.list_hypotheses("m-test", status="validated")[0].id == "h-1"


def _seed_w1_finding(store: MissionStore) -> str:
    """Phase 3 (Fix D): mark_milestone_delivered now requires a finding_id.
    Tests that exercise the tool seed a W1-scoped finding to anchor against.
    """
    from marvin.mission.schema import Finding

    fid = "f-tool-test"
    store.save_finding(
        Finding(
            id=fid,
            mission_id="m-test",
            workstream_id="W1",
            hypothesis_id="h-1",
            claim_text="anchor finding",
            confidence="REASONED",
            agent_id="dora",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    return fid


def test_mark_milestone_delivered_updates_store(store: MissionStore, state: dict[str, str]):
    fid = _seed_w1_finding(store)
    result = mission_tools.mark_milestone_delivered("W1.1", "Delivered", fid, state)
    assert result["status"] == "delivered"
    assert any(m.id == "W1.1" and m.status == "delivered" for m in store.list_milestones("m-test"))


def test_mark_milestone_delivered_recovers_id_from_label_noise(
    store: MissionStore,
    state: dict[str, str],
):
    fid = _seed_w1_finding(store)
    result = mission_tools.mark_milestone_delivered(
        "W1 Market & Competitive Analysis (W1.1, W1.2, W1.3)",
        "Delivered",
        fid,
        state,
    )

    assert result["milestone_id"] == "W1.1"
    assert any(m.id == "W1.1" and m.status == "delivered" for m in store.list_milestones("m-test"))


def test_mark_milestone_delivered_returns_error_for_unknown_id(
    store: MissionStore,
    state: dict[str, str],
):
    """Unknown milestone id must return a structured error, not raise.

    Live mission m-uber-eats-...-89fc01f6 crashed mid-Adversus when the
    LLM called mark_milestone_delivered("W4") (the workstream id) instead
    of "W4.1". The uncaught KeyError terminated the graph run before
    Merlin could synthesize.
    """
    fid = _seed_w1_finding(store)
    result = mission_tools.mark_milestone_delivered("W4", "Done", fid, state)

    assert result["status"] == "error"
    assert "W4" in result["reason"]
    assert "valid milestones" in result["reason"].lower()
    # No state mutation: nothing should have been marked delivered
    assert all(
        m.status != "delivered" or m.id.startswith("W1.1")
        for m in store.list_milestones("m-test")
    )


def test_add_finding_to_mission_requires_state():
    with pytest.raises(KeyError, match="mission_id not in state"):
        mission_tools.add_finding_to_mission("Claim", "REASONED", "dora", state=None)


def test_add_finding_to_mission_persists_row(store: MissionStore, state: dict[str, str]):
    result = mission_tools.add_finding_to_mission("Market is large and growing in priority segments.", "REASONED", "dora", workstream_id="W1", hypothesis_id="h-1", state=state)
    assert result["finding_id"].startswith("f-")
    assert store.list_findings("m-test")[0].claim_text == "Market is large and growing in priority segments."


def test_add_finding_to_mission_return_includes_claim_and_confidence_for_sse(
    store: MissionStore, state: dict[str, str]
):
    """Phase 1A: streamer reads claim + confidence from tool return to build finding_added event."""
    result = mission_tools.add_finding_to_mission(
        "Penetration is 34% across the priority segments.", "LOW_CONFIDENCE", "dora", workstream_id="W1", hypothesis_id="h-1", state=state
    )
    assert result["claim"] == "Penetration is 34% across the priority segments."
    assert result["confidence"] == "LOW_CONFIDENCE"


def test_mark_milestone_delivered_return_includes_label_for_sse(
    store: MissionStore, state: dict[str, str]
):
    """Phase 1A: streamer reads label from tool return to build milestone_done event."""
    fid = _seed_w1_finding(store)
    result = mission_tools.mark_milestone_delivered("W1.1", "Done", fid, state)
    assert result["milestone_id"] == "W1.1"
    # label is the milestone's seeded label, sourced from the post-update store row
    assert isinstance(result.get("label"), str) and result["label"]


def test_papyrus_returns_include_deliverable_id_and_type_for_sse(
    store: MissionStore, state: dict[str, str]
):
    """Phase 1A: streamer reads deliverable_id + deliverable_type to build deliverable_ready event."""
    mission_tools.add_finding_to_mission(
        "Market evidence is sufficient for a workstream report",
        "REASONED",
        "dora",
        workstream_id="W1",
        hypothesis_id="h-1",
        state=state,
    )
    brief = papyrus_tools.generate_engagement_brief(state)
    assert brief["deliverable_id"] == f"deliverable-m-test-engagement-brief"
    assert brief["deliverable_type"] == "engagement_brief"

    ws_report = papyrus_tools.generate_workstream_report("W1", state)
    assert ws_report["deliverable_id"] == f"deliverable-m-test-w1-report"
    assert ws_report["deliverable_type"] == "workstream_report"

    summary = papyrus_tools.generate_exec_summary(state)
    assert summary["deliverable_id"] == f"deliverable-m-test-exec-summary"
    assert summary["deliverable_type"] == "exec_summary"

    data_book = papyrus_tools.generate_data_book(state)
    assert data_book["deliverable_id"] == f"deliverable-m-test-data-book"
    assert data_book["deliverable_type"] == "data_book"


def test_persist_source_for_mission_writes_row(store: MissionStore, state: dict[str, str]):
    result = mission_tools.persist_source_for_mission("https://example.com", "Quoted", state)
    assert result["source_id"].startswith("s-")
    assert store.list_sources("m-test")[0].quote == "Quoted"


def test_ask_question_returns_pending_payload(state: dict[str, str]):
    result = mission_tools.ask_question("Need customer evidence", True, state)
    assert result["blocking"] is True
    assert result["status"] == "pending"


def test_set_and_check_merlin_verdict(store: MissionStore, state: dict[str, str]):
    saved = mission_tools.set_merlin_verdict("SHIP", "Looks good", state)
    assert saved["verdict"] == "SHIP"
    checked = mission_tools.check_merlin_verdict(state)
    assert checked["verdict"] == "SHIP"


def test_set_merlin_verdict_is_idempotent_for_same_pass(store: MissionStore, state: dict[str, str]):
    first = mission_tools.set_merlin_verdict("BACK_TO_DRAWING_BOARD", "Need stronger sourcing.", state)
    second = mission_tools.set_merlin_verdict("BACK_TO_DRAWING_BOARD", "Need stronger sourcing.", state)

    assert second["verdict_id"] == first["verdict_id"]
    assert second["deduped"] is True
    verdict_rows = store._execute(  # noqa: SLF001 - test asserts persistence contract
        "SELECT COUNT(*) AS count FROM merlin_verdicts WHERE mission_id = ?",
        ("m-test",),
    ).fetchone()
    assert verdict_rows["count"] == 1
    merlin_findings = [f for f in store.list_findings("m-test") if f.agent_id == "merlin"]
    assert len(merlin_findings) == 1


def test_generate_interview_guides_returns_hypothesis_guides(store: MissionStore, state: dict[str, str]):
    result = mission_tools.generate_interview_guides(["h-1"], state)
    assert result["guides"][0]["hypothesis_id"] == "h-1"
    assert len(result["guides"][0]["questions"]) == 3


def test_generate_hypotheses_inline_uses_brief_context(store: MissionStore):
    for hypothesis in store.list_hypotheses("m-test"):
        store.update_hypothesis(hypothesis.id, "abandoned", "reset for test")

    hypotheses = mission_tools._generate_hypotheses_inline(
        "m-test",
        "Focus on pricing power, retention, and whether unit economics can scale.",
    )

    texts = " ".join(h.text for h in hypotheses).lower()
    assert "pricing power" in texts
    assert "unit economics" in texts or "financial quality" in texts


def test_tavily_search_returns_empty_when_api_key_missing(monkeypatch):
    """tavily_search no longer returns hardcoded example.com stubs. Without
    an API key it returns empty results plus a clear error code so the LLM
    can fall back to REASONED findings rather than fabricate KNOWN ones.
    Live HTTP behaviour is covered in tests/test_dora_tools.py."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    result = dora_tools.tavily_search("vinted resale")
    assert result["provider"] == "tavily"
    assert result["results"] == []
    assert result["error"] == "no_api_key"


def test_build_bottom_up_tam_computes_and_persists(store: MissionStore, state: dict[str, str]):
    result = dora_tools.build_bottom_up_tam(1000, 0.2, 500.0, state, hypothesis_id="h-1")
    assert result["tam"] == 100000.0
    assert any("Bottom-up TAM estimate" in finding.claim_text for finding in store.list_findings("m-test"))


def test_analyze_market_data_summarizes_segments(store: MissionStore, state: dict[str, str]):
    result = dora_tools.analyze_market_data(
        {"segments": [{"revenue": 100, "growth_rate": 0.1}, {"revenue": 50, "growth_rate": 0.2}]},
        state,
    )
    assert result["total_revenue"] == 150
    assert result["avg_growth_rate"] == pytest.approx(0.15)


def test_run_pestel_returns_all_categories(state: dict[str, str]):
    result = dora_tools.run_pestel("Vinted", "resale", state)
    assert sorted(result["analysis"].keys()) == ["economic", "environmental", "legal", "political", "social", "technological"]


def test_search_company_returns_summary():
    result = dora_tools.search_company("Vinted")
    assert result["company_name"] == "Vinted"
    assert "profile" in result["summary"]


def test_get_recent_filings_returns_stub_list():
    result = dora_tools.get_recent_filings("Vinted", "annual report")
    assert result["filings"][0]["title"].startswith("Vinted")


def test_moat_analysis_persists_hypothesis_finding(store: MissionStore, state: dict[str, str]):
    result = dora_tools.moat_analysis("Vinted", "h-1", state)
    assert result["hypothesis_id"] == "h-1"
    assert any(f.hypothesis_id == "h-1" for f in store.list_findings("m-test"))


def test_win_loss_framework_counts_outcomes(store: MissionStore, state: dict[str, str]):
    result = dora_tools.win_loss_framework({"interviews": [{"outcome": "win"}, {"outcome": "loss"}, {"outcome": "win"}]}, state)
    assert result["wins"] == 2
    assert result["losses"] == 1


def test_parse_data_room_reads_file(tmp_path: Path):
    file_path = tmp_path / "room.txt"
    file_path.write_text("line1\nline2\n", encoding="utf-8")
    result = calculus_tools.parse_data_room(str(file_path))
    assert result["exists"] is True
    assert result["line_count"] == 2


def test_quality_of_earnings_computes_adjusted_ebitda(store: MissionStore, state: dict[str, str]):
    result = calculus_tools.quality_of_earnings({"revenue": 1000, "cogs": 300, "opex": 400, "add_backs": 50}, state, hypothesis_id="h-1")
    assert result["adjusted_ebitda"] == 350
    assert result["missing_inputs"] == []
    assert any("Adjusted EBITDA" in finding.claim_text for finding in store.list_findings("m-test"))


def test_quality_of_earnings_tolerates_null_inputs(store: MissionStore, state: dict[str, str]):
    # LLM-supplied JSON with explicit nulls used to crash the tool with
    # "TypeError: unsupported operand type(s) for -: 'int' and 'NoneType'".
    result = calculus_tools.quality_of_earnings(
        {"revenue": 813_000_000, "cogs": None, "opex": None, "add_backs": None},
        state,
        hypothesis_id="h-1",
    )
    assert result["revenue"] == 813_000_000
    assert result["cogs"] == 0
    assert result["adjusted_ebitda"] == 813_000_000
    assert set(result["missing_inputs"]) == {"cogs", "opex", "add_backs"}
    finding_texts = [f.claim_text for f in store.list_findings("m-test")]
    assert any("missing inputs" in text for text in finding_texts)


def test_quality_of_earnings_tolerates_missing_keys_and_strings(store: MissionStore, state: dict[str, str]):
    # Missing keys and non-numeric strings must be treated like None: zeroed
    # and surfaced via missing_inputs, not silently coerced.
    result = calculus_tools.quality_of_earnings(
        {"revenue": "1000", "cogs": "n/a"},
        state,
    )
    assert result["revenue"] == 1000.0
    assert result["cogs"] == 0
    assert result["adjusted_ebitda"] == 1000.0
    assert "cogs" in result["missing_inputs"]
    assert "opex" in result["missing_inputs"]
    assert "add_backs" in result["missing_inputs"]


def test_cohort_analysis_computes_average_retention(store: MissionStore, state: dict[str, str]):
    result = calculus_tools.cohort_analysis({"cohorts": [{"month_0": 100, "month_3": 80}, {"month_0": 50, "month_3": 35}]}, state)
    assert result["average_m3_retention"] == pytest.approx(0.75)


def test_compute_cac_ltv_returns_ratio(store: MissionStore, state: dict[str, str]):
    result = calculus_tools.compute_cac_ltv({"sales_spend": 1000, "new_customers": 10, "gross_margin": 0.8, "arpu": 50, "monthly_churn": 0.1}, state)
    assert result["cac"] == 100
    assert result["ltv_to_cac"] == pytest.approx(4.0)


def test_concentration_analysis_reports_top_customer_share(store: MissionStore, state: dict[str, str]):
    result = calculus_tools.concentration_analysis({"customers": [{"revenue": 60}, {"revenue": 40}]}, state)
    assert result["top_customer_share"] == pytest.approx(0.6)


def test_concentration_analysis_tolerates_null_customers(store: MissionStore, state: dict[str, str]):
    # LLM-supplied JSON with `customers: null` used to crash with
    # "TypeError: 'NoneType' object is not iterable".
    result = calculus_tools.concentration_analysis({"customers": None}, state)
    assert result["customer_count"] == 0
    assert result["total_revenue"] == 0
    assert result["top_customer_share"] == 0
    assert result["top_10_concentration"] == 0


def test_anomaly_detector_flags_mismatches_and_persists_known(store: MissionStore, state: dict[str, str]):
    result = calculus_tools.anomaly_detector({"revenue": 100, "margin": 0.2}, {"revenue": 90, "margin": 0.2}, state, hypothesis_id="h-1")
    assert result["count"] == 1
    assert any(f.agent_id == "calculus" and f.confidence == "KNOWN" for f in store.list_findings("m-test"))


def test_search_sec_filings_unknown_company_returns_no_filings(monkeypatch):
    # When EDGAR can't resolve the target, the tool must return an explicit
    # error and an empty filings list — never a fabricated stub URL.
    import marvin.tools.edgar_client as ec
    ec._TICKER_CACHE = {}  # force "not found" without HTTP
    result = calculus_tools.search_sec_filings("Acme-not-public", 2024)
    assert result["filings"] == []
    assert result.get("error") == "company_not_found_on_edgar"
    ec._TICKER_CACHE = None


def test_attack_hypothesis_persists_redteam_finding(store: MissionStore, state: dict[str, str]):
    result = adversus_tools.attack_hypothesis("h-1", "empirical", state)
    assert result["angle"] == "empirical"
    assert any(f.agent_id == "adversus" for f in store.list_findings("m-test"))


def test_attack_hypothesis_returns_cap_status_without_crashing(store: MissionStore, state: dict[str, str]):
    cap = mission_tools.MAX_FINDINGS_PER_AGENT_PER_MISSION["adversus"]
    for i in range(cap):
        mission_tools.add_finding_to_mission(
            claim_text=f"Existing adversus attack {i} with enough distinct detail.",
            confidence="REASONED",
            agent_id="adversus",
            workstream_id="W4",
            hypothesis_id="h-1",
            state=state,
        )

    result = adversus_tools.attack_hypothesis("h-1", "empirical", state)

    assert result["status"] == "cap_reached"
    assert result["finding_id"] is None
    assert result["agent_id"] == "adversus"
    assert result["existing"] == cap
    assert len(
        [finding for finding in store.list_findings("m-test") if finding.agent_id == "adversus"]
    ) == cap


def test_generate_stress_scenarios_returns_three_items(state: dict[str, str]):
    result = adversus_tools.generate_stress_scenarios(state=state)
    assert len(result["scenarios"]) == 3


def test_identify_weakest_link_uses_lowest_evidence_count(store: MissionStore, state: dict[str, str]):
    mission_tools.add_finding_to_mission("Supports h1 with sustained evidence base.", "REASONED", "dora", hypothesis_id="h-1", state=state)
    result = adversus_tools.identify_weakest_link(state)
    assert result["weakest_link"] == "h-2"


def test_run_ansoff_returns_four_quadrants(state: dict[str, str]):
    result = adversus_tools.run_ansoff("Vinted", state)
    assert len(result["matrix"]) == 4


def test_check_mece_detects_duplicates(state: dict[str, str]):
    result = merlin_tools.check_mece({"sections": [{"title": "Market", "claims": [1]}, {"title": "Market", "claims": [2]}]}, state)
    assert result["is_mece"] is False
    assert result["duplicates"] == ["market"]


def test_update_action_title_returns_updated_payload(state: dict[str, str]):
    result = merlin_tools.update_action_title("slide-1", "Stronger takeaway", state)
    assert result["status"] == "updated"


def test_get_storyline_findings_groups_by_workstream(store: MissionStore, state: dict[str, str]):
    mission_tools.add_finding_to_mission("W1 market claim about competitive moat.", "REASONED", "dora", workstream_id="W1", hypothesis_id="h-1", state=state)
    result = merlin_tools.get_storyline_findings(state)
    assert "W1" in result["findings_by_workstream"]


def test_generate_engagement_brief_is_idempotent(store: MissionStore, state: dict[str, str]):
    first = papyrus_tools.generate_engagement_brief(state)
    second = papyrus_tools.generate_engagement_brief(state)
    assert first["status"] == "generated"
    assert second["status"] == "skipped"
    assert Path(first["file_path"]).is_absolute()
    assert len(store.list_deliverables("m-test")) == 1
    body = Path(first["file_path"]).read_text(encoding="utf-8")
    # New-mode (LLM) format: structural markers present, NO internal IDs.
    assert "## IC Question" in body
    assert "## Hypotheses to Test" in body
    assert "hyp-" not in body
    assert "Hypothesis ID:" not in body


def test_generate_workstream_report_writes_markdown(store: MissionStore, state: dict[str, str]):
    mission_tools.add_finding_to_mission("Market is growing with healthy retention metrics.", "REASONED", "dora", workstream_id="W1", hypothesis_id="h-1", state=state)
    result = papyrus_tools.generate_workstream_report("W1", state)
    body = Path(result["file_path"]).read_text(encoding="utf-8")
    assert "# Workstream Report" in body
    assert "## Findings" in body
    assert "## Coverage Gaps" in body


def test_generate_report_pdf_requires_ship_or_g3(store: MissionStore, state: dict[str, str]):
    with pytest.raises(ValueError, match="requires SHIP verdict or completed G3 gate"):
        papyrus_tools.generate_report_pdf(state)
    store.update_gate_status(f"gate-m-test-G3", "completed", notes="Approved")
    result = papyrus_tools.generate_report_pdf(state)
    assert result["status"] == "blocked"
    assert result["deliverable_type"] == "report_pdf"
    assert not any(d.deliverable_type == "report_pdf" for d in store.list_deliverables("m-test"))


def test_generate_exec_summary_and_data_book_write_non_empty_files(store: MissionStore, state: dict[str, str]):
    mission_tools.add_finding_to_mission("Claim 1 about market with sourced evidence.", "REASONED", "dora", workstream_id="W1", hypothesis_id="h-1", state=state)
    summary = papyrus_tools.generate_exec_summary(state)
    data_book = papyrus_tools.generate_data_book(state)
    assert Path(summary["file_path"]).stat().st_size > 0
    assert Path(data_book["file_path"]).stat().st_size > 0


def test_papyrus_context_uses_consultant_verdict_labels(store: MissionStore):
    mission = store.get_mission("m-test")
    hypotheses = store.list_hypotheses("m-test")
    brief = store.get_mission_brief("m-test")
    verdict = MerlinVerdict(
        id="mv-test",
        mission_id="m-test",
        verdict="BACK_TO_DRAWING_BOARD",
        notes="Primary financial evidence is missing.",
        created_at=datetime.now(UTC).isoformat(),
    )

    prompt = papyrus_tools._build_papyrus_context(
        "exec_summary",
        mission,
        hypotheses,
        [],
        brief,
        extra={"verdict": verdict},
    )

    assert "Evidence gaps" in prompt
    assert "Run targeted follow-up diligence" in prompt
    assert "BACK_TO_DRAWING_BOARD" not in prompt


def test_papyrus_markdown_sanitizer_removes_internal_verdict_enums():
    body = (
        "# Executive Summary — Uber\n\n"
        "**Verdict:** BACK_TO_DRAWING_BOARD\n\n"
        "The alternative is MINOR_FIXES, not SHIP.\n"
        "# Data Book — CDD cdd\n"
    )

    sanitized = papyrus_tools._sanitize_user_facing_markdown(body)

    assert "BACK_TO_DRAWING_BOARD" not in sanitized
    assert "MINOR_FIXES" not in sanitized
    assert "SHIP" not in sanitized
    assert "Evidence gaps" in sanitized
    assert "Additional diligence needed" in sanitized
    assert "Ready to present" in sanitized
    assert "CDD cdd" not in sanitized


def test_check_internal_consistency_flags_missing_source_and_stale_source(store: MissionStore):
    stale_time = (datetime.now(UTC) - timedelta(days=600)).isoformat()
    store.save_source(Source(id="s-old", mission_id="m-test", url_or_ref="old", quote="old", retrieved_at=stale_time))
    store.save_finding(
        Finding(
            id="f-known",
            mission_id="m-test",
            claim_text="Revenue growth accelerated",
            confidence="KNOWN",
            source_id="s-old",
            agent_id="dora",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    original_list_findings = store.list_findings

    def list_findings_with_bad_known(mission_id: str):
        rows = original_list_findings(mission_id)
        rows.append(
            Finding.model_construct(
                id="f-bad",
                mission_id="m-test",
                claim_text="GMV expanded",
                confidence="KNOWN",
                source_id=None,
                agent_id="dora",
                human_validated=False,
                created_at=datetime.now(UTC).isoformat(),
                workstream_id=None,
                hypothesis_id=None,
            )
        )
        return rows

    store.list_findings = list_findings_with_bad_known  # type: ignore[method-assign]
    result = arbiter_tools.check_internal_consistency("m-test")
    assert any(item["type"] == "missing_source" for item in result["inconsistencies"])
    assert any(flag["type"] == "stale_source" for flag in result["flags"])


def test_check_internal_consistency_flags_contradictions(store: MissionStore):
    store.save_source(Source(id="s-1", mission_id="m-test", url_or_ref="a", quote="a", retrieved_at=datetime.now(UTC).isoformat()))
    store.save_source(Source(id="s-2", mission_id="m-test", url_or_ref="b", quote="b", retrieved_at=datetime.now(UTC).isoformat()))
    store.save_finding(Finding(id="f-1", mission_id="m-test", claim_text="Share is 20%", confidence="KNOWN", source_id="s-1", agent_id="dora"))
    store.save_finding(Finding(id="f-2", mission_id="m-test", claim_text="Share is 20%", confidence="REASONED", source_id="s-2", agent_id="dora"))
    result = arbiter_tools.check_internal_consistency("m-test")
    assert any(item["type"] == "contradiction" for item in result["inconsistencies"])


def test_tools_accept_json_strings(store: MissionStore, state: dict[str, str]):
    market_result = dora_tools.analyze_market_data(json.dumps({"segments": [{"revenue": 10, "growth_rate": 0.1}]}), state)
    cohort_result = calculus_tools.cohort_analysis(json.dumps({"cohorts": [{"month_0": 10, "month_3": 5}]}), state)
    assert market_result["total_revenue"] == 10
    assert cohort_result["cohort_count"] == 1
