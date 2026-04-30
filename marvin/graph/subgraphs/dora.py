from __future__ import annotations

from marvin.graph.subgraphs.common import build_agent
from marvin.tools.dora_tools import (
    analyze_market_data,
    build_bottom_up_tam,
    get_recent_filings,
    moat_analysis,
    run_pestel,
    search_company,
    tavily_search,
    win_loss_framework,
)
from marvin.tools.data_room_tools import query_data_room, query_transcripts
from marvin.tools.mission_tools import add_finding_to_mission, mark_milestone_delivered, persist_source_for_mission

_tools = [
    tavily_search,
    build_bottom_up_tam,
    analyze_market_data,
    run_pestel,
    search_company,
    get_recent_filings,
    moat_analysis,
    win_loss_framework,
    query_data_room,
    query_transcripts,
    add_finding_to_mission,
    persist_source_for_mission,
    mark_milestone_delivered,
]
_agent_factory = build_agent("dora", _tools)


async def dora_agent_node(state):
    try:
        agent = _agent_factory()
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY is not set" in str(exc):
            return dict(state)
        raise
    return await agent.ainvoke(state)
