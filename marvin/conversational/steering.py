"""C-CONV — mid-mission steering classifier + apply helper.

The "redirect the mission" half of the chat input is wired here. When the
graph is *running* (not interrupted at a gate) and the user types a message,
`classify_message` decides between:

- ``qa``     — the message is a question or comment; route to read-only
               orchestrator_qa as before.
- ``steer``  — the message is an imperative instruction; queue it on the
               ``mission_steering`` table so the next agent picks it up.

The classifier is heuristic-first so the chat path stays cheap and
deterministic. We do not need partner-grade nuance to decide "ask vs
instruct" — false positives downgrade gracefully (the agent receives an
extra instruction line, no harm done) and false negatives just route the
message to QA where the user can retry with clearer phrasing.

`apply_pending_steering(state)` is called at the entry of every agent
node (dora / calculus / adversus / merlin). It pops every unconsumed
steering row for the mission and returns them as a list of HumanMessage
objects for the agent to receive at the top of its message tape.
"""
from __future__ import annotations

import logging
from typing import Iterable, Literal

from langchain_core.messages import HumanMessage

from marvin.mission.store import MissionStore

logger = logging.getLogger(__name__)


# Imperative cues — English + French. The list is intentionally small and
# unambiguous; broader natural-language coverage is the LLM classifier's
# job, but we keep this synchronous to avoid adding latency to every chat
# message.
_STEER_CUES_EN = (
    "focus on", "skip", "prioritize", "drop", "add ", "instead of",
    "also look", "ignore", "don't bother", "specifically", "make sure",
    "remember to", "include", "exclude", "switch to", "change the",
    "redirect", "pivot", "remove", "stop ", "do not", "don't ",
)
_STEER_CUES_FR = (
    "concentre", "concentrez", "ignore", "ajoute", "retire", "vérifie",
    "verifie", "demande", "remplace", "change", "n'oublie", "n'oubliez",
    "redirige", "stop ", "arrête", "arrete", "n'hésite", "n'hesite",
    "fais en sorte", "exclus", "inclus", "priorise",
)
_QA_CUES = (
    "what", "why", "how", "explain", "tell me", "show me", "do you",
    "is there", "are there", "qu'est", "pourquoi", "comment", "explique",
    "qui ", "quand ",
)
_RERUN_CUES_EN = ("rerun", "redo", "retry", "try again", "run again", "restart")
_RERUN_CUES_FR = ("relancer", "réessayer", "redémarrer", "recommencer", "refaire")


def classify_message(text: str) -> Literal["qa", "steer", "rerun"]:
    """Heuristic message intent classifier. Default is ``qa`` (safer)."""
    if not text:
        return "qa"
    lowered = text.strip().lower()
    if not lowered:
        return "qa"
    # Trailing question mark is a strong QA signal.
    if lowered.endswith("?"):
        return "qa"
    head = lowered[:30]
    # QA cues at the head of the message win first — "why did X skip Y"
    # contains a steer cue but is clearly a question.
    for cue in _QA_CUES:
        if head.startswith(cue) or f" {cue}" in head[:15]:
            return "qa"
    # Imperative cue at sentence start carries the most signal — anchor
    # at the first 30 chars to avoid false positives from the cue
    # appearing mid-prose.
    for cue in _STEER_CUES_EN + _STEER_CUES_FR:
        if cue in head:
            return "steer"
    # Check for rerun intent (whole-word match to avoid false positives)
    for cue in _RERUN_CUES_EN + _RERUN_CUES_FR:
        if cue in lowered:
            return "rerun"
    return "qa"


def queue_steering(mission_id: str, instruction: str) -> str:
    """Persist a steering row. Returns the new id."""
    store = MissionStore()
    return store.add_steering(mission_id, instruction.strip())


def apply_pending_steering(mission_id: str) -> list[HumanMessage]:
    """Drain unconsumed steering rows and return them as HumanMessages.

    Called at the entry of each agent node. Rows are marked consumed
    immediately so a subsequent agent (e.g. Calculus after Dora) does
    not re-receive the same instruction unless the user re-issues it.

    Returns an empty list when no steering is pending — agents append
    the result without conditional logic.
    """
    if not mission_id:
        return []
    try:
        store = MissionStore()
    except Exception:  # noqa: BLE001 - steering must never block the main run
        return []
    pending = store.list_pending_steering(mission_id)
    if not pending:
        return []
    messages: list[HumanMessage] = []
    for row in pending:
        instruction = (row.get("instruction") or "").strip()
        if not instruction:
            store.consume_steering(row["id"])
            continue
        messages.append(
            HumanMessage(
                content=(
                    f"[user steering — apply this to your current task] "
                    f"{instruction}"
                )
            )
        )
        store.consume_steering(row["id"])
    if messages:
        logger.info(
            "apply_pending_steering: surfaced %d instruction(s) to agent for %s",
            len(messages),
            mission_id,
        )
    return messages


def merge_steering_into_messages(
    mission_id: str,
    messages: Iterable,
) -> list:
    """Convenience wrapper used by agent entry points: append pending
    steering after the existing message tape so the agent sees both
    its task brief and the user override."""
    base = list(messages)
    base.extend(apply_pending_steering(mission_id))
    return base
