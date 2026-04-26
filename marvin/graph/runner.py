"""
LangGraph runtime for Marvin mission orchestration.

Architecture:
- phase_router is a CONDITIONAL edge function (not a node)
- It returns route keys (strings) or Send objects for fan-out
- State updates happen in regular nodes, not in the router
- Each node returns dict state updates only
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from marvin.graph.gates import gate_node
from marvin.graph.subgraphs.calculus import calculus_agent_node
from marvin.graph.subgraphs.dora import dora_agent_node
from marvin.graph.subgraphs.orchestrator import orchestrator_agent_node
from marvin.graph.state import MarvinState
from marvin.mission.store import MissionStore


def _resolve_gate_by_day(mission_id: str, day: int) -> str:
    store = MissionStore()
    for gate in store.list_gates(mission_id):
        if gate.scheduled_day == day:
            return gate.id
    raise KeyError(f"gate not found for mission={mission_id} day={day}")


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
        return "papyrus_phase0"

    if phase == "framing":
        # framing_node handles this, route to it
        return "framing"

    if phase == "awaiting_confirmation":
        return "gate_entry"

    if phase == "confirmed":
        # Fan-out to dora and calculus in parallel
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
        w2_msg = HumanMessage(
            content=(
                f"Mission: {mission.client} - {mission.target}\n"
                "Task: W2 Financial Analysis (W2.1 unit economics, QoE, anomalies)\n"
                "No data room yet: use search_sec_filings for public data.\n"
                f"Hypotheses to test (use the bracketed id verbatim for any tool that takes hypothesis_id):\n{hyp_text}"
            )
        )
        return [
            Send("dora", {**state, "messages": messages + [w1_msg]}),
            Send("calculus", {**state, "messages": messages + [w2_msg]}),
        ]

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

    if phase == "gate_g3_passed":
        return "papyrus_delivery"

    if phase == "done":
        return END

    return "orchestrator"


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

    _generate_workstream_report_impl("W1", mission_id)
    _generate_workstream_report_impl("W2", mission_id)
    store.mark_workstream_delivered(mission_id, "W1")
    store.mark_workstream_delivered(mission_id, "W2")
    return {"phase": "research_done"}


async def papyrus_phase0_node(state: MarvinState) -> dict:
    """Generate engagement brief and move to framing phase."""
    from marvin.tools.papyrus_tools import generate_engagement_brief

    generate_engagement_brief(state)
    return {"phase": "framing"}


async def framing_node(state: MarvinState) -> dict:
    """Generate hypotheses and move to awaiting confirmation."""
    mission_id = state.get("mission_id", "")
    messages = state.get("messages", [])
    
    from marvin.tools.mission_tools import _generate_hypotheses_inline, generate_interview_guides

    hypotheses = _generate_hypotheses_inline(mission_id)
    generate_interview_guides([hypothesis.id for hypothesis in hypotheses], state=state)
    return {"phase": "awaiting_confirmation", "messages": messages}


async def gate_entry_node(state: MarvinState) -> dict:
    """Prepare gate state with pending_gate_id based on phase, then route to gate."""
    phase = state.get("phase", "")
    mission_id = state.get("mission_id", "")

    if phase == "awaiting_confirmation":
        gate_id = f"gate-{mission_id}-hyp-confirm"
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


async def merlin_node(state: MarvinState) -> dict:
    """Run merlin agent and determine next phase based on verdict."""
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
    verdict = verdict_row.verdict if verdict_row else "MINOR_FIXES"
    
    if verdict == "SHIP":
        return {**result, "phase": "synthesis_done"}

    count = state.get("synthesis_retry_count", 0) + 1
    if count >= 3:
        return {**result, "phase": "synthesis_done", "synthesis_retry_count": 0}
    # synthesis_retry, NOT redteam_done: routes back through adversus for
    # another red-team pass before merlin re-evaluates. redteam_done would
    # route directly to merlin and crash with KeyError when merlin's outgoing
    # path map is consulted (no self-loop entry).
    return {**result, "phase": "synthesis_retry", "synthesis_retry_count": count}


async def papyrus_delivery_node(state: MarvinState) -> dict:
    """Generate final deliverables and mark mission done."""
    mission_id = state.get("mission_id", "")
    messages = state.get("messages", [])
    
    msg = HumanMessage(
        content=(
            f"Mission: {mission_id}\n"
            "Task: Generate final deliverables.\n"
            "Call: generate_report_pdf, generate_exec_summary, generate_data_book"
        )
    )
    
    from marvin.tools.papyrus_tools import _generate_data_book_impl, _generate_exec_summary_impl, _generate_report_pdf_impl

    _generate_report_pdf_impl(mission_id)
    _generate_exec_summary_impl(mission_id)
    _generate_data_book_impl(mission_id)
    return {"phase": "done"}


def build_graph(checkpointer=None):
    """
    Build the Marvin mission orchestration graph.
    
    Uses conditional edges with phase_router to determine flow.
    Fan-out (parallel execution) handled via Send objects from router.
    """
    builder = StateGraph(MarvinState)
    
    # Add all regular nodes (these return dict state updates)
    builder.add_node("papyrus_phase0", papyrus_phase0_node)
    builder.add_node("framing", framing_node)
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
            "papyrus_phase0": "papyrus_phase0",
            "framing": "framing",
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
    builder.add_conditional_edges("papyrus_phase0", phase_router, {
        "framing": "framing",
        "gate": "gate",
        "orchestrator": "orchestrator",
        END: END,
    })
    
    builder.add_conditional_edges("framing", phase_router, {
        "gate_entry": "gate_entry",
        "gate": "gate",
        "orchestrator": "orchestrator",
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
        "papyrus_phase0": "papyrus_phase0",
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
