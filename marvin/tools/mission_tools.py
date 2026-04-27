from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from langgraph.types import Command

from marvin.events import emit_finding_persisted
from marvin.mission.schema import Finding, Hypothesis, MerlinVerdict, Mission, MissionBrief, Source
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools.common import (
    InjectedStateArg,
    get_store,
    normalize_hypothesis_id,
    require_mission_id,
    serialize_models,
    short_id,
    slugify,
    utc_now_iso,
)

_STORE_FACTORY = MissionStore


def _clean_brief_text(raw_brief: str) -> str:
    return " ".join(raw_brief.strip().split())


def _derive_ic_question(mission: Mission, raw_brief: str) -> str:
    if (mission.ic_question or "").strip():
        return mission.ic_question.strip()

    match = re.search(r"([^.!?\n]{20,180}\?)", raw_brief)
    if match:
        return match.group(1).strip()

    return f"Should IC invest in {mission.target}?"


def _derive_mission_angle(raw_brief: str) -> str:
    lowered = raw_brief.lower()
    if any(token in lowered for token in ("unit economics", "qoe", "margin", "revenue", "concentration")):
        return "Financial quality and unit economics"
    if any(token in lowered for token in ("market", "competitive", "competition", "moat", "positioning")):
        return "Market position and competitive durability"
    if any(token in lowered for token in ("risk", "red flag", "downside", "churn")):
        return "Risk-adjusted investment case"
    return "Commercial diligence of the investment thesis"


def _brief_summary(raw_brief: str) -> str:
    cleaned = _clean_brief_text(raw_brief)
    return cleaned[:360] if cleaned else "Initial mission brief captured."


def _workstream_plan(mission: Mission, mission_angle: str) -> list[dict[str, str]]:
    return [
        {
            "id": "W1",
            "label": "Market and competitive analysis",
            "agent": "dora",
            "focus": f"Test market position, competitive dynamics, and moat signals for {mission.target}.",
        },
        {
            "id": "W2",
            "label": "Financial analysis",
            "agent": "calculus",
            "focus": f"Test unit economics, quality of earnings, anomalies, and concentration for {mission.target}.",
        },
        {
            "id": "W4",
            "label": "Red-team and stress testing",
            "agent": "adversus",
            "focus": f"Challenge the {mission_angle.lower()} story and identify the weakest link.",
        },
        {
            "id": "W3",
            "label": "Storyline synthesis",
            "agent": "merlin",
            "focus": "Synthesize claims, gaps, and final readiness after research and red-team.",
        },
    ]


def create_cdd_mission(
    client: str,
    target: str,
    ic_question: str,
    mission_type: str = "cdd",
) -> Command:
    """Create a new CDD mission."""
    store = get_store(_STORE_FACTORY)
    mission_id = f"m-{slugify(target)}-{date.today().strftime('%Y%m%d')}"
    base_id = mission_id
    suffix = 1
    while _mission_exists(store, mission_id):
        suffix += 1
        mission_id = f"{base_id}-{suffix}"
    mission = Mission(
        id=mission_id,
        client=client,
        target=target,
        mission_type=mission_type,
        ic_question=ic_question,
        status="active",
        created_at=utc_now_iso(),
    )
    store.save_mission(mission)
    _seed_standard_workplan(mission_id, store)
    return Command(
        update={
            "mission_id": mission_id,
            "phase": "setup",
        }
    )


def _mission_exists(store: MissionStore, mission_id: str) -> bool:
    try:
        store.get_mission(mission_id)
        return True
    except KeyError:
        return False


def get_workplan_for_mission(state: InjectedStateArg = None) -> dict[str, Any]:
    """Retrieve the workplan (workstreams and milestones) for a mission."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    workstreams = store.list_workstreams(mission_id)
    milestones = store.list_milestones(mission_id)
    gates = store.list_gates(mission_id)
    return {
        "mission_id": mission_id,
        "workstreams": serialize_models(workstreams),
        "milestones": serialize_models(milestones),
        "gates": serialize_models(gates),
    }


def get_mission_brief(state: InjectedStateArg = None) -> dict[str, Any]:
    """Retrieve the persisted mission brief/framing state."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    brief = store.get_mission_brief(mission_id)
    return {"mission_id": mission_id, "brief": brief.model_dump() if brief else None}


def get_hypotheses(state: InjectedStateArg = None) -> dict[str, Any]:
    """Retrieve all hypotheses for the current mission."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    hypotheses = store.list_hypotheses(mission_id)
    return {"mission_id": mission_id, "hypotheses": serialize_models(hypotheses)}


def add_hypothesis_to_mission(text: str, state: InjectedStateArg = None) -> dict[str, Any]:
    """Add a hypothesis to the mission."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    hypothesis = Hypothesis(
        id=short_id("hyp"),
        mission_id=mission_id,
        text=text,
        created_at=utc_now_iso(),
    )
    store.save_hypothesis(hypothesis)
    return {"hypothesis_id": hypothesis.id, "text": text, "status": "saved"}


