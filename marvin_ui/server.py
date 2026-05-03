"""
FastAPI backend for Marvin frontend.

Exposes mission APIs, SSE chat streaming, gate validation, and deliverable download.
Wires to existing marvin package (store, tools, graph, agents).

Run:
    uvicorn marvin_ui.server:app --port 8091
    # or
    python -m marvin_ui.server
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import time
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, date
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, ToolMessage
import aiosqlite

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from marvin.artifacts import artifact_file_is_ready
from marvin.events import (
    emit_graph_event,
    register_deliverable_listener,
    register_finding_listener,
    register_graph_event_listener,
    register_milestone_listener,
    unregister_deliverable_listener,
    unregister_finding_listener,
    unregister_graph_event_listener,
    unregister_milestone_listener,
)
from marvin.graph.gate_material import evaluate_gate_material
from marvin.graph.runner import build_graph
from marvin.graph.state import MarvinState
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools.common import slugify, short_id, utc_now_iso
from marvin.tools.mission_tools import (
    compute_hypothesis_status,
    consultant_verdict_action,
    consultant_verdict_label,
)
from marvin.mission.schema import (
    DataRoomFile,
    DealTerms,
    Finding,
    Gate,
    Hypothesis,
    Mission as MissionModel,
    MissionChatMessage,
    Transcript,
    TranscriptSegment,
)
from marvin.economics.deal_math import compute_deal_math
from marvin.ingestion.data_room import MAX_BYTES as DATA_ROOM_MAX_BYTES, parse_file as parse_data_room_file
from marvin.ingestion.transcripts import parse_transcript

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("marvin.server")

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else [
    "http://localhost:3000",
]
# Allow any localhost/127.0.0.1 port in local dev so the frontend isn't pinned to :3000.
# Production should set CORS_ORIGINS explicitly and ALLOW_LOCALHOST_ANY_PORT=0.
ALLOW_LOCALHOST_ANY_PORT = os.getenv("ALLOW_LOCALHOST_ANY_PORT", "1") == "1"
CORS_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if ALLOW_LOCALHOST_ANY_PORT else None
API_KEY_HEADER = "X-API-Key"
API_KEY_ENV = "MARVIN_API_KEY"

# Display name mapping for user-facing event emission. Explicit None for
# internal/system nodes so they never leak into the live rail; explicit
# Title Case for working agents so casing is consistent end-to-end (Bug 3).
_DISPLAY_NAME: dict[str, str | None] = {
    # Working agents
    "dora": "Dora",
    "calculus": "Calculus",
    "adversus": "Adversus",
    "merlin": "Merlin",
    "synthesis_critic": "Merlin",
    # Document agents
    "papyrus_phase0": "Papyrus",
    "papyrus_delivery": "Papyrus",
    # Orchestration voice
    "orchestrator": "MARVIN",
    "orchestrator_qa": "MARVIN",
    "framing": "MARVIN",
    "framing_orchestrator": "MARVIN",
    # 9-bug triage D: gate/phase narration is emitted with agent="workflow";
    # surface it under the MARVIN brand instead of an unowned "Workflow"
    # sender label that confused users about who is speaking.
    "workflow": "MARVIN",
    # System / control-flow nodes — must NEVER appear in the rail
    "phase_router": None,
    "research_join": None,
    "gate": None,
    "gate_node": None,
    "gate_entry": None,
}


def get_display_name(node_name: str | None) -> str | None:
    """Resolve a graph node identifier to a user-facing display name.

    Returns None for internal/system nodes — callers must skip emitting any
    event for those. Unknown nodes fall through to Title Case so a new agent
    never leaks as "AGENT" or as a snake_case identifier.
    """
    if not node_name:
        return None
    if node_name in _DISPLAY_NAME:
        return _DISPLAY_NAME[node_name]
    return node_name.replace("_", " ").title()

# Nodes whose AIMessage content speaks to the user as Marvin's voice in the
# chat. Sub-agents (dora/calculus/adversus/merlin) are doing work, not
# conversing — their content streams to the live rail as agent_message
# entries instead of polluting the chat with verbose reasoning.
_CHAT_VOICE_NODES = {"framing", "framing_orchestrator", "orchestrator", "papyrus_delivery"}

# LangGraph can occasionally checkpoint a mission with no pending node
# (`snapshot.next == ()`) while the persisted phase still represents a
# continuable workflow boundary. Treating those snapshots as terminal leaves
# the mission paused with no pending gate and no downstream work running.
_CONTINUABLE_CHECKPOINT_PHASES = {
    "framing",
    "awaiting_confirmation",
    "confirmed",
    "research_done",
    "gate_g1_passed",
    "redteam_done",
    "rebuttal_done",
    "synthesis_retry",
    "synthesis_done",
    "gate_g3_passed",
}


def _continuation_input_from_snapshot(snapshot: Any) -> dict[str, Any] | None:
    values = dict(getattr(snapshot, "values", None) or {})
    phase = values.get("phase")
    mission_id = values.get("mission_id")
    if not isinstance(phase, str) or phase not in _CONTINUABLE_CHECKPOINT_PHASES:
        return None
    if not isinstance(mission_id, str) or not mission_id:
        return None
    return values

_TRACE_ONLY_TOOLS = {
    "add_finding_to_mission",
    "mark_milestone_delivered",
    "mark_milestone_blocked",
    "set_merlin_verdict",
    "get_hypotheses",
    "search_sec_filings",
    "fetch_filing_section",
    "get_recent_filings",
    "search_company",
    "tavily_search",
    "persist_source_for_mission",
    "generate_workstream_report",
    "generate_exec_summary",
    "generate_data_book",
    "generate_report_pdf",
}

# Tool result summaries for user-friendly display
_TOOL_SUMMARIES: dict[str, callable] = {
    "add_finding_to_mission": lambda r: f"Finding added · {r.get('finding_id', '')[:12]}",
    "mark_milestone_delivered": lambda r: f"✓ {r.get('milestone_id', '')} delivered",
    "generate_engagement_brief": lambda r: "Engagement Brief ready",
    "set_merlin_verdict": lambda r: f"Verdict: {r.get('verdict', '')}",
    "add_hypothesis_to_mission": lambda r: "Hypothesis recorded",
    "persist_source_for_mission": lambda r: "Source added",
    # Humanized labels for common tool calls surfaced in the live rail
    "tavily_search": lambda r: (
        f"Searching the web for {str(r.get('query', r.get('result', {}).get('query', '')))[:40]}"
        if (r.get('query') or r.get('result', {}).get('query'))
        else "Searching the web"
    ),
    "search_company": lambda r: (
        f"Looking up company: {str(r.get('company_name', ''))[:40]}"
        if r.get('company_name')
        else "Looking up company"
    ),
    "search_sec_filings": lambda r: (
        f"Searching SEC filings for {str(r.get('company_name', ''))[:30]}"
        if r.get('company_name')
        else "Searching SEC filings"
    ),
    "get_recent_filings": lambda r: (
        f"Fetching {r.get('filing_type', '')} filings for {str(r.get('company_name', ''))[:30]}"
        if r.get('company_name')
        else "Fetching filings"
    ),
    "parse_data_room": lambda r: (
        f"Reading {str(r.get('file_path', ''))[-40:]}"
        if r.get('file_path')
        else "Reading data room file"
    ),
    "quality_of_earnings": lambda r: "Running quality-of-earnings analysis",
    "cohort_analysis": lambda r: "Running cohort analysis",
    "compute_cac_ltv": lambda r: "Computing CAC / LTV metrics",
    "concentration_analysis": lambda r: "Running concentration analysis",
    "anomaly_detector": lambda r: "Scanning for anomalies",
    "attack_hypothesis": lambda r: "Stress-testing hypothesis",
    "generate_stress_scenarios": lambda r: "Generating stress scenarios",
    "identify_weakest_link": lambda r: "Identifying weakest link",
    "run_ansoff": lambda r: "Running Ansoff growth analysis",
    "build_bottom_up_tam": lambda r: "Building bottom-up TAM",
    "analyze_market_data": lambda r: "Analysing market data",
    "run_pestel": lambda r: "Running PESTEL analysis",
    "moat_analysis": lambda r: "Running moat analysis",
    "win_loss_framework": lambda r: "Running win/loss framework",
    "check_mece": lambda r: "Checking MECE coverage",
    "check_internal_consistency": lambda r: "Checking internal consistency",
    "get_storyline_findings": lambda r: "Loading storyline findings",
    "generate_framing_memo": lambda r: "Generating framing memo",
    "generate_workstream_report": lambda r: "Generating workstream report",
    "generate_report_pdf": lambda r: "Generating PDF report",
    "generate_exec_summary": lambda r: "Generating executive summary",
    "generate_data_book": lambda r: "Generating data book",
}


def _get_tool_summary(tool_name: str, result: dict | None) -> str | None:
    """Get user-friendly summary for tool result."""
    if tool_name in _TRACE_ONLY_TOOLS:
        return None
    if tool_name in _TOOL_SUMMARIES:
        try:
            return _TOOL_SUMMARIES[tool_name](result or {})
        except Exception:
            pass
    return None


def _is_trace_only_tool(tool_name: str | None) -> bool:
    return str(tool_name or "").strip() in _TRACE_ONLY_TOOLS


def _show_raw_tool_events() -> bool:
    return os.environ.get("MARVIN_SHOW_RAW_TOOL_EVENTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _is_user_facing_tool_text(text: str | None) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    if clean.startswith(("{", "[", "ToolMessage(", "content=")):
        return False
    lower = clean.lower()
    blocked_fragments = (
        "finding added",
        "get_hypotheses",
        "search_sec_filings",
        "fetch_filing_section",
        "cannot open",
        "back_to_drawing_board",
        "minor_fixes",
    )
    return not any(fragment in lower for fragment in blocked_fragments)


def _mission_exists(store: MissionStore, mission_id: str) -> bool:
    """Check if mission exists without raising KeyError."""
    try:
        store.get_mission(mission_id)
        return True
    except KeyError:
        return False


def _hypotheses_with_status(hypotheses, findings) -> list[dict]:
    """Chantier 4: enrich each hypothesis with computed status + counts.

    Groups findings by hypothesis_id (in Python — no extra DB hit), feeds
    each group into compute_hypothesis_status, and returns the UI payload.
    """
    by_hyp: dict[str | None, list] = {}
    for f in findings:
        by_hyp.setdefault(f.hypothesis_id, []).append(f)
    # Adversus findings saved without a hypothesis_id represent mission-wide
    # red-team challenges. Apply them to every hypothesis so a hypothesis
    # that adversus challenged (but whose finding lacked hypothesis_id) still
    # shows WEAKENED rather than staying TESTING forever.
    unlinked_adversus = [
        f for f in by_hyp.get(None, []) if getattr(f, "agent_id", None) == "adversus"
    ]
    return [
        {
            "id": h.id,
            "label": h.label,
            "text": h.text,
            "status": h.status,
            "computed": compute_hypothesis_status(
                by_hyp.get(h.id, []) + unlinked_adversus
            ),
        }
        for h in hypotheses
    ]


def _deliverable_progress_payload(deliverable) -> dict:
    is_ready = (
        deliverable.status == "ready"
        and artifact_file_is_ready(deliverable.file_path, deliverable.deliverable_type)
    )
    return {
        "id": deliverable.id,
        "deliverable_type": deliverable.deliverable_type,
        "status": "ready" if is_ready else "pending",
        "file_path": deliverable.file_path if is_ready else None,
        "created_at": deliverable.created_at,
        "milestone_id": getattr(deliverable, "milestone_id", None),
    }


# =============================================================================
# GRAPH SINGLETON
# =============================================================================

_graph = None
_graph_lock = asyncio.Lock()
_mission_locks: dict[str, asyncio.Lock] = {}

# Process-local coordination state. The live resume path depends on the chat
# stream and gate validation request landing in the same worker process; run
# uvicorn as a single worker unless this state is moved to shared storage.
#
# Per-mission pending resume futures. When _stream_chat hits an interrupt frame,
# it parks on a future here keyed by mission_id; validate_gate sets the result
# with the approval payload, which unblocks the stream to call
# graph.astream(Command(resume=...)) on the same thread_id and keep yielding SSE
# events to the still-open client connection.
_pending_resumes: dict[str, asyncio.Future[dict]] = {}
_gate_decisions_in_flight: dict[str, dict[str, str]] = {}
_gate_decision_by_mission: dict[str, str] = {}

# Chantier 2.7 FIX 3 — chat-driven gate approval. Matches messages like
# "approved", "yes", "ok", "go ahead", "proceed", "lgtm". Conservative on
# purpose: anything ambiguous routes to QA with a "graph paused" hint.
_APPROVAL_RE = re.compile(
    r"^\s*(approved?|yes|y|ok|okay|go\s+ahead|proceed|lgtm|confirm(ed)?|sure)\b\s*[.!]?\s*$",
    re.IGNORECASE,
)


def _is_approval_text(text: str) -> bool:
    if not text:
        return False
    return bool(_APPROVAL_RE.match(text.strip()))

# Bounded wait so a forgotten gate doesn't pin the per-mission lock forever.
_RESUME_TIMEOUT_SECONDS = 600


def _register_pending_resume(mission_id: str) -> asyncio.Future[dict]:
    fut = asyncio.get_running_loop().create_future()
    existing = _pending_resumes.get(mission_id)
    if existing is not None and not existing.done():
        existing.cancel()
    _pending_resumes[mission_id] = fut
    return fut


def _clear_pending_resume(mission_id: str, fut: asyncio.Future[dict]) -> None:
    current = _pending_resumes.get(mission_id)
    if current is fut:
        _pending_resumes.pop(mission_id, None)


def _deliver_resume(mission_id: str, payload: dict) -> bool:
    """Hand a resume payload to a waiting _stream_chat. Returns True if delivered."""
    fut = _pending_resumes.pop(mission_id, None)
    if fut is None or fut.done():
        return False
    fut.set_result(payload)
    return True


def _mark_gate_decision_in_flight(
    mission_id: str,
    gate_id: str,
    *,
    expected_status: str,
    verdict: str,
    resume_id: str,
) -> None:
    _gate_decisions_in_flight[gate_id] = {
        "expected_status": expected_status,
        "verdict": verdict,
        "resume_id": resume_id,
    }
    _gate_decision_by_mission[mission_id] = gate_id


def _clear_gate_decision_in_flight(gate_id: str | None) -> None:
    if gate_id:
        _gate_decisions_in_flight.pop(gate_id, None)
        for mission_id, active_gate_id in list(_gate_decision_by_mission.items()):
            if active_gate_id == gate_id:
                _gate_decision_by_mission.pop(mission_id, None)


def _clear_gate_decision_for_mission(mission_id: str) -> None:
    _clear_gate_decision_in_flight(_gate_decision_by_mission.get(mission_id))


def _get_mission_lock(mission_id: str) -> asyncio.Lock:
    """Get or create per-mission async lock."""
    if mission_id not in _mission_locks:
        _mission_locks[mission_id] = asyncio.Lock()
    return _mission_locks[mission_id]


# Detached graph drivers spawned by validate_gate when no SSE consumer was
# parked. Keyed by mission_id. Survive client tab close so the workflow
# advances regardless of whether anyone is watching. CLAUDE.md §1: no silent
# degradation — gate validation must always advance the graph.
_detached_drivers: dict[str, asyncio.Task] = {}
_queued_detached_resumes: dict[str, dict] = {}


async def _drive_detached_resume(mission_id: str, resume_payload: dict) -> None:
    """Drive `graph.astream(Command(resume=...))` to completion or next interrupt.

    Runs after `validate_gate` could not deliver the resume to a parked
    `_stream_chat`. Findings/deliverables/milestones still persist via the
    agent tools' direct DB writes; the next `/resume` call replays the latest
    checkpoint and surfaces any new gate_pending interrupt.
    """
    from langgraph.types import Command

    lock = _get_mission_lock(mission_id)
    try:
        await asyncio.wait_for(lock.acquire(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning(
            "Detached resume aborted — mission already locked: mission=%s",
            mission_id,
        )
        return
    try:
        try:
            graph = await get_graph()
        except Exception as exc:  # noqa: BLE001 - never crash the worker pool
            logger.error("Detached resume could not load graph: %s", exc)
            return

        from marvin.graph.tool_callbacks import MarvinToolCallbacks
        config = {
            "configurable": {"thread_id": mission_id},
            "callbacks": [MarvinToolCallbacks(mission_id)],
        }
        target_gate_id = resume_payload.get("gate_id")
        has_target_gate = isinstance(target_gate_id, str) and bool(target_gate_id)
        # If the graph already has a parked interrupt waiting for us, feed the
        # resume payload immediately. Otherwise drive forward with no input
        # until we *see* our target gate park, then feed the resume. This
        # handles the case where validate_gate fires before _stream_chat had
        # time to checkpoint the gate park (client disconnected mid-framing).
        try:
            _state0 = await graph.aget_state(config)
            _has_parked = any(getattr(t, "interrupts", None) for t in _state0.tasks)
        except Exception:  # noqa: BLE001 - defensive: aget_state shouldn't fail
            _has_parked = False
        # A detached driver has two modes:
        #   1. gate resume: consume the specific gate interrupt.
        #   2. continuation recovery: keep a routable/cancelled checkpoint
        #      moving after a client disconnect.
        # Mode 2 must never feed Command(resume=...) into an already-open gate,
        # otherwise a passive reconnect can accidentally consume a human
        # checkpoint with a synthetic no-op payload.
        next_input: Any = (
            Command(resume=resume_payload)
            if has_target_gate and _has_parked
            else None
        )
        fed_resume = bool(has_target_gate and _has_parked)
        # F1-A: broadcast SSE strings as the graph runs so a passively-attached
        # /resume client (which cannot run its own astream while we hold the
        # lock) can relay agent_active / narration / phase_changed / agent_done
        # events to the user. Persistence-derived events (finding_added etc.)
        # flow through marvin.events listeners independently.
        current_agent: str | None = None
        current_phase: str | None = None
        throttle_state: dict[tuple[str, str], float] = {}
        continued_terminal_phases: set[str] = set()
        try:
            emit_graph_event(mission_id, await _emit_run_start())
            # Bounded loop. We pass through framing/gate_entry on the first
            # turn (when the parked frame wasn't ready), then re-enter with
            # Command(resume=...) to consume our gate's interrupt, then run
            # forward to the next gate or completion.
            for _step in range(8):
                interrupted_for_target = False
                interrupted_other = False
                async for event in graph.astream(
                    next_input, config, stream_mode="updates"
                ):
                    if isinstance(event, dict) and "__interrupt__" in event:
                        for it in event["__interrupt__"]:
                            ipayload = getattr(it, "value", None)
                            if not isinstance(ipayload, dict) and isinstance(it, dict):
                                ipayload = it
                            gid = ipayload.get("gate_id") if isinstance(ipayload, dict) else None
                            if has_target_gate and gid == target_gate_id and not fed_resume:
                                interrupted_for_target = True
                            else:
                                interrupted_other = True
                                # P18a fix: emit gate_pending + narration for the
                                # new (non-target) interrupt so passive listeners
                                # attached via _stream_resume_passive receive the
                                # gate CTA bubble. Without this, the gate_pending
                                # SSE is never broadcast and the chat bubble with
                                # Approve/Reject buttons never appears.
                                if isinstance(ipayload, dict):
                                    emit_graph_event(
                                        mission_id,
                                        await _emit_gate_pending(ipayload, mission_id=mission_id),
                                    )
                                    emit_graph_event(
                                        mission_id,
                                        await _emit_narration(
                                            "workflow",
                                            _gate_narration(ipayload),
                                        ),
                                    )
                        break
                    if isinstance(event, dict):
                        sse_strings, current_agent, current_phase, _is_int = await _emit_for_update(
                            event, current_agent, current_phase, throttle_state, mission_id=mission_id
                        )
                        for s in sse_strings:
                            if s:
                                emit_graph_event(mission_id, s)
                if interrupted_for_target:
                    # Our gate just parked. Re-enter with the resume payload
                    # to consume it and drive past gate_node.
                    next_input = Command(resume=resume_payload)
                    fed_resume = True
                    continue
                if not interrupted_other:
                    try:
                        snapshot = await graph.aget_state(config)
                    except Exception:  # noqa: BLE001 - best-effort recovery
                        snapshot = None
                    continuation_input = _continuation_input_from_snapshot(snapshot)
                    continuation_phase = (
                        continuation_input.get("phase")
                        if continuation_input is not None
                        else None
                    )
                    if (
                        isinstance(continuation_phase, str)
                        and continuation_phase not in continued_terminal_phases
                    ):
                        continued_terminal_phases.add(continuation_phase)
                        logger.warning(
                            "Detached resume continuing from routable terminal "
                            "checkpoint: mission=%s phase=%s",
                            mission_id,
                            continuation_phase,
                        )
                        next_input = continuation_input
                        continue
                    if snapshot is not None and getattr(snapshot, "next", None):
                        logger.warning(
                            "Detached resume continuing from runnable checkpoint: "
                            "mission=%s next=%s",
                            mission_id,
                            getattr(snapshot, "next", None),
                        )
                        next_input = None
                        continue
                # Either no interrupt (graph completed) or interrupt on a
                # different gate (next workflow checkpoint) — exit and let
                # the user's next /resume attach to the new parked frame.
                break
            if current_agent is not None:
                emit_graph_event(mission_id, await _emit_agent_done(current_agent))
            emit_graph_event(mission_id, await _emit_run_end())
            logger.info(
                "Detached resume finished: mission=%s gate=%s",
                mission_id,
                resume_payload.get("gate_id"),
            )
        except asyncio.CancelledError:
            logger.info("Detached resume cancelled: mission=%s", mission_id)
            raise
        except Exception as exc:  # noqa: BLE001 - log and exit cleanly
            logger.exception(
                "Detached resume failed: mission=%s gate=%s err=%s",
                mission_id,
                resume_payload.get("gate_id"),
                exc,
            )
    finally:
        lock.release()
        existing = _detached_drivers.get(mission_id)
        if existing is asyncio.current_task():
            _detached_drivers.pop(mission_id, None)
        queued_payload = _queued_detached_resumes.pop(mission_id, None)
        if queued_payload is not None:
            logger.info(
                "Starting queued detached resume: mission=%s gate=%s",
                mission_id,
                queued_payload.get("gate_id"),
            )
            _spawn_detached_resume(mission_id, queued_payload)


def _spawn_detached_resume(mission_id: str, resume_payload: dict) -> str:
    """Schedule a detached resume task. Idempotent per mission."""
    existing = _detached_drivers.get(mission_id)
    if existing is not None and not existing.done():
        _queued_detached_resumes[mission_id] = resume_payload
        logger.info(
            "Detached resume already running for mission=%s — queued gate=%s",
            mission_id,
            resume_payload.get("gate_id"),
        )
        return "queued"
    task = asyncio.create_task(
        _drive_detached_resume(mission_id, resume_payload),
        name=f"detached-resume-{mission_id}",
    )
    _detached_drivers[mission_id] = task
    return "spawned"


_checkpoint_conn: aiosqlite.Connection | None = None


async def _build_checkpointer():
    """Build the graph checkpointer.

    Default: AsyncSqliteSaver backed by ~/.marvin/checkpoints.db so graph
    state survives uvicorn restarts. Tests / ephemeral runs can opt out via
    MARVIN_CHECKPOINT_BACKEND=memory.
    """
    global _checkpoint_conn
    backend = os.getenv("MARVIN_CHECKPOINT_BACKEND", "sqlite").strip().lower()
    if backend == "memory":
        logger.info("Graph checkpointer: MemorySaver (in-process only)")
        return MemorySaver()

    db_path = os.getenv("MARVIN_CHECKPOINT_DB") or os.path.expanduser("~/.marvin/checkpoints.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    _checkpoint_conn = conn
    logger.info("Graph checkpointer: AsyncSqliteSaver at %s", db_path)
    return saver


async def get_graph():
    """Get compiled graph singleton with checkpointer."""
    global _graph
    async with _graph_lock:
        if _graph is None:
            checkpointer = await _build_checkpointer()
            _graph = build_graph(checkpointer=checkpointer)
        return _graph


# =============================================================================
# STORE FACTORY
# =============================================================================

def get_store() -> MissionStore:
    """Get MissionStore instance. Uses MARVIN_DB_PATH env var if set."""
    db_path = os.getenv("MARVIN_DB_PATH")
    return MissionStore(db_path) if db_path else MissionStore()


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class CreateMissionRequest(BaseModel):
    client: str
    target: str
    ic_question: str = ""
    mission_type: str = "cdd"


class CreateMissionResponse(BaseModel):
    mission_id: str
    status: str
    client: str
    target: str


class MissionSummary(BaseModel):
    id: str
    client: str
    target: str
    mission_type: str
    status: str
    progress: float
    next_checkpoint: str | None
    created_at: str


class ListMissionsResponse(BaseModel):
    missions: list[MissionSummary]


class ChatRequest(BaseModel):
    text: str


class GateValidateRequest(BaseModel):
    # Approval gates supply verdict + optional notes; clarification gates
    # supply answers (one per question); data_decision gates supply a
    # `decision` value (skip_calculus / proceed_low_confidence /
    # request_data_room). All shapes share the endpoint.
    verdict: str | None = None
    notes: str = ""
    answers: list[str] | None = None
    decision: str | None = None


class GateValidateResponse(BaseModel):
    status: Literal[
        "resumed",
        "resumed_detached",
        "validated_no_stream",
        "already_processed",
        "resume_pending",
        "conflict",
    ]
    mission_id: str
    gate_id: str
    resume_id: str
    # Bug 4 (chantier 2.6): idempotency / conflict signal so the frontend
    # can show a toast instead of a console error on double-click.
    idempotent: bool = False
    conflict: bool = False
    message: str | None = None


# =============================================================================
# SSE EVENT EMITTER
# =============================================================================

def _sse_event(event_type: str, data: dict) -> str:
    """Format SSE event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _sse_heartbeat() -> str:
    """SSE heartbeat comment."""
    return ": ping\n\n"


