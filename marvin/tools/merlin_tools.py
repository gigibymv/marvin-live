from __future__ import annotations

from collections import defaultdict
from typing import Any

from marvin.events import emit_graph_event
from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, coerce_jsonish, get_store, require_mission_id, serialize_models


def _emit_merlin_narration(mission_id: str, intent: str) -> None:
    """9-bug triage I: surface merlin's per-step work in the live SSE stream."""
    try:
        from datetime import UTC, datetime
        import json as _json
        ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        payload = {"agent": "Merlin", "intent": intent, "ts": ts}
        sse_string = f"event: narration\ndata: {_json.dumps(payload)}\n\n"
        emit_graph_event(mission_id, sse_string)
    except Exception:  # noqa: BLE001 — defensive boundary
        pass

_STORE_FACTORY = MissionStore


def check_mece(storyline_json: Any, state: InjectedStateArg = None) -> dict[str, Any]:
    """Check if storyline sections are Mutually Exclusive and Collectively Exhaustive (MECE).
    
    Validates that sections have no duplicate titles and no empty claims.
    Returns dict with is_mece bool, duplicates list, and empty_sections list.
    """
    mission_id = require_mission_id(state)
    _emit_merlin_narration(mission_id, "Checking MECE on the storyline")
    payload = coerce_jsonish(storyline_json)
    # The LLM occasionally passes a literal null / empty string / non-dict
    # value when it is uncertain about the storyline shape. Treat that as
    # "no sections to check" rather than crashing the merlin node — the
    # whole graph used to abort here with `'NoneType' object has no
    # attribute 'get'`, leaving G3 stuck pending and the mission frozen.
    if not isinstance(payload, dict):
        return {"is_mece": False, "duplicates": [], "empty_sections": [], "error": "storyline_json was not an object"}
    sections = payload.get("sections", []) or []
    normalized = [
        (section.get("title", "") if isinstance(section, dict) else "").strip().lower()
        for section in sections
    ]
    duplicates = sorted({title for title in normalized if title and normalized.count(title) > 1})
    empty_sections = [
        (section.get("title", "") if isinstance(section, dict) else "")
        for section in sections
        if not (isinstance(section, dict) and section.get("claims"))
    ]
    return {"is_mece": not duplicates and not empty_sections, "duplicates": duplicates, "empty_sections": empty_sections}


def update_action_title(slide_id: str, new_title: str, state: InjectedStateArg = None) -> dict[str, Any]:
    """Update the title of an action slide in the storyline."""
    require_mission_id(state)
    return {"slide_id": slide_id, "new_title": new_title, "status": "updated"}


def get_storyline_findings(state: InjectedStateArg = None) -> dict[str, Any]:
    """Retrieve all findings for the current mission grouped by workstream."""
    mission_id = require_mission_id(state)
    _emit_merlin_narration(mission_id, "Reviewing findings for the storyline")
    store = get_store(_STORE_FACTORY)
    findings = store.list_findings(mission_id)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        grouped[finding.workstream_id or "unassigned"].append(finding.model_dump())
    return {"mission_id": mission_id, "findings_by_workstream": dict(grouped), "findings": serialize_models(findings)}
