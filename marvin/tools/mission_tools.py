from __future__ import annotations

from datetime import date
from typing import Any

from langgraph.types import Command

from marvin.events import emit_finding_persisted
from marvin.mission.schema import Finding, Hypothesis, MerlinVerdict, Mission, Source
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools.common import (
    InjectedStateArg,
    get_store,
    require_mission_id,
    serialize_models,
    short_id,
    slugify,
    utc_now_iso,
)

_STORE_FACTORY = MissionStore


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
    # Placeholder - not implemented in store yet
    return {"hypothesis_id": hypothesis_id, "status": status}


def mark_milestone_delivered(
    milestone_id: str,
    result_summary: str,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Mark a milestone as delivered with a result summary."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    delivered = store.mark_milestone_delivered(milestone_id, result_summary, mission_id=mission_id)
    return {
        "milestone_id": milestone_id,
        "status": "delivered",
        "label": delivered.label,
    }


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
        allowed = {h.id for h in store.list_hypotheses(mission_id)}
        if hypothesis_id not in allowed:
            raise ValueError(
                f"hypothesis_id {hypothesis_id!r} is not a valid hypothesis for "
                f"mission {mission_id}. Allowed: {sorted(allowed)}. "
                "Pass one of these IDs verbatim, or omit hypothesis_id."
            )

    if workstream_id is not None:
        allowed_ws = {w.id for w in store.list_workstreams(mission_id)}
        if workstream_id not in allowed_ws:
            raise ValueError(
                f"workstream_id {workstream_id!r} is not a valid workstream for "
                f"mission {mission_id}. Allowed: {sorted(allowed_ws)}. "
                "Pass one of these IDs verbatim, or omit workstream_id."
            )

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
        id=short_id("src"),
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
    return {"question": text, "blocking": blocking, "mission_id": mission_id}


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
        # Placeholder - would generate actual interview guide
        guides.append({
            "hypothesis_id": hypothesis_id,
            "questions": [
                f"How does {hypothesis.text[:50]}... affect the business?",
            ],
        })
    return {"guides": guides}


def _generate_hypotheses_inline(mission_id: str) -> list[Hypothesis]:
    """Internal helper to generate hypotheses without state injection."""
    store = get_store(_STORE_FACTORY)
    mission = store.get_mission(mission_id)
    # Generate 3 default hypotheses for CDD
    hypotheses = [
        Hypothesis(
            id=short_id("hyp"),
            mission_id=mission_id,
            text=f"{mission.target} has a durable competitive advantage",
            created_at=utc_now_iso(),
        ),
        Hypothesis(
            id=short_id("hyp"),
            mission_id=mission_id,
            text=f"{mission.target}'s unit economics are attractive at scale",
            created_at=utc_now_iso(),
        ),
        Hypothesis(
            id=short_id("hyp"),
            mission_id=mission_id,
            text=f"{mission.target} faces execution risk in key growth markets",
            created_at=utc_now_iso(),
        ),
    ]
    for hyp in hypotheses:
        store.save_hypothesis(hyp)
    return hypotheses