async def _emit_run_start() -> str:
    return _sse_event("run_start", {})


async def _emit_text(agent: str, text: str) -> str:
    display = get_display_name(agent)
    if display is None:
        return ""
    logger.info(f"Emitting text event: agent={display}, text_length={len(text)}")
    return _sse_event("text", {"agent": display, "text": text})


async def _emit_persisted_text(mission_id: str, agent: str, text: str) -> str:
    _persist_chat_message(mission_id, "marvin", text)
    return await _emit_text(agent, text)


def _persist_chat_message(
    mission_id: str,
    role: str,
    text: str,
    *,
    message_id: str | None = None,
    deliverable_id: str | None = None,
    deliverable_label: str | None = None,
    gate_id: str | None = None,
    gate_action: str | None = None,
) -> None:
    clean = str(text or "").strip()
    if not clean:
        return
    try:
        ts = datetime.now(UTC).isoformat()
        store = MissionStore()
        existing = store.list_chat_messages(mission_id)
        seq = len(existing) + 1
        store.save_chat_message(
            MissionChatMessage(
                id=message_id or f"chat-{mission_id}-{uuid.uuid4().hex[:12]}",
                mission_id=mission_id,
                role="user" if role == "user" else "marvin",
                text=clean,
                deliverable_id=deliverable_id,
                deliverable_label=deliverable_label,
                gate_id=gate_id,
                gate_action=gate_action,
                seq=seq,
                created_at=ts,
            )
        )
    except Exception as exc:  # noqa: BLE001 - chat persistence must not break SSE
        logger.warning("chat message persistence failed: %s", exc)


async def _emit_tool_call(agent: str, tool: str) -> str:
    display = get_display_name(agent)
    if display is None:
        return ""
    return _sse_event("tool_call", {"agent": display, "tool": tool})


async def _emit_tool_result(agent: str, text: str) -> str:
    display = get_display_name(agent)
    if display is None:
        return ""
    return _sse_event("tool_result", {"agent": display, "text": text})


def _gate_chat_text(payload: dict) -> str:
    title = str(payload.get("title") or payload.get("gate_type") or "Validation requested").strip()
    summary = str(payload.get("summary") or "").strip()
    parts = [title]
    if summary:
        parts.append(summary)
    parts.append("Use the actions below to continue.")
    return "\n\n".join(parts)


async def _emit_gate_pending(payload: dict, *, mission_id: str | None = None) -> str:
    if mission_id:
        gate_id = str(payload.get("gate_id") or "").strip()
        if gate_id:
            _persist_chat_message(
                mission_id,
                "marvin",
                _gate_chat_text(payload),
                message_id=f"{gate_id}-gate-pending",
                gate_id=gate_id,
                gate_action="pending",
            )
    return _sse_event("gate_pending", payload)


def _open_gate_payload_from_store(store: MissionStore, mission_id: str) -> dict | None:
    """Return the first currently-open gate payload from persisted truth.

    A reconnect should surface an already-open checkpoint, not re-run graph
    nodes just to rediscover the LangGraph interrupt frame.
    """
    try:
        gates = sorted(store.list_gates(mission_id), key=lambda g: (g.scheduled_day, g.id))
        hypotheses = store.list_hypotheses(mission_id)
        findings = store.list_findings(mission_id)
        mission_brief = store.get_mission_brief(mission_id)
        workstreams = store.list_workstreams(mission_id)
        milestones = store.list_milestones(mission_id)
        for gate in gates:
            if gate.status != "pending":
                continue
            if gate.id in _gate_decisions_in_flight:
                continue
            material = evaluate_gate_material(
                store,
                mission_id,
                gate,
                hypotheses=hypotheses,
                findings=findings,
                mission_brief=mission_brief,
                workstreams=workstreams,
                milestones=milestones,
            )
            if not material.is_open:
                continue
            payload = dict(material.review_payload)
            research_findings = payload.get("research_findings", [])
            if isinstance(research_findings, list):
                payload["findings_snapshot"] = research_findings[-3:]
            return payload
    except Exception as exc:  # noqa: BLE001 — reconnect must stay best-effort
        logger.warning("Could not reconstruct open gate for mission=%s: %s", mission_id, exc)
    return None


async def _emit_phase_blocked(payload: dict) -> str:
    return _sse_event("phase_blocked", payload)


async def _emit_finding_added(payload: dict) -> str:
    return _sse_event("finding_added", payload)


async def _emit_milestone_done(payload: dict) -> str:
    return _sse_event("milestone_done", payload)


async def _emit_deliverable_ready(payload: dict) -> str:
    return _sse_event("deliverable_ready", payload)


# Tool name → (event_type, builder) mapping. Builder takes the parsed result dict
# and returns a payload dict, or None if required fields are missing.
def _build_finding_added(result: dict) -> dict | None:
    claim = result.get("claim")
    if not claim:
        return None
    payload = {"text": str(claim)}
    confidence = result.get("confidence")
    if confidence:
        payload["badge"] = str(confidence)
    return payload


