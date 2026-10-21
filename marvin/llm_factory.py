from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Free demo routing, checked against OpenRouter's live catalogue on 2026-10-20.
# MiniMax M3.1 Flash supports tools and a 1M-token context. Keep the explicit
# :free variant: the unsuffixed model is paid. No paid fallback is configured.

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
FREE_MODEL = "minimax/minimax-m3.1-flash:free"
MODEL_BY_ROLE = {
    role: FREE_MODEL
    for role in (
        "dora", "calculus", "orchestrator", "framing", "merlin", "adversus", "papyrus"
    )
}


def get_chat_llm(role: str) -> ChatOpenAI:
    load_dotenv()
    model = MODEL_BY_ROLE.get(role)
    if model is None:
        raise KeyError(f"unknown LLM role: {role}")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    # Hard wall-clock cap on every LLM round-trip. Without this, a stalled
    # OpenRouter response (rare 5xx HTML or hung TLS) freezes any sync graph
    # node calling llm.invoke (e.g. Papyrus inside research_join), which has
    # surfaced as 30-min mission stalls in prod. The bounded retry helpers
    # in marvin.llm.transient classify ReadTimeout as transient and retry.
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
        timeout=120,
        max_retries=0,
        # Also reject endpoints with token or per-request charges if provider
        # availability changes. A free endpoint outage must surface as an error.
        extra_body={
            "provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0}}
        },
    )
