from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from marvin.graph.gate_material import evaluate_gate_material, human_gate_copy
from marvin.graph.state import MarvinState
from marvin.mission.store import MissionStore
from marvin.tools.arbiter_tools import check_internal_consistency


logger = logging.getLogger(__name__)


def _human_copy(gate_type: str) -> dict[str, str]:
    """Backward-compatible alias for existing tests/imports."""
    return human_gate_copy(gate_type)


async def gate_node(state: MarvinState, config=None) -> dict:
    gate_id = state.get("pending_gate_id")
    mission_id = state.get("mission_id")

    if not gate_id:
        return {"phase": "idle"}
    if not mission_id:
        raise KeyError("mission_id not in state")

    store = MissionStore()
    arbiter_result = check_internal_consistency(mission_id)
    gates = store.list_gates(mission_id)
    gate = next((candidate for candidate in gates if candidate.id == gate_id), None)
    findings = store.list_findings(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    mission_brief = store.get_mission_brief(mission_id)
    workstreams = store.list_workstreams(mission_id)
    milestones = store.list_milestones(mission_id)

    if gate is None:
        return {"phase": "idle", "pending_gate_id": None}

    arbiter_flags = arbiter_result.get("inconsistencies", []) + arbiter_result.get("flags", [])
    material = evaluate_gate_material(
        store,
        mission_id,
        gate,
        hypotheses=hypotheses,
        findings=findings,
        mission_brief=mission_brief,
        workstreams=workstreams,
        milestones=milestones,
        arbiter_flags=arbiter_flags,
    )
    if not material.is_open:
        logger.info(
            "gate_node: gate %s not opened; missing material: %s",
            gate_id,
            ", ".join(material.missing_material),
        )
        return {"phase": "idle", "pending_gate_id": None}

    payload = dict(material.review_payload)
    research_findings = payload.get("research_findings", [])
    payload["findings_snapshot"] = research_findings[-3:]

    if config:
        from langchain_core.callbacks import adispatch_custom_event
        import asyncio

        await adispatch_custom_event("gate_pending", payload, config=config)
        await asyncio.sleep(0.1)

    decision = interrupt(payload)

    # Clarification gate: the decision payload carries `answers`, not a
    # verdict. Persist each answer to the mission, mark the gate completed
    # for audit, and route back to framing for re-evaluation by the
    # orchestrator with the new context appended.
    # Bug 3 (chantier 2.6): data-availability gate carries the user's
    # decision (skip_calculus / proceed_low_confidence / request_data_room)
    # in the answers payload. Persist the gate as completed and write the
    # decision back to graph state so phase_router can re-fan-out research.
    if gate.format == "data_decision":
        decision_value = decision.get("decision") or decision.get("verdict") or ""
        decision_value = str(decision_value).strip().lower()
        valid = {"skip_calculus", "proceed_low_confidence", "request_data_room"}
        if decision_value not in valid:
            decision_value = "proceed_low_confidence"
        store.update_gate_status(
            gate_id, "completed", notes=f"data_decision={decision_value}",
        )
        if decision_value == "request_data_room":
            return {
                "pending_gate_id": None,
                "data_decision": decision_value,
                "phase": "awaiting_data_room",
            }
        return {
            "pending_gate_id": None,
            "data_decision": decision_value,
            "phase": "confirmed",
        }

    if gate.format == "clarification_questions":
        answers = decision.get("answers")
        if not isinstance(answers, list):
            answers = []
        joined = "; ".join(str(a).strip() for a in answers if str(a).strip())
        if joined:
            store.append_clarification_answer(mission_id, joined)
        store.update_gate_status(
            gate_id,
            "completed",
            notes=decision.get("notes") or (joined or "no answers provided"),
        )
        return {
            "pending_gate_id": None,
            "phase": "framing",
            "messages": [HumanMessage(content=joined)] if joined else [],
        }

    approved = decision.get("approved", False) or decision.get("verdict") == "APPROVED"
    store.update_gate_status(gate_id, "completed" if approved else "failed", notes=decision.get("notes", ""))

    return {
        "gate_passed": approved,
        "pending_gate_id": None,
        "phase": _gate_to_next_phase(gate_id, gate, approved),
    }


def _gate_to_next_phase(gate_id: str, gate, approved: bool) -> str:
    if gate is None:
        return "idle"

    if gate.gate_type == "hypothesis_confirmation":
        return "confirmed" if approved else "framing"

    if gate.scheduled_day <= 3:
        return "gate_g1_passed" if approved else "research_done"

    if gate.scheduled_day <= 10:
        return "gate_g3_passed" if approved else "redteam_done"

    return "idle"
