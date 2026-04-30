"""C-CONV — mid-mission steering classifier + queue + apply tests."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langchain_core.messages import HumanMessage

from marvin.conversational.steering import (
    apply_pending_steering,
    classify_message,
    queue_steering,
)
from marvin.mission.schema import Mission
from marvin.mission.store import MissionStore


@pytest.fixture
def store(tmp_path, monkeypatch) -> MissionStore:
    db = tmp_path / "marvin.db"
    s = MissionStore(db_path=str(db))
    s.save_mission(
        Mission(
            id="m-conv",
            client="C",
            target="T",
            mission_type="cdd",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        )
    )
    # Force MissionStore() default-constructed instances inside the steering
    # module to land on this same DB.
    monkeypatch.setattr(
        "marvin.conversational.steering.MissionStore",
        lambda: s,
    )
    yield s
    s._conn.close()


# ---------------------------------------------------------------------------
# classify_message
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "what is the unit economics?",
        "Why did Calculus skip QoE",
        "tell me what hypotheses are active",
        "is there a data room?",
        "qu'est-ce qui se passe avec H2",
        "explique pourquoi H1 est weakest link",
    ],
)
def test_classify_qa_questions(text):
    assert classify_message(text) == "qa"


@pytest.mark.parametrize(
    "text",
    [
        "Focus on retention cohorts for H2",
        "Skip the regulatory hypothesis, no time",
        "Add a check on AWS dependency risk",
        "ignore the founder background angle",
        "make sure to source FY2024 revenue from the 10-K",
        "Concentre-toi sur les cohortes de retention",
        "Ajoute un finding sur les marges brutes",
        "Ignore le risque réglementaire pour cette passe",
    ],
)
def test_classify_steer_instructions(text):
    assert classify_message(text) == "steer"


def test_classify_empty_returns_qa():
    assert classify_message("") == "qa"
    assert classify_message("   ") == "qa"


# ---------------------------------------------------------------------------
# queue_steering + apply_pending_steering
# ---------------------------------------------------------------------------

def test_queue_and_apply_drains_pending(store):
    queue_steering("m-conv", "Focus on retention cohorts for H2.")
    queue_steering("m-conv", "Add an AWS concentration check.")

    # First call drains both rows and returns them as HumanMessage tape.
    extra = apply_pending_steering("m-conv")
    assert len(extra) == 2
    assert all(isinstance(m, HumanMessage) for m in extra)
    assert "user steering" in extra[0].content
    assert "Focus on retention" in extra[0].content
    assert "AWS concentration" in extra[1].content

    # Second call returns nothing — rows were marked consumed.
    assert apply_pending_steering("m-conv") == []


def test_apply_with_empty_mission_id_returns_empty():
    assert apply_pending_steering("") == []


def test_queue_persists_then_consumes(store):
    sid = queue_steering("m-conv", "Skip W2.3 entirely.")
    pending = store.list_pending_steering("m-conv")
    assert len(pending) == 1 and pending[0]["id"] == sid

    apply_pending_steering("m-conv")
    pending_after = store.list_pending_steering("m-conv")
    assert pending_after == []


def test_blank_instruction_is_silently_consumed(store):
    # Bypass the classifier and write a whitespace row directly.
    store.add_steering("m-conv", "   ")
    extra = apply_pending_steering("m-conv")
    assert extra == []
    # Row is consumed even though we surfaced nothing.
    assert store.list_pending_steering("m-conv") == []
