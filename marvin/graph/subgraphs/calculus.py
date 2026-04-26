from __future__ import annotations

from marvin.graph.subgraphs.common import build_agent
from marvin.tools.calculus_tools import (
    anomaly_detector,
    cohort_analysis,
    compute_cac_ltv,
    concentration_analysis,
    parse_data_room,
    quality_of_earnings,
    search_sec_filings,
)
from marvin.tools.mission_tools import add_finding_to_mission, mark_milestone_delivered, persist_source_for_mission

_tools = [
    parse_data_room,
    quality_of_earnings,
    cohort_analysis,
    compute_cac_ltv,
    concentration_analysis,
    anomaly_detector,
    search_sec_filings,
    add_finding_to_mission,
    persist_source_for_mission,
    mark_milestone_delivered,
]
_agent_factory = build_agent("calculus", _tools)


async def calculus_agent_node(state):
    try:
        agent = _agent_factory()
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY is not set" in str(exc):
            return dict(state)
        raise
    return await agent.ainvoke(state)
