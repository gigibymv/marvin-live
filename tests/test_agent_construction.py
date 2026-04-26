"""Targeted tests for the tool-registration contract.

Proves:
1. Every raw tool function passed to an agent factory satisfies the
   `StructuredTool.from_function` description requirement (i.e. has either a
   docstring or an explicit description). This is the exact failure surface
   that previously blocked the resumed graph: `create_react_agent` →
   `StructuredTool.from_function` → `ValueError: Function must have a
   docstring if description not provided.`
2. Each subgraph factory in `marvin/graph/subgraphs/*.py` constructs an
   agent successfully when handed a tool-capable chat model. We monkeypatch
   `get_chat_llm` with a minimal fake that supports `bind_tools` so the test
   exercises the real factory path (load_prompt + create_react_agent over
   the real tool list) without needing OPENROUTER_API_KEY.
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from marvin.graph.subgraphs import adversus, calculus, common, dora, merlin, orchestrator


class _FakeChatWithTools(GenericFakeChatModel):
    """GenericFakeChatModel doesn't implement bind_tools; create_react_agent
    requires it. This stub returns self on bind_tools so registration is
    exercised but no real LLM call happens."""

    def bind_tools(self, tools: Any, **_: Any) -> "_FakeChatWithTools":
        return self


def _fake_llm(_role: str) -> _FakeChatWithTools:
    return _FakeChatWithTools(messages=iter([AIMessage(content="ok")]))


@pytest.fixture(autouse=True)
def _patch_llm(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(common, "get_chat_llm", _fake_llm)
    yield


@pytest.mark.parametrize(
    "module,name",
    [
        (dora, "dora"),
        (calculus, "calculus"),
        (merlin, "merlin"),
        (adversus, "adversus"),
        (orchestrator, "orchestrator"),
    ],
)
def test_subgraph_factory_constructs_agent(module, name):
    # Each subgraph module exposes a build_agent-wrapped lru_cache factory at
    # module load time. Re-build it here so the patched llm is captured even
    # if a previous test cached the real one.
    factory = common.build_agent(name, module._tools)
    agent = factory()
    assert agent is not None


def test_every_registered_tool_has_description():
    """Walk every tool in every subgraph factory and confirm StructuredTool
    can register it. This is the precise contract create_react_agent enforces."""
    seen_failures: list[str] = []
    for module in (dora, calculus, merlin, adversus, orchestrator):
        for fn in module._tools:
            try:
                StructuredTool.from_function(fn)
            except Exception as exc:
                seen_failures.append(f"{module.__name__}.{fn.__name__}: {exc}")
    assert not seen_failures, "tools failed registration: " + "; ".join(seen_failures)
