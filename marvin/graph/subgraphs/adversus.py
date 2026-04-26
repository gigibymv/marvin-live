from __future__ import annotations

from marvin.graph.subgraphs.common import build_agent
from marvin.tools.adversus_tools import attack_hypothesis, generate_stress_scenarios, identify_weakest_link, run_ansoff
from marvin.tools.dora_tools import run_pestel
from marvin.tools.mission_tools import add_finding_to_mission

_tools = [
    attack_hypothesis,
    generate_stress_scenarios,
    identify_weakest_link,
    run_ansoff,
    run_pestel,
    add_finding_to_mission,
]
_agent_factory = build_agent("adversus", _tools)


async def adversus_agent_node(state):
    try:
        agent = _agent_factory()
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY is not set" in str(exc):
            return dict(state)
        raise
    return await agent.ainvoke(state)
