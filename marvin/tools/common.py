from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from langgraph.prebuilt import InjectedState

from marvin.mission.store import MissionStore

# Type alias for state parameter that should be injected by LangGraph
# Use this for tool parameters that need access to the current graph state
InjectedStateArg = Annotated[dict[str, Any] | None, InjectedState]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def short_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "mission"


_HYP_ID_SHAPE = re.compile(r"^hyp-[a-f0-9]+$")
_WRAPPER_PAIRS = (("[", "]"), ("(", ")"), ("<", ">"), ('"', '"'), ("'", "'"), ("`", "`"))


def _strip_one_wrapper(value: str) -> str:
    for left, right in _WRAPPER_PAIRS:
        if len(value) >= 2 and value.startswith(left) and value.endswith(right):
            return value[1:-1].strip()
    return value


def normalize_hypothesis_id(raw: str) -> str:
    """Strip recoverable LLM formatting noise around an otherwise-valid hyp ID.

    Conservative: any returned value MUST still be checked against the mission's
    allowed-id set by the caller. This function never selects, infers, or
    fabricates an ID; it only removes wrappers/whitespace/trailing tokens when
    the residue looks like a real `hyp-...` shape.
    """
    if not isinstance(raw, str):
        return raw
    candidate = raw.strip()
    # Pass 1: remove a single matched outer wrapper + any trailing punctuation
    # ("[hyp-79a14102]," -> "hyp-79a14102").
    candidate = candidate.rstrip(".,;:")
    candidate = _strip_one_wrapper(candidate).rstrip(".,;:")
    # Pass 2: if there is still a tail after whitespace, keep only the first
    # token IF that token (after wrapper/punct strip) matches the hyp shape.
    # ("[hyp-79a14102] AcmeH2..." -> first token "[hyp-79a14102]" -> "hyp-79a14102").
    if any(ws in candidate for ws in (" ", "\t", "\n")):
        first_token = candidate.split(None, 1)[0].rstrip(".,;:")
        first_token = _strip_one_wrapper(first_token).rstrip(".,;:")
        if _HYP_ID_SHAPE.match(first_token):
            return first_token
        return candidate
    return candidate


def require_mission_id(state: dict[str, Any] | None) -> str:
    mission_id = (state or {}).get("mission_id")
    if not mission_id:
        raise KeyError("mission_id not in state")
    return mission_id


def get_store(factory: type[MissionStore] | Any) -> MissionStore:
    return factory()


def ensure_output_dir(project_root: Path, mission_id: str) -> Path:
    output_dir = project_root / "output" / mission_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def coerce_jsonish(payload: Any) -> Any:
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def serialize_models(rows: list[Any]) -> list[dict[str, Any]]:
    return [row.model_dump() for row in rows]
