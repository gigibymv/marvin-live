"""Bug 1 regression tests: chat messages during awaiting_*/done phases must
NOT replay the mission. Continuation messages route to orchestrator_qa, which
reads state and answers in 1-3 sentences without modifying anything."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from marvin.graph.subgraphs import orchestrator_qa
from marvin.mission.schema import Gate, Hypothesis, MerlinVerdict, Mission, MissionBrief
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin_ui import server as srv


@pytest.fixture
def mission_store(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    store = MissionStore(str(db_path))
    mid = "m-test-qa"
    store.save_mission(
        Mission(
            id=mid,
            client="ClientCo",
            target="TargetCo",
            ic_question="Is this attractive?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan(mid, store)
    monkeypatch.setattr(srv, "get_store", lambda: MissionStore(str(db_path)))
    monkeypatch.setattr(
        orchestrator_qa, "MissionStore", lambda: MissionStore(str(db_path))
    )
    yield mid, store
    store.close()


def _persist_brief(store: MissionStore, mission_id: str, text: str) -> None:
    now = datetime.now(UTC).isoformat()
    store.save_mission_brief(
        MissionBrief(
            mission_id=mission_id,
            raw_brief=text,
            ic_question="Is this attractive?",
            mission_angle="test",
            brief_summary=text[:200],
            workstream_plan_json="{}",
            created_at=now,
            updated_at=now,
        )
    )


def test_qa_returns_short_response_without_modifying_state(mission_store):
    mid, store = mission_store
    _persist_brief(store, mid, "Substantive brief about Target — moat, growth, risks.")

    findings_before = len(store.list_findings(mid))
    hypotheses_before = len(store.list_hypotheses(mid))

    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "Approved"))

    assert isinstance(reply, str)
    assert reply.strip()
    # 1-3 sentences only
    sentence_count = sum(reply.count(p) for p in (".", "!", "?"))
    assert 1 <= sentence_count <= 4

    # State unchanged
    assert len(store.list_findings(mid)) == findings_before
    assert len(store.list_hypotheses(mid)) == hypotheses_before
    # Brief unchanged
    brief = store.get_mission_brief(mid)
    assert brief is not None
    assert "Substantive brief" in brief.raw_brief


def test_qa_approved_points_to_gate(mission_store):
    mid, store = mission_store
    _persist_brief(store, mid, "Substantive brief about Target.")

    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "Approved"))
    # Deterministic fallback says "pending. Click 'Review now'..."
    assert "pending" in reply.lower() or "review" in reply.lower()


def test_qa_verdict_question(mission_store):
    mid, store = mission_store
    _persist_brief(store, mid, "Substantive brief.")
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-1",
            mission_id=mid,
            verdict="INVEST_WITH_CONDITIONS",
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "what's the verdict?"))
    assert "INVEST_WITH_CONDITIONS" in reply or "invest" in reply.lower() or "verdict" in reply.lower()


def test_qa_reports_blocked_calculus_from_milestones(mission_store):
    mid, store = mission_store
    _persist_brief(store, mid, "Substantive brief.")
    store.mark_milestone_blocked("W2.1", "agent produced no findings", mid)

    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "Why is Calculus blocked?"))

    assert "calculus" in reply.lower()
    assert "blocked" in reply.lower()
    assert "no findings" in reply.lower() or "agent produced no findings" in reply.lower()


def test_chat_during_awaiting_does_not_replay(mission_store, monkeypatch):
    """Sending a chat message after the brief is set must NOT trigger the
    full mission flow. We assert that graph.astream is NEVER called."""
    mid, store = mission_store
    _persist_brief(store, mid, "Substantive brief about Target — moat, growth, risks.")

    astream_calls = []

    class _FakeGraph:
        async def astream(self, *args, **kwargs):
            astream_calls.append((args, kwargs))
            if False:
                yield None  # generator type

    async def _fake_get_graph():
        return _FakeGraph()

    monkeypatch.setattr(srv, "get_graph", _fake_get_graph)

    async def _drain():
        events = []
        async for event in srv._stream_chat(mid, "Approved"):
            events.append(event)
        return events

    events = asyncio.run(_drain())
    assert astream_calls == [], "Graph must NOT be invoked for continuation messages"
    text_events = [e for e in events if "event: text" in e]
    assert len(text_events) >= 1


def test_initial_brief_runs_graph(mission_store, monkeypatch):
    """First substantive message (no brief in DB) must run the graph flow."""
    mid, store = mission_store
    assert store.get_mission_brief(mid) is None

    astream_calls = []

    class _FakeGraph:
        async def astream(self, *args, **kwargs):
            astream_calls.append((args, kwargs))
            if False:
                yield None

    async def _fake_get_graph():
        return _FakeGraph()

    monkeypatch.setattr(srv, "get_graph", _fake_get_graph)

    initial_brief = (
        "TargetCo — European LLM provider. IC question: is the moat defensible? "
        "Concern: open-weight commoditization."
    )

    async def _drain():
        async for _event in srv._stream_chat(mid, initial_brief):
            pass

    asyncio.run(_drain())
    assert len(astream_calls) >= 1, "Graph must be invoked for initial brief"


def test_short_message_without_brief_routes_to_qa(mission_store, monkeypatch):
    """Short message ('hi') with no brief yet — Q&A mode, not initial brief."""
    mid, store = mission_store

    astream_calls = []

    class _FakeGraph:
        async def astream(self, *args, **kwargs):
            astream_calls.append((args, kwargs))
            if False:
                yield None

    async def _fake_get_graph():
        return _FakeGraph()

    monkeypatch.setattr(srv, "get_graph", _fake_get_graph)

    async def _drain():
        return [event async for event in srv._stream_chat(mid, "hi")]

    events = asyncio.run(_drain())
    assert astream_calls == [], "Short messages must not start the mission flow"
    replies = " ".join(event for event in events if "event: text" in event)
    assert "brief" in replies.lower()
    assert "has not started" in replies.lower()
    assert "still running" not in replies.lower()
    assert any("event: run_end" in event for event in events)


def test_fresh_greeting_requests_brief_without_model(mission_store, monkeypatch):
    mid, store = mission_store

    def unexpected_model(*args, **kwargs):
        raise AssertionError("Fresh onboarding must not call the model")

    monkeypatch.setattr("marvin.llm_factory.get_chat_llm", unexpected_model)
    reply = asyncio.run(orchestrator_qa.respond_qa(mid, "hi"))
    assert reply.startswith("Hi.")
    assert "brief" in reply.lower()
    assert "has not started" in reply.lower()
    assert "still running" not in reply.lower()
    assert "pending" not in reply.lower()  # seeded future gates are not open
    assert store.get_mission_brief(mid) is None
    assert store.list_hypotheses(mid) == []


@pytest.mark.parametrize("status, agents, expected", [
    ("active", [], "No agent is currently marked as working"),
    ("active", ["dora"], "Work is in progress with dora"),
    ("complete", [], "This mission is complete"),
])
def test_no_open_gate_does_not_imply_running(status, agents, expected):
    state = {
        "mission": {"status": status, "active_agents": agents},
        "has_brief": True,
        "pending_gate": None,
    }
    reply = orchestrator_qa._deterministic_response(state, "hello")
    assert expected in reply


def test_real_clarification_gate_is_not_fresh_onboarding(mission_store, monkeypatch):
    mid, store = mission_store
    _persist_brief(store, mid, "Assess TargetCo, but the investment question needs clarification.")
    store.save_gate(Gate(id="g-clarify", mission_id=mid, gate_type="clarification_request", scheduled_day=0))

    def no_model(*args, **kwargs):
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    monkeypatch.setattr("marvin.llm_factory.get_chat_llm", no_model)
    reply = asyncio.run(orchestrator_qa.respond_qa(
        mid, "hi", interrupted_gate_id="g-clarify", interrupt_known=True,
    ))
    assert "Clarification" in reply
    assert "pending" in reply
    assert "has not started" not in reply