def _build_finding_added_from_emit(payload: dict) -> dict:
    """Shape the finding_added SSE payload from a marvin.events emission.

    Propagates full context (agent, workstream, hypothesis, source, timestamp)
    so the rail can render typed entries instead of opaque text+badge."""
    out: dict = {"text": str(payload.get("claim_text", ""))}
    confidence = payload.get("confidence")
    if confidence:
        out["badge"] = str(confidence)
        out["confidence"] = str(confidence)
    for src_key, wire_key in (
        ("finding_id", "findingId"),
        ("agent_id", "agent"),
        ("workstream_id", "workstreamId"),
        ("hypothesis_id", "hypothesisId"),
        ("source_id", "sourceId"),
        ("source_type", "sourceType"),
        ("created_at", "ts"),
    ):
        value = payload.get(src_key)
        if value:
            out[wire_key] = str(value)
    return out


def _build_milestone_done(result: dict) -> dict | None:
    milestone_id = result.get("milestone_id")
    if not milestone_id:
        return None
    payload = {"milestoneId": str(milestone_id)}
    label = result.get("label")
    if label:
        payload["label"] = str(label)
    return payload


def _build_deliverable_ready_from_emit(payload: dict) -> dict:
    out: dict = {"deliverableId": str(payload.get("deliverable_id", ""))}
    for src_key, wire_key in (
        ("deliverable_type", "label"),
        ("deliverable_type", "deliverableType"),
        ("file_path", "filePath"),
        ("file_size_bytes", "fileSizeBytes"),
        ("created_at", "ts"),
    ):
        value = payload.get(src_key)
        if value is not None and value != "":
            out[wire_key] = value if isinstance(value, int) else str(value)
    return out


def _build_papyrus_chat_event(payload: dict, *, mission_id: str | None = None) -> str | None:
    """Build a Papyrus chat bubble SSE string for a freshly persisted deliverable.

    Bug 6: deliverable_ready hydrates the sidebar but produced no chat
    narration — users saw 7 deliverables READY without any Papyrus voice
    confirming generation. Emit one bubble per deliverable so MARVIN feels
    alive and the user has an inline OPEN affordance.
    """
    deliverable_id = str(payload.get("deliverable_id") or "").strip()
    if not deliverable_id:
        return None
    raw_type = str(payload.get("deliverable_type") or "deliverable").strip()
    label = raw_type.replace("_", " ").strip().capitalize() or "Deliverable"
    display = get_display_name("papyrus_delivery") or "Papyrus"
    text = f"{display} — {label} ready. OPEN \u2192"
    if mission_id:
        _persist_chat_message(
            mission_id,
            "marvin",
            text,
            message_id=f"{deliverable_id}-chat",
            deliverable_id=deliverable_id,
            deliverable_label=label,
        )
    return _sse_event("text", {
        "agent": display,
        "text": text,
        "deliverableId": deliverable_id,
    })


_WORKSTREAM_AGENT: dict[str, str] = {
    "W1": "dora",
    "W2": "calculus",
    "W3": "merlin",
    "W4": "adversus",
}


def _build_milestone_done_from_emit(payload: dict) -> dict:
    out: dict = {"milestoneId": str(payload.get("milestone_id", ""))}
    for src_key, wire_key in (
        ("label", "label"),
        ("workstream_id", "workstreamId"),
        ("status", "status"),
        ("result_summary", "resultSummary"),
    ):
        value = payload.get(src_key)
        if value:
            out[wire_key] = str(value)
    # Derive agent attribution from explicit agent_id or workstream_id fallback
    agent_id = payload.get("agent_id") or _WORKSTREAM_AGENT.get(
        str(payload.get("workstream_id", ""))
    )
    if agent_id:
        out["agent"] = str(agent_id)
    return out


_TOOL_EVENT_BUILDERS: dict[str, tuple[str, callable]] = {
    # All three live events (finding_added, deliverable_ready, milestone_done)
    # are owned by listeners in marvin.events registered by _stream_chat — they
    # fire on the persistence chokepoint regardless of whether the LLM picked
    # the tool directly or a deterministic graph node (e.g. runner.research_join,
    # runner._generate_*_impl, dora_tools.moat_analysis) drove the write.
    # Keeping the mapper empty avoids double-fire on the LLM-driven path.
}


def _coerce_tool_result(content: Any) -> dict | None:
    """Best-effort parse of a ToolMessage.content into a dict; never raises."""
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return None
    s = content.strip()
    if not s or s[0] not in "{[":
        return None
    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def map_tool_to_sse_event(tool_name: str | None, content: Any) -> tuple[str, dict] | None:
    """Map a completed ToolMessage to an (event_type, payload) tuple, or None.

    Defensive: unknown tools, non-JSON content, malformed JSON, and missing
    required fields all yield None — never raise.
    """
    if not tool_name:
        return None
    spec = _TOOL_EVENT_BUILDERS.get(tool_name)
    if spec is None:
        return None
    event_type, builder = spec
    result = _coerce_tool_result(content)
    if result is None:
        return None
    try:
        payload = builder(result)
    except Exception:  # noqa: BLE001 — defensive boundary, never let mapper crash the stream
        return None
    if payload is None:
        return None
    return event_type, payload


async def _emit_agent_active(agent: str) -> str:
    """Emit event when an agent starts processing."""
    display = get_display_name(agent)
    if display is None:
        return ""
    return _sse_event("agent_active", {"agent": display})


async def _emit_agent_done(agent: str) -> str:
    display = get_display_name(agent)
    if display is None:
        return ""
    return _sse_event("agent_done", {"agent": display})


async def _emit_agent_message(agent: str, text: str) -> str:
    """Sub-agent prose for the live rail (not chat). Used when a working
    agent like Dora/Calculus emits AIMessage content — the user sees what
    the agent is reasoning about in the rail without flooding the chat."""
    display = get_display_name(agent)
    if display is None:
        return ""
    return _sse_event("agent_message", {"agent": display, "text": text})


async def _emit_run_end() -> str:
    return _sse_event("run_end", {})


_MISSION_COMPLETE_TEXT = (
    "Mission complete. The executive summary, data book, and workstream "
    "reports are ready for review. All deliverables have been generated "
    "and persisted."
)

# Module-level dedup for the closing chat bubble. The text is reachable via
# 5 independent paths (phase=done emit, AIMessage relay from papyrus_delivery,
# defensive run-end emit, terminal-state /resume branch, and the relayed
# broadcast from a detached driver). Without this set, the same mission could
# show up to 3 "Mission complete" bubbles to the user. Cleared on mission
# delete; otherwise persists for the process lifetime (acceptable for a
# display-only signal).
_MISSION_COMPLETE_EMITTED: set[str] = set()


async def _emit_mission_complete_once(mission_id: str | None) -> str:
    """Emit the closing chat bubble at most once per mission per process.

    Returns the SSE string on first call, "" on subsequent calls. mission_id=
    None falls back to unconditional emit (preserves behavior for paths that
    don't have mission scope, e.g. error-handling fallbacks).
    """
    if mission_id is None:
        return await _emit_text("papyrus_delivery", _MISSION_COMPLETE_TEXT)
    if mission_id in _MISSION_COMPLETE_EMITTED:
        return ""
    _MISSION_COMPLETE_EMITTED.add(mission_id)
    return await _emit_text("papyrus_delivery", _MISSION_COMPLETE_TEXT)


async def _maybe_emit_mission_complete(mission_id: str) -> str:
    """Defensive emit: when papyrus_delivery flips status to complete but
    LangGraph drops its final state delta (stream_mode=updates loses the
    last node's emit when it routes straight to END), the user never sees
    the completion message. We check status here and re-emit the standard
    text so the chat reflects truth.

    Idempotent: phase=done is the trigger, mission status=complete is the
    confirmation. Both must hold or this is a no-op.
    """
    try:
        store = get_store()
        mission = store.get_mission(mission_id)
        if mission and mission.status == "complete":
            return await _emit_mission_complete_once(mission_id)
    except Exception:  # noqa: BLE001 — never crash the SSE stream
        pass
    return ""


_PHASE_LABELS: dict[str, str] = {
    "setup": "Setup",
    "framing": "Framing",
    "awaiting_clarification": "Awaiting clarification",
    "awaiting_confirmation": "Hypothesis review pending",
    "confirmed": "Research kickoff",
    "research_done": "Research complete",
    "gate_g1_passed": "Manager review passed",
    "research_rebuttal": "Research rebuttal",
    "rebuttal_done": "Rebuttal complete",
    "redteam_done": "Red-team complete",
    "synthesis_retry": "Synthesis retry",
    "synthesis_done": "Synthesis complete",
    "gate_g3_passed": "Final review passed",
    "done": "Mission complete",
}

_PHASE_NARRATION: dict[str, str] = {
    "setup": "Initializing mission workspace…",
    "framing": "Framing the engagement brief…",
    "awaiting_clarification": "Waiting for the missing context before framing continues.",
    "awaiting_confirmation": "Hypotheses ready for review.",
    "confirmed": "Starting the research workstreams.",
    "research_done": "Research is complete and ready for manager review.",
    "gate_g1_passed": "Manager review passed; starting the red-team challenge.",
    "research_rebuttal": "Research counter-pass: re-running Dora and Calculus on adversus's weakest claims.",
    "rebuttal_done": "Counter-pass complete; back to red-team synthesis.",
    "redteam_done": "Red-team challenge complete; moving into synthesis.",
    "synthesis_retry": "Synthesis needs another challenge pass before final review.",
    "synthesis_done": "Synthesis is complete and ready for final review.",
    "gate_g3_passed": "Final review passed; assembling deliverables.",
    "done": "Mission complete; deliverables are ready for review.",
}

# Bug 8: chat-voice copilot narration. When a major reasoning agent first
# activates we surface a bubble in the chat (not just the rail) so the
# user has a continuous read on what MARVIN is doing. Emitted once per
# (node, phase) tuple — see throttle in _emit_for_update.
_AGENT_CHAT_NARRATION: dict[str, str] = {
    "dora": "Dora is mapping the competitive landscape and pulling sources.",
    "calculus": "Calculus is crunching the financial signals and reconciling the numbers.",
    "adversus": "Adversus is stress-testing the hypotheses and looking for the weakest claims.",
    "merlin": "Merlin is synthesising the verdict from the evidence collected so far.",
    "synthesis_critic": "Refining the synthesis and tightening the IC narrative.",
    "papyrus_phase0": "Papyrus is drafting the framing memo.",
}

_AGENT_NARRATION: dict[str, str] = {
    "dora": "Mapping the competitive landscape",
    "calculus": "Crunching financial signals",
    "adversus": "Stress-testing the hypothesis",
    "merlin": "Synthesising the verdict",
    "synthesis_critic": "Refining the synthesis",
    "papyrus_phase0": "Drafting the framing memo",
    "papyrus_delivery": "Assembling the deliverable",
    "orchestrator": "Coordinating mission tasks",
    "orchestrator_qa": "Running quality checks",
    "framing": "Framing the mission",
    "framing_orchestrator": "Structuring the brief",
}


def _narration_agent(agent: str | None = None) -> str:
    display = get_display_name(agent)
    return display or "MARVIN"


def _agent_narration(agent: str) -> str | None:
    return _AGENT_NARRATION.get(agent)


def _phase_narration(phase: str) -> str | None:
    return _PHASE_NARRATION.get(phase)


def _heartbeat_narration() -> str:
    return "Still working — analysis in progress"


def _gate_narration(payload: dict) -> str:
    title = str(payload.get("title") or payload.get("gate_type") or "Validation required").strip()
    if not title:
        title = "Validation required"
    title = title.replace("_", " ")
    return f"Human review needed: {title}"


def _phase_blocked_narration(payload: dict) -> str:
    message = str(payload.get("message") or "").strip()
    if message:
        return _humanize_blocked_message(message)
    missing = payload.get("missing_material")
    if isinstance(missing, (list, tuple)):
        missing_text = ", ".join(str(item) for item in missing if item)
    else:
        missing_text = ""
    gate_type = str(payload.get("gate_type") or "gate").replace("_", " ")
    if missing_text:
        return _humanize_blocked_message(f"Cannot open {gate_type}: missing {missing_text}")
    return "Review material is still being prepared."


def _humanize_blocked_message(message: str) -> str:
    text = message.strip()
    lower = text.lower()
    if "deliverable_writing_in_progress" in lower or "deliverable writing in progress" in lower:
        return "Deliverable writing in progress."
    if lower.startswith("cannot open"):
        return "Review material is still being prepared."
    return text


async def _emit_narration(agent: str, intent: str) -> str:
    """Emit deterministic user-facing narration for the live rail."""
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return _sse_event("narration", {"agent": _narration_agent(agent), "intent": intent, "ts": ts})


_LIVE_FEED_HEARTBEAT_INTERVAL = 15.0


async def _astream_with_heartbeat(graph, next_input, config, *, current_agent_ref):
    """Yield graph.astream events, emitting a wall-clock 'still working'
    narration every _LIVE_FEED_HEARTBEAT_INTERVAL seconds of silence.

    Live missions reported the live feed appearing frozen during long LLM
    calls because LangGraph's "updates" stream only fires on node completion.
    A 30s adversus pass produced zero events for 30s. This wrapper guarantees
    the user sees something every 15s — either a real graph update or a
    heartbeat narration tagged with the currently-active agent.

    current_agent_ref is a single-element list used as a mutable cell so the
    consumer can update the active agent name without re-entering this
    iterator (Python closures over loop-local rebinds don't work otherwise).
    """
    iterator = graph.astream(next_input, config, stream_mode="updates").__aiter__()
    while True:
        try:
            event = await asyncio.wait_for(
                iterator.__anext__(), timeout=_LIVE_FEED_HEARTBEAT_INTERVAL,
            )
        except asyncio.TimeoutError:
            agent = current_agent_ref[0] if current_agent_ref else None
            if agent:
                yield ("heartbeat", await _emit_narration(agent, _heartbeat_narration()))
            else:
                yield ("heartbeat", _sse_heartbeat())
            continue
        except StopAsyncIteration:
            return
        yield ("event", event)


async def _emit_phase_changed(phase: str) -> str:
    payload = {"phase": phase, "label": _PHASE_LABELS.get(phase, phase)}
    return _sse_event("phase_changed", payload)


async def _emit_error(message: str) -> str:
    return _sse_event("error", {"message": message})


# =============================================================================
# SSE STREAM GENERATOR
# =============================================================================

