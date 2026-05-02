from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from marvin.mission.schema import (
    Finding,
    Gate,
    Hypothesis,
    MerlinVerdict,
    Milestone,
    MissionBrief,
    Workstream,
)
from marvin.mission.store import MissionStore
from marvin.tools.mission_tools import consultant_verdict_action, consultant_verdict_label


GATE_COPY = {
    "hypothesis_confirmation": {
        "title": "Confirm initial hypotheses",
        "stage": "Framing",
        "summary": (
            "MARVIN has framed the deal into testable hypotheses. "
            "Approve to start parallel research workstreams. "
            "Reject to revise the framing before any research runs."
        ),
        "unlocks_on_approve": "Dora and Calculus begin parallel research.",
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
            "Reject to run targeted follow-up diligence before finalization."
        ),
        "unlocks_on_approve": "Papyrus produces the final memo and deliverable set.",
        "unlocks_on_reject": "The team revisits the unresolved evidence gaps.",
    },
}


@dataclass(frozen=True)
class GateMaterial:
    lifecycle_status: str
    is_open: bool
    missing_material: tuple[str, ...]
    review_payload: dict[str, Any]


def human_gate_copy(gate_type: str) -> dict[str, str]:
    return GATE_COPY.get(
        gate_type,
        {
            "title": gate_type.replace("_", " ").capitalize() if gate_type else "Validation required",
            "stage": "Mission checkpoint",
            "summary": "A gate is waiting for human review before the mission can proceed.",
            "unlocks_on_approve": "Mission continues to the next phase.",
            "unlocks_on_reject": "Mission pauses; team revisits the prior phase.",
        },
    )