def update_hypothesis(
    hypothesis_id: str,
    status: str,
    abandon_reason: str | None = None,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Update hypothesis status."""
    require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    hypothesis_id = normalize_hypothesis_id(hypothesis_id)
    updated = store.update_hypothesis(hypothesis_id, status, abandon_reason)
    return {"hypothesis_id": updated.id, "status": updated.status}


def mark_milestone_delivered(
    milestone_id: str,
    result_summary: str,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Mark a milestone as delivered with a result summary."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    milestone_id = _normalize_milestone_id(milestone_id)
    delivered = store.mark_milestone_delivered(milestone_id, result_summary, mission_id=mission_id)
    return {
        "milestone_id": milestone_id,
        "status": "delivered",
        "label": delivered.label,
    }


def _normalize_finding_claim_text(claim_text: str) -> str:
    """Normalize only formatting noise; do not guess semantic equivalence."""
    return re.sub(r"\s+", " ", claim_text.casefold()).strip().rstrip(".!?;:")


def _find_duplicate_finding(
    findings: list[Finding],
    *,
    claim_text: str,
    workstream_id: str | None,
) -> Finding | None:
    # One factual claim should appear once per workstream. Hypothesis IDs are
    # deliberately excluded so agents do not inflate gates by filing the same
    # claim under multiple plausible hypotheses.
    normalized_claim = _normalize_finding_claim_text(claim_text)
    for finding in findings:
        if finding.workstream_id != workstream_id:
            continue
        if _normalize_finding_claim_text(finding.claim_text) == normalized_claim:
            return finding
    return None


def _normalize_workstream_id(raw_workstream_id: str) -> str:
    """Accept milestone-shaped workstream refs like W1.1 as recoverable W1."""
    return raw_workstream_id.split(".", 1)[0].strip()


def _normalize_milestone_id(raw_milestone_id: str) -> str:
    """Extract a real seeded milestone id from recoverable LLM label noise."""
    candidate = raw_milestone_id.strip()
    if match := re.search(r"\bW\d+\.\d+\b", candidate):
        return match.group(0)
    return candidate


def add_finding_to_mission(
    claim_text: str,
    confidence: str,
    agent_id: str | None = None,
    workstream_id: str | None = None,
    hypothesis_id: str | None = None,
    source_id: str | None = None,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Add a finding to the mission.

    `hypothesis_id` and `workstream_id` are validated against the store
    BEFORE insert. Invalid references raise ValueError with the allowed set,
    so the LLM tool-loop receives a corrective message instead of an opaque
    SQLite FOREIGN KEY error. Pass None when no link applies.
    """
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)

    if hypothesis_id is not None:
        hypothesis_id = normalize_hypothesis_id(hypothesis_id)
        allowed = {h.id for h in store.list_hypotheses(mission_id)}
        if hypothesis_id not in allowed:
            raise ValueError(
                f"hypothesis_id {hypothesis_id!r} is not a valid hypothesis for "
                f"mission {mission_id}. Allowed: {sorted(allowed)}. "
                "Pass one of these IDs verbatim, or omit hypothesis_id."
            )

    if workstream_id is not None:
        workstream_id = _normalize_workstream_id(workstream_id)
        allowed_ws = {w.id for w in store.list_workstreams(mission_id)}
        if workstream_id not in allowed_ws:
            raise ValueError(
                f"workstream_id {workstream_id!r} is not a valid workstream for "
                f"mission {mission_id}. Allowed: {sorted(allowed_ws)}. "
                "Pass one of these IDs verbatim, or omit workstream_id."
            )

    duplicate = _find_duplicate_finding(
        store.list_findings(mission_id),
        claim_text=claim_text,
        workstream_id=workstream_id,
    )
    if duplicate is not None:
        return {
            "finding_id": duplicate.id,
            "claim": duplicate.claim_text,
            "confidence": duplicate.confidence,
            "status": "duplicate",
        }

    finding = Finding(
        id=short_id("f"),
        mission_id=mission_id,
        workstream_id=workstream_id,
        hypothesis_id=hypothesis_id,
        claim_text=claim_text,
        confidence=confidence,
        source_id=source_id,
        agent_id=agent_id,
        created_at=utc_now_iso(),
    )
    store.save_finding(finding)
    emit_finding_persisted(
        mission_id,
        {
            "finding_id": finding.id,
            "claim_text": claim_text,
            "confidence": confidence,
            "agent_id": agent_id,
            "workstream_id": workstream_id,
            "hypothesis_id": hypothesis_id,
        },
    )
    return {
        "finding_id": finding.id,
        "claim": claim_text,
        "confidence": confidence,
        "status": "saved",
    }


