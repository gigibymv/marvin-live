from __future__ import annotations

from marvin.graph.subgraphs.common import build_agent
from marvin.tools.mission_tools import get_hypotheses, get_workplan_for_mission

_tools = [
    get_workplan_for_mission,
    get_hypotheses,
]
_agent_factory = build_agent("orchestrator", _tools)


async def orchestrator_agent_node(state):
    try:
        agent = _agent_factory()
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY is not set" in str(exc):
            return dict(state)
        raise
    return await agent.ainvoke(state)
