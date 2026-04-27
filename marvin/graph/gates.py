from __future__ import annotations

from langgraph.types import interrupt

from marvin.graph.state import MarvinState
from marvin.mission.store import MissionStore
from marvin.tools.arbiter_tools import check_internal_consistency


_GATE_COPY = {
    "hypothesis_confirmation": {
        "title": "Confirm initial hypotheses",
        "stage": "Framing",
        "summary": (
            "MARVIN has framed the deal into testable hypotheses. "
            "Approve to start parallel research workstreams. "
            "Reject to revise the framing before any research runs."
        ),
        "unlocks_on_approve": "Dora, Calculus, and Lector begin Day 1–3 research.",
        "unlocks_on_reject": "MARVIN reopens framing for revision.",
    },
    "manager_review": {
        "title": "Manager review of research claims",
        "stage": "Mid-mission checkpoint (G1)",
        "summary": (
            "Initial research is complete. Review the claims surfaced so far for "
            "soundness, sourcing, and confidence before red-team challenges them."
        ),
        "unlocks_on_approve": "Adversus runs the red-team challenge against the storyline.",
        "unlocks_on_reject": "Workstreams loop back for additional research.",
    },
    "final_review": {
        "title": "Final IC memo review",
        "stage": "Pre-delivery (G3)",
        "summary": (
            "Synthesis is complete after the red-team pass. "
            "Approve to finalize the IC memo and deliverables. "
            "Reject to send Merlin back through another synthesis pass."
        ),
        "unlocks_on_approve": "Papyrus produces the final memo and deliverable set.",
        "unlocks_on_reject": "Merlin re-runs synthesis incorporating remaining concerns.",
    },
}


def _human_copy(gate_type: str) -> dict:
    return _GATE_COPY.get(gate_type, {
        "title": gate_type.replace("_", " ").capitalize() if gate_type else "Validation required",
        "stage": "Mission checkpoint",
        "summary": "A gate is waiting for human review before the mission can proceed.",
        "unlocks_on_approve": "Mission continues to the next phase.",
        "unlocks_on_reject": "Mission pauses; team revisits the prior phase.",
    })


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

    gate_type = gate.gate_type if gate else "unknown"
    copy = _human_copy(gate_type)

    redteam_findings = [
        {"claim_text": f.claim_text, "confidence": f.confidence, "agent_id": f.agent_id}
        for f in findings
        if (f.agent_id or "").lower() == "adversus"
    ]
    research_findings = [
        {"claim_text": f.claim_text, "confidence": f.confidence, "agent_id": f.agent_id}
        for f in findings
        if (f.agent_id or "").lower() != "adversus"
    ]

    payload = {
        "gate_id": gate_id,
        "gate_type": gate_type,
        "format": gate.format if gate else "review_claims",
        "title": copy["title"],
        "stage": copy["stage"],
        "summary": copy["summary"],
        "unlocks_on_approve": copy["unlocks_on_approve"],
        "unlocks_on_reject": copy["unlocks_on_reject"],
        "hypotheses": [
            {"id": h.id, "text": h.text, "status": h.status} for h in hypotheses
        ],
        "research_findings": research_findings[-12:],
        "redteam_findings": redteam_findings[-8:],
        "findings_total": len(findings),
        "findings_snapshot": research_findings[-3:],
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