def evaluate_gate_material(
    store: MissionStore,
    mission_id: str,
    gate: Gate,
    *,
    hypotheses: list[Hypothesis] | None = None,
    findings: list[Finding] | None = None,
    mission_brief: MissionBrief | None = None,
    workstreams: list[Workstream] | None = None,
    milestones: list[Milestone] | None = None,
    merlin_verdict: MerlinVerdict | None = None,
    arbiter_flags: list[str] | None = None,
) -> GateMaterial:
    """Build the review material required to open a human gate."""
    hypotheses = store.list_hypotheses(mission_id) if hypotheses is None else hypotheses
    findings = store.list_findings(mission_id) if findings is None else findings
    mission_brief = store.get_mission_brief(mission_id) if mission_brief is None else mission_brief
    workstreams = store.list_workstreams(mission_id) if workstreams is None else workstreams
    milestones = store.list_milestones(mission_id) if milestones is None else milestones
    if merlin_verdict is None and gate.gate_type == "final_review":
        merlin_verdict = store.get_latest_merlin_verdict(mission_id)

    research_findings = [
        _finding_payload(finding)
        for finding in findings
        if (finding.agent_id or "").lower() != "adversus"
    ]
    redteam_findings = [
        _finding_payload(finding)
        for finding in findings
        if (finding.agent_id or "").lower() == "adversus"
    ]

    missing_material: list[str] = []
    payload: dict[str, Any] = {
        "gate_id": gate.id,
        "gate_type": gate.gate_type,
        "format": gate.format,
        **human_gate_copy(gate.gate_type),
        "material_status": "pending",
        "arbiter_flags": arbiter_flags or [],
    }

    if gate.gate_type == "hypothesis_confirmation":
        framing = _framing_payload(mission_brief)
        if not framing:
            missing_material.append("framing_summary")
        if not hypotheses:
            missing_material.append("hypotheses")
        payload.update(
            {
                "framing": framing,
                "hypotheses": [_hypothesis_payload(h) for h in hypotheses],
            }
        )

    elif gate.gate_type == "manager_review":
        coverage = _coverage_payload(workstreams, milestones, findings)
        # Gate opens only when ALL W1+W2 milestones have reached a terminal
        # state (delivered, skipped, or blocked). W3 (red-team) and W4
        # (synthesis/adversus) come AFTER manager_review and must NOT be
        # required here — they would deadlock the gate if checked prematurely.
        # Edge case: if there are somehow zero W1/W2 milestones (mission seeded
        # without standard research workstreams), fall back to the old "any
        # milestone resolved" rule so the gate can still fire.
        _RESEARCH_WORKSTREAMS = {"W1", "W2"}
        _INTERNAL_OPTIONAL_MILESTONES = {"W2.2", "W2.3"}
        _TERMINAL = {"delivered", "skipped", "blocked"}
        research_milestones = [
            m for m in (milestones or [])
            if (m.workstream_id or "").upper() in _RESEARCH_WORKSTREAMS
            and (m.id or "").upper() not in _INTERNAL_OPTIONAL_MILESTONES
        ]
        if research_milestones:
            research_complete = all(
                (m.status or "").lower() in _TERMINAL
                for m in research_milestones
            )
        else:
            # Fallback: no W1/W2 milestones found — open if any milestone resolved
            research_complete = any(
                (m.status or "").lower() in _TERMINAL
                for m in (milestones or [])
            )
        if not research_complete:
            missing_material.append("research_in_progress")

        # Gate requires ALL expected deliverables for each non-skipped research
        # workstream (W1 and W2) to be status='ready'. "Expected" means:
        #   1. The workstream-level report (deliverable_type='workstream_report')
        #   2. A milestone report for every DELIVERED milestone in that workstream
        # This prevents the gate from opening while Papyrus is still drafting
        # any per-milestone deliverable.
        # Edge case: if ALL milestones for a workstream are `skipped`
        # (e.g. Calculus skipped via data_availability gate), that workstream's
        # deliverable requirement is considered satisfied — there is nothing to
        # compile. A blocked visible milestone is different: it means work was
        # attempted but failed, so the manager gate must wait for an explicit
        # report/caveat rather than silently treating the branch as complete.
        deliverables = store.list_deliverables(mission_id)
        ready_deliverable_ids = {
            (d.workstream_id or "").upper()
            for d in deliverables
            if (d.status or "").lower() == "ready"
        }
        # Index ready milestone-report deliverables by milestone_id for fast lookup.
        ready_milestone_report_ids: set[str] = {
            d.milestone_id
            for d in deliverables
            if (d.status or "").lower() == "ready"
            and (d.deliverable_type or "").lower() == "milestone_report"
            and d.milestone_id
        }
        for ws_id in _RESEARCH_WORKSTREAMS:
            ws_milestones = [
                m for m in (milestones or [])
                if (m.workstream_id or "").upper() == ws_id
                and (m.id or "").upper() not in _INTERNAL_OPTIONAL_MILESTONES
            ]
            all_skipped = ws_milestones and all(
                (m.status or "").lower() == "skipped" for m in ws_milestones
            )
            if all_skipped:
                # Workstream was entirely skipped/blocked — no deliverable expected
                continue
            # Require the workstream-level report to be ready.
            has_ready_ws_report = any(
                (d.workstream_id or "").upper() == ws_id
                and (d.status or "").lower() == "ready"
                and (d.deliverable_type or "").lower() == "workstream_report"
                for d in deliverables
            )
            if not has_ready_ws_report:
                missing_material.append("deliverable_writing_in_progress")
                break
            # Require a milestone report for every DELIVERED milestone.
            delivered_milestones = [
                m for m in ws_milestones
                if (m.status or "").lower() == "delivered"
            ]
            missing_milestone_report = any(
                m.id not in ready_milestone_report_ids
                for m in delivered_milestones
            )
            if missing_milestone_report:
                missing_material.append("deliverable_writing_in_progress")
                break
        payload.update(
            {
                "research_findings": research_findings[-12:],
                "findings_total": len(research_findings),
                "coverage": coverage,
                "findings_warning": "Research agents ran but produced no persisted findings (possible API failure). Review coverage before approving." if research_complete and not research_findings else None,
            }
        )

    elif gate.gate_type == "data_availability":
        # Bug 3 (chantier 2.6): pre-flight data check; the gate is open as
        # soon as it is created, no upstream material required. Surfaces the
        # 3 user options inline so the frontend can render decision buttons.
        if not gate.questions:
            missing_material.append("data_decision_question")
        payload.update(
            {
                "questions": list(gate.questions or []),
                "title": "Data availability check",
                "stage": "Pre-flight",
                "summary": (
                    "Calculus cannot run financial analysis on this target. "
                    "Choose how to proceed."
                ),
                "options": [
                    {
                        "value": "skip_calculus",
                        "label": "Skip W2 — qualitative analysis only",
                        "consequence": (
                            "Calculus is not run. W2 findings panel stays empty. "
                            "Diligence focuses on market and competitive analysis."
                        ),
                    },
                    {
                        "value": "proceed_low_confidence",
                        "label": "Proceed — accept LOW_CONFIDENCE only",
                        "consequence": (
                            "Calculus runs but cannot produce KNOWN findings. "
                            "All financial claims will be LOW_CONFIDENCE."
                        ),
                    },
                    {
                        "value": "request_data_room",
                        "label": "Pause — I'll provide a data room",
                        "consequence": (
                            "Mission pauses. Add data room files via UI, then resume."
                        ),
                    },
                ],
            }
        )

    elif gate.gate_type == "clarification_request":
        if not gate.questions:
            missing_material.append("clarification_questions")
        payload.update(
            {
                "questions": list(gate.questions or []),
                "round": _clarification_rounds(store, mission_id),
                "max_rounds": 3,
                "title": "Clarification needed",
                "stage": "Framing",
                "summary": (
                    "MARVIN needs more context before framing the mission. "
                    "Answer the questions below to continue."
                ),
            }
        )

    elif gate.gate_type == "final_review":
        # G3 must wait for G2 (manager_review) to be completed. Without this
        # check, G3 evaluates is_open=True the moment Merlin saves an interim
        # verdict during synthesis_retry — even though the mission is still
        # looping back through Adversus and the final synthesis hasn't run.
        # Symptom: "IC sign-off" banner appears at ~42% while Adversus is
        # still RUNNING.
        manager_gate = next(
            (g for g in store.list_gates(mission_id) if g.gate_type == "manager_review"),
            None,
        )
        if manager_gate is None or manager_gate.status != "completed":
            missing_material.append("prior_gate_pending")
        if merlin_verdict is None:
            missing_material.append("merlin_verdict")
        if not redteam_findings:
            missing_material.append("redteam_evidence")
        open_risks = [
            f["claim_text"]
            for f in redteam_findings
            if f.get("confidence") == "LOW_CONFIDENCE"
        ]
        payload.update(
            {
                "merlin_verdict": _verdict_payload(merlin_verdict),
                "redteam_findings": redteam_findings[-8:],
                "research_findings": research_findings[-6:],
                "weakest_links": redteam_findings[-5:],
                "open_risks": open_risks,
                "arbiter_flags": arbiter_flags or [],
                "findings_total": len(findings),
            }
        )

    else:
        missing_material.append("gate_material")

    if gate.status != "pending":
        lifecycle_status = gate.status
        is_open = False
    else:
        is_open = not missing_material
        lifecycle_status = "open" if is_open else "scheduled"

    payload["material_status"] = "ready" if is_open else lifecycle_status
    payload["missing_material"] = list(missing_material)
    return GateMaterial(
        lifecycle_status=lifecycle_status,
        is_open=is_open,
        missing_material=tuple(missing_material),
        review_payload=payload,
    )


