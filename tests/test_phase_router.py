from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from marvin.graph import gates, runner
from marvin.mission.schema import Finding, MerlinVerdict, Mission
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
    monkeypatch.setattr(papyrus_tools, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(papyrus_tools, "_papyrus_llm_generate", _stub_papyrus_llm_generate)
    yield store
    store.close()


def _stub_papyrus_llm_generate(
    deliverable_type, mission, hypotheses, findings, mission_brief=None, extra=None,
):
    """Test stub matching new-mode validation: structural markers, no IDs."""
    if deliverable_type == "engagement_brief":
        hyp_block = "\n\n".join(
            f"**H{i + 1} — {h.text[:48].rstrip('.')}**.\n\n{h.text}"
            for i, h in enumerate(hypotheses)
        )
        raw_recap = (mission_brief.raw_brief if mission_brief else "")
        return (
            f"# Engagement Brief — {mission.target}\n\n"
            f"**Client:** {mission.client}\n"
            f"**Target:** {mission.target}\n"
            f"**Date:** 2026-04-28\n\n"
            f"## IC Question\n\n{mission.ic_question}\n\n"
            f"## Context\n\n{raw_recap}\n\n"
            "This diligence frames the binding constraints on the investment "
            "thesis and sets the testable hypotheses ahead of any field research.\n\n"
            f"## Hypotheses to Test\n\n{hyp_block}\n\n"
            "## Workstream Plan\n\n"
            "- **W1 Market analysis** — Tests H1 through market evidence.\n\n"
            "## Validation Focus\n\n"
            "Gate G1 should validate that these hypotheses capture the binding "
            "risks before research begins.\n"
        )
    raise NotImplementedError(f"stub does not yet handle {deliverable_type}")


def test_phase_router_setup_routes_to_framing():
    result = runner.phase_router({"phase": "setup", "mission_id": "m-test", "messages": []})
    assert result == "framing"


def test_phase_router_framing_generates_hypotheses(graph_store: MissionStore):
    result = asyncio.run(
        runner.framing_node(
            {
                "phase": "framing",
                "mission_id": "m-test",
                "messages": [
                    HumanMessage(
                        content=(
                            "Assess pricing power, retention, and whether Target can "
                            "defend growth against larger competitors."
                        )
                    )
                ],
            }
        )
    )
    assert result["phase"] == "awaiting_confirmation"
    # Framing now goes through the framing LLM (or its deterministic fallback
    # if no API key). Both paths are contracted to produce 3 to 5 hypotheses.
    hypothesis_count = len(graph_store.list_hypotheses("m-test"))
    assert 3 <= hypothesis_count <= 5
    # framing_node must surface a conversational AIMessage so the chat is not
    # silent after the user submits a brief.
    from langchain_core.messages import AIMessage
    assert any(isinstance(msg, AIMessage) and (msg.content or "").strip() for msg in result["messages"])
    brief = graph_store.get_mission_brief("m-test")
    assert brief is not None
    assert "pricing power" in brief.raw_brief
    deliverable = graph_store.list_deliverables("m-test")[0]
    assert deliverable.deliverable_type == "engagement_brief"
    content = Path(deliverable.file_path or "").read_text(encoding="utf-8")
    # Engagement brief is now LLM-driven (Path B). Validate new structure.
    assert "## IC Question" in content
    assert "## Hypotheses to Test" in content
    assert "## Workstream Plan" in content
    # No internal database IDs leak into client-facing deliverables.
    assert "hyp-" not in content
    assert "Hypothesis ID:" not in content


def test_framing_waits_for_non_empty_human_brief(graph_store: MissionStore):
    result = asyncio.run(runner.framing_node({"phase": "framing", "mission_id": "m-test", "messages": []}))
    assert result["phase"] == "setup"
    assert graph_store.get_mission_brief("m-test") is None
    assert graph_store.list_deliverables("m-test") == []


def test_phase_router_confirmed_sends_dora_and_calculus(graph_store: MissionStore):
    mission_tools._generate_hypotheses_inline("m-test")
    result = runner.phase_router({"phase": "confirmed", "mission_id": "m-test", "messages": []})
    nodes = [send.node for send in result]
    assert "dora" in nodes
    assert "calculus" in nodes


def test_research_join_advances_unconditionally(graph_store: MissionStore):
    """research_join must advance phase deterministically — by the time it
    runs, both branches have returned, so the research milestone is done by
    architectural definition. The previous "wait for both" predicate coupled
    graph progression to LLM tool selection and produced infinite fan-out
    when a branch failed to mark its milestone. See
    tests/test_graph_progression.py for the rationale."""
    # No milestone marked yet — join must still advance.
    result = runner.research_join({"mission_id": "m-test", "phase": "confirmed"})
    assert result["phase"] == "research_done"
    milestones = {milestone.id: milestone.status for milestone in graph_store.list_milestones("m-test")}
    assert milestones["W1.1"] == "delivered"
    assert milestones["W2.1"] == "delivered"
    workstreams = {workstream.id: workstream.status for workstream in graph_store.list_workstreams("m-test")}
    assert workstreams["W1"] == "pending"
    assert workstreams["W2"] == "pending"


def test_papyrus_never_called_without_ship():
    state = {"phase": "redteam_done", "mission_id": "m-test", "messages": []}
    result = runner.phase_router(state)
    # phase_router returns string for single-node routing
    assert result != "papyrus_delivery"


def test_phase_router_synthesis_retry_routes_to_adversus():
    """When merlin's verdict is not SHIP and retry budget remains, merlin returns
    phase='synthesis_retry'. The router must route that back to adversus, NOT
    back to merlin — merlin's outgoing conditional-edge path map intentionally
    has no self-loop entry, and routing 'merlin' there raises
    `KeyError: 'merlin'` at the Pregel step. Regression test for the post-G1
    crash observed in real run m-acmeh3-20260426."""
    result = runner.phase_router({"phase": "synthesis_retry", "mission_id": "m-test", "messages": []})
    assert result == "adversus"


def test_merlin_outgoing_path_map_does_not_self_loop():
    """Document the structural invariant: merlin's compiled conditional-edge
    path map must NOT include 'merlin' as a key. If a future change adds it,
    the symptom (silent infinite self-routing) is far worse than the explicit
    KeyError we currently get; this test fails loudly so the next maintainer
    notices."""
    graph = runner.build_graph()
    edges = [(edge.source, edge.target) for edge in graph.get_graph().edges]
    merlin_targets = {target for source, target in edges if source == "merlin"}
    assert "merlin" not in merlin_targets, (
        f"merlin must not have a self-loop edge; merlin_targets={merlin_targets!r}"
    )


def test_phase_router_gate_g3_passed_routes_to_papyrus_delivery():
    result = runner.phase_router({"phase": "gate_g3_passed", "mission_id": "m-test", "messages": []})
    assert result == "papyrus_delivery"


def test_gate_to_next_phase_maps_hypothesis_confirmation(graph_store: MissionStore):
    gate = graph_store.list_gates("m-test")[0]
    assert gates._gate_to_next_phase(gate.id, gate, True) == "confirmed"
    assert gates._gate_to_next_phase(gate.id, gate, False) == "framing"


def test_gate_node_completes_gate_when_approved(monkeypatch: pytest.MonkeyPatch, graph_store: MissionStore):
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
    monkeypatch.setattr(gates, "interrupt", lambda payload: {"approved": True, "notes": "Approved"})
    result = asyncio.run(gates.gate_node({"mission_id": "m-test", "pending_gate_id": "gate-m-test-G1"}))
    updated_gate = next(gate for gate in graph_store.list_gates("m-test") if gate.id == "gate-m-test-G1")
    assert result["phase"] == "gate_g1_passed"
    assert updated_gate.status == "completed"


def test_merlin_node_retries_until_threshold(graph_store: MissionStore):
    pytest.skip("Requires OpenAI API access")
    state = {"mission_id": "m-test", "synthesis_retry_count": 1}
    result = asyncio.run(runner.merlin_node(state))
    assert result["phase"] == "redteam_done"
    assert result["synthesis_retry_count"] == 2


def test_merlin_node_advances_on_ship_verdict(graph_store: MissionStore):
    pytest.skip("Requires OpenAI API access")
    graph_store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-1",
            mission_id="m-test",
            verdict="SHIP",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    result = asyncio.run(runner.merlin_node({"mission_id": "m-test"}))
    assert result["phase"] == "synthesis_done"


def test_build_graph_compiles():
    graph = runner.build_graph()
    assert graph is not None
    assert "papyrus_phase0" not in graph.get_graph().nodes


def test_phase_router_routes_gate_phases_through_gate_entry():
    """Phases that need a gate gate_id must route through gate_entry first
    so pending_gate_id is set before gate_node runs. Otherwise gate_node
    returns phase='idle' and the run loops in the orchestrator."""
    for phase in ("awaiting_confirmation", "research_done", "synthesis_done"):
        result = runner.phase_router({"phase": phase, "mission_id": "m-test", "messages": []})
        assert result == "gate_entry", f"phase={phase!r} routed to {result!r}, expected 'gate_entry'"


def test_gate_entry_node_sets_pending_gate_id_for_awaiting_confirmation(graph_store: MissionStore):
    """gate_entry_node, given an awaiting_confirmation phase, must set
    pending_gate_id so the downstream gate_node can run instead of falling
    back to phase='idle'."""
    result = asyncio.run(
        runner.gate_entry_node({"phase": "awaiting_confirmation", "mission_id": "m-test", "messages": []})
    )
    assert result.get("pending_gate_id") == "gate-m-test-hyp-confirm"


def test_gate_entry_is_registered_node_with_edge_to_gate():
    """Compiled graph must contain gate_entry as a real node and a
    deterministic edge gate_entry -> gate."""
    graph = runner.build_graph()
    nodes = set(graph.get_graph().nodes.keys())
    assert "gate_entry" in nodes, f"gate_entry missing from compiled graph; nodes={nodes!r}"
    edge_pairs = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    assert ("gate_entry", "gate") in edge_pairs, (
        f"deterministic edge gate_entry->gate missing; got edges={edge_pairs!r}"
    )
