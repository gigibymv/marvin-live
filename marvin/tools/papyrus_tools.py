from __future__ import annotations

from pathlib import Path
from typing import Any

from marvin.events import emit_deliverable_persisted
from marvin.mission.schema import Deliverable
from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, ensure_output_dir, get_store, require_mission_id, utc_now_iso

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STORE_FACTORY = MissionStore


def _save_deliverable(
    store: MissionStore,
    mission_id: str,
    deliverable_id: str,
    deliverable_type: str,
    file_path: Path,
) -> None:
    resolved = str(file_path.resolve())
    store.save_deliverable(
        Deliverable(
            id=deliverable_id,
            mission_id=mission_id,
            deliverable_type=deliverable_type,
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
    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / "engagement_brief.md"
    existed = path.exists()
    if not existed:
        lines = [
            f"# Engagement Brief: {mission.target}",
            "",
            f"Client: {mission.client}",
            f"Target: {mission.target}",
            f"Mission Type: {mission.mission_type}",
            f"IC Question: {mission.ic_question or 'N/A'}",
            "",
            "## Hypotheses",
        ]
        if hypotheses:
            lines.extend([f"- {hypothesis.text}" for hypothesis in hypotheses])
        else:
            lines.append("- No hypotheses yet")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    deliverable_id = f"deliverable-{mission_id}-engagement-brief"
    deliverable_type = "engagement_brief"
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "status": "skipped" if existed else "generated",
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
    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / f"{workstream_id}_report.md"
    lines = [f"# {workstream_id} Report", ""]
    if findings:
        for finding in findings:
            lines.append(f"- [{finding.confidence}] {finding.claim_text}")
    else:
        lines.append("- No findings yet")
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
    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / "cdd_report_v1.pdf"
    path.write_bytes(b"%PDF-1.4\n% MARVIN generated placeholder report\n")
    deliverable_id = f"deliverable-{mission_id}-report-pdf"
    deliverable_type = "report_pdf"
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_report_pdf(state: InjectedStateArg = None) -> dict[str, Any]:
    """Generate PDF report for the mission."""
    mission_id = require_mission_id(state)
    return _generate_report_pdf_impl(mission_id)


def _generate_exec_summary_impl(mission_id: str) -> dict[str, Any]:
    store = get_store(_STORE_FACTORY)
    mission = store.get_mission(mission_id)
    findings = store.list_findings(mission_id)
    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / "exec_summary.md"
    lines = [
        f"# Executive Summary: {mission.target}",
        "",
        f"Mission: {mission.client} / {mission.target}",
        "",
        "## Key Findings",
    ]
    lines.extend([f"- {finding.claim_text}" for finding in findings[:10]] or ["- No findings yet"])
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
    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / "data_book.md"
    lines = ["# Data Book", "", "## Findings"]
    for finding in findings:
        lines.append(f"- {finding.id}: {finding.claim_text} [{finding.confidence}]")
    if not findings:
        lines.append("- No findings yet")
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