async def _emit_for_update(
    event: dict,
    current_agent: str | None,
    current_phase: str | None,
    throttle_state: dict[tuple[str, str], float] | None = None,
    mission_id: str | None = None,
) -> tuple[list[str], str | None, str | None, bool]:
    """Translate one graph.astream update into SSE strings.

    Returns (sse_strings, new_current_agent, new_current_phase, is_interrupt).

    throttle_state: mutable dict keyed by (event_type, node_name) → last emit
    timestamp (time.monotonic()). Limits agent_active, tool_call, and agent_done
    events to at most one per 500 ms per (type, node) pair. Pass the same dict
    object across calls within a stream session.
    """
    out: list[str] = []
    if "__interrupt__" in event:
        # When the graph parks at a gate, no further node updates will arrive
        # until the user resumes. Close out the currently-active agent so the
        # left rail doesn't show e.g. "Calculus RUNNING" indefinitely.
        if current_agent is not None:
            out.append(await _emit_agent_done(current_agent))
            current_agent = None
            from marvin.graph.tool_callbacks import set_active_agent
            set_active_agent(mission_id, None)
        interrupts = event["__interrupt__"]
        if isinstance(interrupts, tuple) and interrupts:
            interrupt_value = getattr(interrupts[0], "value", None)
            if isinstance(interrupt_value, dict):
                out.append(await _emit_gate_pending(interrupt_value, mission_id=mission_id))
                out.append(await _emit_narration("workflow", _gate_narration(interrupt_value)))
        return out, current_agent, current_phase, True

    for node_name, output in event.items():
        if not isinstance(output, dict):
            continue

        new_phase = output.get("phase")
        if isinstance(new_phase, str) and new_phase and new_phase != current_phase:
            out.append(await _emit_phase_changed(new_phase))
            phase_intent = _phase_narration(new_phase)
            if phase_intent:
                out.append(await _emit_narration("workflow", phase_intent))
            # Bug 7: when the graph reaches done, surface the closing chat
            # bubble immediately rather than waiting on stream close. The
            # _maybe_emit_mission_complete path on run_end is a defensive
            # catch — this emit fires the moment the phase flips so the user
            # sees "Mission complete" without lag.
            if new_phase == "done":
                out.append(await _emit_mission_complete_once(mission_id))
            current_phase = new_phase

        if output.get("phase_blocked"):
            blocked_payload = output["phase_blocked"]
            out.append(await _emit_phase_blocked(blocked_payload))
            if isinstance(blocked_payload, dict):
                out.append(await _emit_narration("workflow", _phase_blocked_narration(blocked_payload)))
                missing = blocked_payload.get("missing_material") or []
                if isinstance(missing, (list, tuple)) and "research_findings" in missing:
                    out.append(_sse_event("text", {
                        "agent": "MARVIN",
                        "text": (
                            "Research completed but no findings were saved — the manager review gate cannot open. "
                            "Check that the research agents produced findings, or contact support."
                        ),
                    }))

        display = get_display_name(node_name)
        if display is None:
            continue

        # Emit agent_active/agent_done as soon as a node with a display name
        # produces ANY output update — not gated on whether the node happened
        # to emit an AIMessage. This is what makes the agents panel reflect
        # real activity (Bug C). Without this, a node that only persists
        # findings via tools never flips to "running".
        if node_name != current_agent:
            if current_agent is not None:
                _throttle_key_done = ("agent_done", current_agent)
                _now = time.monotonic()
                _last_done = (throttle_state or {}).get(_throttle_key_done, 0.0)
                if _now - _last_done >= 0.5:
                    out.append(await _emit_agent_done(current_agent))
                    if throttle_state is not None:
                        throttle_state[_throttle_key_done] = _now
            current_agent = node_name
            from marvin.graph.tool_callbacks import set_active_agent
            set_active_agent(mission_id, node_name)
            _throttle_key_active = ("agent_active", node_name)
            _now = time.monotonic()
            _last_active = (throttle_state or {}).get(_throttle_key_active, 0.0)
            if _now - _last_active >= 0.5:
                out.append(await _emit_agent_active(node_name))
                if throttle_state is not None:
                    throttle_state[_throttle_key_active] = _now
            # Always emit narration (not throttled) — unique signal per activation.
            _intent = _agent_narration(node_name)
            if _intent:
                out.append(await _emit_narration(node_name, _intent))
            # Bug 8: copilot chat narration — push a one-line bubble into the
            # chat the first time a reasoning agent activates within a phase
            # so the user has a running commentary, not just rail signal.
            # Dedup by (node, phase) via throttle_state so each agent gets
            # at most one bubble per phase even if the node re-enters
            # (e.g., adversus iterating over hypotheses).
            _chat_intent = _AGENT_CHAT_NARRATION.get(node_name)
            if _chat_intent:
                _chat_key = ("chat_narration", f"{node_name}:{current_phase or ''}")
                if throttle_state is None or _chat_key not in throttle_state:
                    out.append(await _emit_text(node_name, _chat_intent))
                    if throttle_state is not None:
                        throttle_state[_chat_key] = time.monotonic()

        messages = list(output.get("messages", []) or [])
        if node_name not in _CHAT_VOICE_NODES:
            last_ai = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
            messages = [last_ai] if last_ai is not None else []

        for msg in messages:
            if isinstance(msg, AIMessage):
                if msg.content:
                    if node_name in _CHAT_VOICE_NODES:
                        # papyrus_delivery's AIMessage carries the same closing
                        # text that the phase=="done" branch already emitted via
                        # _emit_mission_complete_once. Skip to avoid double-fire
                        # within a single update.
                        if (
                            node_name == "papyrus_delivery"
                            and isinstance(msg.content, str)
                            and msg.content.strip().startswith("Mission complete.")
                        ):
                            pass
                        else:
                            # Marvin's voice — host nodes speak to the user in chat.
                            out.append(await _emit_text(node_name, msg.content))
                    else:
                        # Working sub-agent reasoning — surface in rail only,
                        # keep chat clean. Mission events (findings/milestones)
                        # still flow through their own persistence-driven SSE
                        # events; this is purely the prose stream.
                        out.append(await _emit_agent_message(node_name, msg.content))
                # AIMessage may carry pending tool_calls before the matching
                # ToolMessage is appended. Surface them in the rail so the user
                # sees who's about to call which tool.
                tool_calls = getattr(msg, "tool_calls", None) or []
                for call in tool_calls:
                    name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                    if (
                        name
                        and _show_raw_tool_events()
                        and not _is_trace_only_tool(str(name))
                    ):
                        _throttle_key_tc = ("tool_call", node_name)
                        _now_tc = time.monotonic()
                        _last_tc = (throttle_state or {}).get(_throttle_key_tc, 0.0)
                        if _now_tc - _last_tc >= 0.5:
                            out.append(await _emit_tool_call(node_name, str(name)))
                            if throttle_state is not None:
                                throttle_state[_throttle_key_tc] = _now_tc
            elif isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", "tool")
                summary = _get_tool_summary(tool_name, {"result": msg.content})
                if _is_trace_only_tool(tool_name):
                    pass
                elif summary:
                    out.append(await _emit_tool_result(node_name, summary))
                elif msg.content and _is_user_facing_tool_text(str(msg.content)[:200]):
                    out.append(await _emit_tool_result(node_name, str(msg.content)[:200]))

                mapped = map_tool_to_sse_event(tool_name, msg.content)
                if mapped is not None:
                    event_type, payload = mapped
                    if event_type == "finding_added":
                        out.append(await _emit_finding_added(payload))
                    elif event_type == "milestone_done":
                        out.append(await _emit_milestone_done(payload))
                    elif event_type == "deliverable_ready":
                        out.append(await _emit_deliverable_ready(payload))

    return out, current_agent, current_phase, False


