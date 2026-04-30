from __future__ import annotations

from marvin.graph.subgraphs.common import build_agent
from marvin.tools.calculus_tools import (
    anomaly_detector,
    cohort_analysis,
    compute_cac_ltv,
    concentration_analysis,
    fetch_filing_section,
    parse_data_room,
    quality_of_earnings,
    search_sec_filings,
)
from marvin.tools.data_room_tools import query_data_room, query_transcripts
from marvin.tools.mission_tools import (
    add_finding_to_mission,
    add_source_to_finding,
    get_hypotheses,
    mark_milestone_blocked,
    mark_milestone_delivered,
    persist_source_for_mission,
)

_tools = [
    get_hypotheses,
    parse_data_room,
    quality_of_earnings,
    cohort_analysis,
    compute_cac_ltv,
    concentration_analysis,
    anomaly_detector,
    search_sec_filings,
    fetch_filing_section,
    query_data_room,
    query_transcripts,
    add_finding_to_mission,
    add_source_to_finding,
    persist_source_for_mission,
    mark_milestone_delivered,
    mark_milestone_blocked,
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
