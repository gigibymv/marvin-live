from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# OpenAI GPT models via OpenRouter:
# - gpt-5.4-nano for all agents (fast, capable, cost-efficient)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_BY_ROLE = {
    "dora": "openai/gpt-5.4-nano",
    "calculus": "openai/gpt-5.4-nano",
    "adversus": "openai/gpt-5.4-nano",
    "merlin": "openai/gpt-5.4-nano",
    "orchestrator": "openai/gpt-5.4-nano",
    "framing": "openai/gpt-5.4-nano",
    # Papyrus produces client-facing IC documents — quality > cost.
    "papyrus": "anthropic/claude-sonnet-4.6",
}


def get_chat_llm(role: str) -> ChatOpenAI:
    load_dotenv()
    model = MODEL_BY_ROLE.get(role)
    if model is None:
        raise KeyError(f"unknown LLM role: {role}")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
    )
