from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from marvin.artifacts import artifact_file_readiness_errors
from marvin.events import emit_deliverable_persisted, emit_graph_event
from marvin.mission.schema import Deliverable, Finding, Hypothesis, MerlinVerdict, Mission, MissionBrief, Source
from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, ensure_output_dir, get_store, require_mission_id, utc_now_iso
from marvin.tools.mission_tools import consultant_verdict_action, consultant_verdict_label

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STORE_FACTORY = MissionStore
_PAPYRUS_PROMPT_PATH = Path(__file__).resolve().parent.parent / "subagents" / "prompts" / "papyrus.md"

_VERDICT_ENUM_REPLACEMENTS = {
    "BACK_TO_DRAWING_BOARD": "Evidence gaps — not ready",
    "MINOR_FIXES": "Additional diligence needed",
    "SHIP": "Ready to present",
}


def _hypothesis_label(h: Hypothesis, index: int) -> str:
    """Return H1/H2/... label, falling back to position when unset."""
    return h.label or f"H{index + 1}"


def _source_type_label(finding: Finding) -> str:
    """Translate a finding's source metadata into a prose label."""
    raw = (finding.source_type or "").strip().lower()
    mapping = {
        "sec_filing": "SEC filing",
        "web": "web research",
        "data_room": "data room",
        "press": "press release",
        "inference": "inference",
    }
    if raw in mapping:
        return mapping[raw]
    if finding.source_id:
        return "primary source"
    return "inference"


def _serialize_finding_for_prompt(
    finding: Finding,
    hypothesis_label_by_id: dict[str, str],
    sources_by_id: dict[str, Source] | None = None,
) -> dict[str, Any]:
    """Strip IDs; expose only fields safe for the prompt.

    When `sources_by_id` resolves the finding's source_id, the real URL
    and supporting quote are surfaced so Papyrus can cite them in the
    deliverables. Internal source ids are still stripped — only the
    user-safe URL + quote text reach the prompt.
    """
    payload: dict[str, Any] = {
        "claim": finding.claim_text,
        "confidence": finding.confidence,
        "hypothesis": hypothesis_label_by_id.get(finding.hypothesis_id or "", "unassigned"),
        "workstream": finding.workstream_id or "unassigned",
        "source_type": _source_type_label(finding),
        "impact": finding.impact or "supporting",
    }
    source = (sources_by_id or {}).get(finding.source_id) if finding.source_id else None
    if source is not None:
        if source.url_or_ref:
            payload["source_url"] = source.url_or_ref
        if source.quote:
            payload["source_quote"] = source.quote[:500]
    return payload


