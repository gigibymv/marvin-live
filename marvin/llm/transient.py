"""C-RESUME-RECOVERY — bounded retry around LLM-bearing async calls.

OpenRouter occasionally returns HTML 5xx pages instead of JSON. The OpenAI
SDK then raises ``json.JSONDecodeError`` deep inside the agent invocation
and the LangGraph node fails the whole detached run. We want a tight
retry-with-backoff *inside* the node so a single transient blip does not
require a full mission rerun, and a typed failure when retries are
exhausted so the caller can persist a structured gate failure.

This module is intentionally small and dependency-light — it is imported
from runner.py only. Do not couple it to MissionStore.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_BACKOFFS: tuple[float, ...] = (1.0, 2.0)
"""Default backoff schedule. Length implies retry budget: 2 retries → 3 attempts."""


class LLMTransientFailure(Exception):
    """Raised when the retry budget is exhausted on a transient class error.

    The caller (typically a LangGraph node) catches this, persists a
    structured gate failure with ``failure_reason`` populated, and lets
    the graph advance to a quiescent ``llm_transient_failure`` phase
    instead of crashing the whole detached run.
    """

    def __init__(self, agent: str, cause: str, attempts: int, error: str):
        self.agent = agent
        self.cause = cause
        self.attempts = attempts
        self.error = error
        super().__init__(
            f"{agent}: {cause} after {attempts} attempt(s) — {error}"
        )

    def to_failure_reason(self) -> dict:
        return {
            "agent": self.agent,
            "error": self.error,
            "cause": self.cause,
            "retries_exhausted": self.attempts,
        }


def _classify(exc: BaseException) -> str | None:
    """Return a short cause label if ``exc`` is a known transient class.

    Recognized:
    - ``json.JSONDecodeError`` — OpenRouter returned HTML 5xx
    - openai/httpx 5xx surfaces — APIError, APIStatusError, HTTPStatusError
    - asyncio/network timeout

    Returns None for anything else so the caller re-raises and the
    graph treats it as a real bug rather than a flaky upstream.
    """
    if isinstance(exc, json.JSONDecodeError):
        return "OpenRouter non-JSON response (likely 5xx HTML)"

    name = type(exc).__name__
    msg = str(exc).lower()

    if name in {"APIStatusError", "APIError", "InternalServerError"}:
        if "5" in msg[:20] or "internal" in msg or "bad gateway" in msg or "unavailable" in msg:
            return f"upstream {name}"
        return f"upstream {name}"
    if name in {"HTTPStatusError"}:
        # httpx surfaces status code in str(exc); 5xx only.
        if any(code in msg for code in (" 500", " 502", " 503", " 504", " 520", " 522")):
            return f"upstream HTTP 5xx"
        return None
    if name in {"ReadTimeout", "ConnectTimeout", "TimeoutException", "TimeoutError"}:
        return f"upstream timeout ({name})"
    if name == "APIConnectionError":
        return "upstream connection error"
    return None


async def async_invoke_with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    agent: str,
    backoffs: Sequence[float] = DEFAULT_BACKOFFS,
) -> T:
    """Invoke ``func`` with bounded retry on known transient classes.

    Total attempts = ``len(backoffs) + 1`` (default: 3). Each retry
    sleeps for the matching backoff entry before the next attempt.
    On exhaustion raises :class:`LLMTransientFailure`. Non-transient
    exceptions propagate unchanged on the first occurrence.
    """
    attempts = 0
    last_cause = ""
    last_error = ""
    total = len(backoffs) + 1
    for attempt in range(total):
        attempts = attempt + 1
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001 — classifier decides
            cause = _classify(exc)
            if cause is None:
                raise
            last_cause = cause
            last_error = type(exc).__name__
            if attempt < len(backoffs):
                delay = backoffs[attempt]
                logger.warning(
                    "[%s] transient (%s): %s — retry %d/%d in %.1fs",
                    agent, cause, exc, attempt + 1, total - 1, delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.error(
                "[%s] transient (%s) exhausted after %d attempts: %s",
                agent, cause, attempts, exc,
            )
            raise LLMTransientFailure(
                agent=agent,
                cause=cause,
                attempts=attempts,
                error=last_error,
            ) from exc
    # Unreachable — loop either returns or raises.
    raise LLMTransientFailure(
        agent=agent, cause=last_cause or "unknown", attempts=attempts, error=last_error
    )


def sync_invoke_with_retry(
    func: Callable[[], T],
    *,
    agent: str,
    backoffs: Sequence[float] = DEFAULT_BACKOFFS,
) -> T:
    """Sync sibling of :func:`async_invoke_with_retry`.

    Used by Papyrus deliverable generators that run inside synchronous
    LangGraph nodes (e.g. ``research_join``) where introducing an async
    boundary would force a much wider refactor. Same retry budget and
    same transient classification.
    """
    attempts = 0
    last_cause = ""
    last_error = ""
    total = len(backoffs) + 1
    for attempt in range(total):
        attempts = attempt + 1
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 — classifier decides
            cause = _classify(exc)
            if cause is None:
                raise
            last_cause = cause
            last_error = type(exc).__name__
            if attempt < len(backoffs):
                delay = backoffs[attempt]
                logger.warning(
                    "[%s] transient (%s): %s — retry %d/%d in %.1fs",
                    agent, cause, exc, attempt + 1, total - 1, delay,
                )
                time.sleep(delay)
                continue
            logger.error(
                "[%s] transient (%s) exhausted after %d attempts: %s",
                agent, cause, attempts, exc,
            )
            raise LLMTransientFailure(
                agent=agent,
                cause=cause,
                attempts=attempts,
                error=last_error,
            ) from exc
    raise LLMTransientFailure(
        agent=agent, cause=last_cause or "unknown", attempts=attempts, error=last_error
    )
