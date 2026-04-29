from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from marvin.graph.gate_material import evaluate_gate_material, human_gate_copy
from marvin.graph.state import MarvinState
from marvin.mission.schema import Gate
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

    extra_messages: list = []
    if not approved:
        # A rejected gate must (a) tell the user what re-runs next instead of
        # the dead-end "Awaiting further instructions" frontend message, and
        # (b) leave a fresh pending gate row for the retry pass to land on —
        # the just-failed row would refuse to re-open in evaluate_gate_material.
        retry_msg = _retry_message_for(gate)
        if retry_msg:
            extra_messages.append(AIMessage(content=retry_msg))
        _seed_retry_gate(store, gate)

    return {
        "gate_passed": approved,
        "pending_gate_id": None,
        "phase": _gate_to_next_phase(gate_id, gate, approved),
        "messages": extra_messages,
    }


def _retry_message_for(gate) -> str:
    if gate is None:
        return ""
    if gate.gate_type == "hypothesis_confirmation":
        return (
            "Hypotheses sent back for revision. Re-running framing to produce "
            "updated hypotheses."
        )
    if gate.gate_type == "manager_review":
        return (
            "Research claims rejected. Looping W1 and W2 back for additional "
            "passes — G1 will fire again once the next round completes."
        )
    if gate.gate_type == "final_review":
        return (
            "Synthesis sent back for another pass. Merlin will re-run with the "
            "rejection notes — G3 will fire again with a new verdict."
        )
    return ""


def _seed_retry_gate(store: MissionStore, original_gate: Gate) -> str:
    """Create a fresh pending gate row so the retry pass has somewhere to land.

    The original failed row stays on the audit trail. Re-using it as pending
    would erase the rejection notes; creating a sibling row keeps history
    intact while letting evaluate_gate_material re-open the gate cleanly.
    """
    siblings = [
        gate
        for gate in store.list_gates(original_gate.mission_id)
        if gate.scheduled_day == original_gate.scheduled_day
        and gate.gate_type == original_gate.gate_type
    ]
    retry_count = sum(1 for gate in siblings if "-retry-" in gate.id) + 1
    new_id = f"{original_gate.id}-retry-{retry_count}"
    store.save_gate(
        Gate(
            id=new_id,
            mission_id=original_gate.mission_id,
            gate_type=original_gate.gate_type,
            scheduled_day=original_gate.scheduled_day,
            validator_role=original_gate.validator_role,
            status="pending",
            format=original_gate.format,
            questions=original_gate.questions,
        )
    )
    return new_id


def _gate_to_next_phase(gate_id: str, gate, approved: bool) -> str:
    if gate is None:
        return "idle"

    if gate.gate_type == "hypothesis_confirmation":
        return "confirmed" if approved else "framing"

    if gate.scheduled_day <= 3:
        # G1 reject re-triggers the W1+W2 fan-out via the "confirmed" phase.
        # phase_router's confirmed branch is idempotent on data_decision, so
        # the retry pass goes straight to dora+calculus and back to G1.
        return "gate_g1_passed" if approved else "confirmed"

    if gate.scheduled_day <= 10:
        return "gate_g3_passed" if approved else "redteam_done"

    return "idle"
