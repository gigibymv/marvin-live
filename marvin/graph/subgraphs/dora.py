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
from marvin.tools.mission_tools import add_finding_to_mission, add_source_to_finding, mark_milestone_delivered, persist_source_for_mission

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
    add_source_to_finding,
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
    # C-CONV: drain any pending user steering and surface it to the
    # agent before it picks up the task brief.
    from marvin.conversational.steering import apply_pending_steering
    extra = apply_pending_steering(state.get("mission_id", ""))
    if extra:
        state = {**state, "messages": list(state.get("messages", [])) + extra}
    return await agent.ainvoke(state)
