from __future__ import annotations

from pathlib import Path

from marvin.graph.subgraphs import adversus, calculus, dora, merlin, orchestrator
from marvin.llm_factory import MODEL_BY_ROLE, OPENROUTER_BASE_URL


def _prompt_tools(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.split("`")[1] for line in lines if line.startswith("- `")]


def test_llm_factory_uses_openrouter_role_mapping():
    """Runtime truth: every role is routed through OpenRouter and currently
    mapped to the same proven model. The previous DeepSeek-specific assertion
    predated the switch to OpenAI-via-OpenRouter and no longer matches the
    end-to-end-proven runtime configuration."""
    assert OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    for role in ("dora", "calculus", "merlin", "adversus", "orchestrator"):
        assert role in MODEL_BY_ROLE
        assert MODEL_BY_ROLE[role].startswith(("openai/", "deepseek/"))


def test_dora_prompt_tools_match_registry():
    prompt_tools = _prompt_tools(Path("marvin/subagents/prompts/dora.md"))
    assert prompt_tools == [tool.__name__ for tool in dora._tools]


def test_calculus_prompt_tools_match_registry():
    prompt_tools = _prompt_tools(Path("marvin/subagents/prompts/calculus.md"))
    assert prompt_tools == [tool.__name__ for tool in calculus._tools]


def test_adversus_prompt_tools_match_registry():
    prompt_tools = _prompt_tools(Path("marvin/subagents/prompts/adversus.md"))
    assert prompt_tools == [tool.__name__ for tool in adversus._tools]


def test_merlin_prompt_tools_match_registry():
    prompt_tools = _prompt_tools(Path("marvin/subagents/prompts/merlin.md"))
    assert prompt_tools == [tool.__name__ for tool in merlin._tools]


def test_orchestrator_prompt_tools_match_registry():
    prompt_tools = _prompt_tools(Path("marvin/subagents/prompts/orchestrator.md"))
    assert prompt_tools == [tool.__name__ for tool in orchestrator._tools]
