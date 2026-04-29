"""
LangGraph runtime for Marvin mission orchestration.

Architecture:
- phase_router is a CONDITIONAL edge function (not a node)
- It returns route keys (strings) or Send objects for fan-out
- State updates happen in regular nodes, not in the router
- Each node returns dict state updates only
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from marvin.graph.gates import gate_node
from marvin.graph.subgraphs.calculus import calculus_agent_node
from marvin.graph.subgraphs.dora import dora_agent_node
from marvin.graph.subgraphs.framing_orchestrator import (
    framing_orchestrator_node,
    reset_clarification_state,
)
from marvin.graph.subgraphs.orchestrator import orchestrator_agent_node
from marvin.graph.state import MarvinState
from marvin.mission.store import MissionStore
from marvin.runtime_debug import log_node_entry

logger = logging.getLogger(__name__)


# Bug 3 (chantier 2.6): pre-flight check before launching W2 financial agent.
# Heuristic stand-in for a proper SEC EDGAR check; the spec lists the same set.
_KNOWN_PRIVATE_TARGETS: tuple[str, ...] = (
    "mistral", "cursor", "anthropic", "openai", "perplexity",
    "vinted", "doctolib", "exotec", "stripe", "spacex",
)


def _check_data_availability(mission_id: str) -> dict:
    """Pre-flight check before launching Calculus.

    Returns dict with calculus_viable: bool, reason: str, recommendation: str.
    A target marked private with no data_room_path is not viable; the user
    must decide whether to skip W2, proceed in LOW_CONFIDENCE only, or pause
    and supply a data room.
    """
    store = MissionStore()
    mission = store.get_mission(mission_id)
    target = (mission.target or "").lower().strip()
    if not target:
        return {
            "calculus_viable": False,
            "reason": "no target specified",
            "recommendation": "Cannot run financial analysis without target.",
        }
    is_private = any(kw in target for kw in _KNOWN_PRIVATE_TARGETS)
    has_data_room = bool(mission.data_room_path)
    if is_private and not has_data_room:
        return {
            "calculus_viable": False,
            "reason": (
                f"{mission.target} appears private/non-US — SEC filings unlikely "
                "to have material content"
            ),
            "recommendation": (
                "Skip W2 financial analysis or request data room. Calculus would "
                "produce only LOW_CONFIDENCE findings."
            ),
        }
    return {
        "calculus_viable": True,
        "reason": "data sources available",
        "recommendation": "proceed",
    }


def _resolve_gate_by_day(mission_id: str, day: int) -> str:
    """Return the gate id to open for a given day.

    Prefers the most recently created pending row so that retry rows
    seeded by gate_node on rejection (suffixed -retry-N) win over the
    original failed row that would refuse to re-open.
    """
    store = MissionStore()
    candidates = [gate for gate in store.list_gates(mission_id) if gate.scheduled_day == day]
    pending = [gate for gate in candidates if gate.status == "pending"]
    if pending:
        return pending[-1].id
    if candidates:
        return candidates[-1].id
    raise KeyError(f"gate not found for mission={mission_id} day={day}")


def _resolve_gate_by_type(mission_id: str, gate_type: str) -> str:
    """Same selection logic as _resolve_gate_by_day, keyed on gate_type."""
    store = MissionStore()
    candidates = [gate for gate in store.list_gates(mission_id) if gate.gate_type == gate_type]
    pending = [gate for gate in candidates if gate.status == "pending"]
    if pending:
        return pending[-1].id
    if candidates:
        return candidates[-1].id
    raise KeyError(f"gate not found for mission={mission_id} type={gate_type}")


def phase_router(state: MarvinState) -> str | list[Send]:
    """
    Conditional router function that determines next node based on phase.
    
    Returns:
        - String: route key for the next node
        - List[Send]: for fan-out to multiple nodes
        - END: terminate execution
    """
    phase = state.get("phase", "setup")
    mission_id = state.get("mission_id", "")
    messages = state.get("messages", [])

    if phase == "setup":
        return "framing"

    if phase == "framing":
        # Two-step framing:
        #   - framing_orchestrator first evaluates whether the brief is
        #     substantial enough; asks clarification questions if not.
        #   - Only when framing_complete=True does framing_node generate
        #     hypotheses, the engagement brief, and the framing memo.
        if not state.get("framing_complete"):
            return "framing_orchestrator"
        return "framing"

    if phase == "awaiting_clarification":
        # Orchestrator just opened a clarification gate and set
        # pending_gate_id. Route directly to gate_node; gate_node will
        # dispatch gate_pending over SSE and interrupt for the user's
        # answers.
        return "gate"

    if phase == "awaiting_confirmation":
        return "gate_entry"

    if phase == "confirmed":
        # Bug 3 (chantier 2.6): pre-flight data availability check before
        # launching Calculus. A private/non-US target with no data room
        # cannot produce KNOWN findings — fire a 3-option gate so the user
        # decides upfront instead of discovering empty findings at G1.
        data_decision = state.get("data_decision")
        if not data_decision:
            check = _check_data_availability(mission_id)
            if not check["calculus_viable"]:
                # Persist a data-availability gate row so the gate machinery
                # can surface it via SSE and resume on user decision.
                store = MissionStore()
                gate_id = f"gate-{mission_id}-data-availability"
                from marvin.mission.schema import Gate
                existing = next((g for g in store.list_gates(mission_id) if g.id == gate_id), None)
                if existing is None:
                    store.save_gate(Gate(
                        id=gate_id,
                        mission_id=mission_id,
                        gate_type="data_availability",
                        scheduled_day=2,
                        validator_role="manager",
                        status="pending",
                        format="data_decision",
                        questions=[(
                            f"Calculus cannot run financial analysis: {check['reason']}. "
                            "How should we proceed? Options: skip_calculus | "
                            "proceed_low_confidence | request_data_room."
                        )],
                    ))
                return [Send("gate", {**state, "pending_gate_id": gate_id, "phase": "awaiting_data_decision"})]

        store = MissionStore()
        mission = store.get_mission(mission_id)
        hypotheses = store.list_hypotheses(mission_id)
        hyp_text = "\n".join([f"- [{hypothesis.id}] {hypothesis.text}" for hypothesis in hypotheses])

        w1_msg = HumanMessage(
            content=(
                f"Mission: {mission.client} - {mission.target}\n"
                f"IC: {mission.ic_question}\n"
                "Task: W1 Market & Competitive Analysis (W1.1, W1.2, W1.3)\n"
                f"Hypotheses to test (use the bracketed id verbatim for any tool that takes hypothesis_id):\n{hyp_text}\n"
                "Deliver each milestone via mark_milestone_delivered()."
            )
        )
        if data_decision == "skip_calculus":
            # Run W1 only; research_join still advances to research_done.
            return [Send("dora", {**state, "messages": messages + [w1_msg]})]

        caveat = ""
        if data_decision == "proceed_low_confidence":
            caveat = (
                "\nDATA CAVEAT: target is private and no data room is available. "
                "Findings must be LOW_CONFIDENCE; do not fabricate KNOWN/REASONED "
                "claims from missing data."
            )
        w2_msg = HumanMessage(
            content=(
                f"Mission: {mission.client} - {mission.target}\n"
                "Task: W2 Financial Analysis (W2.1 unit economics, QoE, anomalies)\n"
                "No data room yet: use search_sec_filings for public data."
                f"{caveat}\n"
                f"Hypotheses to test (use the bracketed id verbatim for any tool that takes hypothesis_id):\n{hyp_text}"
            )
        )
        return [
            Send("dora", {**state, "messages": messages + [w1_msg]}),
            Send("calculus", {**state, "messages": messages + [w2_msg]}),
        ]

    if phase == "awaiting_data_decision":
        return "gate"

    if phase == "awaiting_data_room":
        return END

    if phase == "research_done":
        return "gate_entry"

    if phase == "gate_g1_passed":
        return "adversus"

    if phase == "redteam_done":
        return "merlin"

    if phase == "synthesis_retry":
        # Merlin asked for another red-team pass before re-evaluating.
        # Bounce through adversus first; adversus will return redteam_done,
        # which routes back to merlin for a fresh verdict. Returning "merlin"
        # here would map to merlin's own conditional-edge path map, which
        # intentionally does not include a "merlin" key (no self-loop).
        return "adversus"

    if phase == "synthesis_done":
        return "gate_entry"

    if phase == "merlin_failed":
        # Merlin ran but did not persist a verdict. Do not advance to G3 with
        # an empty verdict. Terminate the run; user must re-trigger synthesis.
        return END

    if phase == "gate_g3_passed":
        return "papyrus_delivery"

    if phase == "done":
        return END

    # Default: do NOT route to orchestrator. Orchestrator is reserved for
    # explicit free-form user questions, not as a fallback for unknown phases.
    # An unknown/idle phase means the graph has nothing to do — terminate the
    # run and wait for the next user input. This prevents the infinite
    # orchestrator self-loop that occurs when gate_node returns phase="idle".
    return END


def _log_join(state: MarvinState) -> None:
    log_node_entry("research_join", state)


def research_join(state: MarvinState) -> dict:
    """Deterministic join after the dora/calculus parallel branches.

    Reaching this node means both branches have already returned (LangGraph
    waits on every Send fan-out edge). The graph's contract is "these two
    parallel branches collectively constitute the W1+W2 research milestone",
    so we mark the gating milestones idempotently and advance the phase
    unconditionally. Previously this node gated phase advancement on whether
    each agent had called mark_milestone_delivered for W1.1/W2.1; an asymmetric
    prompt (only dora was told to mark) left W2.1 perpetually pending, the
    join returned `{}`, and phase_router re-fanned the parallel branches into
    an infinite loop. Coupling graph progression to LLM tool selection is the
    same anti-pattern we removed for event ownership in marvin.events — the
    fix is to own the business fact in graph control flow.
    """
    _log_join(state)
    mission_id = state.get("mission_id", "")
    store = MissionStore()

    for milestone_id in ("W1.1", "W2.1"):
        try:
            store.mark_milestone_delivered(
                milestone_id,
                "research branch complete",
                mission_id=mission_id,
            )
        except KeyError:
            # Milestone not seeded for this mission — defensive boundary only.
            pass

    from marvin.tools.papyrus_tools import _generate_workstream_report_impl

    for workstream_id in ("W1", "W2"):
        report = _generate_workstream_report_impl(workstream_id, mission_id)
        if report.get("status") == "blocked":
            continue
        store.mark_workstream_delivered(mission_id, workstream_id)
    return {"phase": "research_done"}


async def framing_node(state: MarvinState) -> dict:
    """Generate hypotheses through the framing LLM and surface a
    conversational reply in chat. Then move to awaiting confirmation."""
    from langchain_core.messages import AIMessage

    mission_id = state.get("mission_id", "")
    messages = state.get("messages", [])

    from marvin.tools.mission_tools import (
        generate_framing_with_reply,
        generate_interview_guides,
        persist_framing_from_brief,
    )
    from marvin.tools.papyrus_tools import (
        _generate_framing_memo_impl,
        generate_engagement_brief,
    )

    raw_brief = ""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            raw_brief = str(message.content)
            break

    if not raw_brief.strip():
        # The framing orchestrator may have already persisted a brief from
        # earlier turns. Use that as the source of truth before giving up.
        from marvin.mission.store import MissionStore

        existing_brief = MissionStore().get_mission_brief(mission_id)
        if existing_brief and (existing_brief.raw_brief or "").strip():
            raw_brief = existing_brief.raw_brief
        else:
            logger.info("framing_node: waiting for a non-empty human brief")
            return {"phase": "setup", "messages": messages}

    persist_framing_from_brief(mission_id, raw_brief)
    hypotheses, reply_prose = generate_framing_with_reply(mission_id, raw_brief)
    generate_interview_guides([hypothesis.id for hypothesis in hypotheses], state=state)
    generate_engagement_brief(state)
    # Framing memo: a one-page record of the brief plus any clarifications
    # collected during the orchestrator's question-and-answer rounds.
    from marvin.graph.subgraphs.framing_orchestrator import get_clarification_answers

    try:
        _generate_framing_memo_impl(
            mission_id,
            clarifications=get_clarification_answers(mission_id),
        )
    except Exception as exc:  # noqa: BLE001 — never block framing on memo write
        logger.warning("framing_node: framing_memo generation failed: %s", exc)

    reset_clarification_state(mission_id)
    return {
        "phase": "awaiting_confirmation",
        "messages": messages + [AIMessage(content=reply_prose)],
        "framing_complete": True,
    }


async def gate_entry_node(state: MarvinState) -> dict:
    """Prepare gate state with pending_gate_id based on phase, then route to gate."""
    phase = state.get("phase", "")
    mission_id = state.get("mission_id", "")

    if phase == "awaiting_confirmation":
        # After a rejection-and-retry, gate_node has seeded a new pending
        # hyp-confirm row; resolve to that one (or the original) instead of
        # hard-coding the base id.
        gate_id = _resolve_gate_by_type(mission_id, "hypothesis_confirmation")
        return {"pending_gate_id": gate_id}

    if phase == "research_done":
        gate_id = _resolve_gate_by_day(mission_id, day=3)
        return {"pending_gate_id": gate_id}

    if phase == "synthesis_done":
        gate_id = _resolve_gate_by_day(mission_id, day=10)
        return {"pending_gate_id": gate_id}

    return {}


async def adversus_node(state: MarvinState) -> dict:
    """Run adversus agent and move to redteam_done phase."""
    log_node_entry("adversus", state)
    mission_id = state.get("mission_id", "")
    messages = state.get("messages", [])
    store = MissionStore()
    hypotheses = store.list_hypotheses(mission_id, status="active")
    hyp_text = "\n".join([f"[{hypothesis.id}] {hypothesis.text}" for hypothesis in hypotheses])
    
    msg = HumanMessage(
        content=(
            f"Mission: {mission_id}\n"
            "Task: Red-team all active hypotheses.\n"
            "Attack each from 3 angles: empirical, logical, contextual.\n"
            "Run PESTEL. Generate stress scenarios. Identify weakest link.\n"
            "Persist ALL findings via add_finding_to_mission().\n"
            f"Hypotheses:\n{hyp_text}"
        )
    )
    
    from marvin.graph.subgraphs.adversus import adversus_agent_node as _adversus_agent_node

    result = await _adversus_agent_node({**state, "messages": messages + [msg]})
    return {**result, "phase": "redteam_done"}


ADVERSUS_FINDING_CAP = 12
SYNTHESIS_MAX_RETRIES = 3


def _next_phase_after_merlin(
    verdict: str,
    retry_count: int,
    current_finding_count: int,
    last_finding_count: int,
    adversus_finding_count: int,
) -> dict:
    """Pure decision for what comes after a merlin verdict.

    Three circuit breakers prevent the post-cap retry loop seen on the Mistral
    mission (Bug 6 — chantier 2.5):
      1. retry_count has reached SYNTHESIS_MAX_RETRIES.
      2. retry produced no new findings since the last verdict.
      3. adversus has hit its 12-finding cap (any further pass is identical).

    Any breaker forces phase=synthesis_done with forced_advance=True so the
    UI surfaces a transparent "advanced after {force_reason}" line instead of
    silently looping. SHIP advances cleanly with no retry counter reset noise.
    """
    if verdict == "SHIP":
        return {"phase": "synthesis_done"}

    base = {"phase": "synthesis_done", "synthesis_retry_count": 0, "forced_advance": True}
    if retry_count >= SYNTHESIS_MAX_RETRIES:
        return {**base, "force_reason": "max_retries"}
    if retry_count > 0 and current_finding_count == last_finding_count:
        return {**base, "force_reason": "no_new_findings"}
    if adversus_finding_count >= ADVERSUS_FINDING_CAP:
        return {**base, "force_reason": "adversus_cap_reached"}

    return {
        "phase": "synthesis_retry",
        "synthesis_retry_count": retry_count + 1,
        "last_verdict_at_finding_count": current_finding_count,
    }


async def merlin_node(state: MarvinState) -> dict:
    """Run merlin agent and determine next phase based on verdict."""
    log_node_entry("merlin", state)
    mission_id = state.get("mission_id", "")
    messages = state.get("messages", [])

    msg = HumanMessage(
        content=(
            f"Mission: {mission_id}\n"
            "Task: Evaluate storyline quality.\n"
            "Check MECE. Update action titles.\n"
            "Call set_merlin_verdict(verdict=..., notes=...) before returning.\n"
            "Verdict options: SHIP | MINOR_FIXES | BACK_TO_DRAWING_BOARD"
        )
    )

    from marvin.graph.subgraphs.merlin import merlin_agent_node as _merlin_agent_node

    result = await _merlin_agent_node({**state, "messages": messages + [msg]})
    store = MissionStore()
    verdict_row = store.get_latest_merlin_verdict(mission_id)
    if not verdict_row:
        # No silent default. A missing verdict means Merlin's LLM never called
        # set_merlin_verdict — defaulting to MINOR_FIXES would let phase
        # advance to synthesis_done and open G3 with zero merlin_verdicts
        # rows, exactly the failure mode this guard prevents.
        logger.error(
            "merlin_node: no verdict persisted for %s; blocking phase "
            "advancement so G3 cannot open without a verdict",
            mission_id,
        )
        err = AIMessage(
            content=(
                "Merlin did not produce a verdict for this synthesis pass. "
                "G3 cannot open without a verdict. Re-run synthesis to retry."
            )
        )
        return {**result, "phase": "merlin_failed", "messages": [err]}
    verdict = verdict_row.verdict

    findings = store.list_findings(mission_id)
    adversus_count = sum(1 for f in findings if f.agent_id == "adversus")
    decision = _next_phase_after_merlin(
        verdict=verdict,
        retry_count=int(state.get("synthesis_retry_count", 0) or 0),
        current_finding_count=len(findings),
        last_finding_count=int(state.get("last_verdict_at_finding_count", 0) or 0),
        adversus_finding_count=adversus_count,
    )
    return {**result, **decision}


async def papyrus_delivery_node(state: MarvinState) -> dict:
    """Generate final deliverables, mark mission complete, and emit completion message."""
    mission_id = state.get("mission_id", "")

    from marvin.tools.papyrus_tools import (
        _generate_data_book_impl,
        _generate_exec_summary_impl,
        _generate_report_pdf_impl,
        _generate_workstream_report_impl,
    )
    from marvin.mission.store import MissionStore

    _generate_report_pdf_impl(mission_id)
    _generate_exec_summary_impl(mission_id)
    _generate_data_book_impl(mission_id)
    _generate_workstream_report_impl("W4", mission_id)

    # Persist mission completion so reconnects and API calls see the final state.
    try:
        store = MissionStore()
        store.update_mission_status(mission_id, "complete")
        store.close()
    except Exception:  # noqa: BLE001 - status update is best-effort; don't crash delivery
        pass

    completion_msg = AIMessage(
        content=(
            "Mission complete. The executive summary, data book, and workstream reports "
            "are ready for review. All deliverables have been generated and persisted."
        )
    )
    return {"phase": "done", "messages": [completion_msg]}


def build_graph(checkpointer=None):
    """
    Build the Marvin mission orchestration graph.
    
    Uses conditional edges with phase_router to determine flow.
    Fan-out (parallel execution) handled via Send objects from router.
    """
    builder = StateGraph(MarvinState)
    
    # Add all regular nodes (these return dict state updates)
    builder.add_node("framing", framing_node)
    builder.add_node("framing_orchestrator", framing_orchestrator_node)
    builder.add_node("dora", dora_agent_node)
    builder.add_node("calculus", calculus_agent_node)
    builder.add_node("research_join", research_join)
    builder.add_node("gate_entry", gate_entry_node)
    builder.add_node("gate", gate_node)
    builder.add_node("adversus", adversus_node)
    builder.add_node("merlin", merlin_node)
    builder.add_node("papyrus_delivery", papyrus_delivery_node)
    builder.add_node("orchestrator", orchestrator_agent_node)
    
    # Entry point with conditional routing
    builder.add_conditional_edges(
        START,
        phase_router,
        {
            "framing": "framing",
            "framing_orchestrator": "framing_orchestrator",
            "gate_entry": "gate_entry",
            "gate": "gate",
            "dora": "dora",
            "calculus": "calculus",
            "adversus": "adversus",
            "merlin": "merlin",
            "papyrus_delivery": "papyrus_delivery",
            "orchestrator": "orchestrator",
            END: END,
        }
    )

    # Each node returns to phase_router for next routing decision
    builder.add_conditional_edges("framing", phase_router, {
        "gate_entry": "gate_entry",
        "gate": "gate",
        "orchestrator": "orchestrator",
        END: END,
    })

    # framing_orchestrator either advances to framing (when ready) or opens
    # a clarification gate that routes through the standard gate node.
    builder.add_conditional_edges("framing_orchestrator", phase_router, {
        "framing": "framing",
        "framing_orchestrator": "framing_orchestrator",
        "gate": "gate",
        END: END,
    })

    # gate_entry deterministically forwards to gate after writing pending_gate_id
    builder.add_edge("gate_entry", "gate")
    
    builder.add_conditional_edges("gate", phase_router, {
        "dora": "dora",
        "calculus": "calculus",
        "adversus": "adversus",
        "merlin": "merlin",
        "papyrus_delivery": "papyrus_delivery",
        "orchestrator": "orchestrator",
        # After a clarification gate completes, gate_node returns
        # phase=framing → router routes to framing_orchestrator (since
        # framing_complete is still False) for re-evaluation with the
        # newly-recorded answer.
        "framing": "framing",
        "framing_orchestrator": "framing_orchestrator",
        END: END,
    })
    
    # Parallel branches join at research_join
    builder.add_edge("dora", "research_join")
    builder.add_edge("calculus", "research_join")
    
    builder.add_conditional_edges("research_join", phase_router, {
        "gate_entry": "gate_entry",
        "gate": "gate",
        "adversus": "adversus",
        "orchestrator": "orchestrator",
        END: END,
    })
    
    builder.add_conditional_edges("adversus", phase_router, {
        "merlin": "merlin",
        "gate": "gate",
        "orchestrator": "orchestrator",
        END: END,
    })
    
    builder.add_conditional_edges("merlin", phase_router, {
        "gate_entry": "gate_entry",
        "gate": "gate",
        "adversus": "adversus",
        "papyrus_delivery": "papyrus_delivery",
        "orchestrator": "orchestrator",
        END: END,
    })
    
    builder.add_conditional_edges("papyrus_delivery", phase_router, {
        "orchestrator": "orchestrator",
        END: END,
    })
    
    builder.add_conditional_edges("orchestrator", phase_router, {
        "framing": "framing",
        "gate_entry": "gate_entry",
        "gate": "gate",
        "dora": "dora",
        "calculus": "calculus",
        "adversus": "adversus",
        "merlin": "merlin",
        "papyrus_delivery": "papyrus_delivery",
        # Self-loop: phase_router falls through to "orchestrator" for any
        # unrecognized phase. Without this entry the orchestrator node
        # cannot route back to itself and the graph crashes with
        # KeyError: 'orchestrator'.
        "orchestrator": "orchestrator",
        END: END,
    })
    
    return builder.compile(checkpointer=checkpointer or MemorySaver())
