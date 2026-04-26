from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langgraph.prebuilt import create_react_agent

from marvin.graph.state import MarvinState
from marvin.llm_factory import get_chat_llm

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "subagents" / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def build_agent(role: str, tools: list) -> object:
    @lru_cache(maxsize=1)
    def _factory():
        # state_schema=MarvinState is required so that mission_id (and other
        # MarvinState fields) propagate through the prebuilt React agent's
        # internal graph and reach tools annotated with InjectedState.
        # Without this, the agent uses its default AgentState which only
        # carries {messages, remaining_steps}, and tools see no mission_id.
        return create_react_agent(
            model=get_chat_llm(role),
            tools=tools,
            prompt=load_prompt(role),
            state_schema=MarvinState,
        )

    return _factory
