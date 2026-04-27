from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps


def last_value(_: object, value: object) -> object:
    return value


class MarvinState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    remaining_steps: RemainingSteps
    mission_id: Annotated[Optional[str], last_value]
    phase: Annotated[str, last_value]
    pending_gate_id: Annotated[Optional[str], last_value]
    gate_passed: Annotated[Optional[bool], last_value]
    synthesis_retry_count: Annotated[int, last_value]
    framing_complete: Annotated[bool, last_value]
    clarification_questions_asked: Annotated[int, last_value]
    pivot_required: Annotated[bool, last_value]
    pivot_reason: Annotated[Optional[str], last_value]
