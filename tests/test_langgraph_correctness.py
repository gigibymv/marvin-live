"""LangGraph correctness regression tests.

Covers the five issues audited in 2026-04-30:
  1. phase_router edge functions are pure (no DB writes)
  2. framing_orchestrator route map covers gate_entry
  3. research_rebuttal surfaces agent failures (error-level log + milestone block)
  4. data-availability fan-out routes via gate_entry (not Send directly to gate)
  5. lifespan closes _checkpoint_conn on shutdown
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from marvin.graph import runner
from marvin.graph.runner import phase_router, gate_entry_node, research_rebuttal_node
from marvin.mission.schema import Mission, Hypothesis
from marvin.mission.store import MissionStore, _seed_standard_workplan


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def store(monkeypatch):
    s = MissionStore(":memory:")
    monkeypatch.setattr(runner, "MissionStore", lambda *a, **kw: s)
    yield s
    s.close()


def _make_mission(store, mission_id: str, target: str = "Microsoft"):
    store.save_mission(
        Mission(
            id=mission_id,
            client="Client",
            target=target,
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan(mission_id, store)
    store.save_hypothesis(
        Hypothesis(
            id="hyp-1",
            mission_id=mission_id,
            text="H1 hypothesis",
            label="H1",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )


# ---------------------------------------------------------------------------
# Issue 1 — phase_router must be a pure edge function (no DB writes)
# ---------------------------------------------------------------------------

class TestPhaseRouterPurity:
    """phase_router is a LangGraph conditional edge function.

    Under AsyncSqliteSaver, conditional edges can be re-fired on checkpoint
    replay. Any DB write inside phase_router would therefore execute twice,
    producing duplicate rows. The write must live in the node that precedes
    the conditional edge (gate_entry_node for gate-triggering phases).
    """

    def test_private_target_returns_string_not_send(self, store):
        """phase_router('confirmed', private target, no data_decision) must
        return the string 'gate_entry', not a Send or list."""
        from langgraph.types import Send

        _make_mission(store, "m-pure", "Mistral AI")
        state = {"mission_id": "m-pure", "phase": "confirmed", "messages": []}

        result = phase_router(state)

        assert result == "gate_entry", (
            f"phase_router returned {result!r}; must return 'gate_entry' — "
            "edge functions must be pure (no DB writes, no direct Send to gate)"
        )

    def test_no_gate_row_created_by_phase_router(self, store):
        """phase_router must not create any DB rows (gate write belongs in gate_entry_node)."""
        _make_mission(store, "m-pure2", "Mistral AI")
        state = {"mission_id": "m-pure2", "phase": "confirmed", "messages": []}

        gates_before = len(store.list_gates("m-pure2"))
        phase_router(state)
        gates_after = len(store.list_gates("m-pure2"))

        assert gates_after == gates_before, (
            f"phase_router created {gates_after - gates_before} gate row(s); "
            "edge functions must be pure"
        )

    def test_gate_entry_node_creates_gate_row_idempotently(self, store):
        """gate_entry_node is the correct home for gate row creation.
        It must be idempotent (calling it twice produces exactly one row)."""
        _make_mission(store, "m-idempotent", "Mistral AI")
        state = {"mission_id": "m-idempotent", "phase": "confirmed", "messages": []}

        asyncio.run(gate_entry_node(state))
        asyncio.run(gate_entry_node(state))  # second call — must not duplicate

        da_gates = [g for g in store.list_gates("m-idempotent") if g.gate_type == "data_availability"]
        assert len(da_gates) == 1, (
            f"Expected exactly 1 data-availability gate row; got {len(da_gates)}"
        )

    def test_gate_entry_node_sets_phase_and_pending_gate_id(self, store):
        """gate_entry_node must return pending_gate_id and advance phase."""
        _make_mission(store, "m-entry", "Mistral AI")
        state = {"mission_id": "m-entry", "phase": "confirmed", "messages": []}

        result = asyncio.run(gate_entry_node(state))

        assert result.get("pending_gate_id", "").endswith("-data-availability")
        assert result.get("phase") == "awaiting_data_decision"


# ---------------------------------------------------------------------------
# Issue 2 — framing_orchestrator route map covers gate_entry
# ---------------------------------------------------------------------------

class TestFramingOrchestratorRouteMap:
    """framing_orchestrator can return phase='awaiting_clarification' which
    routes through gate_entry (CLAUDE.md §4). If gate_entry is absent from
    the compiled outgoing edge map, the graph raises KeyError at runtime."""

    def test_compiled_graph_framing_orchestrator_includes_gate_entry(self):
        graph = runner.build_graph()
        edges = {(e.source, e.target) for e in graph.get_graph().edges}
        # gate_entry must be reachable from framing_orchestrator
        fo_targets = {t for s, t in edges if s == "framing_orchestrator"}
        assert "gate_entry" in fo_targets, (
            f"framing_orchestrator has no edge to gate_entry; "
            f"targets={fo_targets!r}"
        )

    def test_phase_router_awaiting_clarification_returns_gate_entry(self):
        result = phase_router({"phase": "awaiting_clarification", "mission_id": "m-x", "messages": []})
        assert result == "gate_entry", (
            f"awaiting_clarification routed to {result!r}; must go through gate_entry"
        )

    def test_framing_orchestrator_route_map_covers_all_phases(self):
        """Every phase value framing_orchestrator can produce must be present
        in its compiled conditional edge map so no KeyError occurs at runtime."""
        graph = runner.build_graph()
        edges = {(e.source, e.target) for e in graph.get_graph().edges}
        fo_targets = {t for s, t in edges if s == "framing_orchestrator"}

        # Phases framing_orchestrator can return (per framing_orchestrator_node)
        # map to these route keys in phase_router:
        required_targets = {"framing", "framing_orchestrator", "gate_entry"}
        missing = required_targets - fo_targets
        assert not missing, (
            f"framing_orchestrator edge map is missing targets: {missing!r}"
        )


# ---------------------------------------------------------------------------
# Issue 3 — research_rebuttal surfaces agent failures
# ---------------------------------------------------------------------------

class TestRebuttalSurfacesFailures:
    """research_rebuttal_node must log at ERROR level and persist a visible
    diagnostic when calculus or dora fail. Silently swallowing the exception
    (warning-level only, no state update) hides real problems from the UI."""

    @pytest.fixture
    def rebuttal_store(self, monkeypatch, tmp_path):
        import marvin.graph.runner as r
        import marvin.tools.mission_tools as mt
        s = MissionStore(":memory:")
        s.save_mission(Mission(id="m-reb", client="c", target="t", ic_question="q?", status="active"))
        _seed_standard_workplan("m-reb", s)
        monkeypatch.setattr(r, "MissionStore", lambda *a, **kw: s)
        # recompute_mission_corroboration is imported lazily inside the node;
        # patch it at the source module so the lazy import picks up the stub.
        monkeypatch.setattr(mt, "recompute_mission_corroboration", lambda **kw: None)
        yield s
        s.close()

    def test_calculus_failure_logged_at_error(self, rebuttal_store, monkeypatch, caplog):
        import marvin.graph.runner as r
        from marvin.mission.schema import Finding

        # Seed an adversus finding so the node doesn't short-circuit.
        rebuttal_store.save_finding(Finding(
            id="f-atk",
            mission_id="m-reb",
            claim_text="ANOMALY: load_bearing attack",
            confidence="REASONED",
            agent_id="adversus",
            impact="load_bearing",
            created_at=datetime.now(UTC).isoformat(),
        ))

        async def _boom(state):
            raise RuntimeError("calculus exploded")

        async def _ok(state):
            return state

        monkeypatch.setattr(r, "calculus_agent_node", _boom)
        monkeypatch.setattr(r, "dora_agent_node", _ok)

        with caplog.at_level(logging.ERROR, logger="marvin.graph.runner"):
            result = asyncio.run(r.research_rebuttal_node({"mission_id": "m-reb", "messages": []}))

        assert result["phase"] == "rebuttal_done", "Node must not raise; returns rebuttal_done"
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, (
            "calculus failure must be logged at ERROR level, not just WARNING"
        )

    def test_dora_failure_logged_at_error(self, rebuttal_store, monkeypatch, caplog):
        import marvin.graph.runner as r
        from marvin.mission.schema import Finding

        rebuttal_store.save_finding(Finding(
            id="f-atk2",
            mission_id="m-reb",
            claim_text="contradicts management claim",
            confidence="REASONED",
            agent_id="adversus",
            impact="supporting",
            created_at=datetime.now(UTC).isoformat(),
        ))

        async def _ok(state):
            return state

        async def _boom(state):
            raise RuntimeError("dora exploded")

        monkeypatch.setattr(r, "calculus_agent_node", _ok)
        monkeypatch.setattr(r, "dora_agent_node", _boom)

        with caplog.at_level(logging.ERROR, logger="marvin.graph.runner"):
            result = asyncio.run(r.research_rebuttal_node({"mission_id": "m-reb", "messages": []}))

        assert result["phase"] == "rebuttal_done"
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "dora failure must be logged at ERROR level"


# ---------------------------------------------------------------------------
# Issue 4 — data-availability fan-out routes via gate_entry
# ---------------------------------------------------------------------------

class TestDataAvailabilityViaGateEntry:
    """phase_router must not Send directly to gate for the data-availability
    path. Per CLAUDE.md §4, every gate-triggering phase must pass through
    gate_entry first."""

    def test_confirmed_private_target_routes_to_gate_entry_not_gate(self, store):
        from langgraph.types import Send

        _make_mission(store, "m-da", "Mistral AI")
        state = {"mission_id": "m-da", "phase": "confirmed", "messages": []}

        result = phase_router(state)

        assert not isinstance(result, list), (
            "phase_router must not return a Send list for the data-availability path; "
            "it must return 'gate_entry'"
        )
        assert result == "gate_entry"

    def test_compiled_graph_gate_has_edge_to_gate_entry(self):
        """gate node's conditional edge map must include gate_entry so
        confirmed-phase replays can re-enter the gate path."""
        graph = runner.build_graph()
        edges = {(e.source, e.target) for e in graph.get_graph().edges}
        gate_targets = {t for s, t in edges if s == "gate"}
        assert "gate_entry" in gate_targets, (
            f"gate node has no edge to gate_entry; targets={gate_targets!r}"
        )


# ---------------------------------------------------------------------------
# Issue 5 — lifespan closes _checkpoint_conn
# ---------------------------------------------------------------------------

class TestLifespanClosesCheckpoint:
    """On shutdown, the lifespan handler must close the aiosqlite connection
    so the SQLite WAL is properly flushed and the file is not left locked."""

    def test_lifespan_closes_connection_on_shutdown(self, monkeypatch):
        import asyncio

        import marvin_ui.server as srv

        closed: list[bool] = []

        class FakeConn:
            async def close(self):
                closed.append(True)

        # Inject a fake connection into the module global.
        monkeypatch.setattr(srv, "_checkpoint_conn", FakeConn())

        async def _fake_get_graph():
            return None

        # Re-run the lifespan generator through startup + shutdown.
        async def _run():
            from fastapi import FastAPI
            app = FastAPI()
            # Patch get_graph so lifespan doesn't actually build a graph.
            monkeypatch.setattr(srv, "get_graph", _fake_get_graph)
            async with srv.lifespan(app):
                pass  # simulates shutdown after yield

        asyncio.run(_run())

        assert closed, "lifespan must call _checkpoint_conn.close() on shutdown"
