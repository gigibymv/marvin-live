from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from marvin.mission.schema import Hypothesis, Mission, MissionBrief
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin_ui import server as srv
from marvin_ui.server import _continuation_input_from_snapshot


def test_continuation_input_from_routable_terminal_checkpoint():
    snapshot = SimpleNamespace(
        values={
            "mission_id": "m-resume",
            "phase": "gate_g1_passed",
            "pending_gate_id": None,
        },
        next=(),
    )

    continuation = _continuation_input_from_snapshot(snapshot)

    assert continuation == {
        "mission_id": "m-resume",
        "phase": "gate_g1_passed",
        "pending_gate_id": None,
    }


def test_continuation_input_rejects_done_and_missing_mission_id():
    assert _continuation_input_from_snapshot(
        SimpleNamespace(values={"mission_id": "m-resume", "phase": "done"}, next=())
    ) is None
    assert _continuation_input_from_snapshot(
        SimpleNamespace(values={"phase": "gate_g1_passed"}, next=())
    ) is None


@pytest.mark.asyncio
async def test_stream_resume_continues_routable_terminal_checkpoint(monkeypatch):
    store = MissionStore(":memory:")
    store.save_mission(
        Mission(
            id="m-resume",
            client="Client",
            target="Target",
            ic_question="Should IC invest?",
            status="active",
        )
    )

    class FakeGraph:
        def __init__(self):
            self.inputs: list[dict] = []

        async def aget_state(self, config):
            return SimpleNamespace(
                values={"mission_id": "m-resume", "phase": "gate_g1_passed"},
                next=(),
                tasks=[],
            )

        async def astream(self, graph_input, config, stream_mode):
            self.inputs.append(graph_input)
            yield {"adversus": {"phase": "redteam_done", "messages": []}}

    fake_graph = FakeGraph()

    async def get_fake_graph():
        return fake_graph

    monkeypatch.setattr(srv, "get_store", lambda: store)
    monkeypatch.setattr(srv, "get_graph", get_fake_graph)

    chunks = [chunk async for chunk in srv._stream_resume("m-resume")]
    events = [
        (
            next(line.split(":", 1)[1].strip() for line in chunk.splitlines() if line.startswith("event:")),
            json.loads(next(line.split(":", 1)[1].strip() for line in chunk.splitlines() if line.startswith("data:"))),
        )
        for chunk in chunks
        if chunk.startswith("event:")
    ]

    assert fake_graph.inputs == [{"mission_id": "m-resume", "phase": "gate_g1_passed"}]
    assert ("phase_changed", {"phase": "redteam_done", "label": "Red-team complete"}) in events
    assert ("run_end", {}) in events


@pytest.mark.asyncio
async def test_stream_resume_surfaces_open_gate_without_rerunning_graph(monkeypatch):
    store = MissionStore(":memory:")
    store.save_mission(
        Mission(
            id="m-open-gate",
            client="Client",
            target="Target",
            ic_question="Should IC invest?",
            status="active",
        )
    )
    _seed_standard_workplan("m-open-gate", store)
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-open-gate",
            raw_brief="Assess Target.",
            ic_question="Should IC invest?",
            mission_angle="Market attractiveness",
            brief_summary="Assess Target's market attractiveness.",
            workstream_plan_json="[]",
        )
    )
    store.save_hypothesis(
        Hypothesis(
            id="hyp-open",
            mission_id="m-open-gate",
            text="Target can sustain growth.",
        )
    )

    class FakeGraph:
        def __init__(self):
            self.inputs: list[dict] = []

        async def aget_state(self, config):
            return SimpleNamespace(
                values={"mission_id": "m-open-gate", "phase": "awaiting_confirmation"},
                next=(),
                tasks=[],
            )

        async def astream(self, graph_input, config, stream_mode):
            self.inputs.append(graph_input)
            yield {"framing": {"phase": "framing", "messages": []}}

    fake_graph = FakeGraph()

    async def get_fake_graph():
        return fake_graph

    monkeypatch.setattr(srv, "get_store", lambda: store)
    monkeypatch.setattr(srv, "get_graph", get_fake_graph)

    chunks = [chunk async for chunk in srv._stream_resume("m-open-gate")]
    events = [
        (
            next(line.split(":", 1)[1].strip() for line in chunk.splitlines() if line.startswith("event:")),
            json.loads(next(line.split(":", 1)[1].strip() for line in chunk.splitlines() if line.startswith("data:"))),
        )
        for chunk in chunks
        if chunk.startswith("event:")
    ]

    assert fake_graph.inputs == []
    assert any(event == "gate_pending" and payload["gate_type"] == "hypothesis_confirmation" for event, payload in events)
    assert ("run_end", {}) in events
