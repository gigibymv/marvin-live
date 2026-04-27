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
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, date
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from marvin.artifacts import artifact_file_is_ready
from marvin.events import (
    register_deliverable_listener,
    register_finding_listener,
    register_milestone_listener,
    unregister_deliverable_listener,
    unregister_finding_listener,
    unregister_milestone_listener,
)
from marvin.graph.gate_material import evaluate_gate_material
from marvin.graph.runner import build_graph
from marvin.graph.state import MarvinState
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools.common import slugify, short_id, utc_now_iso
from marvin.mission.schema import Finding, Gate, Hypothesis, Mission as MissionModel

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

# Display name mapping for user-facing event emission
_DISPLAY_NAME = {
    "dora": "Dora",
    "calculus": "Calculus",
    "adversus": "Adversus",
    "merlin": "Merlin",
    "synthesis_critic": "Merlin",
    "papyrus_delivery": "Papyrus",
    "orchestrator": "MARVIN",
    "phase_router": None,
    "research_join": None,
    "gate": None,
    "gate_entry": None,
}

# Tool result summaries for user-friendly display
_TOOL_SUMMARIES: dict[str, callable] = {
    "add_finding_to_mission": lambda r: f"Finding added · {r.get('finding_id', '')[:12]}",
    "mark_milestone_delivered": lambda r: f"✓ {r.get('milestone_id', '')} delivered",
    "generate_engagement_brief": lambda r: "Engagement Brief ready",
    "set_merlin_verdict": lambda r: f"Verdict: {r.get('verdict', '')}",
    "add_hypothesis_to_mission": lambda r: "Hypothesis recorded",
    "persist_source_for_mission": lambda r: "Source added",
}


def _get_tool_summary(tool_name: str, result: dict | None) -> str | None:
    """Get user-friendly summary for tool result."""
    if tool_name in _TOOL_SUMMARIES:
        try:
            return _TOOL_SUMMARIES[tool_name](result or {})
        except Exception:
            pass
    return None


def _mission_exists(store: MissionStore, mission_id: str) -> bool:
    """Check if mission exists without raising KeyError."""
    try:
        store.get_mission(mission_id)
        return True
    except KeyError:
        return False


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
    }


# =============================================================================
# GRAPH SINGLETON
# =============================================================================

_graph = None
_graph_lock = asyncio.Lock()
_mission_locks: dict[str, asyncio.Lock] = {}

# Per-mission pending resume futures. When _stream_chat hits an interrupt frame,
# it parks on a future here keyed by mission_id; validate_gate sets the result
# with the approval payload, which unblocks the stream to call
# graph.astream(Command(resume=...)) on the same thread_id and keep yielding SSE
# events to the still-open client connection.
_pending_resumes: dict[str, asyncio.Future[dict]] = {}

# Bounded wait so a forgotten gate doesn't pin the per-mission lock forever.
_RESUME_TIMEOUT_SECONDS = 600


def _register_pending_resume(mission_id: str) -> asyncio.Future[dict]:
    fut = asyncio.get_event_loop().create_future()
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


def _get_mission_lock(mission_id: str) -> asyncio.Lock:
    """Get or create per-mission async lock."""
    if mission_id not in _mission_locks:
        _mission_locks[mission_id] = asyncio.Lock()
    return _mission_locks[mission_id]


async def get_graph():
    """Get compiled graph singleton with checkpointer."""
    global _graph
    async with _graph_lock:
        if _graph is None:
            checkpointer = MemorySaver()
            _graph = build_graph(checkpointer=checkpointer)
            logger.info("Graph initialized with MemorySaver checkpointer")
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
    ic_question: str
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
    verdict: str
    notes: str = ""


class GateValidateResponse(BaseModel):
    status: str
    mission_id: str
    gate_id: str
    resume_id: str


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
    display = _DISPLAY_NAME.get(agent, agent)
    if display is None:
        return ""
    logger.info(f"Emitting text event: agent={display}, text_length={len(text)}")
    return _sse_event("text", {"agent": display, "text": text})


async def _emit_tool_call(agent: str, tool: str) -> str:
    display = _DISPLAY_NAME.get(agent, agent)
    if display is None:
        return ""
    return _sse_event("tool_call", {"agent": display, "tool": tool})


async def _emit_tool_result(agent: str, text: str) -> str:
    display = _DISPLAY_NAME.get(agent, agent)
    if display is None:
        return ""
    return _sse_event("tool_result", {"agent": display, "text": text})


