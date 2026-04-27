"""Bug 4 regression tests: hypotheses carry a user-facing label (H1, H2, ...)
so chat output never shows raw UUIDs like 'hyp-85a6485f'."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marvin.mission.schema import Hypothesis, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools


@pytest.fixture
def graph_store(monkeypatch):
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
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: store)
    yield store
    store.close()


def test_save_and_read_hypothesis_label(graph_store):
    hyp = Hypothesis(
        id="hyp-abc12345",
        mission_id="m-test",
        text="Moat is defensible.",
        label="H1",
        created_at=datetime.now(UTC).isoformat(),
    )
    graph_store.save_hypothesis(hyp)
    rows = graph_store.list_hypotheses("m-test")
    assert rows[0].label == "H1"


def test_legacy_rows_get_backfilled_label(graph_store):
    """A row written without a label (e.g., from a pre-migration DB) must
    surface as H1/H2/... when read."""
    for idx, text in enumerate(["a", "b", "c"], start=1):
        graph_store.save_hypothesis(
            Hypothesis(
                id=f"hyp-{idx:08x}",
                mission_id="m-test",
                text=text,
                label=None,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
    rows = graph_store.list_hypotheses("m-test")
    labels = [r.label for r in rows]
    assert labels == ["H1", "H2", "H3"]


def test_inline_generation_assigns_sequential_labels(graph_store):
    """The framing path must label hypotheses H1..HN in creation order."""
    hyps = mission_tools._generate_hypotheses_inline("m-test")
    labels = [h.label for h in hyps]
    assert labels[: len(hyps)] == [f"H{i}" for i in range(1, len(hyps) + 1)]
    # Persisted form retains the labels
    persisted_labels = [h.label for h in graph_store.list_hypotheses("m-test")]
    assert persisted_labels == labels


def test_get_hypotheses_returns_label_field(graph_store):
    mission_tools._generate_hypotheses_inline("m-test")
    rows = graph_store.list_hypotheses("m-test")
    for row in rows:
        assert row.label and row.label.startswith("H")
