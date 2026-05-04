"""Regression: merlin_node must not silently default the verdict.

Live mission m-uber-eats-...-89fc01f6 surfaced a class of bug where missing
critical state was masked by a plausible default. Specifically:

    verdict = verdict_row.verdict if verdict_row else "MINOR_FIXES"

let phase advance to synthesis_done with zero merlin_verdicts rows, opening
G3 with no verdict for the user to review. The fix routes to a new
`merlin_failed` phase that terminates the run with an explicit error.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from marvin.graph import gates, runner
from marvin.graph.subgraphs import merlin as merlin_subgraph
from marvin.mission.schema import MerlinVerdict, Mission
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


async def _noop_merlin_agent(state):
    """Stand-in for the real merlin agent that returns without persisting a verdict.

    Mirrors the failure mode where the LLM produces text but never calls
    set_merlin_verdict (or the call fails silently).
    """
    return dict(state)


def test_merlin_logs_error_when_llm_skips_verdict(
    graph_store: MissionStore,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """No verdict persisted → phase=merlin_failed, error logged, no silent default."""
    monkeypatch.setattr(merlin_subgraph, "merlin_agent_node", _noop_merlin_agent)

    assert graph_store.get_latest_merlin_verdict("m-test") is None

    with caplog.at_level(logging.ERROR, logger="marvin.graph.runner"):
        result = asyncio.run(
            runner.merlin_node({"mission_id": "m-test", "messages": []})
        )

    assert result["phase"] == "merlin_failed", (
        "merlin_node must not advance phase when no verdict was persisted"
    )
    assert "no verdict persisted" in caplog.text.lower()
    # User-facing failure surfaced in chat, not a silent default
    out_messages = result.get("messages") or []
    assert any(
        isinstance(message, AIMessage) and "verdict" in message.content.lower()
        for message in out_messages
    ), "expected an AIMessage explaining the missing verdict"


def test_merlin_failed_phase_routes_to_end():
    """phase=merlin_failed must terminate, not loop or open G3."""
    result = runner.phase_router(
        {"phase": "merlin_failed", "mission_id": "m-test", "messages": []}
    )
    # langgraph END is a sentinel object exported from langgraph.graph
    from langgraph.graph import END

    assert result == END


def test_merlin_advances_when_verdict_persisted(
    graph_store: MissionStore, monkeypatch: pytest.MonkeyPatch
):
    """Sanity: when a verdict IS persisted, the silent-default fix must not
    regress the happy path."""
    monkeypatch.setattr(merlin_subgraph, "merlin_agent_node", _noop_merlin_agent)
    graph_store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-1",
            mission_id="m-test",
            verdict="INVEST",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    result = asyncio.run(
        runner.merlin_node({"mission_id": "m-test", "messages": []})
    )
    assert result["phase"] == "synthesis_done"
    assert result.get("force_reason") is None
