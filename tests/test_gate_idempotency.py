"""Bug 4 (chantier 2.6) regression tests: gate validation idempotency.

Double-clicking Approve must NOT throw 409. Mismatched verdict on a
finalised gate returns a structured 200 conflict so the UI can show a
toast instead of dumping a console error.
"""
from __future__ import annotations

import asyncio
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
            id="m-idem",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-idem", s)
    monkeypatch.setattr(srv, "get_store", lambda: s)
    yield s
    srv._gate_decisions_in_flight.clear()
    srv._gate_decision_by_mission.clear()
    s.close()


def _close_g1_as(store: MissionStore, status: str, notes: str = "ok") -> None:
    store.update_gate_status("gate-m-idem-G1", status, notes=notes)


def test_double_click_same_verdict_returns_idempotent_200(store: MissionStore):
    _close_g1_as(store, "completed")
    response = asyncio.run(
        srv.validate_gate(
            "m-idem",
            "gate-m-idem-G1",
            srv.GateValidateRequest(verdict="APPROVED", notes=""),
        )
    )
    assert response.status == "already_processed"
    assert response.idempotent is True
    assert response.conflict is False


def test_change_verdict_after_complete_returns_conflict_200(store: MissionStore):
    _close_g1_as(store, "completed", notes="approved")
    response = asyncio.run(
        srv.validate_gate(
            "m-idem",
            "gate-m-idem-G1",
            srv.GateValidateRequest(verdict="REJECTED", notes="changed mind"),
        )
    )
    assert response.status == "conflict"
    assert response.conflict is True
    assert "already completed" in response.message


def test_change_verdict_after_failed_returns_conflict_200(store: MissionStore):
    _close_g1_as(store, "failed", notes="rejected")
    response = asyncio.run(
        srv.validate_gate(
            "m-idem",
            "gate-m-idem-G1",
            srv.GateValidateRequest(verdict="APPROVED", notes="changed mind"),
        )
    )
    assert response.status == "conflict"
    assert response.conflict is True


def test_genuine_invalid_verdict_returns_400(store: MissionStore):
    """Bad verdict string is still a 400, not a conflict — that's a real
    client error, not an idempotency case."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            srv.validate_gate(
                "m-idem",
                "gate-m-idem-G1",
                srv.GateValidateRequest(verdict="MAYBE", notes=""),
            )
        )
    assert exc.value.status_code == 400
