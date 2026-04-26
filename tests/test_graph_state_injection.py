"""Runtime test: prove that mission_id from MarvinState reaches tools annotated
with InjectedState when invoked through the prebuilt React agent.

Failure mode: create_react_agent without state_schema= falls back to the
default AgentState (messages + remaining_steps only). Tools that read
state["mission_id"] then crash with KeyError because the field is silently
dropped at the agent/tool boundary.

Fix: pass state_schema=MarvinState to create_react_agent.
"""
from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from marvin.graph.state import MarvinState
from marvin.tools.common import InjectedStateArg


class _AsyncFakeLLM(FakeMessagesListChatModel):
    """FakeMessagesListChatModel ships sync only and lacks bind_tools; the
    prebuilt React agent needs both. Override accordingly."""

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, **kwargs)

    def bind_tools(self, tools, **_):
        # The canned responses already contain the tool calls we need;
        # binding tools is a no-op for this fake.
        return self


def _make_fake_llm():
    """Fake LLM that on first call asks to invoke `record_mission`, then
    on second call returns a final assistant message."""
    return _AsyncFakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "record_mission",
                    "args": {},
                    "id": "call_1",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="finished"),
        ]
    )


def test_inject_state_carries_mission_id_through_react_agent_with_state_schema():
    """With state_schema=MarvinState, mission_id reaches the tool."""
    captured: dict[str, Any] = {}

    def record_mission(state: InjectedStateArg = None) -> str:
        """Capture state landed in this tool call (test stub)."""
        captured["state"] = state
        return "recorded"

    agent = create_react_agent(
        model=_make_fake_llm(),
        tools=[record_mission],
        state_schema=MarvinState,
    )

    initial_state: MarvinState = {
        "messages": [HumanMessage(content="please call record_mission")],
        "mission_id": "m-injection-test",
        "phase": "setup",
    }

    asyncio.run(agent.ainvoke(initial_state))

    assert "state" in captured, "tool was never invoked"
    assert captured["state"] is not None, "state arrived as None"
    assert captured["state"].get("mission_id") == "m-injection-test", (
        f"mission_id missing from injected state — got {captured['state']!r}"
    )


def test_marvin_build_agent_factory_propagates_mission_id(monkeypatch):
    """Integration with marvin.graph.subgraphs.common.build_agent: confirms
    the production factory passes state_schema=MarvinState so tools see
    mission_id end-to-end through a built agent."""
    captured: dict[str, Any] = {}

    def record_mission(state: InjectedStateArg = None) -> str:
        """Capture state via the real build_agent factory."""
        captured["state"] = state
        return "recorded"

    from marvin.graph.subgraphs import common as common_module
    monkeypatch.setattr(common_module, "get_chat_llm", lambda role: _make_fake_llm())
    monkeypatch.setattr(common_module, "load_prompt", lambda role: "test prompt")

    factory = common_module.build_agent("test_role", [record_mission])
    agent = factory()

    initial_state: MarvinState = {
        "messages": [HumanMessage(content="please call record_mission")],
        "mission_id": "m-build-agent-test",
        "phase": "setup",
    }

    asyncio.run(agent.ainvoke(initial_state))

    assert captured.get("state") is not None
    assert captured["state"].get("mission_id") == "m-build-agent-test"