async def _stream_chat(
    mission_id: str,
    text: str,
    reset: bool = False,
) -> AsyncIterator[str]:
    """
    Generate SSE stream for chat interaction.
    Uses astream() instead of astream_events() for better compatibility with Send nodes.
    """
    store = get_store()
    _persist_chat_message(mission_id, "user", text)
    
    # Verify mission exists
    if not _mission_exists(store, mission_id):
        yield await _emit_error(f"Mission not found: {mission_id}")
        return
    
    mission = store.get_mission(mission_id)

    # Verify mission status
    if mission.status != "active":
        yield await _emit_error(f"Mission is not active: {mission.status}")
        return

    # C-CONV — fast-path for steering instructions while a detached resume
    # is running. The detached driver holds the mission lock for the full
    # research+synthesis pass; without this fast-path a user instruction
    # would 5s-timeout on the lock acquire below. Classify before acquiring
    # the lock so a `steer` message just writes to the steering table and
    # returns. QA still goes through the locked path so the existing
    # interrupted-gate routing keeps working.
    existing_brief_for_steer = store.get_mission_brief(mission_id)
    if existing_brief_for_steer and (existing_brief_for_steer.raw_brief or "").strip():
        from marvin.conversational.steering import classify_message, queue_steering
        _early_intent = classify_message(text)
        if _early_intent == "steer":
            yield await _emit_run_start()
            try:
                queue_steering(mission_id, text)
                yield await _emit_persisted_text(
                    mission_id,
                    "orchestrator",
                    "Got it. The next agent that runs will pick up your "
                    "instruction. To stop the mission and re-frame, reject "
                    "the next gate.",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("steering queue failed: %s", exc)
                yield await _emit_persisted_text(
                    mission_id,
                    "orchestrator",
                    "Could not queue your instruction; please retry.",
                )
            yield await _emit_run_end()
            return
        elif _early_intent == "rerun":
            yield await _emit_run_start()
            yield await _emit_persisted_text(
                mission_id,
                "orchestrator",
                "Reruns can be triggered from the agent cards in the left panel — "
                "click the agent name to see the option. If research is still running, "
                "it will complete first.",
            )
            yield await _emit_run_end()
            return

    # Get per-mission lock to prevent concurrent runs
    mission_lock = _get_mission_lock(mission_id)
    
    try:
        acquired = await asyncio.wait_for(mission_lock.acquire(), timeout=5.0)
        if not acquired:
            yield await _emit_error("Another chat session is active for this mission")
            return
    except asyncio.TimeoutError:
        yield await _emit_error("Could not acquire mission lock - please retry")
        return
    
    try:
        yield await _emit_run_start()
        yield _sse_heartbeat()

        # Mode detection: continuation vs initial brief.
        # If a brief is already persisted, this chat message is a continuation
        # (Q&A) and must NOT replay the mission flow. We answer in 1-3 sentences
        # via orchestrator_qa and skip the graph entirely. The user uses the
        # gate UI (POST /gates/{id}/validate) to advance the mission.
        existing_brief = store.get_mission_brief(mission_id)
        has_brief = bool(existing_brief and (existing_brief.raw_brief or "").strip())
        is_initial_brief = (not has_brief) and len(text.strip()) >= 50

        graph = await get_graph()
        chat_resume_payload: dict[str, Any] | None = None
        chat_resume_gate_id: str | None = None

        if has_brief or not is_initial_brief:
            # Chantier 2.7 FIX 3 — chat-driven gate approval.
            # If the graph is parked at a standard verdict gate AND the user
            # message is approval-like, validate the gate in-line and resume.
            # Anything ambiguous (questions, multi-sentence prose, rejections)
            # falls through to orchestrator_qa with the gate as context.
            config_check = {"configurable": {"thread_id": mission_id}}
            try:
                snapshot = await graph.aget_state(config_check)
            except Exception as exc:  # noqa: BLE001 - defensive: missing aget_state in tests
                logger.debug("aget_state unavailable: %s", exc)
                snapshot = None
            is_interrupted = bool(snapshot and snapshot.next)
            pending_gate = None
            if is_interrupted:
                for g in store.list_gates(mission_id):
                    if g.status != "pending":
                        continue
                    # Approval shortcut applies only to gates that take a
                    # boolean verdict. Clarifications need answers; data
                    # decisions need a discrete option — both must use the UI.
                    if g.format in ("clarification_questions", "data_decision"):
                        continue
                    # Fix B: a DB row marked status='pending' is a *seeded*
                    # row, not necessarily the gate the graph is parked at.
                    # G1/G3 are seeded pending at mission init; while research
                    # is running, G3's row says pending even though merlin
                    # hasn't produced a verdict yet. Use evaluate_gate_material
                    # to filter for gates that actually have all required
                    # material — those are the gates the graph would
                    # interrupt on. This stops orchestrator_qa from claiming
                    # "G3 is pending" mid-research and stops chat-driven
                    # approve from delivering verdicts to the wrong gate.
                    material = evaluate_gate_material(store, mission_id, g)
                    if not material.is_open:
                        continue
                    pending_gate = g
                    break

            if pending_gate is not None and _is_approval_text(text):
                resume_id = f"resume-{uuid.uuid4().hex[:8]}"
                chat_resume_payload = {
                    "approved": True,
                    "verdict": "APPROVED",
                    "notes": text.strip(),
                    "gate_id": pending_gate.id,
                }
                chat_resume_gate_id = pending_gate.id
                _mark_gate_decision_in_flight(
                    mission_id,
                    pending_gate.id,
                    expected_status="completed",
                    verdict="APPROVED",
                    resume_id=resume_id,
                )
                # Do NOT pre-write status="completed" here. gate_node re-runs
                # from the top on Command(resume=...); if the gate row is
                # already completed, evaluate_gate_material() returns
                # is_open=False and the node bails to phase="idle" instead of
                # routing to adversus/merlin. Let gate_node own the verdict
                # persistence + routing on the post-interrupt branch — the
                # same path used by /gates/{id}/validate.
                logger.info(
                    "Chat-driven gate approval: mission=%s gate=%s",
                    mission_id, pending_gate.id,
                )
                # #4: when the user types "approve" in chat (vs. clicking the
                # banner Approve button), the UI's handleGateApprove path is
                # NOT invoked — so no chat bubble confirms the action. Without
                # this emit, the very next thing the user sees is the next
                # agent narration ("Adversus is stress-testing…", "Merlin is
                # synthesising…") with no acknowledgement that the gate just
                # opened. Mirror the banner-click confirmation here.
                _gate_label = {
                    "hypothesis_confirmation": "G1 — research approved",
                    "manager_review": "G2 — red-team approved",
                    "final_review": "G3 — IC sign-off",
                }.get(pending_gate.gate_type, "Gate approved")
                yield await _emit_persisted_text(
                    mission_id,
                    "orchestrator",
                    f"✓ {_gate_label}. Continuing the mission.",
                )
            else:
                # C-CONV — when the graph is *running* (not interrupted) the
                # user can either ask a question (read-only QA) or send a
                # steering instruction. Classify and queue if instruction.
                if not is_interrupted:
                    from marvin.conversational.steering import (
                        classify_message,
                        queue_steering,
                    )

                    intent = classify_message(text)
                    if intent == "steer":
                        try:
                            queue_steering(mission_id, text)
                            yield await _emit_persisted_text(
                                mission_id,
                                "orchestrator",
                                "Got it. The next agent that runs will pick "
                                "up your instruction. To stop the mission "
                                "and re-frame, reject the next gate.",
                            )
                            yield await _emit_run_end()
                            return
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "queue_steering failed: %s — falling through to QA",
                                exc,
                            )
                    elif intent == "rerun":
                        yield await _emit_persisted_text(
                            mission_id,
                            "orchestrator",
                            "Reruns can be triggered from the agent cards in the left panel — "
                            "click the agent name to see the option. If research is still running, "
                            "it will complete first.",
                        )
                        yield await _emit_run_end()
                        return

                from marvin.graph.subgraphs.orchestrator_qa import respond_qa

                qa_input = text
                if pending_gate is not None:
                    qa_input = (
                        f"[graph paused at gate {pending_gate.gate_type or pending_gate.id} "
                        f"— reply 'approve' to proceed or click Review] {text}"
                    )
                try:
                    reply = await respond_qa(
                        mission_id,
                        qa_input,
                        interrupted_gate_id=(pending_gate.id if pending_gate else None),
                        interrupt_known=True,
                    )
                except Exception as exc:  # noqa: BLE001 - defensive: never crash the SSE stream
                    logger.warning("orchestrator_qa failed: %s", exc)
                    reply = "Mission paused. Use the gate panel to continue."
                if reply:
                    yield await _emit_persisted_text(mission_id, "orchestrator", reply)
                yield await _emit_run_end()
                return

        # Build initial state
        initial_state: MarvinState = {
            "messages": [HumanMessage(content=text)],
            "mission_id": mission_id,
            "phase": "setup",
        }
        
        # Guard: verify mission_id is present
        if not initial_state.get("mission_id"):
            yield await _emit_error("mission_id missing from state")
            return
        
        logger.info(f"Starting stream with state: mission_id={initial_state.get('mission_id')}, phase={initial_state.get('phase')}")

        if is_initial_brief:
            yield await _emit_persisted_text(
                mission_id,
                "orchestrator",
                "Framing the deal thesis from your brief — pulling out the "
                "target, scope, and key questions before kicking off research.",
            )

        thread_id = mission_id
        # Wave 1 transparency: attach the tool-callback handler so every
        # tool invocation inside an agent node emits an SSE narration event,
        # turning the previously-blank intra-node periods into a live trace.
        from marvin.graph.tool_callbacks import MarvinToolCallbacks
        config = {
            "configurable": {
                "thread_id": thread_id,
            },
            "callbacks": [MarvinToolCallbacks(mission_id)],
        }

        current_agent = None
        current_phase: str | None = None
        throttle_state: dict[tuple[str, str], float] = {}
        heartbeat_counter = 0
        # Chat-driven approval (FIX 3) bypasses the initial-brief state and
        # drives the parked checkpoint forward via Command(resume=...). The
        # gate_id clear runs in the same cleanup path as a UI-driven resume.
        if chat_resume_payload is not None:
            next_input: Any = Command(resume=chat_resume_payload)
            resume_payload_to_clear: dict[str, Any] | None = chat_resume_payload
        else:
            next_input = initial_state
            resume_payload_to_clear = None

        # Recovery payload — set whenever we're mid-flight through a
        # Command(resume=...) astream pass. If the SSE socket dies and our
        # task is cancelled before astream finishes, the outer finally spawns
        # a detached driver with this payload so the graph still advances.
        # Without this, gate is "approved" in DB but graph stalls until the
        # user manually clicks /resume — the "stop after approve / reprend
        # out of nowhere" symptom.
        pending_recovery_payload: dict[str, Any] | None = chat_resume_payload
        graph_pass_in_flight = False

        # Side channel for finding_added events. The listener fires from
        # whichever thread the persistence call runs on (LangGraph tools run
        # in run_in_executor), so we use a thread-safe queue.Queue and drain
        # it from the async loop between graph events.
        finding_q: "queue.Queue[dict]" = queue.Queue()
        deliverable_q: "queue.Queue[dict]" = queue.Queue()
        milestone_q: "queue.Queue[dict]" = queue.Queue()
        graph_event_q: "queue.Queue[str]" = queue.Queue()

        def _on_finding(payload: dict) -> None:
            finding_q.put_nowait(payload)

        def _on_deliverable(payload: dict) -> None:
            deliverable_q.put_nowait(payload)

        def _on_milestone(payload: dict) -> None:
            milestone_q.put_nowait(payload)

        def _on_graph_event(sse_string: str) -> None:
            graph_event_q.put_nowait(sse_string)

        register_finding_listener(mission_id, _on_finding)
        register_deliverable_listener(mission_id, _on_deliverable)
        register_milestone_listener(mission_id, _on_milestone)
        register_graph_event_listener(mission_id, _on_graph_event)

        papyrus_chat_emitted: set[str] = set()

        def _drain_events() -> list[str]:
            out: list[str] = []
            while True:
                try:
                    payload = finding_q.get_nowait()
                except queue.Empty:
                    break
                out.append(_sse_event("finding_added", _build_finding_added_from_emit(payload)))
            while True:
                try:
                    payload = deliverable_q.get_nowait()
                except queue.Empty:
                    break
                out.append(_sse_event("deliverable_ready", _build_deliverable_ready_from_emit(payload)))
                deliverable_id = str(payload.get("deliverable_id") or "").strip()
                if deliverable_id and deliverable_id not in papyrus_chat_emitted:
                    chat_event = _build_papyrus_chat_event(payload, mission_id=mission_id)
                    if chat_event:
                        out.append(chat_event)
                        papyrus_chat_emitted.add(deliverable_id)
            while True:
                try:
                    payload = milestone_q.get_nowait()
                except queue.Empty:
                    break
                out.append(_sse_event("milestone_done", _build_milestone_done_from_emit(payload)))
            while True:
                try:
                    sse_string = graph_event_q.get_nowait()
                except queue.Empty:
                    break
                out.append(sse_string)
            return out

        # Drive the graph; on each __interrupt__ frame, park on a per-mission
        # resume future and continue with Command(resume=...) on the same
        # thread_id. Loop terminates when astream finishes without an
        # interrupt or when the resume wait times out.
        while True:
            interrupted = False
            clearing_resume_payload = resume_payload_to_clear
            resume_payload_to_clear = None
            pending_recovery_payload = clearing_resume_payload
            agent_ref: list[str | None] = [current_agent]
            try:
                graph_pass_in_flight = True
                async for kind, payload in _astream_with_heartbeat(
                    graph, next_input, config, current_agent_ref=agent_ref,
                ):
                    if kind == "heartbeat":
                        yield payload
                        continue
                    event = payload
                    heartbeat_counter += 1
                    if heartbeat_counter % 10 == 0:
                        yield _sse_heartbeat()

                    if not isinstance(event, dict):
                        continue

                    sse_strings, current_agent, current_phase, is_interrupt = await _emit_for_update(
                        event, current_agent, current_phase, throttle_state, mission_id=mission_id
                    )
                    agent_ref[0] = current_agent
                    if is_interrupt or current_phase == "done":
                        # Flush side-channel queues before gate_pending (and
                        # before mission-complete) so deliverable_ready events
                        # reach the client before the completion message.
                        for s in _drain_events():
                            yield s
                    for s in sse_strings:
                        if s:
                            yield s
                    if not is_interrupt and current_phase != "done":
                        for s in _drain_events():
                            yield s
                    if is_interrupt:
                        interrupted = True
                graph_pass_in_flight = False
            finally:
                if clearing_resume_payload is not None:
                    _clear_gate_decision_in_flight(clearing_resume_payload.get("gate_id"))

            # astream pass returned cleanly — no recovery needed for that
            # payload anymore.
            pending_recovery_payload = None

            for s in _drain_events():
                yield s

            if not interrupted:
                break

            fut = _register_pending_resume(mission_id)
            try:
                resume_payload = await asyncio.wait_for(fut, timeout=_RESUME_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                yield await _emit_error("Gate approval timed out")
                break
            except asyncio.CancelledError:
                _clear_gate_decision_for_mission(mission_id)
                raise
            finally:
                _clear_pending_resume(mission_id, fut)

            resume_payload_to_clear = resume_payload
            next_input = Command(resume=resume_payload)

        if current_agent is not None:
            yield await _emit_agent_done(current_agent)

        # Bug 7: skip the defensive completion emit if the phase=="done"
        # transition already pushed the closing bubble during the update
        # stream, otherwise the user sees the message twice.
        if current_phase != "done":
            completion = await _maybe_emit_mission_complete(mission_id)
            if completion:
                yield completion
        yield await _emit_run_end()

    except Exception as e:
        import traceback as _tb
        tb_text = _tb.format_exc()
        logger.exception(f"Error in chat stream: {e}")
        # Surface traceback frames in the SSE error event so silent runtime
        # failures can be diagnosed from client-side capture (no log file
        # access required). Truncate to keep payload small.
        last_frames = "\n".join(tb_text.splitlines()[-12:])
        yield await _emit_error(f"{type(e).__name__}: {e}\n{last_frames}")
    
    finally:
        try:
            unregister_finding_listener(mission_id, _on_finding)
        except (NameError, UnboundLocalError):
            pass
        try:
            unregister_deliverable_listener(mission_id, _on_deliverable)
        except (NameError, UnboundLocalError):
            pass
        try:
            unregister_milestone_listener(mission_id, _on_milestone)
        except (NameError, UnboundLocalError):
            pass
        try:
            unregister_graph_event_listener(mission_id, _on_graph_event)
        except (NameError, UnboundLocalError):
            pass
        mission_lock.release()
        # Recovery: if our task is dying (cancellation / SSE socket dead /
        # unhandled exception) while a Command(resume=payload) astream pass
        # was in flight, spawn a detached driver to advance the graph from
        # the parked checkpoint. Without this, gate is "approved" in the DB
        # but the graph stalls — the "stop after approve / reprend out of
        # nowhere" symptom (validate_gate's fast path returned status=resumed
        # because we were parked, but the resume never reached the next
        # interrupt or completion before our task got cut off).
        try:
            recovery_payload = pending_recovery_payload  # type: ignore[name-defined]
        except NameError:
            recovery_payload = None
        try:
            unfinished_graph_pass = bool(graph_pass_in_flight)  # type: ignore[name-defined]
        except NameError:
            unfinished_graph_pass = False
        if recovery_payload is None and unfinished_graph_pass:
            recovery_payload = {
                "gate_id": None,
                "reason": "stream_cancelled_during_graph_pass",
            }
        if recovery_payload is not None:
            try:
                _spawn_detached_resume(mission_id, recovery_payload)
                logger.warning(
                    "Spawned recovery detached driver after _stream_chat exit: "
                    "mission=%s gate=%s",
                    mission_id,
                    recovery_payload.get("gate_id"),
                )
            except Exception:  # noqa: BLE001 — best-effort recovery
                logger.exception(
                    "Recovery detached driver spawn failed: mission=%s",
                    mission_id,
                )


async def _stream_resume_passive(
    mission_id: str, detached_task: asyncio.Task
) -> AsyncIterator[str]:
    """Relay events from a running detached driver to a re-attached SSE client.

    F1-A. The detached driver (`_drive_detached_resume`) holds the mission lock
    for the entire graph run, so a re-attaching `/resume` cannot acquire it and
    cannot run its own `graph.astream`. Instead we subscribe to:

      * the graph-event channel (`emit_graph_event`) for SSE strings the driver
        broadcasts (agent_active, narration, phase_changed, text, agent_done,
        run_start/run_end);
      * the persistence channels (finding/deliverable/milestone) for events
        the agent tools emit when writing to the store.

    We yield to the client until the detached task completes, then return.
    """
    sse_q: "queue.Queue[str]" = queue.Queue()
    finding_q: "queue.Queue[dict]" = queue.Queue()
    deliverable_q: "queue.Queue[dict]" = queue.Queue()
    milestone_q: "queue.Queue[dict]" = queue.Queue()

    def _on_sse(s: str) -> None:
        sse_q.put_nowait(s)

    def _on_finding(payload: dict) -> None:
        finding_q.put_nowait(payload)

    def _on_deliverable(payload: dict) -> None:
        deliverable_q.put_nowait(payload)

    def _on_milestone(payload: dict) -> None:
        milestone_q.put_nowait(payload)

    register_graph_event_listener(mission_id, _on_sse)
    register_finding_listener(mission_id, _on_finding)
    register_deliverable_listener(mission_id, _on_deliverable)
    register_milestone_listener(mission_id, _on_milestone)

    papyrus_chat_emitted: set[str] = set()

    try:
        # The driver may already have emitted run_start before we attached.
        # Emit a defensive run_start so the client's UI flips out of stalled
        # state regardless of attach timing.
        yield await _emit_run_start()
        while True:
            drained_any = False
            while True:
                try:
                    yield sse_q.get_nowait()
                    drained_any = True
                except queue.Empty:
                    break
            while True:
                try:
                    payload = finding_q.get_nowait()
                except queue.Empty:
                    break
                yield _sse_event("finding_added", _build_finding_added_from_emit(payload))
                drained_any = True
            while True:
                try:
                    payload = deliverable_q.get_nowait()
                except queue.Empty:
                    break
                yield _sse_event("deliverable_ready", _build_deliverable_ready_from_emit(payload))
                deliverable_id = str(payload.get("deliverable_id") or "").strip()
                if deliverable_id and deliverable_id not in papyrus_chat_emitted:
                    chat_event = _build_papyrus_chat_event(payload, mission_id=mission_id)
                    if chat_event:
                        yield chat_event
                        papyrus_chat_emitted.add(deliverable_id)
                drained_any = True
            while True:
                try:
                    payload = milestone_q.get_nowait()
                except queue.Empty:
                    break
                yield _sse_event("milestone_done", _build_milestone_done_from_emit(payload))
                drained_any = True

            if detached_task.done():
                next_detached = _detached_drivers.get(mission_id)
                if next_detached is not None and next_detached is not detached_task and not next_detached.done():
                    detached_task = next_detached
                    continue
                break
            # Tight poll when events were just drained; back off when idle so
            # we don't burn CPU. 50ms keeps the feed visually live.
            await asyncio.sleep(0.0 if drained_any else 0.05)

        # Final drain after the driver finishes.
        while not sse_q.empty():
            try:
                yield sse_q.get_nowait()
            except queue.Empty:
                break
        while not finding_q.empty():
            try:
                payload = finding_q.get_nowait()
            except queue.Empty:
                break
            yield _sse_event("finding_added", _build_finding_added_from_emit(payload))
        while not deliverable_q.empty():
            try:
                payload = deliverable_q.get_nowait()
            except queue.Empty:
                break
            yield _sse_event("deliverable_ready", _build_deliverable_ready_from_emit(payload))
            deliverable_id = str(payload.get("deliverable_id") or "").strip()
            if deliverable_id and deliverable_id not in papyrus_chat_emitted:
                chat_event = _build_papyrus_chat_event(payload, mission_id=mission_id)
                if chat_event:
                    yield chat_event
                    papyrus_chat_emitted.add(deliverable_id)
        while not milestone_q.empty():
            try:
                payload = milestone_q.get_nowait()
            except queue.Empty:
                break
            yield _sse_event("milestone_done", _build_milestone_done_from_emit(payload))

        yield await _emit_run_end()
    finally:
        unregister_graph_event_listener(mission_id, _on_sse)
        unregister_finding_listener(mission_id, _on_finding)
        unregister_deliverable_listener(mission_id, _on_deliverable)
        unregister_milestone_listener(mission_id, _on_milestone)


async def _stream_resume(mission_id: str) -> AsyncIterator[str]:
    """Re-attach to a checkpointed mission and continue streaming.

    Chantier 2.7 FIX 2. Used when the client lost the SSE connection (tab
    close, network blip, process restart). Reads the LangGraph checkpoint:

    - Terminal: emit phase + run_end so the UI flips to done.
    - Interrupted: replay astream(None) so the parked interrupt frame fires
      again, then enter the same park/resume loop as _stream_chat.
    - No checkpoint: emit error — initial brief still flows through /chat.
    """
    store = get_store()
    if not _mission_exists(store, mission_id):
        yield await _emit_error(f"Mission not found: {mission_id}")
        return

    mission = store.get_mission(mission_id)
    if mission.status != "active":
        # Done/archived missions need no live stream — but a re-attach should
        # still show the user the final completion state, otherwise the chat
        # log on a refresh ends mid-flow.
        if mission.status == "complete":
            yield await _emit_phase_changed("done")
            bubble = await _emit_mission_complete_once(mission_id)
            if bubble:
                yield bubble
        yield await _emit_run_end()
        return

    mission_lock = _get_mission_lock(mission_id)
    detached = _detached_drivers.get(mission_id)
    if detached is not None and not detached.done():
        async for s in _stream_resume_passive(mission_id, detached):
            yield s
        return

    try:
        await asyncio.wait_for(mission_lock.acquire(), timeout=5.0)
    except asyncio.TimeoutError:
        # F1-A: if a detached driver is running, attach as a passive listener
        # instead of erroring out. The driver does the driving; we relay its
        # broadcast SSE strings + persistence-bus events to this client.
        detached = _detached_drivers.get(mission_id)
        if detached is not None and not detached.done():
            async for s in _stream_resume_passive(mission_id, detached):
                yield s
            return
        yield await _emit_error("Mission is active in another stream — close the other tab")
        return

    try:
        graph = await get_graph()
        thread_id = mission_id
        from marvin.graph.tool_callbacks import MarvinToolCallbacks
        config = {
            "configurable": {"thread_id": thread_id},
            "callbacks": [MarvinToolCallbacks(mission_id)],
        }

        snapshot = await graph.aget_state(config)
        # No checkpoint at all → nothing to replay. Don't surface as an error;
        # this is the legitimate state right after mission creation, before the
        # user sends the brief via /chat. The UI calls /resume on mount
        # unconditionally, so silent run_end is the right answer.
        if snapshot is None or not (snapshot.values or {}):
            yield await _emit_run_end()
            return

        open_gate_payload = _open_gate_payload_from_store(store, mission_id)
        continuation_input: dict[str, Any] | None = None

        # Terminal state: graph completed cleanly, unless the persisted phase
        # is a routable boundary that still needs to drive the next node.
        if not snapshot.next and open_gate_payload is None:
            continuation_input = None if open_gate_payload is not None else _continuation_input_from_snapshot(snapshot)
            if continuation_input is not None:
                logger.warning(
                    "Continuing mission from routable terminal checkpoint: "
                    "mission=%s phase=%s",
                    mission_id,
                    continuation_input.get("phase"),
                )
            else:
                phase = (snapshot.values or {}).get("phase")
                if isinstance(phase, str) and phase:
                    yield await _emit_phase_changed(phase)
                yield await _emit_run_end()
                return

        if continuation_input is None:
            phase = (snapshot.values or {}).get("phase")
            # 9-bug triage H: the graph is interrupted. If a gate is currently
            # parked, the in-process notify-guard (`_GATE_PENDING_NOTIFIED`) may
            # suppress re-emission of `gate_pending` on the astream(None) replay
            # below — leaving a fresh client (page reload, second tab) without
            # the gate banner the user expects. Clear the guard for the pending
            # gate so the interrupt frame re-fires its SSE event.
            try:
                from marvin.graph.gates import _GATE_PENDING_NOTIFIED
                pending_gate_id = (snapshot.values or {}).get("pending_gate_id")
                if isinstance(pending_gate_id, str) and pending_gate_id:
                    # Do not clear the guard if an approval is already in-flight
                    # for this gate — clearing it would cause gate_node to re-emit
                    # gate_pending on the astream(None) replay, surfacing a stale
                    # gate banner to the reconnecting client and requiring a second
                    # click to advance the graph.
                    if pending_gate_id not in _gate_decisions_in_flight:
                        _GATE_PENDING_NOTIFIED.discard(pending_gate_id)
            except Exception:  # noqa: BLE001 — defensive boundary
                pass

        yield await _emit_run_start()
        yield _sse_heartbeat()

        finding_q: "queue.Queue[dict]" = queue.Queue()
        deliverable_q: "queue.Queue[dict]" = queue.Queue()
        milestone_q: "queue.Queue[dict]" = queue.Queue()
        graph_event_q: "queue.Queue[str]" = queue.Queue()

        def _on_finding(payload: dict) -> None:
            finding_q.put_nowait(payload)

        def _on_deliverable(payload: dict) -> None:
            deliverable_q.put_nowait(payload)

        def _on_milestone(payload: dict) -> None:
            milestone_q.put_nowait(payload)

        def _on_graph_event(sse_string: str) -> None:
            graph_event_q.put_nowait(sse_string)

        register_finding_listener(mission_id, _on_finding)
        register_deliverable_listener(mission_id, _on_deliverable)
        register_milestone_listener(mission_id, _on_milestone)
        register_graph_event_listener(mission_id, _on_graph_event)

        papyrus_chat_emitted: set[str] = set()

        def _drain_events() -> list[str]:
            out: list[str] = []
            while True:
                try:
                    payload = finding_q.get_nowait()
                except queue.Empty:
                    break
                out.append(_sse_event("finding_added", _build_finding_added_from_emit(payload)))
            while True:
                try:
                    payload = deliverable_q.get_nowait()
                except queue.Empty:
                    break
                out.append(_sse_event("deliverable_ready", _build_deliverable_ready_from_emit(payload)))
                deliverable_id = str(payload.get("deliverable_id") or "").strip()
                if deliverable_id and deliverable_id not in papyrus_chat_emitted:
                    chat_event = _build_papyrus_chat_event(payload, mission_id=mission_id)
                    if chat_event:
                        out.append(chat_event)
                        papyrus_chat_emitted.add(deliverable_id)
            while True:
                try:
                    payload = milestone_q.get_nowait()
                except queue.Empty:
                    break
                out.append(_sse_event("milestone_done", _build_milestone_done_from_emit(payload)))
            while True:
                try:
                    sse_string = graph_event_q.get_nowait()
                except queue.Empty:
                    break
                out.append(sse_string)
            return out

        current_agent: str | None = None
        current_phase: str | None = (snapshot.values or {}).get("phase") if isinstance((snapshot.values or {}).get("phase"), str) else None
        throttle_state: dict[tuple[str, str], float] = {}
        heartbeat_counter = 0

        # Replay persistence-owned events from the store before driving the
        # graph. If the SSE socket died during a long-running phase (e.g.
        # research_join's 3-5 min synchronous report compilation), the
        # corresponding finding/deliverable/milestone events that fired
        # during that window are gone — they were drained from the dead
        # stream's queue, never reached the client, and the LangGraph
        # checkpoint replay below only re-fires the parked gate_pending.
        # Without this, a reconnecting client sees gate_pending without the
        # outputs it's supposed to validate. We emit the store's current
        # rows so the UI rehydrates findings/deliverables/milestones before
        # the gate banner appears.
        try:
            for f in store.list_findings(mission_id):
                payload = {
                    "claim_text": f.claim_text,
                    "confidence": f.confidence,
                    "finding_id": f.id,
                    "agent_id": f.agent_id,
                    "workstream_id": f.workstream_id,
                    "hypothesis_id": f.hypothesis_id,
                    "source_id": f.source_id,
                    "source_type": f.source_type,
                    "created_at": f.created_at,
                }
                yield _sse_event("finding_added", _build_finding_added_from_emit(payload))
            for d in store.list_deliverables(mission_id):
                if d.status != "ready":
                    continue
                payload = {
                    "deliverable_id": d.id,
                    "deliverable_type": d.deliverable_type,
                    "file_path": d.file_path,
                    "file_size_bytes": d.file_size_bytes,
                    "created_at": d.created_at,
                }
                yield _sse_event("deliverable_ready", _build_deliverable_ready_from_emit(payload))
                chat_event = _build_papyrus_chat_event(payload)
                if chat_event:
                    yield chat_event
                    papyrus_chat_emitted.add(d.id)
            for m in store.list_milestones(mission_id):
                if m.status not in ("delivered", "blocked"):
                    continue
                payload = {
                    "milestone_id": m.id,
                    "label": m.label,
                    "workstream_id": m.workstream_id,
                    "status": m.status,
                    "result_summary": m.result_summary,
                }
                yield _sse_event("milestone_done", _build_milestone_done_from_emit(payload))
        except Exception as exc:  # noqa: BLE001 — replay best-effort
            logger.warning(
                "Store replay failed for mission=%s: %s", mission_id, exc
            )

        if open_gate_payload is not None:
            yield await _emit_gate_pending(open_gate_payload, mission_id=mission_id)
            yield await _emit_narration("workflow", _gate_narration(open_gate_payload))
            yield await _emit_run_end()
            return

        # First iteration: None drives astream from an interrupted checkpoint.
        # For a routable terminal checkpoint, feed the persisted state so the
        # START phase_router can continue to the next workflow node.
        # Subsequent iterations use Command(resume=payload) after a gate decision.
        next_input: Any = continuation_input
        resume_payload_to_clear: dict[str, Any] | None = None
        # Recovery payload — see _stream_chat for rationale. If a post-resume
        # astream pass crashes/cancels, the outer finally spawns a detached
        # driver with this payload so the graph still advances.
        pending_recovery_payload: dict[str, Any] | None = None
        graph_pass_in_flight = False
        resume_steps = 0
        continued_terminal_phases: set[str] = set()
        if isinstance(next_input, dict):
            phase = next_input.get("phase")
            if isinstance(phase, str):
                continued_terminal_phases.add(phase)

        while resume_steps < 8:
            resume_steps += 1
            interrupted = False
            clearing_resume_payload = resume_payload_to_clear
            resume_payload_to_clear = None
            pending_recovery_payload = clearing_resume_payload
            agent_ref: list[str | None] = [current_agent]
            try:
                graph_pass_in_flight = True
                async for kind, payload in _astream_with_heartbeat(
                    graph, next_input, config, current_agent_ref=agent_ref,
                ):
                    if kind == "heartbeat":
                        yield payload
                        continue
                    event = payload
                    heartbeat_counter += 1
                    if heartbeat_counter % 10 == 0:
                        yield _sse_heartbeat()
                    if not isinstance(event, dict):
                        continue
                    sse_strings, current_agent, current_phase, is_interrupt = await _emit_for_update(
                        event, current_agent, current_phase, throttle_state, mission_id=mission_id
                    )
                    agent_ref[0] = current_agent
                    if is_interrupt:
                        for s in _drain_events():
                            yield s
                    for s in sse_strings:
                        if s:
                            yield s
                    if not is_interrupt:
                        for s in _drain_events():
                            yield s
                    if is_interrupt:
                        interrupted = True
                graph_pass_in_flight = False
            finally:
                if clearing_resume_payload is not None:
                    _clear_gate_decision_in_flight(clearing_resume_payload.get("gate_id"))

            # astream pass returned cleanly — no recovery needed.
            pending_recovery_payload = None

            for s in _drain_events():
                yield s

            if not interrupted:
                post_gate_payload = _open_gate_payload_from_store(store, mission_id)
                if post_gate_payload is not None:
                    yield await _emit_gate_pending(post_gate_payload, mission_id=mission_id)
                    yield await _emit_narration("workflow", _gate_narration(post_gate_payload))
                    yield await _emit_run_end()
                    return
                try:
                    post_snapshot = await graph.aget_state(config)
                except Exception:  # noqa: BLE001 - best-effort continuation
                    post_snapshot = None
                post_continuation = _continuation_input_from_snapshot(post_snapshot)
                post_phase = (
                    post_continuation.get("phase")
                    if post_continuation is not None
                    else None
                )
                if isinstance(post_phase, str) and post_phase not in continued_terminal_phases:
                    continued_terminal_phases.add(post_phase)
                    logger.warning(
                        "Resume continuing from routable terminal checkpoint: "
                        "mission=%s phase=%s",
                        mission_id,
                        post_phase,
                    )
                    next_input = post_continuation
                    continue
                if post_snapshot is not None and getattr(post_snapshot, "next", None):
                    logger.warning(
                        "Resume continuing from runnable checkpoint: mission=%s next=%s",
                        mission_id,
                        getattr(post_snapshot, "next", None),
                    )
                    next_input = None
                    continue
                break

            fut = _register_pending_resume(mission_id)
            try:
                resume_payload = await asyncio.wait_for(fut, timeout=_RESUME_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                yield await _emit_error("Gate approval timed out")
                break
            except asyncio.CancelledError:
                _clear_gate_decision_for_mission(mission_id)
                raise
            finally:
                _clear_pending_resume(mission_id, fut)

            resume_payload_to_clear = resume_payload
            next_input = Command(resume=resume_payload)
        else:
            logger.warning("Resume step limit reached for mission=%s", mission_id)

        if current_agent is not None:
            yield await _emit_agent_done(current_agent)
        # Bug 7: skip if the phase=="done" transition already emitted the
        # closing bubble during this stream's update loop.
        completion = "" if current_phase == "done" else await _maybe_emit_mission_complete(mission_id)
        if completion:
            yield completion
        yield await _emit_run_end()

    except Exception as e:
        import traceback as _tb
        tb_text = _tb.format_exc()
        logger.exception(f"Error in resume stream: {e}")
        last_frames = "\n".join(tb_text.splitlines()[-12:])
        yield await _emit_error(f"{type(e).__name__}: {e}\n{last_frames}")

    finally:
        try:
            unregister_finding_listener(mission_id, _on_finding)
        except (NameError, UnboundLocalError):
            pass
        try:
            unregister_deliverable_listener(mission_id, _on_deliverable)
        except (NameError, UnboundLocalError):
            pass
        try:
            unregister_milestone_listener(mission_id, _on_milestone)
        except (NameError, UnboundLocalError):
            pass
        try:
            unregister_graph_event_listener(mission_id, _on_graph_event)
        except (NameError, UnboundLocalError):
            pass
        mission_lock.release()
        # Recovery: see _stream_chat. If a /resume client consumes a gate
        # verdict but its socket dies before astream reaches the next
        # interrupt, spawn a detached driver so the graph advances.
        try:
            recovery_payload = pending_recovery_payload  # type: ignore[name-defined]
        except NameError:
            recovery_payload = None
        try:
            unfinished_graph_pass = bool(graph_pass_in_flight)  # type: ignore[name-defined]
        except NameError:
            unfinished_graph_pass = False
        if recovery_payload is None and unfinished_graph_pass:
            recovery_payload = {
                "gate_id": None,
                "reason": "stream_cancelled_during_graph_pass",
            }
        if recovery_payload is not None:
            try:
                _spawn_detached_resume(mission_id, recovery_payload)
                logger.warning(
                    "Spawned recovery detached driver after _stream_resume exit: "
                    "mission=%s gate=%s",
                    mission_id,
                    recovery_payload.get("gate_id"),
                )
            except Exception:  # noqa: BLE001 — best-effort recovery
                logger.exception(
                    "Recovery detached driver spawn failed: mission=%s",
                    mission_id,
                )


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Marvin server...")
    await get_graph()
    logger.info("Graph initialized, server ready")
    yield
    logger.info("Shutting down Marvin server...")
    if _checkpoint_conn is not None:
        await _checkpoint_conn.close()
        logger.info("Closed checkpoint DB connection")


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Marvin Backend",
    description="FastAPI backend for Marvin mission control",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# SECURITY MIDDLEWARE
# =============================================================================

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Simple security middleware for local trust or API key."""
    if request.url.path == "/health":
        return await call_next(request)
    
    client_host = request.client.host if request.client else ""
    is_local = client_host in ("127.0.0.1", "::1", "localhost")
    
    if is_local:
        return await call_next(request)
    
    api_key = os.getenv(API_KEY_ENV)
    if api_key:
        provided_key = request.headers.get(API_KEY_HEADER)
        if provided_key != api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
    
    return await call_next(request)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# =============================================================================
# MISSION ENDPOINTS
# =============================================================================

@app.post("/api/v1/missions", response_model=CreateMissionResponse)
async def create_mission(body: CreateMissionRequest):
    """Create a new mission."""
    store = get_store()
    
    base_id = f"m-{slugify(body.target)}-{date.today().strftime('%Y%m%d')}"
    mission_id = base_id
    
    suffix_counter = 0
    while _mission_exists(store, mission_id):
        suffix_counter += 1
        suffix = short_id("x")
        mission_id = f"{base_id}-{suffix}"
    
    created_at = utc_now_iso()
    mission_obj = MissionModel(
        id=mission_id,
        client=body.client,
        target=body.target,
        mission_type=body.mission_type,
        ic_question=body.ic_question,
        status="active",
        created_at=created_at,
        updated_at=created_at,
    )
    store.save_mission(mission_obj)
    _seed_standard_workplan(mission_id, store)
    
    logger.info(f"Created mission: {mission_id}")
    
    return CreateMissionResponse(
        mission_id=mission_id,
        status="active",
        client=body.client,
        target=body.target,
    )



@app.get("/api/v1/missions", response_model=ListMissionsResponse)
async def list_missions():
    """List all missions with progress computation."""
    store = get_store()
    
    missions_data = store.list_missions()
    
    missions = []
    for mission_row in missions_data:
        mission_id = mission_row.id
        
        milestones = store.list_milestones(mission_id)
        delivered = sum(1 for m in milestones if m.status == "delivered")
        total = len(milestones)
        progress = delivered / total if total > 0 else 0.0
        
        gates = store.list_gates(mission_id)
        hypotheses = store.list_hypotheses(mission_id)
        findings = store.list_findings(mission_id)
        mission_brief = store.get_mission_brief(mission_id)
        workstreams = store.list_workstreams(mission_id)
        open_gates = [
            g for g in gates
            if evaluate_gate_material(
                store,
                mission_id,
                g,
                hypotheses=hypotheses,
                findings=findings,
                mission_brief=mission_brief,
                workstreams=workstreams,
                milestones=milestones,
            ).is_open
        ]
        next_checkpoint = None
        if open_gates:
            open_gates.sort(key=lambda g: g.scheduled_day)
            next_checkpoint = open_gates[0].gate_type
        
        missions.append(MissionSummary(
            id=mission_id,
            client=mission_row.client,
            target=mission_row.target,
            mission_type=mission_row.mission_type or "cdd",
            status=mission_row.status,
            progress=round(progress, 2),
            next_checkpoint=next_checkpoint,
            created_at=mission_row.created_at or "",
        ))
    
    return ListMissionsResponse(missions=missions)


@app.get("/api/v1/missions/{mission_id}")
async def get_mission(mission_id: str):
    """Get full mission object from store."""
    store = get_store()
    
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    
    mission = store.get_mission(mission_id)
    return mission.model_dump()


@app.delete("/api/v1/missions/{mission_id}")
async def delete_mission(mission_id: str):
    store = MissionStore()
    deleted = store.delete_mission(mission_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"deleted": mission_id}


@app.get("/api/v1/missions/{mission_id}/hypotheses")
async def get_mission_hypotheses(mission_id: str):
    """Chantier 4: hypotheses with computed status for HypothesisPanel.

    Each entry carries {id, label, text, status, computed: {status, counts}}.
    Status comes from compute_hypothesis_status (pure function over linked
    findings)."""
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    hypotheses = store.list_hypotheses(mission_id)
    findings = store.list_findings(mission_id)
    return {
        "mission_id": mission_id,
        "hypotheses": _hypotheses_with_status(hypotheses, findings),
    }


@app.get("/api/v1/missions/{mission_id}/workstreams/{ws_id}/findings")
async def get_workstream_findings(mission_id: str, ws_id: str):
    """Bug 6 (chantier 2.6): per-workstream findings for tab display.

    Tabs are content (findings from DB), not the SSE meta-event stream.
    The agent → workstream map is intentionally hard-coded here so the
    UI does not depend on workstream_id annotations the agents may skip.
    """
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")

    AGENT_TO_WORKSTREAM = {
        "dora": "W1",
        "calculus": "W2",
        "merlin": "W3",
        "adversus": "W4",
    }
    findings = store.list_findings(mission_id)
    workstream_findings = [
        f for f in findings
        if AGENT_TO_WORKSTREAM.get((f.agent_id or "").lower()) == ws_id
        or (f.workstream_id or "") == ws_id
    ]
    label_by_id = {h.id: (h.label or "") for h in store.list_hypotheses(mission_id)}
    return {
        "workstream_id": ws_id,
        "count": len(workstream_findings),
        "findings": [
            {
                "id": f.id,
                "claim_text": f.claim_text,
                "confidence": f.confidence,
                "agent_id": f.agent_id,
                "workstream_id": f.workstream_id,
                "hypothesis_id": f.hypothesis_id,
                "hypothesis_label": label_by_id.get(f.hypothesis_id or ""),
                "source_id": f.source_id,
                "created_at": f.created_at,
            }
            for f in workstream_findings
        ],
    }


# ---------------------------------------------------------------------------
# C2 — Data room upload + parser
# ---------------------------------------------------------------------------

def _data_room_dir(mission_id: str) -> Path:
    base = Path.home() / ".marvin" / "data_rooms" / mission_id
    base.mkdir(parents=True, exist_ok=True)
    return base


@app.post("/api/v1/missions/{mission_id}/data-room/upload")
async def upload_data_room_file(mission_id: str, file: UploadFile = File(...)):
    """Upload a data-room file. Stored at ~/.marvin/data_rooms/<mid>/<id>_<name>.
    Parsed text persisted in DB; parse failures captured in parse_error.
    """
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    contents = await file.read()
    if len(contents) > DATA_ROOM_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {DATA_ROOM_MAX_BYTES} bytes",
        )
    file_id = short_id("dr")
    safe_name = (file.filename or "upload").replace("/", "_")
    target = _data_room_dir(mission_id) / f"{file_id}_{safe_name}"
    target.write_bytes(contents)
    parsed: str | None = None
    parse_error: str | None = None
    try:
        parsed = parse_data_room_file(target)
    except ValueError as exc:
        parse_error = str(exc)
    record = DataRoomFile(
        id=file_id,
        mission_id=mission_id,
        filename=safe_name,
        file_path=str(target),
        mime_type=file.content_type,
        size_bytes=len(contents),
        parsed_text=parsed,
        parse_error=parse_error,
        uploaded_at=utc_now_iso(),
    )
    store.save_data_room_file(record)
    return record.model_dump()


@app.get("/api/v1/missions/{mission_id}/data-room")
async def list_data_room_files_endpoint(mission_id: str):
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    files = store.list_data_room_files(mission_id)
    return {
        "mission_id": mission_id,
        "files": [
            {
                "id": f.id,
                "filename": f.filename,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "parse_error": f.parse_error,
                "parsed_chars": len(f.parsed_text or ""),
                "uploaded_at": f.uploaded_at,
            }
            for f in files
        ],
    }


@app.delete("/api/v1/missions/{mission_id}/data-room/{file_id}")
async def delete_data_room_file_endpoint(mission_id: str, file_id: str):
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    record = store.get_data_room_file(file_id)
    if record is None or record.mission_id != mission_id:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        Path(record.file_path).unlink(missing_ok=True)
    except OSError:
        pass
    store.delete_data_room_file(file_id)
    return {"deleted": file_id}


# ---------------------------------------------------------------------------
# C3 — Expert-call transcript ingestion
# ---------------------------------------------------------------------------


@app.post("/api/v1/missions/{mission_id}/transcripts")
async def upload_transcript(
    mission_id: str,
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    title: str | None = Form(None),
    expert_name: str | None = Form(None),
    expert_role: str | None = Form(None),
):
    """Upload a transcript either as a .txt file or as a raw text form field.
    Speaker tagging is parsed at ingest; segments persisted alongside.
    """
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    raw: str
    if file is not None:
        contents = await file.read()
        if len(contents) > DATA_ROOM_MAX_BYTES:
            raise HTTPException(status_code=413, detail="file too large")
        raw = contents.decode("utf-8", errors="replace")
        if title is None:
            title = file.filename
    elif text:
        raw = text
    else:
        raise HTTPException(status_code=400, detail="provide file or text")

    transcript_id = short_id("tx")
    segments_parsed = parse_transcript(raw)
    segments = [
        TranscriptSegment(
            id=f"{transcript_id}-seg-{i}",
            transcript_id=transcript_id,
            speaker=s.speaker,
            text=s.text,
            line_start=s.line_start,
            line_end=s.line_end,
        )
        for i, s in enumerate(segments_parsed)
    ]
    record = Transcript(
        id=transcript_id,
        mission_id=mission_id,
        title=title,
        expert_name=expert_name,
        expert_role=expert_role,
        raw_text=raw,
        line_count=raw.count("\n") + 1,
        uploaded_at=utc_now_iso(),
    )
    store.save_transcript(record, segments)
    return {
        "transcript": record.model_dump(),
        "segment_count": len(segments),
    }


@app.get("/api/v1/missions/{mission_id}/transcripts")
async def list_transcripts_endpoint(mission_id: str):
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    transcripts = store.list_transcripts(mission_id)
    return {
        "mission_id": mission_id,
        "transcripts": [
            {
                "id": t.id,
                "title": t.title,
                "expert_name": t.expert_name,
                "expert_role": t.expert_role,
                "line_count": t.line_count,
                "uploaded_at": t.uploaded_at,
            }
            for t in transcripts
        ],
    }


@app.delete("/api/v1/missions/{mission_id}/transcripts/{transcript_id}")
async def delete_transcript_endpoint(mission_id: str, transcript_id: str):
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    transcripts = store.list_transcripts(mission_id)
    if not any(t.id == transcript_id for t in transcripts):
        raise HTTPException(status_code=404, detail="Transcript not found")
    store.delete_transcript(transcript_id)
    return {"deleted": transcript_id}


class DealTermsPayload(BaseModel):
    entry_revenue: float | None = None
    entry_ebitda: float | None = None
    entry_multiple: float | None = None
    entry_equity: float | None = None
    leverage_x: float | None = None
    hold_years: int | None = None
    target_irr: float | None = None
    target_moic: float | None = None
    sector_multiple_low: float | None = None
    sector_multiple_high: float | None = None
    notes: str | None = None


@app.get("/api/v1/missions/{mission_id}/deal-terms")
async def get_deal_terms(mission_id: str):
    """C10: return current deal terms for a mission, or empty object if unset."""
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    terms = store.get_deal_terms(mission_id)
    if terms is None:
        return {"mission_id": mission_id, "terms": None}
    return {"mission_id": mission_id, "terms": terms.model_dump()}


@app.put("/api/v1/missions/{mission_id}/deal-terms")
async def put_deal_terms(mission_id: str, payload: DealTermsPayload):
    """C10: upsert deal terms for a mission."""
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    now = utc_now_iso()
    existing = store.get_deal_terms(mission_id)
    created_at = existing.created_at if existing else now
    terms = DealTerms(
        mission_id=mission_id,
        **payload.model_dump(),
        created_at=created_at,
        updated_at=now,
    )
    store.save_deal_terms(terms)
    return {"mission_id": mission_id, "terms": terms.model_dump()}


@app.get("/api/v1/missions/{mission_id}/deal-math")
async def get_deal_math(mission_id: str):
    """C10: return computed deal-math view (entry, scenarios, missing inputs).

    If terms are not yet captured, scenarios are absent and missing_inputs
    lists every required field. The frontend can render this directly.
    """
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    terms = store.get_deal_terms(mission_id)
    terms_dict = terms.model_dump() if terms else {}
    return {
        "mission_id": mission_id,
        "terms": terms_dict or None,
        "math": compute_deal_math(terms_dict),
    }


@app.get("/api/v1/missions/{mission_id}/progress")
async def get_mission_progress(mission_id: str):
    """Get mission progress with gates, milestones, findings, hypotheses, and deliverables."""
    store = get_store()
    
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    
    mission = store.get_mission(mission_id)
    gates = store.list_gates(mission_id)
    milestones = store.list_milestones(mission_id)
    findings = store.list_findings(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    deliverables = store.list_deliverables(mission_id)
    workstreams = store.list_workstreams(mission_id)
    mission_brief = store.get_mission_brief(mission_id)
    _hypothesis_label_by_id = {h.id: (h.label or "") for h in hypotheses}
    gate_material = {
        g.id: evaluate_gate_material(
            store,
            mission_id,
            g,
            hypotheses=hypotheses,
            findings=findings,
            mission_brief=mission_brief,
            workstreams=workstreams,
            milestones=milestones,
        )
        for g in gates
    }
    
    return {
        "mission": {
            "id": mission.id,
            "client": mission.client,
            "target": mission.target,
            "ic_question": mission.ic_question,
            "created_at": mission.created_at or "",
            "status": mission.status,
        },
        "framing": mission_brief.model_dump() if mission_brief else None,
        "gates": [
            {
                "id": g.id,
                "gate_type": g.gate_type,
                "scheduled_day": g.scheduled_day,
                "status": g.status,
                "lifecycle_status": gate_material[g.id].lifecycle_status,
                "is_open": gate_material[g.id].is_open,
                "missing_material": gate_material[g.id].missing_material,
                "review_payload": gate_material[g.id].review_payload,
                "format": g.format,
                "failure_reason": g.failure_reason,
            }
            for g in gates
        ],
        "milestones": [
            {
                "id": m.id,
                "workstream_id": m.workstream_id,
                "label": m.label,
                "status": m.status,
                "result_summary": m.result_summary,
            }
            for m in milestones
        ],
        "findings": [
            {
                "id": f.id,
                "workstream_id": f.workstream_id,
                "hypothesis_id": f.hypothesis_id,
                "hypothesis_label": _hypothesis_label_by_id.get(f.hypothesis_id or ""),
                "confidence": f.confidence,
                "claim_text": f.claim_text,
                "agent_id": f.agent_id,
                "source_id": f.source_id,
                "impact": f.impact,  # Chantier 4 CP2: drives load_bearing emphasis
                "created_at": f.created_at,
            }
            for f in findings
        ],
        "hypotheses": _hypotheses_with_status(hypotheses, findings),
        "deliverables": [_deliverable_progress_payload(d) for d in deliverables],
        "workstreams": [
            {
                "id": w.id,
                "label": w.label,
                "assigned_agent": w.assigned_agent,
                "status": w.status,
            }
            for w in workstreams
        ],
        # Merlin verdict, if any. Surfaced here so the Synthesis (W3) tab
        # can render it as content — merlin doesn't add findings, so the
        # tab would otherwise stay empty even after the verdict shipped.
        "merlin_verdict": (
            {
                "verdict": v.verdict,
                "label": consultant_verdict_label(v.verdict),
                "recommended_action": consultant_verdict_action(v.verdict),
                "notes": v.notes,
                "created_at": v.created_at,
            }
            if (v := store.get_latest_merlin_verdict(mission_id))
            else None
        ),
    }


@app.get("/api/v1/missions/{mission_id}/events")
async def get_mission_events(mission_id: str):
    """Chronological event log reconstructed from persisted state.

    The live SSE rail is volatile (in-memory queue per chat session). This
    endpoint exposes the same events derived from the store, so the UI can
    hydrate after refresh and stay aligned with backend truth (CLAUDE.md
    invariant: "what is displayed corresponds exactly to mission state")."""
    store = get_store()

    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")

    findings = store.list_findings(mission_id)
    milestones = store.list_milestones(mission_id)
    deliverables = store.list_deliverables(mission_id)
    gates = store.list_gates(mission_id)

    events: list[dict] = []

    for finding in findings:
        events.append({
            "type": "finding_added",
            "ts": finding.created_at or "",
            "findingId": finding.id,
            "text": finding.claim_text,
            "confidence": finding.confidence,
            "agent": finding.agent_id,
            "workstreamId": finding.workstream_id,
            "hypothesisId": finding.hypothesis_id,
            "sourceId": finding.source_id,
        })

    for milestone in milestones:
        if milestone.status not in ("delivered", "blocked"):
            continue
        events.append({
            "type": "milestone_done",
            "ts": "",
            "milestoneId": milestone.id,
            "label": milestone.label,
            "workstreamId": milestone.workstream_id,
            "status": milestone.status,
            "resultSummary": milestone.result_summary,
        })

    for deliverable in deliverables:
        if deliverable.status != "ready":
            continue
        events.append({
            "type": "deliverable_ready",
            "ts": deliverable.created_at or "",
            "deliverableId": deliverable.id,
            "label": deliverable.deliverable_type,
            "deliverableType": deliverable.deliverable_type,
            "filePath": deliverable.file_path,
            "fileSizeBytes": deliverable.file_size_bytes,
        })

    for gate in gates:
        if gate.status == "pending":
            continue
        events.append({
            "type": "gate_resolved",
            "ts": "",
            "gateId": gate.id,
            "gateType": gate.gate_type,
            "status": gate.status,
            "completionNotes": gate.completion_notes,
        })

    events.sort(key=lambda evt: (evt.get("ts") or "", evt.get("type", "")))

    return {"mission_id": mission_id, "events": events}


# =============================================================================
# CHAT ENDPOINT (SSE STREAMING)
# =============================================================================

@app.get("/api/v1/missions/{mission_id}/chat/messages")
async def get_chat_messages(mission_id: str):
    """Return persisted user/MARVIN chat messages for reload recovery."""
    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    messages = store.list_chat_messages(mission_id)
    return {
        "mission_id": mission_id,
        "messages": [
            {
                "id": msg.id,
                "from": "u" if msg.role == "user" else "m",
                "text": msg.text,
                "deliverableId": msg.deliverable_id,
                "deliverableLabel": msg.deliverable_label,
                "gateId": msg.gate_id,
                "gateAction": msg.gate_action,
                "seq": msg.seq,
                "createdAt": msg.created_at,
            }
            for msg in messages
        ],
    }


@app.post("/api/v1/missions/{mission_id}/chat")
async def chat_mission_post(
    mission_id: str,
    body: ChatRequest,
    reset: bool = Query(default=False),
):
    """POST chat message and receive SSE stream."""
    return StreamingResponse(
        _stream_chat(mission_id, body.text, reset=reset),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/missions/{mission_id}/chat")
async def chat_mission_get(
    mission_id: str,
    text: str = Query(default=""),
    reset: bool = Query(default=False),
):
    """GET chat message and receive SSE stream."""
    if not text:
        async def idle_stream():
            yield _sse_heartbeat()
            for _ in range(10):
                await asyncio.sleep(30)
                yield _sse_heartbeat()
            yield await _emit_run_end()
        
        return StreamingResponse(
            idle_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    
    return StreamingResponse(
        _stream_chat(mission_id, text, reset=reset),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# RESUME ENDPOINT (SSE STREAMING)
# =============================================================================

@app.post("/api/v1/missions/{mission_id}/resume")
@app.get("/api/v1/missions/{mission_id}/resume")
async def resume_mission(mission_id: str):
    """Re-attach to a checkpointed mission and stream events.

    Chantier 2.7 FIX 2. Allows the client to recover after tab close, network
    blip, or uvicorn restart. Returns the same SSE event vocabulary as /chat.
    """
    return StreamingResponse(
        _stream_resume(mission_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# C-RESUME-RECOVERY — agent rerun endpoint
# =============================================================================

# Map a failed agent → (gate_type to clear, phase to drop checkpoint into so
# phase_router re-routes the graph back to that agent on the next astream).
_RERUN_TARGETS: dict[str, tuple[str, str]] = {
    "adversus": ("manager_review", "gate_g1_passed"),
    "merlin": ("final_review", "rebuttal_done"),
}


@app.post("/api/v1/missions/{mission_id}/agents/{agent}/rerun")
async def rerun_agent(mission_id: str, agent: str):
    """C-RESUME-RECOVERY: rerun a specific agent after a transient LLM failure.

    Refuses unless the matching gate is in ``status="failed"``. Clears the
    failure_reason, updates the checkpoint phase so phase_router re-routes
    back to the target node on the next astream, and spawns a detached
    driver to run forward to the next interrupt or completion. The client
    re-attaches via ``GET /api/v1/missions/{id}/resume``.

    Does NOT replay G0/G1/research — the checkpoint already has the prior
    research state; only the failed node re-executes.
    """
    if agent not in _RERUN_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported agent for rerun: {agent}. Allowed: {list(_RERUN_TARGETS)}",
        )
    gate_type, kick_phase = _RERUN_TARGETS[agent]

    store = get_store()
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")

    target_gate = next(
        (g for g in store.list_gates(mission_id)
         if g.gate_type == gate_type and g.status == "failed"),
        None,
    )
    if target_gate is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No failed {gate_type} gate to rerun. Rerun is only allowed "
                "after a transient LLM failure has been recorded."
            ),
        )

    store.clear_gate_failure(target_gate.id)

    try:
        graph = await get_graph()
        config = {"configurable": {"thread_id": mission_id}}
        await graph.aupdate_state(config, {"phase": kick_phase, "failed_agent": None})
    except Exception as exc:  # noqa: BLE001
        logger.exception("rerun_agent: aupdate_state failed for %s: %s", mission_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Could not stage checkpoint for rerun: {exc}",
        ) from exc

    # Synthesize a no-op resume payload — the detached driver loop tolerates
    # the absence of a parked interrupt and falls through to plain astream.
    payload = {"gate_id": None, "rerun_agent": agent}
    spawn_status = _spawn_detached_resume(mission_id, payload)
    logger.info(
        "rerun_agent: spawned detached driver for mission=%s agent=%s status=%s",
        mission_id, agent, spawn_status,
    )

    return {
        "status": "spawned",
        "mission_id": mission_id,
        "agent": agent,
        "gate_id": target_gate.id,
    }


# =============================================================================
# GATE VALIDATION ENDPOINT
# =============================================================================

@app.post("/api/v1/missions/{mission_id}/gates/{gate_id}/validate", response_model=GateValidateResponse)
async def validate_gate(mission_id: str, gate_id: str, body: GateValidateRequest):
    """Validate gate and resume graph if approved."""
    store = get_store()
    
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    
    gate = None
    for g in store.list_gates(mission_id):
        if g.id == gate_id:
            gate = g
            break
    
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")

    is_clarification = gate.format == "clarification_questions"
    is_data_decision = gate.format == "data_decision"

    _VALID_DATA_DECISIONS = {
        "skip_calculus",
        "proceed_low_confidence",
        "request_data_room",
    }

    if is_clarification:
        if body.answers is None:
            raise HTTPException(
                status_code=400,
                detail="Clarification gate requires `answers`",
            )
        # A clarification gate always resolves as completed (we record the
        # answers regardless of how thin they are).
        expected_status = "completed"
    elif is_data_decision:
        # Bug 3 / CP2 (chantier 2.6.1): data_decision gates use `decision`
        # instead of `verdict`. Validate against the allowed set; any
        # data_decision resolution closes the gate as completed.
        if not body.decision or body.decision.strip().lower() not in _VALID_DATA_DECISIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    "data_decision gate requires `decision` in "
                    "{skip_calculus, proceed_low_confidence, request_data_room}"
                ),
            )
        expected_status = "completed"
    else:
        if body.verdict not in ("APPROVED", "REJECTED"):
            raise HTTPException(status_code=400, detail="Verdict must be APPROVED or REJECTED")
        expected_status = "completed" if body.verdict == "APPROVED" else "failed"
    if gate.status == expected_status:
        _clear_gate_decision_in_flight(gate_id)
        resume_id = f"resume-{uuid.uuid4().hex[:8]}"
        logger.info(f"Gate {gate_id} already {expected_status}, skipping resume")
        # Bug 4 (chantier 2.6): same-verdict re-submit is idempotent.
        return GateValidateResponse(
            status="already_processed",
            mission_id=mission_id,
            gate_id=gate_id,
            resume_id=resume_id,
            idempotent=True,
            message=f"Gate already validated with this verdict ({expected_status}).",
        )
    if gate.status in ("completed", "failed"):
        # Bug 4 (chantier 2.6): mismatched-verdict on a finalised gate is a
        # user error, not a 409 server error. Surface a structured conflict
        # so the UI shows a toast and the console stays clean.
        _clear_gate_decision_in_flight(gate_id)
        resume_id = f"resume-{uuid.uuid4().hex[:8]}"
        return GateValidateResponse(
            status="conflict",
            mission_id=mission_id,
            gate_id=gate_id,
            resume_id=resume_id,
            conflict=True,
            message=(
                f"Gate already completed with status={gate.status}. "
                "Cannot change after completion."
            ),
        )

    in_flight = _gate_decisions_in_flight.get(gate_id)
    if in_flight is not None:
        if in_flight["expected_status"] == expected_status:
            return GateValidateResponse(
                status="resume_pending",
                mission_id=mission_id,
                gate_id=gate_id,
                resume_id=in_flight["resume_id"],
            )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Gate decision is already being processed",
                "gate_id": gate_id,
                "gate_type": gate.gate_type,
                "lifecycle_status": "resuming",
            },
        )

    hypotheses = store.list_hypotheses(mission_id)
    findings = store.list_findings(mission_id)
    mission_brief = store.get_mission_brief(mission_id)
    workstreams = store.list_workstreams(mission_id)
    milestones = store.list_milestones(mission_id)
    material = evaluate_gate_material(
        store,
        mission_id,
        gate,
        hypotheses=hypotheses,
        findings=findings,
        mission_brief=mission_brief,
        workstreams=workstreams,
        milestones=milestones,
    )
    if not material.is_open:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Gate cannot be validated until required review material exists",
                "gate_id": gate_id,
                "gate_type": gate.gate_type,
                "lifecycle_status": material.lifecycle_status,
                "missing_material": material.missing_material,
            },
        )
    
    resume_id = f"resume-{uuid.uuid4().hex[:8]}"
    if is_clarification:
        resume_payload = {
            "answers": list(body.answers or []),
            "notes": body.notes,
            "gate_id": gate_id,
        }
        verdict_label = "ANSWERED"
    elif is_data_decision:
        decision_value = (body.decision or "").strip().lower()
        resume_payload = {
            "decision": decision_value,
            "notes": body.notes,
            "gate_id": gate_id,
        }
        verdict_label = decision_value.upper()
    else:
        approved = body.verdict == "APPROVED"
        resume_payload = {
            "approved": approved,
            "verdict": body.verdict,
            "notes": body.notes,
            "gate_id": gate_id,
        }
        verdict_label = body.verdict or ""
    _mark_gate_decision_in_flight(
        mission_id,
        gate_id,
        expected_status=expected_status,
        verdict=verdict_label,
        resume_id=resume_id,
    )
    delivered = _deliver_resume(mission_id, resume_payload)

    if delivered:
        logger.info(
            f"Resume delivered to active stream: mission={mission_id} gate={gate_id} resume_id={resume_id}"
        )
        status = "resumed"
    else:
        try:
            if is_clarification:
                joined = "; ".join(
                    str(a).strip() for a in (body.answers or []) if str(a).strip()
                )
                if joined:
                    store.append_clarification_answer(mission_id, joined)
                store.update_gate_status(
                    gate_id,
                    expected_status,
                    notes=body.notes or joined or "no answers provided",
                )
            elif is_data_decision:
                decision_value = (body.decision or "").strip().lower()
                store.update_gate_status(
                    gate_id,
                    expected_status,
                    notes=body.notes or f"data_decision={decision_value}",
                )
            else:
                # Standard verdict (approve/reject): do NOT pre-write the gate
                # row here. gate_node owns the write at gates.py:141 — it runs
                # AFTER interrupt() returns the verdict. Pre-writing causes
                # gate_node's replay to see status!='pending', take the
                # missing-material early-exit branch in gate_material.py:229,
                # and terminate the graph at phase=idle without consuming the
                # resume payload or transitioning to "confirmed".
                pass
        finally:
            _clear_gate_decision_in_flight(gate_id)
        # No SSE stream is parked. Persisting the verdict to the DB alone
        # used to leave the LangGraph run frozen — the user closed the chat
        # tab between gate emission and approval, and dora/calculus/merlin
        # never executed. Spawn a detached driver that picks up the parked
        # interrupt frame and runs the graph forward to the next interrupt
        # or to completion. Findings/deliverables persist via the agent
        # tools' direct DB writes; the next /resume reattaches and surfaces
        # the new state to the UI.
        if not is_clarification and not is_data_decision:
            # Clarification / data_decision verdicts re-enter framing or
            # re-fan-out; the existing /resume + /chat flow handles those
            # without a detached driver.
            spawn_status = _spawn_detached_resume(mission_id, resume_payload)
            logger.info(
                "Gate validated, detached driver %s: "
                f"mission={mission_id} gate={gate_id}",
                spawn_status,
            )
            status = "resumed_detached" if spawn_status == "spawned" else "resume_pending"
        else:
            logger.warning(
                "Gate validated but no active stream to resume: "
                f"mission={mission_id} gate={gate_id}"
            )
            status = "validated_no_stream"

    return GateValidateResponse(
        status=status,
        mission_id=mission_id,
        gate_id=gate_id,
        resume_id=resume_id,
    )


# =============================================================================
# DELIVERABLE DOWNLOAD ENDPOINT
# =============================================================================

@app.get("/api/v1/deliverables/{deliverable_id}/preview")
async def get_deliverable_preview(deliverable_id: str):
    """Chantier 4 CP3: inline preview content + linked findings.

    Returns:
        - content: file contents as text (markdown / plain)
        - content_type: "markdown" | "pdf" | "text"
        - linked_findings: findings whose claims were used by Papyrus
          (heuristic: same mission, ordered by created_at)
        - file_path: absolute path (still useful for the download fallback)

    Path traversal is enforced: resolved_path must stay under output_dir.
    PDFs are not embedded inline; the modal falls back to the download URL.
    """
    store = get_store()
    deliverable = None
    for m in store.list_missions():
        for d in store.list_deliverables(m.id):
            if d.id == deliverable_id:
                deliverable = d
                mission_id = m.id
                break
        if deliverable:
            break
    if deliverable is None:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    if not deliverable.file_path:
        raise HTTPException(status_code=409, detail="Deliverable not yet generated")

    output_dir = (PROJECT_ROOT / "output").resolve()
    from pathlib import Path as _Path
    resolved = _Path(deliverable.file_path).resolve()
    try:
        resolved.relative_to(output_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Path escapes allowed directory")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    suffix = resolved.suffix.lower()
    if suffix == ".md":
        content_type = "markdown"
        content = resolved.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        content_type = "pdf"
        content = ""  # Caller embeds the download URL.
    else:
        content_type = "text"
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""

    findings = store.list_findings(mission_id)
    label_by_id = {h.id: (h.label or "") for h in store.list_hypotheses(mission_id)}
    return {
        "deliverable_id": deliverable.id,
        "deliverable_type": deliverable.deliverable_type,
        "mission_id": mission_id,
        "file_path": str(resolved),
        "content_type": content_type,
        "content": content,
        "linked_findings": [
            {
                "id": f.id,
                "claim_text": f.claim_text,
                "agent_id": f.agent_id,
                "confidence": f.confidence,
                "hypothesis_label": label_by_id.get(f.hypothesis_id or ""),
                "impact": f.impact,
            }
            for f in findings
        ],
    }


@app.get("/api/v1/deliverables/download")
async def download_deliverable(rel_path: str = Query(...)):
    """Download deliverable file.

    Accepts either a path relative to the output directory (e.g.
    "m-x/W1_report.md") OR an absolute path that already lives inside
    the allowed output directory. The DB stores absolute file_path
    values today, so this endpoint normalizes both shapes.
    """
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_root = output_dir.resolve()

    if not rel_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    from pathlib import Path as _Path

    candidate = _Path(rel_path)
    try:
        if candidate.is_absolute():
            resolved_path = candidate.resolve()
        else:
            safe_rel_path = rel_path.lstrip("/").lstrip(".")
            if not safe_rel_path:
                raise HTTPException(status_code=400, detail="Invalid path")
            resolved_path = (output_dir / safe_rel_path).resolve()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    try:
        resolved_path.relative_to(output_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Path escapes allowed directory")
    
    if resolved_path.is_symlink():
        real_path = resolved_path.resolve()
        try:
            real_path.relative_to(output_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Symlink escapes allowed directory")
    
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    if not resolved_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
    
    return FileResponse(
        path=str(resolved_path),
        filename=resolved_path.name,
        media_type="application/octet-stream",
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

def run_server():
    """Run the server using uvicorn."""
    import uvicorn
    # Railway injects PORT; MARVIN_PORT as fallback for local dev
    port = int(os.getenv("PORT", os.getenv("MARVIN_PORT", "8095")))
    uvicorn.run(app, host=os.getenv("MARVIN_HOST", "0.0.0.0"), port=port)


if __name__ == "__main__":
    run_server()
