from __future__ import annotations

from marvin.graph.subgraphs import adversus, calculus, dora, merlin, orchestrator
from marvin.llm_factory import MODEL_BY_ROLE, OPENROUTER_BASE_URL


def test_llm_factory_uses_openrouter_role_mapping():
    """Runtime truth: every role is routed through OpenRouter and currently
    mapped to the same proven model. The previous DeepSeek-specific assertion
    predated the switch to OpenAI-via-OpenRouter and no longer matches the
    end-to-end-proven runtime configuration."""
    assert OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    for role in ("dora", "calculus", "merlin", "adversus", "orchestrator", "papyrus"):
        assert role in MODEL_BY_ROLE
        assert MODEL_BY_ROLE[role].startswith(("openai/", "deepseek/", "google/", "anthropic/"))

    assert MODEL_BY_ROLE["papyrus"] == "anthropic/claude-3.5-haiku"


def test_agent_tool_registries_non_empty():
    """The agent tool registry — not the prompt — is the source of truth for
    which tools each agent can call. Prompts are voice-only; tools are bound
    by build_agent. This test guards the registry shape; per-tool assertions
    belong in agent-behavior tests."""
    for mod in (orchestrator, dora, calculus, adversus, merlin):
        assert mod._tools, f"{mod.__name__} has empty tool registry"
        names = [t.__name__ for t in mod._tools]
        assert len(names) == len(set(names)), f"{mod.__name__} has duplicate tools"