def persist_source_for_mission(
    url_or_ref: str,
    quote: str,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Persist a source reference for the mission."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    source = Source(
        id=short_id("s"),
        mission_id=mission_id,
        url_or_ref=url_or_ref,
        quote=quote,
        retrieved_at=utc_now_iso(),
    )
    store.save_source(source)
    return {"source_id": source.id}


def ask_question(text: str, blocking: bool, state: InjectedStateArg = None) -> dict[str, Any]:
    """Ask a question to the user."""
    mission_id = require_mission_id(state)
    return {"question": text, "blocking": blocking, "mission_id": mission_id, "status": "pending"}


def set_merlin_verdict(
    verdict: str,
    notes: str,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Record Merlin's final verdict (SHIP, MINOR_FIXES, or BACK_TO_DRAWING_BOARD) for the mission."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    g3_gate = next((gate for gate in store.list_gates(mission_id) if gate.scheduled_day == 10), None)
    verdict_row = MerlinVerdict(
        id=short_id("mv"),
        mission_id=mission_id,
        verdict=verdict,
        gate_id=g3_gate.id if g3_gate else None,
        notes=notes,
        created_at=utc_now_iso(),
    )
    store.save_merlin_verdict(verdict_row)
    return {"verdict": verdict_row.verdict, "verdict_id": verdict_row.id}


def check_merlin_verdict(state: InjectedStateArg = None) -> dict[str, Any]:
    """Check if a Merlin verdict has been recorded for the mission."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    verdict = store.get_latest_merlin_verdict(mission_id)
    if verdict is None:
        return {"mission_id": mission_id, "verdict": None}
    return {"mission_id": mission_id, "verdict": verdict.verdict, "notes": verdict.notes}


def generate_interview_guides(
    hypothesis_ids: list[str],
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Generate interview guides for the given hypotheses."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    by_id = {hypothesis.id: hypothesis for hypothesis in store.list_hypotheses(mission_id)}
    guides = []
    for hypothesis_id in hypothesis_ids:
        hypothesis = by_id[hypothesis_id]
        excerpt = hypothesis.text[:80]
        guides.append({
            "hypothesis_id": hypothesis_id,
            "questions": [
                f"What evidence would confirm or refute that {excerpt}?",
                f"Where have you seen counter-examples to {excerpt}?",
                f"Which leading indicator best tracks {excerpt} over the next 12 months?",
            ],
        })
    return {"guides": guides}


def _generate_hypotheses_inline(mission_id: str, raw_brief: str | None = None) -> list[Hypothesis]:
    """Internal helper to generate hypotheses without state injection."""
    store = get_store(_STORE_FACTORY)
    mission = store.get_mission(mission_id)
    existing = store.list_hypotheses(mission_id, status="active")
    if existing:
        return existing

    brief = _clean_brief_text(raw_brief or "")
    mission_angle = _derive_mission_angle(brief)
    evidence_context = brief[:140] if brief else mission.ic_question or "the initial investment thesis"
    hypotheses = [
        Hypothesis(
            id=short_id("hyp"),
            mission_id=mission_id,
            text=f"{mission.target}'s investment case depends on {mission_angle.lower()} holding under diligence.",
            created_at=utc_now_iso(),
        ),
        Hypothesis(
            id=short_id("hyp"),
            mission_id=mission_id,
            text=f"{mission.target} can support the thesis in the brief: {evidence_context}",
            created_at=utc_now_iso(),
        ),
        Hypothesis(
            id=short_id("hyp"),
            mission_id=mission_id,
            text=f"The main diligence risk is that evidence from Dora, Calculus, or Adversus disproves the {mission_angle.lower()} story.",
            created_at=utc_now_iso(),
        ),
    ]
    for hyp in hypotheses:
        store.save_hypothesis(hyp)
    return hypotheses


def persist_framing_from_brief(mission_id: str, raw_brief: str) -> MissionBrief:
    """Persist the user's brief and deterministic framing scaffold."""
    store = get_store(_STORE_FACTORY)
    mission = store.get_mission(mission_id)
    cleaned = _clean_brief_text(raw_brief)
    if not cleaned:
        raise ValueError("framing requires a non-empty brief")

    ic_question = _derive_ic_question(mission, cleaned)
    mission_angle = _derive_mission_angle(cleaned)
    now = utc_now_iso()
    existing = store.get_mission_brief(mission_id)
    created_at = existing.created_at if existing else now
    brief = MissionBrief(
        mission_id=mission_id,
        raw_brief=cleaned,
        ic_question=ic_question,
        mission_angle=mission_angle,
        brief_summary=_brief_summary(cleaned),
        workstream_plan_json=json.dumps(_workstream_plan(mission, mission_angle), ensure_ascii=True),
        created_at=created_at,
        updated_at=now,
    )
    store.save_mission_brief(brief)
    return brief
