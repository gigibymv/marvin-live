from __future__ import annotations

from marvin.graph.subgraphs.common import build_agent
from marvin.runtime_debug import log_agent_io
from marvin.tools.mission_tools import set_merlin_verdict

_tools = [
    set_merlin_verdict,
]
_agent_factory = build_agent("merlin", _tools)


async def merlin_agent_node(state):
    try:
        agent = _agent_factory()
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY is not set" in str(exc):
            return dict(state)
        raise
    log_agent_io("merlin", "before_invoke", state)
    # Cap React iterations: Merlin should call set_merlin_verdict ONCE and
    # stop. Without a cap, an LLM that misreads the dedup return signal as
    # failure can loop indefinitely (observed: 70+ OpenRouter calls after a
    # successful verdict persistence). 6 = first tool call + minor retries.
    result = await agent.ainvoke(state, config={"recursion_limit": 6})
    log_agent_io("merlin", "after_invoke", result)
    return result
