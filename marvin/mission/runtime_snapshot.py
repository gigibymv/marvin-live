from __future__ import annotations

from typing import Any

from marvin.graph.gate_material import GateMaterial
from marvin.mission.schema import (
    Deliverable,
    Finding,
    Gate,
    Hypothesis,
    Milestone,
    Mission,
    MissionBrief,
    Workstream,
)


_RESEARCH_WORKSTREAMS = {"W1", "W2"}
_STRESS_WORKSTREAMS = {"W3", "W4"}
_FINAL_DELIVERABLE_TYPES = {"exec_summary", "executive_summary", "data_book", "stress_testing_report"}


def build_mission_runtime_snapshot(
    *,
    mission: Mission,
    gates: list[Gate],
    gate_material: dict[str, GateMaterial],
    milestones: list[Milestone],
    findings: list[Finding],
    hypotheses: list[Hypothesis],
    deliverables: list[Deliverable],
    workstreams: list[Workstream],
    mission_brief: MissionBrief | None,
    merlin_verdict: Any | None = None,
) -> dict[str, Any]:
    """Return the canonical mission truth consumed by /progress and the UI.

    This is intentionally derived from persisted business facts, not from live
    SSE events. SSE remains transport; this snapshot answers "what is MARVIN
    actually waiting on right now?" after refresh, resume, or a long-running
    agent pass.
    """

    mission_complete = mission.status in {"complete", "completed"}
    active_agents = [] if mission_complete else _dedupe_agents(mission.active_phase_agents or [])
    open_gate = _open_gate(gates, gate_material)
    blockers = _blockers(gates, gate_material)
    current_phase = _derive_current_phase(
        mission=mission,
        open_gate=open_gate,
        mission_brief=mission_brief,
        hypotheses=hypotheses,
        gates=gates,
        milestones=milestones,
        deliverables=deliverables,
        active_agents=active_agents,
        merlin_verdict=merlin_verdict,
    )
    workstream_contracts = _workstream_contracts(workstreams, milestones, deliverables, findings)
    deliverable_contract = _deliverable_contract(deliverables)
    waiting_reason = _waiting_reason(
        mission=mission,
        open_gate=open_gate,
        active_agents=active_agents,
        blockers=blockers,
        current_phase=current_phase,
    )
    next_action = _next_action(
        mission=mission,
        open_gate=open_gate,
        active_agents=active_agents,
        blockers=blockers,
        current_phase=current_phase,
    )

    return {
        "mission_id": mission.id,
        "status": mission.status,
        "current_phase": current_phase,
        "active_agents": active_agents,
        "active_agent": mission.active_agent if mission.active_agent in active_agents else None,
        "open_gate": open_gate,
        "blockers": blockers,
        "waiting_reason": waiting_reason,
        "next_action": next_action,
        "workstreams": workstream_contracts,
        "deliverables": deliverable_contract,
        "counts": {
            "hypotheses": len(hypotheses),
            "findings": len(findings),
            "deliverables_ready": sum(1 for d in deliverables if (d.status or "").lower() == "ready"),
            "milestones_delivered": sum(1 for m in milestones if (m.status or "").lower() == "delivered"),
            "milestones_blocked": sum(1 for m in milestones if (m.status or "").lower() == "blocked"),
        },
    }