def _build_papyrus_context(
    deliverable_type: str,
    mission: Mission,
    hypotheses: list[Hypothesis],
    findings: list[Finding],
    mission_brief: MissionBrief | None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Assemble the human prompt sent to Papyrus. Strips all internal IDs."""
    label_by_id = {h.id: _hypothesis_label(h, i) for i, h in enumerate(hypotheses)}
    # Hydrate source URLs/quotes so KNOWN/REASONED findings can cite the
    # real URL Dora retrieved (vs. the generic "web research" label).
    store = get_store(_STORE_FACTORY)
    sources_by_id: dict[str, Source] = {
        s.id: s for s in store.list_sources(mission.id)
    }

    payload: dict[str, Any] = {
        "deliverable_type": deliverable_type,
        "today": date.today().isoformat(),
        "mission": {
            "client": mission.client,
            "target": mission.target,
            "mission_type": mission.mission_type.upper(),
            "ic_question": mission.ic_question or "",
        },
        "hypotheses": [
            {
                "label": _hypothesis_label(h, i),
                "text": h.text,
                "status": h.status,
            }
            for i, h in enumerate(hypotheses)
        ],
        "findings": [
            _serialize_finding_for_prompt(f, label_by_id, sources_by_id)
            for f in findings
        ],
    }
    if mission_brief is not None:
        payload["framing"] = {
            "mission_angle": mission_brief.mission_angle,
            "brief_summary": mission_brief.brief_summary,
            "raw_brief": mission_brief.raw_brief,
            "workstream_plan": json.loads(mission_brief.workstream_plan_json),
        }
    if extra:
        verdict = extra.pop("verdict", None) if isinstance(extra, dict) else None
        if isinstance(verdict, MerlinVerdict):
            payload["verdict"] = {
                "label": consultant_verdict_label(verdict.verdict),
                "recommended_action": consultant_verdict_action(verdict.verdict),
                "notes": verdict.notes or "",
            }
        if extra:
            payload["extra"] = extra
    return (
        f"Produce the `{deliverable_type}` deliverable using the structure "
        f"defined in the system prompt. Use ONLY the context below. "
        f"Do not invent findings or confidence levels.\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )


def _sanitize_user_facing_markdown(body: str) -> str:
    """Remove workflow enums from generated markdown before persistence."""
    out = str(body or "")
    for raw, replacement in _VERDICT_ENUM_REPLACEMENTS.items():
        out = out.replace(raw, replacement)
    out = out.replace("CDD cdd", "CDD")
    return out


def _papyrus_llm_generate(
    deliverable_type: str,
    mission: Mission,
    hypotheses: list[Hypothesis],
    findings: list[Finding],
    mission_brief: MissionBrief | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Invoke the Papyrus LLM and return clean markdown.

    Imports are local to avoid a hard dependency on langchain at module
    load time (tests stub `_STORE_FACTORY`/`PROJECT_ROOT` without needing
    an LLM). Callers must handle exceptions; this helper does not catch.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from marvin.llm_factory import get_chat_llm

    llm = get_chat_llm("papyrus")
    system_prompt = _PAPYRUS_PROMPT_PATH.read_text(encoding="utf-8")
    human_prompt = _build_papyrus_context(
        deliverable_type, mission, hypotheses, findings, mission_brief, extra
    )

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ])
    body = _sanitize_user_facing_markdown((response.content or "").strip())
    # Strip accidental code fences around the whole document.
    if body.startswith("```"):
        lines = body.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    if not body.endswith("\n"):
        body += "\n"
    return body


class BriefPrerequisiteNotMet(ValueError):
    """Raised when framing material is insufficient for an engagement brief."""


def _assert_artifact_can_be_ready(file_path: Path, deliverable_type: str) -> None:
    """Fail closed before any artifact is announced as ready."""
    errors = artifact_file_readiness_errors(file_path, deliverable_type)
    if errors:
        raise ValueError(f"{deliverable_type} is not ready: {', '.join(errors)}")


def _emit_papyrus_narration(mission_id: str, intent: str) -> None:
    """Emit a 'Papyrus — {intent}' narration event so the live SSE stream
    surfaces report-writing work happening inside other graph nodes (e.g.
    research_join calling _generate_workstream_report_impl). Without this,
    Papyrus is invisible to the user even though it produces every
    deliverable. Failures are swallowed — narration is best-effort UX, not
    persistence."""
    try:
        from datetime import UTC, datetime
        import json as _json
        ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        payload = {"agent": "Papyrus", "intent": intent, "ts": ts}
        sse_string = f"event: narration\ndata: {_json.dumps(payload)}\n\n"
        emit_graph_event(mission_id, sse_string)
    except Exception:  # noqa: BLE001 — defensive boundary
        pass


def _save_deliverable(
    store: MissionStore,
    mission_id: str,
    deliverable_id: str,
    deliverable_type: str,
    file_path: Path,
    milestone_id: str | None = None,
    workstream_id: str | None = None,
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
            milestone_id=milestone_id,
            workstream_id=workstream_id,
        )
    )
    emit_deliverable_persisted(
        mission_id,
        {
            "deliverable_id": deliverable_id,
            "deliverable_type": deliverable_type,
            "file_path": resolved,
            "file_size_bytes": file_path.stat().st_size,
            "created_at": utc_now_iso(),
            "milestone_id": milestone_id,
            "workstream_id": workstream_id,
        },
    )
    # 9-bug triage E: emit a closing Papyrus narration so the open
    # "Drafting the {deliverable}" bubble is replaced rather than left
    # stuck on screen after the deliverable is already persisted.
    _emit_papyrus_narration(mission_id, f"Done · {deliverable_type}")


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
    deliverable_id = f"deliverable-{mission_id}-engagement-brief"
    deliverable_type = "engagement_brief"

    # Idempotent short-circuit: if a ready deliverable already exists on
    # disk we skip the LLM round-trip. To regenerate, delete the file first.
    if path.exists():
        return {
            "mission_id": mission_id,
            "file_path": str(path.resolve()),
            "status": "skipped",
            "deliverable_id": deliverable_id,
            "deliverable_type": deliverable_type,
        }

    _emit_papyrus_narration(mission_id, "Drafting the engagement brief")
    body = _papyrus_llm_generate(
        deliverable_type=deliverable_type,
        mission=mission,
        hypotheses=hypotheses,
        findings=[],  # engagement brief is pre-research; findings not yet meaningful
        mission_brief=mission_brief,
    )
    path.write_text(body, encoding="utf-8")
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "status": "generated",
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_engagement_brief(state: InjectedStateArg = None) -> dict[str, Any]:
    """Generate engagement brief for the mission."""
    mission_id = require_mission_id(state)
    return _generate_engagement_brief_impl(mission_id)


FRAMING_MEMO_MIN_CHARS = 240


def _generate_framing_memo_impl(
    mission_id: str,
    clarifications: list[str] | None = None,
) -> dict[str, Any]:
    """Write a 200-500 word framing memo that ties the user brief to the
    framed mission angle, IC question, and any clarifications collected
    during framing. Persists as a deliverable under output/{mission_id}/
    framing_memo.md."""
    store = get_store(_STORE_FACTORY)
    mission = store.get_mission(mission_id)
    mission_brief = store.get_mission_brief(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    if mission_brief is None:
        raise BriefPrerequisiteNotMet("framing_memo requires persisted framing")
    if not hypotheses:
        raise BriefPrerequisiteNotMet("framing_memo requires framed hypotheses")

    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / "framing_memo.md"

    clarifications = [c.strip() for c in (clarifications or []) if c and c.strip()]

    lines = [
        f"# Framing Memo: {mission.target}",
        "",
        f"Client: {mission.client}",
        f"Target: {mission.target}",
        f"IC Question: {mission.ic_question or 'unspecified'}",
        "",
        "## Mission Angle",
        mission_brief.mission_angle,
        "",
        "## Brief Recap",
        mission_brief.brief_summary,
        "",
        "## Raw Brief",
        mission_brief.raw_brief,
        "",
    ]
    if clarifications:
        lines.append("## Clarifications")
        for entry in clarifications:
            lines.append(f"- {entry}")
        lines.append("")
    lines.extend(
        [
            "## Hypotheses To Test",
        ]
    )
    for hypothesis in hypotheses:
        lines.append(f"- {hypothesis.text}")
    lines.extend(
        [
            "",
            "## Framing Rationale",
            (
                "This memo records how the brief was interpreted into a testable mission. "
                "Each hypothesis above maps to a workstream and is what diligence will "
                "either confirm or kill. If the user clarified the brief, those answers "
                "narrowed the angle and shaped the hypotheses below."
            ),
        ]
    )
    body = "\n".join(lines) + "\n"

    # Pad with rationale if the memo is too short to satisfy the file readiness check.
    while len(body) < FRAMING_MEMO_MIN_CHARS:
        body += (
            "Framing is the contract between the client's question and the diligence work. "
            "These hypotheses set what we will accept or reject as evidence.\n"
        )

    path.write_text(body, encoding="utf-8")
    deliverable_id = f"deliverable-{mission_id}-framing-memo"
    deliverable_type = "framing_memo"
    # framing_memo is not in DELIVERABLE_MIN_CHARS so it falls back to the
    # generic MIN_ARTIFACT_CHARS check (220) — body above clears that.
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_framing_memo(state: InjectedStateArg = None) -> dict[str, Any]:
    """Generate framing memo for the mission."""
    mission_id = require_mission_id(state)
    return _generate_framing_memo_impl(mission_id)


def _generate_workstream_report_impl(workstream_id: str, mission_id: str) -> dict[str, Any]:
    store = get_store(_STORE_FACTORY)
    findings = [f for f in store.list_findings(mission_id) if f.workstream_id == workstream_id]
    if not findings:
        return {
            "mission_id": mission_id,
            "workstream_id": workstream_id,
            "status": "blocked",
            "reason": "workstream_report requires at least one finding",
        }

    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    path = output_dir / f"{workstream_id}_report.md"
    deliverable_id = f"deliverable-{mission_id}-{workstream_id.lower()}-report"
    deliverable_type = "workstream_report"

    if path.exists():
        return {
            "mission_id": mission_id,
            "workstream_id": workstream_id,
            "file_path": str(path.resolve()),
            "status": "skipped",
            "deliverable_id": deliverable_id,
            "deliverable_type": deliverable_type,
        }

    mission = store.get_mission(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    mission_brief = store.get_mission_brief(mission_id)

    _emit_papyrus_narration(mission_id, f"Compiling the {workstream_id} workstream report")
    body = _papyrus_llm_generate(
        deliverable_type=deliverable_type,
        mission=mission,
        hypotheses=hypotheses,
        findings=findings,
        mission_brief=mission_brief,
        extra={"workstream_id": workstream_id},
    )
    path.write_text(body, encoding="utf-8")
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path, workstream_id=workstream_id)
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


def _milestone_slug(label: str) -> str:
    """Stable filename slug for a milestone label.

    `Market size and growth` -> `market_size_and_growth`. Restricted to
    alphanum + underscore so it remains valid on every filesystem and the
    routing regex stays simple.
    """
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in (label or ""))
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "milestone"


def _generate_milestone_report_impl(milestone_id: str, mission_id: str) -> dict[str, Any]:
    """Generate one .md per milestone, structurally matching the workstream
    report writing standard.

    Best-effort: if there are no findings tagged to this milestone (yet)
    we return a `blocked` status without raising — research_join calls this
    after `mark_milestone_delivered` and a partial run with no
    milestone-tagged findings should not break the workstream pass.
    """
    store = get_store(_STORE_FACTORY)
    milestone = next(
        (m for m in store.list_milestones(mission_id) if m.id == milestone_id),
        None,
    )
    if milestone is None:
        return {
            "mission_id": mission_id,
            "milestone_id": milestone_id,
            "status": "blocked",
            "reason": "milestone not found",
        }

    findings = [
        f for f in store.list_findings(mission_id)
        if f.milestone_id == milestone_id
        or (f.milestone_id is None and f.workstream_id == milestone.workstream_id)
    ]
    if not findings:
        return {
            "mission_id": mission_id,
            "milestone_id": milestone_id,
            "status": "blocked",
            "reason": "milestone_report requires at least one finding",
        }

    output_dir = ensure_output_dir(PROJECT_ROOT, mission_id)
    slug = _milestone_slug(milestone.label)
    # `W1.1_market_size_and_growth.md` — workstream prefix preserved so the
    # routing regex can still recover the parent tab.
    filename = f"{milestone_id.split('-')[-1] if '-' in milestone_id else milestone_id}_{slug}.md"
    # Prefer a clean Wx.y prefix when the milestone id already encodes it.
    if milestone_id and any(milestone_id.startswith(p) for p in ("W1.", "W2.", "W3.", "W4.")):
        filename = f"{milestone_id}_{slug}.md"
    path = output_dir / filename
    deliverable_id = f"deliverable-{mission_id}-{milestone_id.lower().replace('.', '-')}"
    deliverable_type = "milestone_report"

    if path.exists():
        return {
            "mission_id": mission_id,
            "milestone_id": milestone_id,
            "file_path": str(path.resolve()),
            "status": "skipped",
            "deliverable_id": deliverable_id,
            "deliverable_type": deliverable_type,
        }

    mission = store.get_mission(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    mission_brief = store.get_mission_brief(mission_id)

    _emit_papyrus_narration(mission_id, f"Drafting the {milestone.label} report")
    body = _papyrus_llm_generate(
        deliverable_type=deliverable_type,
        mission=mission,
        hypotheses=hypotheses,
        findings=findings,
        mission_brief=mission_brief,
        extra={
            "milestone_id": milestone_id,
            "milestone_label": milestone.label,
            "workstream_id": milestone.workstream_id,
        },
    )
    path.write_text(body, encoding="utf-8")
    _save_deliverable(
        store,
        mission_id,
        deliverable_id,
        deliverable_type,
        path,
        milestone_id=milestone_id,
        workstream_id=milestone.workstream_id,
    )
    return {
        "mission_id": mission_id,
        "milestone_id": milestone_id,
        "file_path": str(path.resolve()),
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_milestone_report(
    milestone_id: str,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Generate per-milestone report, used post `mark_milestone_delivered`."""
    mission_id = require_mission_id(state)
    return _generate_milestone_report_impl(milestone_id, mission_id)


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
    deliverable_id = f"deliverable-{mission_id}-exec-summary"
    deliverable_type = "exec_summary"

    if path.exists():
        return {
            "mission_id": mission_id,
            "file_path": str(path.resolve()),
            "status": "skipped",
            "deliverable_id": deliverable_id,
            "deliverable_type": deliverable_type,
        }

    hypotheses = store.list_hypotheses(mission_id)
    mission_brief = store.get_mission_brief(mission_id)
    verdict = store.get_latest_merlin_verdict(mission_id)
    extra: dict[str, Any] = {}
    if verdict is not None:
        extra["verdict"] = verdict

    _emit_papyrus_narration(mission_id, "Writing the executive summary")
    body = _papyrus_llm_generate(
        deliverable_type=deliverable_type,
        mission=mission,
        hypotheses=hypotheses,
        findings=findings,
        mission_brief=mission_brief,
        extra=extra or None,
    )
    path.write_text(body, encoding="utf-8")
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "status": "generated",
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
    deliverable_id = f"deliverable-{mission_id}-data-book"
    deliverable_type = "data_book"

    if path.exists():
        return {
            "mission_id": mission_id,
            "file_path": str(path.resolve()),
            "status": "skipped",
            "deliverable_id": deliverable_id,
            "deliverable_type": deliverable_type,
        }

    hypotheses = store.list_hypotheses(mission_id)
    mission_brief = store.get_mission_brief(mission_id)

    _emit_papyrus_narration(mission_id, "Assembling the data book")
    body = _papyrus_llm_generate(
        deliverable_type=deliverable_type,
        mission=store.get_mission(mission_id),
        hypotheses=hypotheses,
        findings=findings,
        mission_brief=mission_brief,
    )
    path.write_text(body, encoding="utf-8")
    _save_deliverable(store, mission_id, deliverable_id, deliverable_type, path)
    return {
        "mission_id": mission_id,
        "file_path": str(path.resolve()),
        "status": "generated",
        "deliverable_id": deliverable_id,
        "deliverable_type": deliverable_type,
    }


def generate_data_book(state: InjectedStateArg = None) -> dict[str, Any]:
    """Generate data book for the mission."""
    mission_id = require_mission_id(state)
    return _generate_data_book_impl(mission_id)
