"""Framing orchestrator: evaluates brief completeness and asks clarification
questions before hypotheses are generated.

Flow:
- First call with a brief → LLM evaluates {ready, questions, reply}.
- If ready (or 3 rounds asked) → set framing_complete=True, advance to framing.
- If thin → create a clarification gate row, increment the round counter on
  the mission, and route to phase=awaiting_clarification with pending_gate_id
  set. The gate_node then dispatches gate_pending over SSE and interrupts;
  validate_gate hands the user's answers back as the resume payload, which
  the gate_node persists and routes back to phase=framing for another
  orchestrator pass.

State persistence:
- raw_brief is concatenated and persisted to MissionBrief on every turn.
- clarification rounds + answers live on the mission row in the DB so the
  flow survives uvicorn restarts and multi-worker deploys (Chantier 2 D2).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from marvin.graph.state import MarvinState
from marvin.llm_factory import get_chat_llm
from marvin.mission.schema import Gate
from marvin.mission.store import MissionStore
from marvin.tools.common import short_id
from marvin.tools.mission_tools import _clean_brief_text, persist_framing_from_brief

logger = logging.getLogger(__name__)

MAX_CLARIFICATION_ROUNDS = 3


def get_clarification_rounds(mission_id: str) -> int:
    """Read the rounds counter from the DB. Kept as a helper for callers
    (e.g. tests) that previously read a module-level dict."""
    store = MissionStore()
    return store.get_clarification_state(mission_id)["rounds"]


def get_clarification_answers(mission_id: str) -> list[str]:
    store = MissionStore()
    return store.get_clarification_state(mission_id)["answers"]


def reset_clarification_state(mission_id: str) -> None:
    """Drop tracked clarification state. Called when framing completes or
    when a pivot resets framing."""
    store = MissionStore()
    store.reset_clarification_state(mission_id)


def _latest_human_text(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _persist_brief_with_history(mission_id: str, new_text: str) -> str:
    """Persist the brief on the FIRST substantive message; thereafter route
    later turns into clarification_answers. The raw_brief field is frozen
    once set so the framing memo always reflects the original brief
    (Bug 2 — chantier 2.5).

    Returns the combined "brief + clarifications" text used as LLM context.
    """
    store = MissionStore()
    existing = store.get_mission_brief(mission_id)
    cleaned_new = _clean_brief_text(new_text)

    if existing is None or not (existing.raw_brief or "").strip():
        if cleaned_new:
            persist_framing_from_brief(mission_id, cleaned_new)
            return cleaned_new
        return ""

    raw_brief = (existing.raw_brief or "").strip()
    if cleaned_new and cleaned_new != raw_brief:
        # Subsequent message — clarification answer, NOT brief.
        existing_answers = store.get_clarification_state(mission_id)["answers"]
        if cleaned_new not in existing_answers:
            store.append_clarification_answer(mission_id, cleaned_new)
    answers = store.get_clarification_state(mission_id)["answers"]
    if answers:
        return (raw_brief + "\n\nClarifications:\n" + "\n".join(answers)).strip()
    return raw_brief


def _evaluate_brief_via_llm(mission_id: str, raw_brief: str) -> dict:
    """Ask the LLM to evaluate brief completeness."""
    try:
        llm = get_chat_llm("framing")
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY" in str(exc):
            return {
                "ready": True,
                "missing": [],
                "questions": [],
                "reply": "Framing now (no LLM key set — deterministic path).",
            }
        raise

    prompt_path = Path(__file__).resolve().parents[2] / "subagents" / "prompts" / "framing_orchestrator.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    store = MissionStore()
    mission = store.get_mission(mission_id)
    rounds = store.get_clarification_state(mission_id)["rounds"]
    context = (
        f"Mission target: {mission.target}\n"
        f"Client: {mission.client}\n"
        f"IC question (if any): {mission.ic_question or '(none provided)'}\n"
        f"Clarification rounds already asked: {rounds} of {MAX_CLARIFICATION_ROUNDS}\n\n"
        f"Brief (with any prior clarifications appended):\n{raw_brief}"
    )

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=context),
    ])
    raw = (response.content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("framing_orchestrator: LLM returned non-JSON; treating as ready")
        return {
            "ready": True,
            "missing": [],
            "questions": [],
            "reply": "Framing now (orchestrator response malformed; proceeding).",
        }

    return {
        "ready": bool(parsed.get("ready", False)),
        "missing": list(parsed.get("missing") or []),
        "questions": [str(q).strip() for q in (parsed.get("questions") or []) if str(q).strip()],
        "reply": str(parsed.get("reply") or "").strip(),
    }


def _create_clarification_gate(mission_id: str, questions: list[str]) -> str:
    """Create a clarification_request gate row carrying the questions list.
    Returns the gate id."""
    store = MissionStore()
    gate_id = f"gate-{mission_id}-clarif-{short_id('r')[2:]}"
    gate = Gate(
        id=gate_id,
        mission_id=mission_id,
        gate_type="clarification_request",
        scheduled_day=0,
        validator_role="manager",
        status="pending",
        format="clarification_questions",
        questions=questions,
    )
    store.save_gate(gate)
    return gate_id


async def framing_orchestrator_node(state: MarvinState) -> dict:
    """Evaluate brief completeness; either advance framing or open a
    clarification gate."""
    mission_id = state.get("mission_id", "")
    messages = state.get("messages", [])

    if not mission_id:
        return {"phase": "setup"}

    latest = _latest_human_text(messages)
    if not latest.strip():
        return {"phase": "setup", "messages": messages}

    store = MissionStore()
    pre_state = store.get_clarification_state(mission_id)
    rounds = pre_state["rounds"]

    merged_brief = _persist_brief_with_history(mission_id, latest)

    # Hard cap: stop asking and force forward.
    if rounds >= MAX_CLARIFICATION_ROUNDS:
        logger.info(
            "framing_orchestrator: cap hit (%d rounds) for %s — forcing framing forward",
            rounds,
            mission_id,
        )
        return {
            "framing_complete": True,
            "clarification_questions_asked": rounds,
            "phase": "framing",
        }

    evaluation = _evaluate_brief_via_llm(mission_id, merged_brief)

    if evaluation["ready"]:
        return {
            "framing_complete": True,
            "clarification_questions_asked": rounds,
            "phase": "framing",
        }

    questions = evaluation["questions"]
    if not questions:
        # Not ready but no questions — force forward to avoid stalling.
        logger.warning(
            "framing_orchestrator: ready=False with no questions for %s — advancing",
            mission_id,
        )
        return {
            "framing_complete": True,
            "clarification_questions_asked": rounds,
            "phase": "framing",
        }

    new_rounds = store.increment_clarification_rounds(mission_id)
    gate_id = _create_clarification_gate(mission_id, questions)

    return {
        "clarification_questions_asked": new_rounds,
        "phase": "awaiting_clarification",
        "pending_gate_id": gate_id,
    }
