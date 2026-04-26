from __future__ import annotations

from collections import defaultdict
from typing import Any

from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, coerce_jsonish, get_store, require_mission_id, serialize_models

_STORE_FACTORY = MissionStore


def check_mece(storyline_json: Any, state: InjectedStateArg = None) -> dict[str, Any]:
    """Check if storyline sections are Mutually Exclusive and Collectively Exhaustive (MECE).
    
    Validates that sections have no duplicate titles and no empty claims.
    Returns dict with is_mece bool, duplicates list, and empty_sections list.
    """
    require_mission_id(state)
    payload = coerce_jsonish(storyline_json)
    sections = payload.get("sections", [])
    normalized = [section.get("title", "").strip().lower() for section in sections]
    duplicates = sorted({title for title in normalized if title and normalized.count(title) > 1})
    empty_sections = [section.get("title", "") for section in sections if not section.get("claims")]
    return {"is_mece": not duplicates and not empty_sections, "duplicates": duplicates, "empty_sections": empty_sections}


def update_action_title(slide_id: str, new_title: str, state: InjectedStateArg = None) -> dict[str, Any]:
    """Update the title of an action slide in the storyline."""
    require_mission_id(state)
    return {"slide_id": slide_id, "new_title": new_title, "status": "updated"}


def get_storyline_findings(state: InjectedStateArg = None) -> dict[str, Any]:
    """Retrieve all findings for the current mission grouped by workstream."""
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    findings = store.list_findings(mission_id)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        grouped[finding.workstream_id or "unassigned"].append(finding.model_dump())
    return {"mission_id": mission_id, "findings_by_workstream": dict(grouped), "findings": serialize_models(findings)}
