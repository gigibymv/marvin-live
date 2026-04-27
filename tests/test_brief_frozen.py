"""Bug 2 regression tests: mission brief is frozen once set; subsequent
messages route to clarification_answers, not into the brief field."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marvin.graph.subgraphs import framing_orchestrator as fo
from marvin.mission.schema import Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools


@pytest.fixture
def graph_store(monkeypatch):
    store = MissionStore(":memory:")
    store.save_mission(
        Mission(
            id="m-test",
            client="Client",
            target="Target",
            ic_question="Is this attractive?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-test", store)
    monkeypatch.setattr(fo, "MissionStore", lambda: store)
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: store)
    yield store
    store.close()


def test_brief_set_once_then_frozen(graph_store):
    original = (
        "Mistral AI — European LLM provider, ~$1Bn ARR. IC question: is the "
        "moat defensible against open-weight commoditization?"
    )
    fo._persist_brief_with_history("m-test", original)
    brief = graph_store.get_mission_brief("m-test")
    assert brief is not None
    assert "Mistral AI" in brief.raw_brief

    # Second call with different text MUST NOT overwrite raw_brief.
    fo._persist_brief_with_history("m-test", "but aren't we at the memo stage?")
    brief = graph_store.get_mission_brief("m-test")
    assert "Mistral AI" in brief.raw_brief
    assert "memo stage" not in brief.raw_brief


def test_clarification_goes_to_clarification_answers(graph_store):
    fo._persist_brief_with_history(
        "m-test",
        "Substantive original brief about Target — moat, growth, exit horizon.",
    )

    fo._persist_brief_with_history("m-test", "Time horizon: 5 years.")
    fo._persist_brief_with_history("m-test", "Buyer type: financial fund.")

    answers = graph_store.get_clarification_state("m-test")["answers"]
    assert "Time horizon: 5 years." in answers
    assert "Buyer type: financial fund." in answers

    # Brief still original
    brief = graph_store.get_mission_brief("m-test")
    assert "moat" in brief.raw_brief
    assert "Time horizon" not in brief.raw_brief


def test_persist_framing_refuses_overwrite(graph_store):
    """Direct call to persist_framing_from_brief with conflicting text is
    a no-op on raw_brief and logs a warning."""
    mission_tools.persist_framing_from_brief(
        "m-test",
        "Original substantive brief about Target.",
    )
    brief = graph_store.get_mission_brief("m-test")
    original_raw = brief.raw_brief

    # Call again with conflicting text
    result = mission_tools.persist_framing_from_brief(
        "m-test", "completely different replacement text"
    )
    assert result.raw_brief == original_raw
    refreshed = graph_store.get_mission_brief("m-test")
    assert refreshed.raw_brief == original_raw


def test_persist_framing_idempotent_with_same_text(graph_store):
    mission_tools.persist_framing_from_brief("m-test", "Substantive Target brief.")
    mission_tools.persist_framing_from_brief("m-test", "Substantive Target brief.")
    brief = graph_store.get_mission_brief("m-test")
    assert "Substantive Target brief" in brief.raw_brief