def _clarification_rounds(store: MissionStore, mission_id: str) -> int:
    try:
        return store.get_clarification_state(mission_id)["rounds"]
    except KeyError:
        return 0


def _hypothesis_payload(hypothesis: Hypothesis) -> dict[str, Any]:
    return {
        "id": hypothesis.id,
        "text": hypothesis.text,
        "status": hypothesis.status,
    }


def _finding_payload(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "workstream_id": finding.workstream_id,
        "hypothesis_id": finding.hypothesis_id,
        "claim_text": finding.claim_text,
        "confidence": finding.confidence,
        "agent_id": finding.agent_id,
    }


def _framing_payload(brief: MissionBrief | None) -> dict[str, Any] | None:
    if brief is None or not brief.ic_question.strip() or not brief.brief_summary.strip():
        return None
    return {
        "ic_question": brief.ic_question,
        "mission_angle": brief.mission_angle,
        "brief_summary": brief.brief_summary,
        "workstream_plan": _parse_workstream_plan(brief.workstream_plan_json),
    }


def _parse_workstream_plan(value: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _coverage_payload(
    workstreams: list[Workstream],
    milestones: list[Milestone],
    findings: list[Finding],
) -> dict[str, Any]:
    research_findings = [
        finding for finding in findings
        if (finding.agent_id or "").lower() != "adversus"
    ]
    workstream_rows: list[dict[str, Any]] = []
    for workstream in workstreams:
        ws_milestones = [m for m in milestones if m.workstream_id == workstream.id]
        ws_findings = [f for f in research_findings if f.workstream_id == workstream.id]
        delivered = [m for m in ws_milestones if m.status == "delivered"]
        blocked = [m for m in ws_milestones if m.status == "blocked"]
        workstream_rows.append(
            {
                "id": workstream.id,
                "label": workstream.label,
                "assigned_agent": workstream.assigned_agent,
                "status": workstream.status,
                "milestones_delivered": len(delivered),
                "milestones_blocked": len(blocked),
                "milestones_total": len(ws_milestones),
                "findings_total": len(ws_findings),
                "has_material": bool(ws_findings or delivered or workstream.status == "delivered"),
            }
        )

    return {
        "findings_total": len(research_findings),
        "workstreams_total": len(workstreams),
        "workstreams_with_material": sum(1 for row in workstream_rows if row["has_material"]),
        "milestones_delivered": sum(1 for m in milestones if m.status == "delivered"),
        "milestones_blocked": sum(1 for m in milestones if m.status == "blocked"),
        "milestones_total": len(milestones),
        "workstreams": workstream_rows,
    }


def _verdict_payload(verdict: MerlinVerdict | None) -> dict[str, Any] | None:
    if verdict is None:
        return None
    return {
        "id": verdict.id,
        "verdict": verdict.verdict,
        "label": consultant_verdict_label(verdict.verdict),
        "recommended_action": consultant_verdict_action(verdict.verdict),
        "notes": verdict.notes,
        "created_at": verdict.created_at,
    }
