from __future__ import annotations

from collections import defaultdict
from typing import Any

from marvin.mission.schema import Confidence, Deliverable, Finding, Hypothesis, Milestone, Workstream
from marvin.mission.store import MissionStore
from marvin.tools.mission_tools import compute_hypothesis_status


def _finding_summary(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "hypothesis_id": finding.hypothesis_id,
        "workstream_id": finding.workstream_id,
        "milestone_id": finding.milestone_id,
        "agent_id": finding.agent_id,
        "claim_text": finding.claim_text,
        "confidence": finding.confidence,
        "source_id": finding.source_id,
        "source_type": finding.source_type,
        "impact": finding.impact,
        "created_at": finding.created_at,
    }


def _deliverable_ready(deliverable: Deliverable) -> bool:
    return deliverable.status == "ready" and bool(deliverable.file_path)


def _counts_by_confidence(findings: list[Finding]) -> dict[Confidence, int]:
    counts: dict[Confidence, int] = {
        "KNOWN": 0,
        "REASONED": 0,
        "LOW_CONFIDENCE": 0,
    }
    for finding in findings:
        counts[finding.confidence] += 1
    return counts


def _workstream_coverage(
    workstream: Workstream,
    milestones: list[Milestone],
    findings: list[Finding],
    deliverables: list[Deliverable],
) -> dict[str, Any]:
    milestone_status_counts: dict[str, int] = defaultdict(int)
    for milestone in milestones:
        milestone_status_counts[milestone.status] += 1
    ready_deliverables = [d for d in deliverables if _deliverable_ready(d)]
    return {
        "id": workstream.id,
        "label": workstream.label,
        "assigned_agent": workstream.assigned_agent,
        "status": workstream.status,
        "milestones": [
            {
                "id": milestone.id,
                "label": milestone.label,
                "status": milestone.status,
                "result_summary": milestone.result_summary,
            }
            for milestone in milestones
        ],
        "milestone_status_counts": dict(milestone_status_counts),
        "findings_total": len(findings),
        "deliverables_ready": [
            {
                "id": deliverable.id,
                "deliverable_type": deliverable.deliverable_type,
                "milestone_id": deliverable.milestone_id,
                "workstream_id": deliverable.workstream_id,
            }
            for deliverable in ready_deliverables
        ],
        "has_material": bool(findings or ready_deliverables),
    }


def build_verdict_dossier(store: MissionStore, mission_id: str) -> dict[str, Any]:
    mission = store.get_mission(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    findings = store.list_findings(mission_id)
    milestones = store.list_milestones(mission_id)
    deliverables = store.list_deliverables(mission_id)
    workstreams = store.list_workstreams(mission_id)

    by_hypothesis: dict[str | None, list[Finding]] = defaultdict(list)
    by_workstream: dict[str | None, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_hypothesis[finding.hypothesis_id].append(finding)
        by_workstream[finding.workstream_id].append(finding)

    unlinked_redteam = [
        finding for finding in by_hypothesis.get(None, []) if finding.agent_id == "adversus"
    ]
    milestone_by_workstream: dict[str, list[Milestone]] = defaultdict(list)
    for milestone in milestones:
        milestone_by_workstream[milestone.workstream_id].append(milestone)
    deliverable_by_workstream: dict[str | None, list[Deliverable]] = defaultdict(list)
    for deliverable in deliverables:
        deliverable_by_workstream[deliverable.workstream_id].append(deliverable)

    hypothesis_sections: list[dict[str, Any]] = []
    gaps: list[str] = []
    contradicting_hypotheses = 0
    unsupported_hypotheses = 0
    low_confidence_hypotheses = 0

    for index, hypothesis in enumerate(hypotheses, start=1):
        scoped = list(by_hypothesis.get(hypothesis.id, []))
        scoped.extend(unlinked_redteam)
        supporting = [finding for finding in scoped if finding.agent_id != "adversus"]
        contradicting = [finding for finding in scoped if finding.agent_id == "adversus"]
        counts = _counts_by_confidence(scoped)
        computed = compute_hypothesis_status(scoped)
        if computed["status"] == "CHALLENGED":
            contradicting_hypotheses += 1
            gaps.append(
                f"{hypothesis.label or f'H{index}'} has unresolved red-team contradiction(s)."
            )
        elif computed["status"] == "WEAKENED":
            low_confidence_hypotheses += 1
            gaps.append(
                f"{hypothesis.label or f'H{index}'} is mostly supported by fragile evidence."
            )
        elif computed["status"] == "NOT_STARTED":
            unsupported_hypotheses += 1
            gaps.append(
                f"{hypothesis.label or f'H{index}'} has no linked evidence yet."
            )
        if counts["KNOWN"] == 0 and supporting:
            gaps.append(
                f"{hypothesis.label or f'H{index}'} lacks primary-sourced support."
            )
        hypothesis_sections.append(
            {
                "id": hypothesis.id,
                "label": hypothesis.label or f"H{index}",
                "text": hypothesis.text,
                "status": computed["status"],
                "status_rationale": computed["rationale"],
                "supporting_findings": [_finding_summary(finding) for finding in supporting[-8:]],
                "contradicting_findings": [_finding_summary(finding) for finding in contradicting[-8:]],
                "primary_sourced_count": counts["KNOWN"],
                "reasoned_count": counts["REASONED"],
                "low_confidence_count": counts["LOW_CONFIDENCE"],
                "total_findings": computed["total"],
            }
        )

    coverage = [
        _workstream_coverage(
            workstream,
            milestone_by_workstream.get(workstream.id, []),
            by_workstream.get(workstream.id, []),
            deliverable_by_workstream.get(workstream.id, []),
        )
        for workstream in workstreams
    ]

    if any(not section["has_material"] for section in coverage if section["id"] in {"W1", "W2", "W4"}):
        gaps.append("One or more visible workstreams still have no user-facing material.")

    ship_risk = "low"
    if contradicting_hypotheses >= 2 or unsupported_hypotheses > 0:
        ship_risk = "high"
    elif low_confidence_hypotheses > 0:
        ship_risk = "medium"

    return {
        "mission": {
            "id": mission.id,
            "client": mission.client,
            "target": mission.target,
            "ic_question": mission.ic_question,
        },
        "hypotheses": hypothesis_sections,
        "coverage": coverage,
        "gaps": gaps,
        "ship_risk": ship_risk,
        "redteam_findings": [
            _finding_summary(finding)
            for finding in findings
            if finding.agent_id == "adversus"
        ][-12:],
    }
