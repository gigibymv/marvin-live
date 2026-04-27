from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from marvin.artifacts import artifact_file_readiness_errors
from marvin.events import emit_deliverable_persisted
from marvin.mission.schema import Deliverable
from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, ensure_output_dir, get_store, require_mission_id, utc_now_iso

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STORE_FACTORY = MissionStore


class BriefPrerequisiteNotMet(ValueError):
    """Raised when framing material is insufficient for an engagement brief."""


def _assert_artifact_can_be_ready(file_path: Path, deliverable_type: str) -> None:
    """Fail closed before any artifact is announced as ready."""
    errors = artifact_file_readiness_errors(file_path, deliverable_type)
    if errors:
        raise ValueError(f"{deliverable_type} is not ready: {', '.join(errors)}")


def _save_deliverable(
    store: MissionStore,
    mission_id: str,
    deliverable_id: str,
    deliverable_type: str,
    file_path: Path,
) -> None:
    try:
        _assert_artifact_can_be_ready(file_path, deliverable_type)
    except ValueError:
        try:
            file_path.unlink()
        except OSError:
            pass
        raise
    resolved = str(file_path.resolve())
    store.save_deliverable(
        Deliverable(
            id=deliverable_id,
            mission_id=mission_id,
            deliverable_type=deliverable_type,
            status="ready",
            file_path=resolved,
            file_size_bytes=file_path.stat().st_size,
            created_at=utc_now_iso(),
        )
    )
    emit_deliverable_persisted(
        mission_id,
        {
            "deliverable_id": deliverable_id,
            "deliverable_type": deliverable_type,
            "file_path": resolved,
        },
    )