def _dedupe_agents(active_agents: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for agent in active_agents:
        key = (agent or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _open_gate(gates: list[Gate], gate_material: dict[str, GateMaterial]) -> dict[str, Any] | None:
    open_rows: list[tuple[int, Gate, GateMaterial]] = []
    for gate in gates:
        material = gate_material.get(gate.id)
        if material is None or not material.is_open:
            continue
        open_rows.append((gate.scheduled_day, gate, material))
    if not open_rows:
        return None
    _, gate, material = sorted(open_rows, key=lambda row: (row[0], row[1].id))[-1]
    return {
        "id": gate.id,
        "gate_type": gate.gate_type,
        "scheduled_day": gate.scheduled_day,
        "title": material.review_payload.get("title"),
        "stage": material.review_payload.get("stage"),
        "missing_material": list(material.missing_material),
    }


def _blockers(gates: list[Gate], gate_material: dict[str, GateMaterial]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for gate in sorted(gates, key=lambda g: (g.scheduled_day, g.id)):
        material = gate_material.get(gate.id)
        if material is None:
            continue
        if gate.status == "failed":
            blockers.append(
                {
                    "type": "gate_failed",
                    "gate_id": gate.id,
                    "gate_type": gate.gate_type,
                    "reason": gate.failure_reason or gate.completion_notes,
                }
            )
        if gate.status == "pending" and material.missing_material:
            blockers.append(
                {
                    "type": "gate_material_missing",
                    "gate_id": gate.id,
                    "gate_type": gate.gate_type,
                    "missing_material": list(material.missing_material),
                }
            )
    return blockers


def _derive_current_phase(
    *,
    mission: Mission,
    open_gate: dict[str, Any] | None,
    mission_brief: MissionBrief | None,
    hypotheses: list[Hypothesis],
    gates: list[Gate],
    milestones: list[Milestone],
    deliverables: list[Deliverable],
    active_agents: list[str],
    merlin_verdict: Any | None,
) -> str:
    if mission.status in {"complete", "completed"}:
        return "done"
    if open_gate is not None:
        return _gate_phase(open_gate["gate_type"])
    if mission_brief is None or not hypotheses:
        return "framing"

    gate_status = {g.gate_type: g.status for g in gates}
    if gate_status.get("hypothesis_confirmation") != "completed":
        return "awaiting_hypothesis_review"
    if gate_status.get("manager_review") != "completed":
        return "research"
    if mission.synthesis_state != "complete" or merlin_verdict is None:
        return "stress_test"
    if gate_status.get("final_review") != "completed":
        return "awaiting_investment_decision"
    if _final_package_ready(deliverables):
        return "done"
    if active_agents:
        return "final_delivery"
    return "final_delivery"


def _gate_phase(gate_type: str | None) -> str:
    if gate_type == "hypothesis_confirmation":
        return "awaiting_hypothesis_review"
    if gate_type == "manager_review":
        return "awaiting_manager_review"
    if gate_type == "final_review":
        return "awaiting_investment_decision"
    if gate_type == "clarification_request":
        return "awaiting_clarification"
    if gate_type == "data_availability":
        return "awaiting_data_decision"
    return "awaiting_review"


def _workstream_contracts(
    workstreams: list[Workstream],
    milestones: list[Milestone],
    deliverables: list[Deliverable],
    findings: list[Finding],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for workstream in workstreams:
        ws_id = (workstream.id or "").upper()
        ws_milestones = [m for m in milestones if (m.workstream_id or "").upper() == ws_id]
        ws_findings = [f for f in findings if (f.workstream_id or "").upper() == ws_id]
        ws_deliverables = [d for d in deliverables if (d.workstream_id or "").upper() == ws_id]
        ready_deliverables = [d for d in ws_deliverables if (d.status or "").lower() == "ready"]
        terminal_milestones = [
            m for m in ws_milestones
            if (m.status or "").lower() in {"delivered", "skipped", "blocked"}
        ]
        expected_done = bool(ws_milestones) and len(terminal_milestones) == len(ws_milestones)
        status = workstream.status
        if ws_id in _RESEARCH_WORKSTREAMS and expected_done and ready_deliverables:
            status = "reviewable"
        elif ws_id in _STRESS_WORKSTREAMS and ready_deliverables:
            status = "reviewable"
        rows.append(
            {
                "id": workstream.id,
                "label": workstream.label,
                "assigned_agent": workstream.assigned_agent,
                "status": status,
                "findings_total": len(ws_findings),
                "milestones_total": len(ws_milestones),
                "milestones_terminal": len(terminal_milestones),
                "deliverables_ready": len(ready_deliverables),
                "missing_deliverables": _missing_workstream_deliverables(ws_id, ws_milestones, ws_deliverables),
            }
        )
    return rows


def _missing_workstream_deliverables(
    ws_id: str,
    milestones: list[Milestone],
    deliverables: list[Deliverable],
) -> list[str]:
    missing: list[str] = []
    if ws_id in _RESEARCH_WORKSTREAMS | _STRESS_WORKSTREAMS:
        has_ready_report = any(
            (d.status or "").lower() == "ready"
            and (d.deliverable_type or "").lower() == "workstream_report"
            for d in deliverables
        )
        if not has_ready_report:
            missing.append("workstream_report")
    ready_milestone_ids = {
        d.milestone_id
        for d in deliverables
        if (d.status or "").lower() == "ready"
        and (d.deliverable_type or "").lower() == "milestone_report"
        and d.milestone_id
    }
    for milestone in milestones:
        if (milestone.status or "").lower() == "delivered" and milestone.id not in ready_milestone_ids:
            missing.append(milestone.id)
    return missing


def _deliverable_contract(deliverables: list[Deliverable]) -> dict[str, Any]:
    ready = [d for d in deliverables if (d.status or "").lower() == "ready"]
    final_ready = [
        d for d in ready
        if _is_final_package_deliverable(d)
    ]
    return {
        "ready_total": len(ready),
        "final_package_ready": _final_package_ready(deliverables),
        "final_ready_types": sorted({(d.deliverable_type or "").lower() for d in final_ready}),
        "ready_ids": [d.id for d in ready],
    }


def _final_package_ready(deliverables: list[Deliverable]) -> bool:
    ready = [
        d for d in deliverables
        if (d.status or "").lower() == "ready" and bool(d.file_path)
    ]
    has_exec_summary = any(
        (d.deliverable_type or "").lower() in {"exec_summary", "executive_summary"}
        for d in ready
    )
    has_data_book = any((d.deliverable_type or "").lower() == "data_book" for d in ready)
    has_stress_report = any(_is_stress_report_deliverable(d) for d in ready)
    return has_exec_summary and has_data_book and has_stress_report


def _is_final_package_deliverable(deliverable: Deliverable) -> bool:
    deliverable_type = (deliverable.deliverable_type or "").lower()
    return deliverable_type in _FINAL_DELIVERABLE_TYPES or _is_stress_report_deliverable(deliverable)


def _is_stress_report_deliverable(deliverable: Deliverable) -> bool:
    deliverable_type = (deliverable.deliverable_type or "").lower()
    workstream_id = (deliverable.workstream_id or "").upper()
    return deliverable_type == "stress_testing_report" or (
        deliverable_type == "workstream_report" and workstream_id == "W4"
    )


def _waiting_reason(
    *,
    mission: Mission,
    open_gate: dict[str, Any] | None,
    active_agents: list[str],
    blockers: list[dict[str, Any]],
    current_phase: str,
) -> str:
    if mission.status in {"complete", "completed"} or current_phase == "done":
        return "complete"
    if open_gate is not None:
        return f"awaiting_{open_gate['gate_type']}"
    if active_agents:
        return "agents_running"
    failed = next((b for b in blockers if b.get("type") == "gate_failed"), None)
    if failed:
        return "gate_failed"
    missing = next((b for b in blockers if b.get("type") == "gate_material_missing"), None)
    if missing:
        return "waiting_for_material"
    return "workflow_continuing"


def _next_action(
    *,
    mission: Mission,
    open_gate: dict[str, Any] | None,
    active_agents: list[str],
    blockers: list[dict[str, Any]],
    current_phase: str,
) -> str:
    if mission.status in {"complete", "completed"} or current_phase == "done":
        return "review_final_deliverables"
    if open_gate is not None:
        return "consultant_review"
    if active_agents:
        return "agent_work"
    if any(b.get("type") == "gate_failed" for b in blockers):
        return "rerun_or_revise"
    if current_phase == "framing":
        return "provide_brief"
    return "continue_runtime"
