"""Regression: validate_gate detached path must NOT pre-write gate.status.

Bug recap: when no live SSE consumer is parked, validate_gate used to call
store.update_gate_status(gate_id, "completed") *before* spawning the detached
resume driver. On replay, gate_node re-fetched the gate, saw status!='pending',
took the missing-material early-exit branch (gate_material.py:229), and
terminated the graph at phase=idle without consuming the resume verdict.

The fix removes that pre-write. gate_node owns the status write at gates.py:141,
which runs only AFTER interrupt() returns the verdict.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin.mission.schema import Hypothesis, Mission, MissionBrief
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin_ui import server as srv


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    srv._gate_decisions_in_flight.clear()
    srv._gate_decision_by_mission.clear()
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-pre-write",
            client="C",
            target="T",
            ic_question="Will X be profitable?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-pre-write", s)
    s.save_mission_brief(
        MissionBrief(
            mission_id="m-pre-write",
            raw_brief="raw",
            ic_question="Will X be profitable?",
            mission_angle="angle",
            brief_summary="summary text",
            workstream_plan_json=json.dumps([{"id": "W1"}]),
        )
    )
    s.save_hypothesis(
        Hypothesis(
            id="hyp-aaa",
            mission_id="m-pre-write",
            text="Hypothesis A about profitability.",
            status="active",
        )
    )
    monkeypatch.setattr(srv, "get_store", lambda: s)
    yield s
    srv._gate_decisions_in_flight.clear()
    srv._gate_decision_by_mission.clear()
    s.close()


def test_detached_path_does_not_pre_write_gate_status(
    store: MissionStore, monkeypatch: pytest.MonkeyPatch
):
    """When no SSE consumer is parked and verdict is APPROVED, validate_gate
    must spawn the detached driver WITHOUT marking the gate completed first.
    gate_node owns the write — pre-writing causes the replay to terminate."""
    gate_id = "gate-m-pre-write-hyp-confirm"

    # No live SSE: _deliver_resume returns False.
    monkeypatch.setattr(srv, "_deliver_resume", lambda *a, **kw: False)

    spawned: list[dict] = []

    def fake_spawn(mission_id: str, payload: dict) -> str:
        # Snapshot the gate row at the EXACT moment the detached driver
        # would start. Must still be "pending" so gate_node's replay reaches
        # interrupt() and consumes the verdict.
        snap = next(
            g for g in store.list_gates(mission_id) if g.id == gate_id
        )
        spawned.append({"status_at_spawn": snap.status, "payload": payload})
        return "spawned"

    monkeypatch.setattr(srv, "_spawn_detached_resume", fake_spawn)

    response = asyncio.run(
        srv.validate_gate(
            "m-pre-write",
            gate_id,
            srv.GateValidateRequest(verdict="APPROVED", notes="ok"),
        )
    )

    assert response.status == "resumed_detached"
    assert len(spawned) == 1
    assert spawned[0]["status_at_spawn"] == "pending", (
        "validate_gate pre-wrote gate.status before the detached driver ran — "
        "this is the bug. gate_node owns this write."
    )
    assert spawned[0]["payload"]["approved"] is True
    assert spawned[0]["payload"]["verdict"] == "APPROVED"
    assert spawned[0]["payload"]["gate_id"] == gate_id

    # And after validate_gate returns, the row is still pending in the DB.
    final = next(g for g in store.list_gates("m-pre-write") if g.id == gate_id)
    assert final.status == "pending", (
        "Gate status was written by validate_gate. The detached driver's "
        "replay of gate_node will now take the early-exit branch and freeze "
        "the graph."
    )
