from __future__ import annotations

from langgraph.types import interrupt

from marvin.graph.state import MarvinState
from marvin.mission.store import MissionStore
from marvin.tools.arbiter_tools import check_internal_consistency


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

    payload = {
        "gate_id": gate_id,
        "gate_type": gate.gate_type if gate else "unknown",
        "format": gate.format if gate else "review_claims",
        "findings_snapshot": [
            {"claim_text": finding.claim_text, "confidence": finding.confidence, "agent_id": finding.agent_id}
            for finding in findings[-3:]
        ],
        "arbiter_flags": arbiter_result.get("inconsistencies", []) + arbiter_result.get("flags", []),
    }

    if config:
        from langchain_core.callbacks import adispatch_custom_event
        import asyncio

        await adispatch_custom_event("gate_pending", payload, config=config)
        await asyncio.sleep(0.1)

    decision = interrupt(payload)
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
