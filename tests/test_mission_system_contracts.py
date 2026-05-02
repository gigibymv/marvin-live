"""Mission-level system contracts.

These tests encode cross-layer product invariants that were previously
validated only by ad hoc live runs. They intentionally audit the LangGraph
shape and mission completion contract as one system.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import AIMessage

from marvin.graph import runner
from marvin.mission.schema import Deliverable, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin_ui import server as srv


def _make_store(mission_id: str = "m-contract", db_path: str | Path = ":memory:") -> MissionStore:
    store = MissionStore(db_path)
    store.save_mission(
        Mission(
            id=mission_id,
            client="CDD",
            target="Uber",
            ic_question="Can Uber sustain durable profitability?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan(mission_id, store)
    return store


def _ready_file(tmp_path: Path, name: str) -> tuple[str, int]:
    path = tmp_path / name
    path.write_text(f"# {name}\n\n" + ("Consultant-grade content.\n" * 20), encoding="utf-8")
    return str(path.resolve()), path.stat().st_size


def _save_ready_deliverable(
    store: MissionStore,
    tmp_path: Path,
    *,
    deliverable_id: str,
    deliverable_type: str,
    file_name: str,
    mission_id: str = "m-contract",
    workstream_id: str | None = None,
) -> None:
    file_path, file_size = _ready_file(tmp_path, file_name)
    store.save_deliverable(
        Deliverable(
            id=deliverable_id,
            mission_id=mission_id,
            deliverable_type=deliverable_type,
            status="ready",
            workstream_id=workstream_id,
            file_path=file_path,
            file_size_bytes=file_size,
            created_at=datetime.now(UTC).isoformat(),
        )
    )


def test_langgraph_gate_phases_route_through_gate_entry():
    graph = runner.build_graph()
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    assert ("research_join", "gate_entry") in edges
    assert ("merlin", "gate_entry") in edges
    assert ("gate_entry", "gate") in edges
    assert ("merlin", "merlin") not in edges


def test_phase_router_keeps_merlin_retry_on_adversus_path():
    route = runner.phase_router(
        {
            "mission_id": "m-contract",
            "phase": "synthesis_retry",
            "messages": [],
        }
    )

    assert route == "adversus"


def test_canonical_completion_requires_financial_report(tmp_path, monkeypatch):
    store = _make_store()
    monkeypatch.setattr(runner, "MissionStore", lambda *args, **kwargs: store)

    _save_ready_deliverable(
        store,
        tmp_path,
        deliverable_id="d-brief",
        deliverable_type="engagement_brief",
        file_name="engagement_brief.md",
    )
    _save_ready_deliverable(
        store,
        tmp_path,
        deliverable_id="d-w1",
        deliverable_type="workstream_report",
        workstream_id="W1",
        file_name="W1_report.md",
    )
    _save_ready_deliverable(
        store,
        tmp_path,
        deliverable_id="d-w4",
        deliverable_type="workstream_report",
        workstream_id="W4",
        file_name="W4_report.md",
    )
    _save_ready_deliverable(
        store,
        tmp_path,
        deliverable_id="d-exec",
        deliverable_type="exec_summary",
        file_name="exec_summary.md",
    )
    _save_ready_deliverable(
        store,
        tmp_path,
        deliverable_id="d-book",
        deliverable_type="data_book",
        file_name="data_book.md",
    )

    assert runner._missing_canonical_cdd_deliverables(store, "m-contract") == ["Financial report"]


def test_papyrus_delivery_does_not_complete_mission_when_canonical_deliverable_missing(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "mission-contract.db"
    monkeypatch.setenv("MARVIN_DB_PATH", str(db_path))
    store = _make_store(db_path=db_path)

    import marvin.tools.papyrus_tools as papyrus_tools

    monkeypatch.setattr(papyrus_tools, "_generate_report_pdf_impl", lambda mission_id: None)
    monkeypatch.setattr(papyrus_tools, "_generate_exec_summary_impl", lambda mission_id: None)
    monkeypatch.setattr(papyrus_tools, "_generate_data_book_impl", lambda mission_id: None)
    monkeypatch.setattr(papyrus_tools, "_generate_workstream_report_impl", lambda workstream_id, mission_id: None)

    for deliverable_id, deliverable_type, workstream_id, file_name in (
        ("d-brief", "engagement_brief", None, "engagement_brief.md"),
        ("d-w1", "workstream_report", "W1", "W1_report.md"),
        ("d-w4", "workstream_report", "W4", "W4_report.md"),
        ("d-exec", "exec_summary", None, "exec_summary.md"),
        ("d-book", "data_book", None, "data_book.md"),
    ):
        _save_ready_deliverable(
            store,
            tmp_path,
            deliverable_id=deliverable_id,
            deliverable_type=deliverable_type,
            workstream_id=workstream_id,
            file_name=file_name,
        )

    result = asyncio.run(runner.papyrus_delivery_node({"mission_id": "m-contract", "messages": []}))

    refreshed = MissionStore(db_path)
    assert refreshed.get_mission("m-contract").status == "active"
    refreshed.close()
    assert result["phase"] == "orchestrator"
    message = result["messages"][0]
    assert isinstance(message, AIMessage)
    assert "Missing deliverables: Financial report" in message.content


def test_gate_pending_and_deliverable_chat_are_persisted_for_reload(tmp_path, monkeypatch):
    db_path = tmp_path / "mission-chat.db"
    monkeypatch.setenv("MARVIN_DB_PATH", str(db_path))
    store = _make_store(db_path=db_path)
    store.close()

    gate_payload = {
        "gate_id": "gate-m-contract-G1",
        "gate_type": "manager_review",
        "title": "Manager review of research claims",
        "summary": "Initial research is complete.",
    }
    asyncio.run(srv._emit_gate_pending(gate_payload, mission_id="m-contract"))
    srv._build_papyrus_chat_event(
        {
            "deliverable_id": "deliverable-m-contract-w1-report",
            "deliverable_type": "workstream_report",
        },
        mission_id="m-contract",
    )

    refreshed = MissionStore(db_path)
    messages = refreshed.list_chat_messages("m-contract")
    refreshed.close()

    assert [m.id for m in messages] == [
        "gate-m-contract-G1-gate-pending",
        "deliverable-m-contract-w1-report-chat",
    ]
    assert messages[0].gate_id == "gate-m-contract-G1"
    assert messages[0].gate_action == "pending"
    assert messages[1].deliverable_id == "deliverable-m-contract-w1-report"
