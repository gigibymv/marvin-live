"""Tool-level SSE narration via LangChain async callbacks.

Wave 1 of the transparency pass. The graph runs at `stream_mode="updates"`,
which only fires at node boundaries. Inside a node, the LLM may run for
30-90s with multiple tool calls and emit nothing. The user sees a frozen
"Agents are working" panel.

This handler subscribes to LangChain's tool-callback bus and emits a
narration SSE event for each tool invocation, keyed by mission_id. It is
the canonical pattern for surfacing intra-node agent work.

Verbosity is controlled by `_TOOL_VERBOSITY`:
  - "raw":         emit start (with short args) AND end (with short result)
  - "summarized":  emit start only, with a humanized verb
  - "silent":      do not emit
Unknown tools default to "summarized".

Agent attribution comes from `metadata["langgraph_node"]` when LangGraph
invokes the tool through a node — falls back to the registered current
agent for that mission, then to "MARVIN".
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

from marvin.events import emit_graph_event
from marvin.mission.store import MissionStore

logger = logging.getLogger(__name__)


# ─── Tool taxonomy ─────────────────────────────────────────────────────────

_TOOL_VERBOSITY: dict[str, str] = {
    # Research agents — show every web/db hit so the user sees real motion
    "search_web": "raw",
    "search_company": "raw",
    "lookup_company": "raw",
    "fetch_filing": "raw",
    "fetch_url": "raw",
    "tavily_search": "raw",
    # Persistence — show, but no result echo (volume + privacy)
    "add_finding_to_mission": "summarized",
    "mark_milestone_delivered": "silent",
    "save_hypothesis": "silent",
    "set_merlin_verdict": "summarized",
    # Read-only state inspection — summarized so they're visible but quiet
    "get_findings": "summarized",
    "get_hypotheses": "summarized",
    "get_storyline_findings": "summarized",
    "check_mece": "summarized",
    "check_merlin_verdict": "silent",
    "check_internal_consistency": "summarized",
    "list_workstreams": "silent",
    "list_milestones": "silent",
    # Writing — Papyrus already emits its own narration via papyrus_tools
    "generate_engagement_brief": "silent",
    "generate_workstream_report": "silent",
    "generate_milestone_report": "silent",
    "generate_executive_summary": "silent",
    "generate_data_book": "silent",
    "generate_framing_memo": "silent",
    # Action / metadata
    "update_action_title": "silent",
    "ask_question": "summarized",
    "generate_interview_guides": "silent",
}


_TOOL_VERBS: dict[str, str] = {
    "search_web": "searching the web",
    "search_company": "looking up the company",
    "lookup_company": "looking up the company",
    "fetch_filing": "fetching SEC filings",
    "fetch_url": "fetching a source",
    "tavily_search": "searching the web",
    "add_finding_to_mission": "recording a finding.",
    "get_findings": "reading existing findings",
    "get_hypotheses": "reading hypotheses",
    "get_storyline_findings": "reviewing findings for the storyline",
    "check_mece": "checking MECE on the storyline",
    "check_internal_consistency": "checking arbiter consistency",
    "set_merlin_verdict": "setting the verdict",
    "ask_question": "asking the user",
    "generate_interview_guides": "silent",
}


# ─── Per-mission active-agent registry ─────────────────────────────────────
# server.py updates this whenever a node emits its first event so callbacks
# can attribute tool calls to the right agent without plumbing a ref through
# every astream call.
_ACTIVE_AGENT: dict[str, str] = {}


def set_active_agent(mission_id: str, agent: str | None) -> None:
    if not mission_id:
        return
    display = None
    if agent:
        display = _NODE_TO_AGENT.get(agent, agent)
    if agent:
        _ACTIVE_AGENT[mission_id] = agent
    else:
        _ACTIVE_AGENT.pop(mission_id, None)
    try:
        store = MissionStore()
        if display:
            store.update_mission_active_agent(mission_id, display)
            store.update_mission_active_phase_agents(mission_id, [display])
        else:
            store.clear_mission_runtime_agents(mission_id)
    except Exception:  # noqa: BLE001 — runtime truth is best-effort, never fatal
        logger.debug("set_active_agent persistence failed for %s", mission_id, exc_info=True)


def _resolve_agent(mission_id: str, metadata: dict | None) -> str:
    if isinstance(metadata, dict):
        node = metadata.get("langgraph_node")
        if isinstance(node, str) and node:
            mapped = _NODE_TO_AGENT.get(node)
            if mapped:
                return mapped
        # When tool runs inside a create_react_agent subgraph, langgraph_node
        # is the inner node name (e.g. "tools") which won't match. Fall back to
        # the outer node extracted from langgraph_checkpoint_ns (e.g. "dora:0").
        ns = metadata.get("langgraph_checkpoint_ns") or ""
        if ns:
            outer = ns.split(":")[0]
            mapped = _NODE_TO_AGENT.get(outer)
            if mapped:
                return mapped
    return _ACTIVE_AGENT.get(mission_id) or "MARVIN"


_NODE_TO_AGENT: dict[str, str] = {
    "dora": "Dora",
    "calculus": "Calculus",
    "adversus": "Adversus",
    "merlin": "Merlin",
    "papyrus_phase0": "Papyrus",
    "papyrus_delivery": "Papyrus",
    "framing": "MARVIN",
    "framing_orchestrator": "MARVIN",
    "orchestrator": "MARVIN",
    "orchestrator_qa": "MARVIN",
}


# ─── Argument / result truncation helpers ──────────────────────────────────

_MAX_ARG_CHARS = 80
_MAX_RESULT_CHARS = 80


def _short_args(input_str: str) -> str:
    """Best-effort: render tool inputs as a compact string. Tool input may be
    JSON, a dict-repr, or a literal scalar. We never truncate mid-token in a
    way that produces unbalanced quotes the UI would render oddly."""
    if not input_str:
        return ""
    text = str(input_str).strip()
    # Unwrap a single-key dict like {"query":"..."} → "..."
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and len(parsed) == 1:
            sole = next(iter(parsed.values()))
            text = str(sole)
        elif isinstance(parsed, dict):
            keys = ", ".join(f"{k}={parsed[k]}" for k in list(parsed.keys())[:2])
            text = keys
    except (TypeError, ValueError):
        pass
    if len(text) > _MAX_ARG_CHARS:
        text = text[: _MAX_ARG_CHARS - 1].rstrip() + "…"
    return text


def _short_result(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, (list, tuple)):
        return f"{len(output)} item{'s' if len(output) != 1 else ''}"
    if isinstance(output, dict):
        # Common shapes: {"results": [...]} / {"findings": [...]} / {"verdict": "SHIP"}
        for key in ("results", "findings", "guides", "items"):
            value = output.get(key)
            if isinstance(value, list):
                return f"{len(value)} {key.rstrip('s')}{'s' if len(value) != 1 else ''}"
        if "verdict" in output:
            return f"verdict={output['verdict']}"
        if "status" in output:
            return f"status={output['status']}"
        return ""
    text = str(output).strip().replace("\n", " ")
    if len(text) > _MAX_RESULT_CHARS:
        text = text[: _MAX_RESULT_CHARS - 1].rstrip() + "…"
    return text


# ─── The callback handler ──────────────────────────────────────────────────


class MarvinToolCallbacks(AsyncCallbackHandler):
    """Emits per-tool SSE narration for a single mission's run."""

    def __init__(self, mission_id: str) -> None:
        self.mission_id = mission_id
        # run_id (str) → (tool_name, agent) so on_tool_end can finalize the
        # narration started by on_tool_start. LangChain doesn't pass the
        # tool name back through on_tool_end — we have to track it ourselves.
        self._inflight: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _emit(mission_id: str, agent: str, intent: str) -> None:
        try:
            ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            # destination=trace → frontend routes to trace lane + activity feed
            # only, never the conversational chat. Conceptual narrations
            # (framing sub-steps, papyrus drafting, merlin verdict) emit
            # without this field and continue to surface in chat.
            payload = {"agent": agent, "intent": intent, "ts": ts, "destination": "trace"}
            sse = f"event: narration\ndata: {json.dumps(payload)}\n\n"
            emit_graph_event(mission_id, sse)
        except Exception:  # noqa: BLE001 — never crash the agent loop on a UX emission
            logger.debug("tool_callbacks: emit failed", exc_info=True)

    async def on_tool_start(  # type: ignore[override]
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = (serialized or {}).get("name") or ""
        if not tool_name:
            return
        verbosity = _TOOL_VERBOSITY.get(tool_name, "summarized")
        if verbosity == "silent":
            return
        agent = _resolve_agent(self.mission_id, metadata)
        if verbosity == "raw":
            args = _short_args(input_str)
            intent = f"{tool_name}({args})" if args else tool_name
        else:
            intent = _TOOL_VERBS.get(tool_name, tool_name.replace("_", " "))
        self._inflight[str(run_id)] = (tool_name, agent)
        self._emit(self.mission_id, agent, intent)

    async def on_tool_end(  # type: ignore[override]
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        record = self._inflight.pop(str(run_id), None)
        if record is None:
            return
        tool_name, agent = record
        if _TOOL_VERBOSITY.get(tool_name, "summarized") != "raw":
            return
        result = _short_result(output)
        intent = f"{tool_name} done · {result}" if result else f"{tool_name} done"
        self._emit(self.mission_id, agent, intent)

    async def on_tool_error(  # type: ignore[override]
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        record = self._inflight.pop(str(run_id), None)
        tool_name, agent = record if record else ("tool", "MARVIN")
        self._emit(self.mission_id, agent, f"{tool_name} failed · {type(error).__name__}")
