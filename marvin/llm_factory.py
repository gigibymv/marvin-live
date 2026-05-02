from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Model routing via OpenRouter:
# - GPT-5.4 Nano: cheap roles where reasoning depth doesn't gate quality
#   (extraction, classification, structured numeric output, chat QA).
# - Gemini 2.5 Pro: reasoning-critical roles (synthesis verdict, red-team).
# - Claude Haiku: client-facing drafting where cost matters more than deep
#   adversarial reasoning.

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_BY_ROLE = {
    "dora": "openai/gpt-5.4-nano",
    "calculus": "openai/gpt-5.4-nano",
    "orchestrator": "openai/gpt-5.4-nano",
    "framing": "openai/gpt-5.4-nano",
    # Reasoning-critical: synthesis verdict and adversarial stress.
    # Nano was borderline on multi-claim reconciliation.
    "merlin": "google/gemini-2.5-pro",
    "adversus": "google/gemini-2.5-pro",
    # Papyrus produces client-facing documents frequently; use Haiku for the
    # writing pass to keep live mission cost under control.
    "papyrus": "anthropic/claude-3.5-haiku",
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
