from __future__ import annotations

from marvin.graph.subgraphs import adversus, calculus, dora, merlin, orchestrator
import pytest

from marvin.llm_factory import FREE_MODEL, MODEL_BY_ROLE, OPENROUTER_BASE_URL, get_chat_llm


def test_llm_factory_uses_openrouter_role_mapping():
    """Every demo role must use the explicit free variant, including drafting."""
    assert OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert FREE_MODEL == "minimax/minimax-m3.1-flash:free"
    for role in ("dora", "calculus", "merlin", "adversus", "orchestrator", "framing", "papyrus"):
        assert role in MODEL_BY_ROLE
        assert MODEL_BY_ROLE[role] == FREE_MODEL


@pytest.mark.parametrize("role", MODEL_BY_ROLE)
def test_llm_factory_rejects_paid_endpoints(monkeypatch, role):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-a-secret")
    llm = get_chat_llm(role)
    assert llm.model_name.endswith(":free")
    assert llm.extra_body == {
        "provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0}}
    }


def test_unknown_role_cannot_select_an_unconfigured_model():
    with pytest.raises(KeyError, match="unknown LLM role"):
        get_chat_llm("unknown")


def test_agent_tool_registries_non_empty():
    """The agent tool registry — not the prompt — is the source of truth for
    which tools each agent can call. Prompts are voice-only; tools are bound
    by build_agent. This test guards the registry shape; per-tool assertions
    belong in agent-behavior tests."""
    for mod in (orchestrator, dora, calculus, adversus, merlin):
        assert mod._tools, f"{mod.__name__} has empty tool registry"
        names = [t.__name__ for t in mod._tools]
        assert len(names) == len(set(names)), f"{mod.__name__} has duplicate tools"
