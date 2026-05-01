"""Regression: gate rejection must re-trigger the right path, not freeze.

Live missions reported "Gate rejected. Awaiting further instructions." with
no recovery. The contract is now:
  - G0 (hypothesis_confirmation) reject → phase=framing → re-run framing
  - G1 (manager_review) reject → phase=confirmed → re-fan-out research
  - G3 (final_review) reject → phase=redteam_done → re-run merlin
And in every case a fresh pending gate row is seeded so the retry pass has
somewhere to land (the original row stays "failed" for audit).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from marvin.graph import gates, runner
from marvin.mission.schema import Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import arbiter_tools, mission_tools, papyrus_tools


@pytest.fixture
def graph_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
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
    monkeypatch.setattr(runner, "MissionStore", lambda: store)
    monkeypatch.setattr(gates, "MissionStore", lambda: store)
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: store)
    monkeypatch.setattr(papyrus_tools, "_STORE_FACTORY", lambda: store)
    monkeypatch.setattr(arbiter_tools, "_STORE_FACTORY", lambda: store)
    yield store
    store.close()


def _gate(store: MissionStore, gate_id: str):
    return next(g for g in store.list_gates("m-test") if g.id == gate_id)


def test_g1_reject_seeds_retry_gate_and_routes_to_confirmed(
    graph_store: MissionStore, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(gates, "interrupt", lambda payload: {"approved": False, "notes": "claims weak"})
    # Seed a finding so material is "ready" for the manager_review gate.
    from marvin.mission.schema import Deliverable, Finding

    graph_store.save_finding(
        Finding(
            id="f-1",
            mission_id="m-test",
            claim_text="Market large",
            confidence="REASONED",
            agent_id="dora",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    # Stricter manager_review gate (Phase A) requires ALL W1+W2 milestones in
    # terminal state before opening — seed them all so gate_node treats the
    # gate as truly pending and runs the reject path.
    for mid in ("W1.1", "W1.2", "W1.3", "W2.1", "W2.2", "W2.3"):
        graph_store.mark_milestone_delivered(mid, "Research complete", "m-test")
    # P16 fix: gate also requires a `ready` deliverable per research workstream.
    for ws_id, d_id in (("W1", "d-w1-reject"), ("W2", "d-w2-reject")):
        graph_store.save_deliverable(
            Deliverable(
                id=d_id,
                mission_id="m-test",
                deliverable_type="workstream_report",
                status="ready",
                workstream_id=ws_id,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
    result = asyncio.run(
        gates.gate_node({"mission_id": "m-test", "pending_gate_id": "gate-m-test-G1"})
    )

    assert result["phase"] == "confirmed", "G1 reject must route to confirmed for re-fan-out"
    assert result["gate_passed"] is False
    # Original gate is failed (audit)
    assert _gate(graph_store, "gate-m-test-G1").status == "failed"
    # New retry row created and pending
    retry_gates = [g for g in graph_store.list_gates("m-test") if "gate-m-test-G1-retry-" in g.id]
    assert len(retry_gates) == 1
    assert retry_gates[0].status == "pending"
    assert retry_gates[0].scheduled_day == _gate(graph_store, "gate-m-test-G1").scheduled_day
    # Specific re-run message in chat (no "Awaiting further instructions")
    msgs = result.get("messages") or []
    assert any(isinstance(m, AIMessage) and "G1 will fire again" in m.content for m in msgs)
    assert not any("awaiting further instructions" in (getattr(m, "content", "") or "").lower() for m in msgs)


def test_g3_reject_routes_to_redteam_done_and_seeds_retry(
    graph_store: MissionStore, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(gates, "interrupt", lambda payload: {"approved": False, "notes": "thesis weak"})
    # G3 evaluate_gate_material requires a verdict; it would refuse to interrupt
    # without one, so seed one.
    from marvin.mission.schema import Finding, MerlinVerdict

    graph_store.save_finding(
        Finding(
            id="f-rt-1",
            mission_id="m-test",
            claim_text="Risk: regulation",
            confidence="REASONED",
            agent_id="adversus",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    graph_store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-1",
            mission_id="m-test",
            verdict="MINOR_FIXES",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    g1_id = next(g.id for g in graph_store.list_gates("m-test") if g.gate_type == "manager_review")
    graph_store.update_gate_status(g1_id, "completed", "approved-for-test")
    g3_id = next(g.id for g in graph_store.list_gates("m-test") if g.scheduled_day == 10)
    result = asyncio.run(
        gates.gate_node({"mission_id": "m-test", "pending_gate_id": g3_id})
    )

    assert result["phase"] == "redteam_done"
    assert _gate(graph_store, g3_id).status == "failed"
    retry = [g for g in graph_store.list_gates("m-test") if g.id.startswith(f"{g3_id}-retry-")]
    assert len(retry) == 1 and retry[0].status == "pending"
    msgs = result.get("messages") or []
    assert any("Merlin will re-run" in (getattr(m, "content", "") or "") for m in msgs)


def test_resolve_gate_by_day_prefers_pending_retry(graph_store: MissionStore):
    # Mark the original G1 as failed and create a retry row.
    graph_store.update_gate_status("gate-m-test-G1", "failed", notes="rejected")
    from marvin.mission.schema import Gate

    graph_store.save_gate(
        Gate(
            id="gate-m-test-G1-retry-1",
            mission_id="m-test",
            gate_type="manager_review",
            scheduled_day=3,
            status="pending",
        )
    )
    # _resolve_gate_by_day must return the pending retry, not the failed original
    assert runner._resolve_gate_by_day("m-test", 3) == "gate-m-test-G1-retry-1"


def test_g0_reject_still_routes_to_framing(
    graph_store: MissionStore, monkeypatch: pytest.MonkeyPatch
):
    """Hypothesis-confirmation reject keeps existing framing-loop behavior."""
    from marvin.mission.schema import Hypothesis, MissionBrief

    graph_store.save_mission_brief(
        MissionBrief(
            mission_id="m-test",
            raw_brief="A brief.",
            ic_question="Should we invest?",
            mission_angle="growth",
            brief_summary="A summary.",
            workstream_plan_json="[]",
        )
    )
    graph_store.save_hypothesis(
        Hypothesis(
            id="hyp-1",
            mission_id="m-test",
            text="H1",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(gates, "interrupt", lambda payload: {"approved": False, "notes": "redo"})
    g0_id = next(g.id for g in graph_store.list_gates("m-test") if g.gate_type == "hypothesis_confirmation")
    result = asyncio.run(
        gates.gate_node({"mission_id": "m-test", "pending_gate_id": g0_id})
    )
    assert result["phase"] == "framing"
    # Retry row seeded so awaiting_confirmation can resolve a pending hyp-confirm gate
    retry = [g for g in graph_store.list_gates("m-test") if g.id.startswith(f"{g0_id}-retry-")]
    assert len(retry) == 1 and retry[0].status == "pending"
    msgs = result.get("messages") or []
    assert any("Re-running framing" in (getattr(m, "content", "") or "") for m in msgs)
