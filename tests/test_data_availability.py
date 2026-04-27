"""Bug 3 (chantier 2.6) regression tests: pre-flight data availability gate.

For private/non-US targets without a data room, the system fires a
data-availability gate AFTER hypothesis confirmation but BEFORE launching
Calculus. The user picks one of three options; phase_router routes
accordingly so we don't waste agent runs and surface absurd findings at G1.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langgraph.types import Send

from marvin.graph.runner import _check_data_availability, phase_router
from marvin.mission.schema import Hypothesis, Mission, MissionBrief
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools


@pytest.fixture
def store(monkeypatch):
    s = MissionStore(":memory:")
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: s)
    monkeypatch.setattr(
        "marvin.graph.runner.MissionStore", lambda *a, **kw: s,
    )
    monkeypatch.setattr(
        "marvin.graph.gates.MissionStore", lambda *a, **kw: s,
    )
    yield s
    s.close()


def _create_mission(store, mission_id: str, target: str, data_room_path: str | None = None):
    store.save_mission(
        Mission(
            id=mission_id,
            client="Client",
            target=target,
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
            data_room_path=data_room_path,
        )
    )
    _seed_standard_workplan(mission_id, store)
    store.save_hypothesis(
        Hypothesis(
            id="hyp-1",
            mission_id=mission_id,
            text="x",
            label="H1",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )


# --- pure check function -------------------------------------------------

def test_check_data_availability_private_target_returns_not_viable(store):
    _create_mission(store, "m-priv", "Mistral AI")
    result = _check_data_availability("m-priv")
    assert result["calculus_viable"] is False
    assert "private" in result["reason"].lower() or "non-us" in result["reason"].lower()


def test_check_data_availability_public_target_returns_viable(store):
    _create_mission(store, "m-pub", "Microsoft")
    result = _check_data_availability("m-pub")
    assert result["calculus_viable"] is True


def test_check_data_availability_with_data_room_overrides_private(store):
    _create_mission(store, "m-priv-dr", "Mistral AI", data_room_path="/tmp/dr")
    result = _check_data_availability("m-priv-dr")
    assert result["calculus_viable"] is True


# --- phase_router integration -------------------------------------------

def test_phase_router_creates_data_gate_for_private_target(store):
    _create_mission(store, "m-priv", "Mistral AI")
    state = {"mission_id": "m-priv", "phase": "confirmed", "messages": []}

    routes = phase_router(state)

    assert isinstance(routes, list)
    assert len(routes) == 1
    send = routes[0]
    assert isinstance(send, Send)
    assert send.node == "gate"
    assert send.arg["phase"] == "awaiting_data_decision"
    assert send.arg["pending_gate_id"].endswith("-data-availability")
    # Gate row was persisted
    gates = store.list_gates("m-priv")
    assert any(g.gate_type == "data_availability" for g in gates)


def test_phase_router_skips_data_check_for_public_target(store):
    _create_mission(store, "m-pub", "Microsoft")
    state = {"mission_id": "m-pub", "phase": "confirmed", "messages": []}

    routes = phase_router(state)

    assert isinstance(routes, list)
    nodes = sorted(s.node for s in routes if isinstance(s, Send))
    assert nodes == ["calculus", "dora"]


def test_phase_router_skips_calculus_after_skip_decision(store):
    _create_mission(store, "m-skip", "Mistral AI")
    state = {
        "mission_id": "m-skip",
        "phase": "confirmed",
        "messages": [],
        "data_decision": "skip_calculus",
    }

    routes = phase_router(state)

    assert isinstance(routes, list)
    nodes = [s.node for s in routes if isinstance(s, Send)]
    assert nodes == ["dora"]


def test_phase_router_runs_both_after_proceed_low_confidence(store):
    _create_mission(store, "m-proceed", "Mistral AI")
    state = {
        "mission_id": "m-proceed",
        "phase": "confirmed",
        "messages": [],
        "data_decision": "proceed_low_confidence",
    }

    routes = phase_router(state)

    nodes = sorted(s.node for s in routes if isinstance(s, Send))
    assert nodes == ["calculus", "dora"]
    # The W2 message must include the data caveat.
    calc = next(s for s in routes if s.node == "calculus")
    last_msg = calc.arg["messages"][-1].content
    assert "DATA CAVEAT" in last_msg or "LOW_CONFIDENCE" in last_msg


def test_phase_router_data_room_decision_pauses(store):
    _create_mission(store, "m-room", "Mistral AI")
    state = {
        "mission_id": "m-room",
        "phase": "awaiting_data_room",
        "messages": [],
    }
    # awaiting_data_room → END. phase_router returns END constant.
    from langgraph.graph import END as LG_END

    assert phase_router(state) == LG_END
