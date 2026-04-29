"""Wiring test for fix A: detached driver must consume the gate interrupt.

Scenario: validate_gate is called when the graph is *not yet* parked at the
target gate (chat stream cancelled mid-framing). The driver must drive the
graph forward, observe the gate park, feed the resume payload, and let
gate_node persist gate.status="completed".

Pre-fix: driver yielded one event then exited, gate stayed pending.
Post-fix: driver loops, recognizes the target gate's interrupt, re-feeds
Command(resume=...), gate transitions to completed.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_detached_driver_consumes_interrupt_when_gate_parks_after_validate(
    tmp_path, monkeypatch
):
    # Use isolated DBs and force memory checkpointer so the test is hermetic.
    db_path = tmp_path / "marvin.db"
    monkeypatch.setenv("MARVIN_DB_PATH", str(db_path))
    monkeypatch.setenv("MARVIN_CHECKPOINT_BACKEND", "memory")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")  # framing path may early-exit without a key

    # Re-import so the env vars take effect on module-level singletons.
    import importlib
    import marvin.mission.store as store_mod
    importlib.reload(store_mod)
    from marvin.mission.store import MissionStore
    from marvin.mission.schema import Mission as MissionModel, Hypothesis, Gate
    from langgraph.types import interrupt
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import StateGraph, END
    from typing import TypedDict

    # --- Build a tiny graph that parks on interrupt() at gate ----------------
    class State(TypedDict, total=False):
        mission_id: str
        phase: str
        pending_gate_id: str
        gate_passed: bool

    GATE_ID = "gate-test-hyp-confirm"
    MID = "m-test-detached"

    framing_calls = {"n": 0}

    async def framing(state: State) -> dict:
        framing_calls["n"] += 1
        return {"phase": "awaiting_confirmation", "pending_gate_id": GATE_ID}

    async def gate(state: State) -> dict:
        decision = interrupt({"gate_id": state.get("pending_gate_id"), "title": "test"})
        approved = decision.get("verdict") == "APPROVED"
        # Persist to the store the same way real gate_node does.
        store = MissionStore(str(db_path))
        store.update_gate_status(state["pending_gate_id"], "completed" if approved else "failed")
        return {"phase": "confirmed", "gate_passed": approved, "pending_gate_id": None}

    g = StateGraph(State)
    g.add_node("framing", framing)
    g.add_node("gate", gate)
    g.set_entry_point("framing")
    g.add_edge("framing", "gate")
    g.add_edge("gate", END)
    saver = MemorySaver()
    graph = g.compile(checkpointer=saver)

    # --- Seed mission + gate row --------------------------------------------
    store = MissionStore(str(db_path))
    store.save_mission(MissionModel(
        id=MID, client="test", target="test", mission_type="cdd",
        ic_question="?", status="active",
    ))
    store.save_gate(Gate(
        id=GATE_ID, mission_id=MID, gate_type="hypothesis_confirmation",
        scheduled_day=0, status="pending", format="review_claims",
    ))

    # --- Inject our toy graph + saver into the server module ----------------
    from marvin_ui import server as srv
    monkeypatch.setattr(srv, "_graph", graph, raising=False)

    async def _fake_get_graph():
        return graph
    monkeypatch.setattr(srv, "get_graph", _fake_get_graph)

    # Suppress SSE emission side effects
    monkeypatch.setattr(srv, "emit_graph_event", lambda *a, **k: None)

    async def _noop_emit(*a, **k):
        return ""
    monkeypatch.setattr(srv, "_emit_run_start", _noop_emit)
    monkeypatch.setattr(srv, "_emit_run_end", _noop_emit)
    monkeypatch.setattr(srv, "_emit_agent_done", _noop_emit)

    async def _noop_for_update(event, agent, phase, throttle):
        return [], agent, phase, False
    monkeypatch.setattr(srv, "_emit_for_update", _noop_for_update)

    # --- Scenario: prior partial run cancelled before parking at gate -------
    # Mirror production: an SSE chat stream began the run, got cancelled
    # mid-framing, and the checkpoint reflects state.next pointing at a
    # node that hasn't yet hit the gate interrupt.
    config = {"configurable": {"thread_id": MID}}
    cancelled_before_park = False
    async for event in graph.astream(
        {"mission_id": MID, "phase": "setup"}, config, stream_mode="updates"
    ):
        if isinstance(event, dict) and "framing" in event:
            # Stop right after framing has emitted its delta but before
            # gate_node has hit interrupt() — emulates the cancelled stream.
            cancelled_before_park = True
            break
    assert cancelled_before_park

    # The gate has not been validated yet; row is still pending.
    pre = next(g for g in store.list_gates(MID) if g.id == GATE_ID)
    assert pre.status == "pending"

    resume_payload = {"approved": True, "verdict": "APPROVED", "gate_id": GATE_ID}
    await srv._drive_detached_resume(MID, resume_payload)

    # --- Assertions: driver drove framing → gate, consumed resume, completed ----
    post = next(g for g in store.list_gates(MID) if g.id == GATE_ID)
    assert post.status == "completed", (
        f"expected gate to be completed after detached resume, got {post.status}"
    )

    state = await graph.aget_state({"configurable": {"thread_id": MID}})
    assert state.values.get("phase") == "confirmed", state.values
    assert state.values.get("gate_passed") is True
    assert state.values.get("pending_gate_id") is None
    # Framing should have run at most twice (initial partial + one re-run
    # by the detached driver). The key invariant is that the gate parked
    # exactly once and the resume payload was consumed.
    assert framing_calls["n"] <= 2
