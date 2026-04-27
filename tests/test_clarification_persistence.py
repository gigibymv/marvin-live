"""Regression tests for Chantier 2 D2 — clarification state must live in
the DB so it survives a process restart, not in module-level memory."""
from __future__ import annotations

import importlib
import os
import tempfile

import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("MARVIN_DB_PATH", path)
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _seed_mission(store, mid: str = "m-clarif"):
    from marvin.mission.schema import Mission

    store.save_mission(Mission(id=mid, client="c", target="t"))
    return mid


def test_clarification_state_starts_empty(fresh_db):
    from marvin.mission.store import MissionStore

    store = MissionStore()
    mid = _seed_mission(store)
    state = store.get_clarification_state(mid)
    assert state == {"rounds": 0, "answers": []}


def test_increment_and_append_persist_to_db(fresh_db):
    from marvin.mission.store import MissionStore

    store = MissionStore()
    mid = _seed_mission(store)
    assert store.increment_clarification_rounds(mid) == 1
    store.append_clarification_answer(mid, "horizon: 5y")
    assert store.increment_clarification_rounds(mid) == 2
    store.append_clarification_answer(mid, "buyer: strategic")

    # Simulate a process restart: drop and re-open the store object.
    store.close()
    store2 = MissionStore()
    state = store2.get_clarification_state(mid)
    assert state["rounds"] == 2
    assert state["answers"] == ["horizon: 5y", "buyer: strategic"]


def test_reset_clarification_state_zeros_db_columns(fresh_db):
    from marvin.mission.store import MissionStore

    store = MissionStore()
    mid = _seed_mission(store)
    store.increment_clarification_rounds(mid)
    store.append_clarification_answer(mid, "answer")
    store.reset_clarification_state(mid)
    assert store.get_clarification_state(mid) == {"rounds": 0, "answers": []}


def test_save_mission_does_not_clobber_clarification_state(fresh_db):
    """Re-saving a mission row must preserve the clarification columns
    rather than reset them to defaults via INSERT OR REPLACE."""
    from marvin.mission.store import MissionStore

    store = MissionStore()
    mid = _seed_mission(store)
    store.increment_clarification_rounds(mid)
    store.append_clarification_answer(mid, "answer")

    # Read, modify a different field, save back.
    mission = store.get_mission(mid)
    assert mission.clarification_rounds_used == 1
    assert mission.clarification_answers == ["answer"]
    store.save_mission(mission.model_copy(update={"target": "new-target"}))

    state = store.get_clarification_state(mid)
    assert state["rounds"] == 1
    assert state["answers"] == ["answer"]


def test_gate_questions_round_trip(fresh_db):
    """Gate.questions must survive save/list as a real list, not JSON text."""
    from marvin.mission.schema import Gate
    from marvin.mission.store import MissionStore

    store = MissionStore()
    mid = _seed_mission(store)
    store.save_gate(
        Gate(
            id="gate-x",
            mission_id=mid,
            gate_type="clarification_request",
            scheduled_day=0,
            format="clarification_questions",
            questions=["Time horizon?", "Buyer type?"],
        )
    )
    [g] = [g for g in store.list_gates(mid) if g.id == "gate-x"]
    assert g.questions == ["Time horizon?", "Buyer type?"]
    assert g.format == "clarification_questions"


def test_framing_orchestrator_helpers_use_db(fresh_db):
    """The framing_orchestrator module's get_clarification_rounds /
    get_clarification_answers helpers must read from the DB, not from a
    module-level dict."""
    # Re-import after env var is set so any module caches see the new DB.
    import marvin.graph.subgraphs.framing_orchestrator as fo

    importlib.reload(fo)

    from marvin.mission.store import MissionStore

    store = MissionStore()
    mid = _seed_mission(store)
    store.increment_clarification_rounds(mid)
    store.append_clarification_answer(mid, "horizon: 5y")

    assert fo.get_clarification_rounds(mid) == 1
    assert fo.get_clarification_answers(mid) == ["horizon: 5y"]

    fo.reset_clarification_state(mid)
    assert fo.get_clarification_rounds(mid) == 0
    assert fo.get_clarification_answers(mid) == []

    # Confirm no module-level dict still exists carrying state.
    assert not hasattr(fo, "_CLARIFICATION_ROUNDS") or not getattr(fo, "_CLARIFICATION_ROUNDS")
    assert not hasattr(fo, "_CLARIFICATION_ANSWERS") or not getattr(fo, "_CLARIFICATION_ANSWERS")
