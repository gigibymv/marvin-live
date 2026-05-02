from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from marvin_ui.server import _emit_for_update


def _events(chunks: list[str]) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []
    for chunk in chunks:
        event_type = ""
        data = ""
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        if event_type and data:
            parsed.append((event_type, json.loads(data)))
    return parsed


@pytest.mark.asyncio
async def test_emit_for_update_adds_workflow_and_agent_narration():
    chunks, current_agent, current_phase, is_interrupt = await _emit_for_update(
        {"dora": {"phase": "confirmed", "messages": []}},
        None,
        None,
        {},
    )

    events = _events(chunks)

    assert ("phase_changed", {"phase": "confirmed", "label": "Research kickoff"}) in events
    assert any(
        event_type == "narration"
        and payload["agent"] == "MARVIN"
        and payload["intent"] == "Starting the research workstreams."
        for event_type, payload in events
    )
    assert any(
        event_type == "agent_active" and payload["agent"] == "Dora"
        for event_type, payload in events
    )
    assert any(
        event_type == "narration"
        and payload["agent"] == "Dora"
        and payload["intent"] == "Mapping the competitive landscape"
        for event_type, payload in events
    )
    assert current_agent == "dora"
    assert current_phase == "confirmed"
    assert is_interrupt is False


@pytest.mark.asyncio
async def test_emit_for_update_narrates_gate_interrupt():
    chunks, current_agent, current_phase, is_interrupt = await _emit_for_update(
        {
            "__interrupt__": (
                SimpleNamespace(
                    value={
                        "gate_id": "gate-1",
                        "gate_type": "manager_review",
                        "title": "Manager review of research claims",
                    }
                ),
            )
        },
        "dora",
        "research_done",
        {},
    )

    events = _events(chunks)

    assert any(event_type == "agent_done" and payload["agent"] == "Dora" for event_type, payload in events)
    assert any(event_type == "gate_pending" and payload["gate_id"] == "gate-1" for event_type, payload in events)
    assert any(
        event_type == "narration"
        and payload["agent"] == "MARVIN"
        and payload["intent"] == "Human review needed: Manager review of research claims"
        for event_type, payload in events
    )
    assert current_agent is None
    assert current_phase == "research_done"
    assert is_interrupt is True


@pytest.mark.asyncio
async def test_emit_for_update_humanizes_gate_type_fallback():
    chunks, _, _, _ = await _emit_for_update(
        {
            "__interrupt__": (
                SimpleNamespace(
                    value={
                        "gate_id": "gate-1",
                        "gate_type": "manager_review",
                        "title": "",
                    }
                ),
            )
        },
        None,
        "research_done",
        {},
    )

    events = _events(chunks)

    assert any(
        event_type == "narration"
        and payload["agent"] == "MARVIN"
        and payload["intent"] == "Human review needed: manager review"
        for event_type, payload in events
    )


@pytest.mark.asyncio
async def test_emit_for_update_narrates_phase_blocked():
    chunks, _, _, _ = await _emit_for_update(
        {
            "gate": {
                "phase_blocked": {
                    "gate_id": "gate-1",
                    "gate_type": "final_review",
                    "missing_material": ["merlin_verdict"],
                }
            }
        },
        None,
        "synthesis_done",
        {},
    )

    events = _events(chunks)

    assert any(event_type == "phase_blocked" for event_type, _ in events)
    assert any(
        event_type == "narration"
        and payload["agent"] == "MARVIN"
        and payload["intent"] == "Review material is still being prepared."
        for event_type, payload in events
    )


@pytest.mark.asyncio
async def test_emit_for_update_humanizes_deliverable_writing_blocker():
    chunks, _, _, _ = await _emit_for_update(
        {
            "gate": {
                "phase_blocked": {
                    "gate_id": "gate-1",
                    "gate_type": "manager_review",
                    "missing_material": ["deliverable_writing_in_progress"],
                }
            }
        },
        None,
        "research_done",
        {},
    )

    events = _events(chunks)

    assert any(
        event_type == "narration"
        and payload["agent"] == "MARVIN"
        and payload["intent"] == "Deliverable writing in progress."
        for event_type, payload in events
    )
