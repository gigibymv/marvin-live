"""Gated runtime instrumentation for the Exit-137 investigation.

All output is suppressed unless MARVIN_DEBUG_RUNTIME is set to a truthy value.
Designed to be removed in one commit once the root cause is identified.
"""

from __future__ import annotations

import json
import logging
import os
import resource
import sys
import time
from typing import Any, Iterable

_ENABLED = os.environ.get("MARVIN_DEBUG_RUNTIME", "").lower() in {"1", "true", "yes", "on"}

_logger = logging.getLogger("marvin.runtime_debug")
if _ENABLED and not _logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[runtime_debug %(asctime)s] %(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False

_T0 = time.monotonic()


def enabled() -> bool:
    return _ENABLED


def _rss_mb() -> float:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return raw / (1024 * 1024)
    return raw / 1024


def _content_bytes(messages: Iterable[Any]) -> int:
    total = 0
    for msg in messages:
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        elif content is not None:
            try:
                total += len(json.dumps(content, default=str))
            except Exception:
                total += len(str(content))
    return total


def _tool_calls_in(messages: Iterable[Any]) -> int:
    count = 0
    for msg in messages:
        tc = getattr(msg, "tool_calls", None) or []
        count += len(tc)
    return count


def log_node_entry(node: str, state: dict) -> None:
    if not _ENABLED:
        return
    msgs = state.get("messages") or []
    _logger.info(
        "node_entry node=%s phase=%s msgs=%d msg_bytes=%d tool_calls=%d rss_mb=%.1f t=%.1fs",
        node,
        state.get("phase"),
        len(msgs),
        _content_bytes(msgs),
        _tool_calls_in(msgs),
        _rss_mb(),
        time.monotonic() - _T0,
    )


def log_agent_io(role: str, when: str, state_or_result: dict, extra: dict | None = None) -> None:
    if not _ENABLED:
        return
    msgs = state_or_result.get("messages") or []
    payload = {
        "role": role,
        "when": when,
        "msgs": len(msgs),
        "msg_bytes": _content_bytes(msgs),
        "tool_calls": _tool_calls_in(msgs),
        "rss_mb": round(_rss_mb(), 1),
        "t": round(time.monotonic() - _T0, 1),
    }
    if extra:
        payload.update(extra)
    _logger.info("agent_io %s", json.dumps(payload, default=str))
