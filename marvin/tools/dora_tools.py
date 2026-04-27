from __future__ import annotations

from statistics import mean
from typing import Any

from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, coerce_jsonish, get_store, require_mission_id
from marvin.tools.mission_tools import add_finding_to_mission

_STORE_FACTORY = MissionStore


def tavily_search(query: str) -> dict[str, Any]:
    """Search the web for market and competitive intelligence on a topic.

    Use when you need exogenous evidence (market sizing, competitor moves,
    sector signals) before forming a finding. Input: a focused search query.
    Returns a provider tag, the query, and a list of result stubs.
    """
    return {
        "provider": "tavily_stub",
        "query": query,
        "results": [
            {"title": f"{query} market overview", "url": "https://example.com/market-overview"},
            {"title": f"{query} competitor landscape", "url": "https://example.com/competitors"},
        ],
    }


def build_bottom_up_tam(
    total_companies: int,
    penetration_rate: float,
    avg_price: float,
    state: InjectedStateArg = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Compute a bottom-up TAM as total_companies * penetration_rate * avg_price.

    Use when sizing an addressable market from per-customer economics rather
    than top-down reports. Required: total_companies (int), penetration_rate
    (0-1), avg_price (per-customer revenue). Persists a finding when state
    carries a mission_id.
    """
    tam = total_companies * penetration_rate * avg_price
    result = {
        "total_companies": total_companies,
        "penetration_rate": penetration_rate,
        "avg_price": avg_price,
        "tam": tam,
    }
    if state is not None and hypothesis_id is not None:
        add_finding_to_mission(
            claim_text=f"Bottom-up TAM estimate is {tam:.2f} based on penetration assumptions.",
            confidence="REASONED",
            agent_id="dora",
            workstream_id="W1",
            hypothesis_id=hypothesis_id,
            state=state,
        )
    return result


def analyze_market_data(
    data_json: Any,
    state: InjectedStateArg = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Aggregate segment-level revenue and growth from a market data payload.

    Use to summarize a multi-segment market description before drawing a
    finding. Input: data_json with a 'segments' list, each entry exposing
    'revenue' and 'growth_rate'. Returns segment count, total revenue, and
    average growth rate; emits a finding when state carries a mission_id.
    """
    payload = coerce_jsonish(data_json)
    segments = payload.get("segments", [])
    total_revenue = sum(segment.get("revenue", 0) for segment in segments)
    avg_growth = mean([segment.get("growth_rate", 0) for segment in segments]) if segments else 0
    result = {"segment_count": len(segments), "total_revenue": total_revenue, "avg_growth_rate": avg_growth}
    if state is not None and hypothesis_id is not None:
        add_finding_to_mission(
            claim_text=f"Market segments total revenue is {total_revenue:.2f} across observed segments.",
            confidence="REASONED",
            agent_id="dora",
            workstream_id="W1",
            hypothesis_id=hypothesis_id,
            state=state,
        )
    return result


def run_pestel(company: str, sector: str, state: InjectedStateArg = None) -> dict[str, Any]:
    """Run a PESTEL (political/economic/social/tech/environmental/legal) scan.

    Use to frame the macro and regulatory context around a target before
    deeper diligence. Required: company name and sector. Requires a
    mission_id in state.
    """
    require_mission_id(state)
    return {
        "company": company,
        "sector": sector,
        "analysis": {
            "political": f"Regulatory scrutiny around {sector}",
            "economic": f"Consumer spending sensitivity for {company}",
            "social": f"Adoption patterns shaping {sector}",
            "technological": "Platform differentiation and automation",
            "environmental": "Sustainability expectations in logistics",
            "legal": "Consumer protection and marketplace compliance",
        },
    }


def search_company(company_name: str) -> dict[str, Any]:
    """Look up a company profile (summary and high-level signals).

    Use as the first step when you need a basic snapshot of a target before
    deeper analysis. Input: company_name.
    """
    return {
        "company_name": company_name,
        "summary": f"{company_name} profile generated from deterministic stub data",
        "signals": ["marketplace", "consumer internet", "Europe"],
    }


def get_recent_filings(company_name: str, filing_type: str) -> dict[str, Any]:
    """Retrieve recent regulatory filings for a company.

    Use to ground claims in primary documents (e.g. annual reports). Required:
    company_name and filing_type (e.g. '10-K', '20-F'). Returns a list of
    filing stubs with title and date.
    """
    return {
        "company_name": company_name,
        "filing_type": filing_type,
        "filings": [
            {"title": f"{company_name} {filing_type} FY2024", "date": "2025-03-31"},
            {"title": f"{company_name} {filing_type} FY2023", "date": "2024-03-31"},
        ],
    }


def moat_analysis(
    company_name: str,
    hypothesis_id: str,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Analyze the competitive moat for a company against a hypothesis.

    Use when testing a hypothesis about durable advantage. Required:
    company_name and hypothesis_id (the hypothesis being evaluated). Returns
    moat drivers and risks; emits a finding tied to the hypothesis when state
    carries a mission_id.
    """
    result = {
        "company_name": company_name,
        "hypothesis_id": hypothesis_id,
        "drivers": ["network effects", "supply liquidity", "brand trust"],
        "risks": ["multi-homing", "category expansion execution"],
    }
    if state is not None:
        add_finding_to_mission(
            claim_text=f"{company_name} moat rests on network effects and supply liquidity",
            confidence="REASONED",
            agent_id="dora",
            workstream_id="W1",
            hypothesis_id=hypothesis_id,
            state=state,
        )
    return result


def win_loss_framework(
    interviews_json: Any,
    state: InjectedStateArg = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Tally wins and losses from a customer interview payload.

    Use to convert raw interview outcomes into a quantitative win/loss
    summary. Input: interviews_json with an 'interviews' list, each entry
    having 'outcome' ('win' or 'loss'). Confidence drops to LOW_CONFIDENCE
    when the sample size is below 5.
    """
    payload = coerce_jsonish(interviews_json)
    interviews = payload.get("interviews", [])
    wins = sum(1 for interview in interviews if interview.get("outcome") == "win")
    losses = sum(1 for interview in interviews if interview.get("outcome") == "loss")
    result = {"wins": wins, "losses": losses, "sample_size": len(interviews)}
    if state is not None and hypothesis_id is not None:
        add_finding_to_mission(
            claim_text=f"Win/loss sample shows {wins} wins and {losses} losses across interviews.",
            confidence="LOW_CONFIDENCE" if len(interviews) < 5 else "REASONED",
            agent_id="dora",
            workstream_id="W1",
            hypothesis_id=hypothesis_id,
            state=state,
        )
    return result