async def _emit_gate_pending(payload: dict) -> str:
    return _sse_event("gate_pending", payload)


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

    The emission carries the canonical fields (claim_text, confidence,
    finding_id, ...) — this helper renames them to the wire format the UI
    consumes (text, badge)."""
    out: dict = {"text": str(payload.get("claim_text", ""))}
    confidence = payload.get("confidence")
    if confidence:
        out["badge"] = str(confidence)
    finding_id = payload.get("finding_id")
    if finding_id:
        out["findingId"] = str(finding_id)
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
    label = payload.get("deliverable_type")
    if label:
        out["label"] = str(label)
    return out


def _build_milestone_done_from_emit(payload: dict) -> dict:
    out: dict = {"milestoneId": str(payload.get("milestone_id", ""))}
    label = payload.get("label")
    if label:
        out["label"] = str(label)
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
    display = _DISPLAY_NAME.get(agent, agent)
    if display is None:
        return ""
    return _sse_event("agent_active", {"agent": display})


async def _emit_agent_done(agent: str) -> str:
    display = _DISPLAY_NAME.get(agent, agent)
    if display is None:
        return ""
    return _sse_event("agent_done", {"agent": display})


async def _emit_run_end() -> str:
    return _sse_event("run_end", {})


async def _emit_error(message: str) -> str:
    return _sse_event("error", {"message": message})


# =============================================================================
# SSE STREAM GENERATOR
# =============================================================================

async def _emit_for_update(
    event: dict,
    current_agent: str | None,
) -> tuple[list[str], str | None, bool]:
    """Translate one graph.astream update into SSE strings.

    Returns (sse_strings, new_current_agent, is_interrupt).
    """
    out: list[str] = []
    if "__interrupt__" in event:
        interrupts = event["__interrupt__"]
        if isinstance(interrupts, tuple) and interrupts:
            interrupt_value = getattr(interrupts[0], "value", None)
            if isinstance(interrupt_value, dict):
                out.append(await _emit_gate_pending(interrupt_value))
        return out, current_agent, True

    for node_name, output in event.items():
        display = _DISPLAY_NAME.get(node_name)
        if display is None:
            continue
        if not isinstance(output, dict):
            continue

        for msg in output.get("messages", []):
            if isinstance(msg, AIMessage):
                if msg.content:
                    if node_name != current_agent:
                        if current_agent is not None:
                            out.append(await _emit_agent_done(current_agent))
                        current_agent = node_name
                        out.append(await _emit_agent_active(node_name))
                    out.append(await _emit_text(node_name, msg.content))
            elif isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", "tool")
                summary = _get_tool_summary(tool_name, {"result": msg.content})
                if summary:
                    out.append(await _emit_tool_result(node_name, summary))
                elif msg.content:
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

        if "gate_pending" in output:
            out.append(await _emit_gate_pending(output["gate_pending"]))

    return out, current_agent, False


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
    
    # Verify mission exists
    if not _mission_exists(store, mission_id):
        yield await _emit_error(f"Mission not found: {mission_id}")
        return
    
    mission = store.get_mission(mission_id)
    
    # Verify mission status
    if mission.status != "active":
        yield await _emit_error(f"Mission is not active: {mission.status}")
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
        
        graph = await get_graph()
        
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
        
        thread_id = mission_id
        config = {
            "configurable": {
                "thread_id": thread_id,
            }
        }
        
        current_agent = None
        heartbeat_counter = 0
        next_input: Any = initial_state

        # Side channel for finding_added events. The listener fires from
        # whichever thread the persistence call runs on (LangGraph tools run
        # in run_in_executor), so we use a thread-safe queue.Queue and drain
        # it from the async loop between graph events.
        finding_q: "queue.Queue[dict]" = queue.Queue()
        deliverable_q: "queue.Queue[dict]" = queue.Queue()
        milestone_q: "queue.Queue[dict]" = queue.Queue()

        def _on_finding(payload: dict) -> None:
            finding_q.put_nowait(payload)

        def _on_deliverable(payload: dict) -> None:
            deliverable_q.put_nowait(payload)

        def _on_milestone(payload: dict) -> None:
            milestone_q.put_nowait(payload)

        register_finding_listener(mission_id, _on_finding)
        register_deliverable_listener(mission_id, _on_deliverable)
        register_milestone_listener(mission_id, _on_milestone)

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
            while True:
                try:
                    payload = milestone_q.get_nowait()
                except queue.Empty:
                    break
                out.append(_sse_event("milestone_done", _build_milestone_done_from_emit(payload)))
            return out

        # Drive the graph; on each __interrupt__ frame, park on a per-mission
        # resume future and continue with Command(resume=...) on the same
        # thread_id. Loop terminates when astream finishes without an
        # interrupt or when the resume wait times out.
        while True:
            interrupted = False
            async for event in graph.astream(next_input, config, stream_mode="updates"):
                heartbeat_counter += 1
                if heartbeat_counter % 10 == 0:
                    yield _sse_heartbeat()

                if not isinstance(event, dict):
                    continue

                sse_strings, current_agent, is_interrupt = await _emit_for_update(event, current_agent)
                for s in sse_strings:
                    if s:
                        yield s
                for s in _drain_events():
                    yield s
                if is_interrupt:
                    interrupted = True

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
                raise
            finally:
                _clear_pending_resume(mission_id, fut)

            next_input = Command(resume=resume_payload)

        if current_agent is not None:
            yield await _emit_agent_done(current_agent)

        yield await _emit_run_end()
    
    except Exception as e:
        logger.exception(f"Error in chat stream: {e}")
        yield await _emit_error(str(e))
    
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
        mission_lock.release()


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
            }
            for g in gates
        ],
        "milestones": [
            {
                "id": m.id,
                "workstream_id": m.workstream_id,
                "label": m.label,
                "status": m.status,
            }
            for m in milestones
        ],
        "findings": [
            {
                "id": f.id,
                "workstream_id": f.workstream_id,
                "hypothesis_id": f.hypothesis_id,
                "confidence": f.confidence,
                "claim_text": f.claim_text,
                "agent_id": f.agent_id,
            }
            for f in findings
        ],
        "hypotheses": [
            {
                "id": h.id,
                "text": h.text,
                "status": h.status,
            }
            for h in hypotheses
        ],
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
    }


# =============================================================================
# CHAT ENDPOINT (SSE STREAMING)
# =============================================================================

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
# GATE VALIDATION ENDPOINT
# =============================================================================

@app.post("/api/v1/missions/{mission_id}/gates/{gate_id}/validate", response_model=GateValidateResponse)
async def validate_gate(mission_id: str, gate_id: str, body: GateValidateRequest):
    """Validate gate and resume graph if approved."""
    store = get_store()
    
    if not _mission_exists(store, mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    
    mission = store.get_mission(mission_id)
    
    gate = None
    for g in store.list_gates(mission_id):
        if g.id == gate_id:
            gate = g
            break
    
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")
    
    if body.verdict not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Verdict must be APPROVED or REJECTED")
    
    expected_status = "completed" if body.verdict == "APPROVED" else "failed"
    if gate.status == expected_status:
        resume_id = f"resume-{uuid.uuid4().hex[:8]}"
        logger.info(f"Gate {gate_id} already {expected_status}, skipping resume")
        return GateValidateResponse(
            status="already_processed",
            mission_id=mission_id,
            gate_id=gate_id,
            resume_id=resume_id,
        )
    if gate.status in ("completed", "failed"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Gate has already been decided with status={gate.status}",
                "gate_id": gate_id,
                "gate_type": gate.gate_type,
                "lifecycle_status": gate.status,
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
    
    store.update_gate_status(gate_id, expected_status, notes=body.notes)

    resume_id = f"resume-{uuid.uuid4().hex[:8]}"
    approved = body.verdict == "APPROVED"
    resume_payload = {
        "approved": approved,
        "verdict": body.verdict,
        "notes": body.notes,
    }
    delivered = _deliver_resume(mission_id, resume_payload)

    if delivered:
        logger.info(
            f"Resume delivered to active stream: mission={mission_id} gate={gate_id} resume_id={resume_id}"
        )
        status = "resumed"
    else:
        # No stream is parked on this mission. The DB has been updated, but
        # without an active SSE consumer we deliberately do not start a
        # detached graph run — events would have nowhere to go and would
        # break the no-silent-degradation rule.
        logger.warning(
            f"Gate validated but no active stream to resume: mission={mission_id} gate={gate_id}"
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
    uvicorn.run(app, host=os.getenv("MARVIN_HOST", "127.0.0.1"), port=int(os.getenv("MARVIN_PORT", "8095")))


if __name__ == "__main__":
    run_server()