def _generate_engagement_brief_impl(mission_id: str) -> dict[str, Any]:
    store = get_store(_STORE_FACTORY)
    mission = store.get_mission(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    mission_brief = store.get_mission_brief(mission_id)
    if not (mission.ic_question or "").strip():
        raise BriefPrerequisiteNotMet("engagement_brief requires an investment committee question")
    if not hypotheses:
        raise BriefPrerequisiteNotMet("engagement_brief requires framed hypotheses")
    if mission_brief is None:
        raise BriefPrerequisiteNotMet("engagement_brief requires persisted framing")

    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / "engagement_brief.md"
    existed = path.exists()
    lines = [
        f"# Engagement Brief: {mission.target}",
        "",
        f"Client: {mission.client}",
        f"Target: {mission.target}",
        f"Mission Type: {mission.mission_type}",
        f"IC Question: {mission.ic_question}",
        "",
        "## Mission Angle",
        mission_brief.mission_angle,
        "",
        "## Brief Summary",
        mission_brief.brief_summary,
        "",
        "## Hypotheses",
    ]
    lines.extend(
        [
            f"- Hypothesis ID: {hypothesis.id} - {hypothesis.text} (status: {hypothesis.status})"
            for hypothesis in hypotheses
        ]
    )
    lines.extend(["", "## Workstream Plan"])
    for item in json.loads(mission_brief.workstream_plan_json):
        lines.append(f"- {item['id']} - {item['label']}: {item['focus']}")
    lines.extend(
        [
            "",
            "## Validation Focus",
            "This engagement brief is ready because it ties the mission angle, IC question, "
            "and initial hypotheses into named diligence workstreams. Gate 1 should validate "
            "whether these hypotheses are the right questions before research begins.",
        ]
    )
    next_body = "\n".join(lines) + "\n"
    status = "generated"
    if existed:
        current_body = path.read_text(encoding="utf-8")
        status = "skipped" if current_body == next_body else "updated"
    if status != "skipped":
        path.write_text(next_body, encoding="utf-8")
    deliverable_id = f"deliverable-{mission_id}-engagement-brief"
    deliverable_type = "engagement_brief"
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "status": status,
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_engagement_brief(state: InjectedStateArg = None) -> dict[str, Any]:
    """Generate engagement brief for the mission."""
    mission_id = require_mission_id(state)
    return _generate_engagement_brief_impl(mission_id)


def _generate_workstream_report_impl(workstream_id: str, mission_id: str) -> dict[str, Any]:
    store = get_store(_STORE_FACTORY)
    findings = [finding for finding in store.list_findings(mission_id) if finding.workstream_id == workstream_id]
    if not findings:
        return {
            "mission_id": mission_id,
            "workstream_id": workstream_id,
            "status": "blocked",
            "reason": "workstream_report requires at least one finding",
        }

    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / f"{workstream_id}_report.md"
    lines = [f"# {workstream_id} Report", ""]
    lines.extend(
        [
            "## Scope",
            f"This workstream report summarizes persisted findings for {workstream_id}. "
            "Each claim below includes the finding identifier that backs the report.",
            "",
            "## Evidence-backed Findings",
        ]
    )
    for finding in findings:
        hypothesis_ref = f" Hypothesis ID: {finding.hypothesis_id}." if finding.hypothesis_id else ""
        source_ref = f" Source ID: {finding.source_id}." if finding.source_id else ""
        lines.append(
            f"- Finding ID: {finding.id}. Confidence: {finding.confidence}. "
            f"Claim: {finding.claim_text}.{hypothesis_ref}{source_ref}"
        )
    lines.extend(
        [
            "",
            "## Manager Review Note",
            "Use this report to confirm whether the workstream has enough evidence for the "
            "manager review gate, and identify any claims that need additional sourcing.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    deliverable_id = f"deliverable-{mission_id}-{workstream_id.lower()}-report"
    deliverable_type = "workstream_report"
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "workstream_id": workstream_id,
        "file_path": str(path.resolve()),
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_workstream_report(
    workstream_id: str,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Generate workstream report for a specific workstream."""
    mission_id = require_mission_id(state)
    return _generate_workstream_report_impl(workstream_id, mission_id)


def _generate_report_pdf_impl(mission_id: str) -> dict[str, Any]:
    store = get_store(_STORE_FACTORY)
    verdict = store.get_latest_merlin_verdict(mission_id)
    g3_completed = any(gate.scheduled_day == 10 and gate.status == "completed" for gate in store.list_gates(mission_id))
    if not ((verdict and verdict.verdict == "SHIP") or g3_completed):
        raise ValueError("generate_report_pdf requires SHIP verdict or completed G3 gate")
    return {
        "mission_id": mission_id,
        "deliverable_type": "report_pdf",
        "status": "blocked",
        "reason": "real PDF generation is not implemented; placeholder PDFs are not marked ready",
    }


def generate_report_pdf(state: InjectedStateArg = None) -> dict[str, Any]:
    """Generate PDF report for the mission."""
    mission_id = require_mission_id(state)
    return _generate_report_pdf_impl(mission_id)


def _generate_exec_summary_impl(mission_id: str) -> dict[str, Any]:
    store = get_store(_STORE_FACTORY)
    mission = store.get_mission(mission_id)
    findings = store.list_findings(mission_id)
    if not findings:
        return {
            "mission_id": mission_id,
            "deliverable_type": "exec_summary",
            "status": "blocked",
            "reason": "exec_summary requires at least one finding",
        }

    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / "exec_summary.md"
    lines = [
        f"# Executive Summary: {mission.target}",
        "",
        f"Mission: {mission.client} / {mission.target}",
        "",
        "## Decision Context",
        "This summary is generated only from persisted mission findings. Each bullet links "
        "back to a finding identifier so reviewers can trace the claim to the mission record.",
        "",
        "## Key Findings",
    ]
    lines.extend(
        [
            f"- Finding ID: {finding.id}. Confidence: {finding.confidence}. Claim: {finding.claim_text}"
            for finding in findings[:10]
        ]
    )
    verdict = store.get_latest_merlin_verdict(mission_id)
    if verdict:
        verdict_notes = (verdict.notes or "").strip()
        verdict_line = f"Verdict ID: {verdict.id}. Outcome: {verdict.verdict}."
        if verdict_notes:
            verdict_line = f"{verdict_line} {verdict_notes}"
        lines.extend(["", "## Merlin Verdict", verdict_line])
    lines.extend(
        [
            "",
            "## Review Use",
            "This document should be used as a concise orientation layer, not as a substitute "
            "for the underlying findings, sources, and gate review payloads.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    deliverable_id = f"deliverable-{mission_id}-exec-summary"
    deliverable_type = "exec_summary"
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_exec_summary(state: InjectedStateArg = None) -> dict[str, Any]:
    """Generate executive summary for the mission."""
    mission_id = require_mission_id(state)
    return _generate_exec_summary_impl(mission_id)


def _generate_data_book_impl(mission_id: str) -> dict[str, Any]:
    store = get_store(_STORE_FACTORY)
    findings = store.list_findings(mission_id)
    if not findings:
        return {
            "mission_id": mission_id,
            "deliverable_type": "data_book",
            "status": "blocked",
            "reason": "data_book requires at least one finding",
        }

    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / "data_book.md"
    lines = [
        "# Data Book",
        "",
        "## Purpose",
        "The data book is an indexed evidence register. Every row below links to a persisted "
        "finding identifier and preserves confidence, hypothesis, source, and agent metadata.",
        "",
        "## Findings",
    ]
    for finding in findings:
        lines.append(
            f"- Finding ID: {finding.id}. Workstream: {finding.workstream_id or 'unassigned'}. "
            f"Hypothesis ID: {finding.hypothesis_id or 'unassigned'}. "
            f"Source ID: {finding.source_id or 'unassigned'}. "
            f"Agent: {finding.agent_id or 'unknown'}. Confidence: {finding.confidence}. "
            f"Claim: {finding.claim_text}"
        )
    lines.extend(
        [
            "",
            "## Traceability",
            "If a row lacks source or hypothesis metadata, reviewers should treat that as an "
            "explicit coverage gap rather than hidden evidence.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    deliverable_id = f"deliverable-{mission_id}-data-book"
    deliverable_type = "data_book"
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_data_book(state: InjectedStateArg = None) -> dict[str, Any]:
    """Generate data book for the mission."""
    mission_id = require_mission_id(state)
    return _generate_data_book_impl(mission_id)
