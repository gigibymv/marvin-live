from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin.mission.schema import Deliverable, Finding, Hypothesis, MerlinVerdict, Mission, MissionBrief
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin_ui import server as srv


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-progress",
            client="Client",
            target="Target",
            ic_question="Should IC invest?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-progress", s)
    monkeypatch.setattr(srv, "get_store", lambda: s)
    yield s
    s.close()


def test_empty_mission_has_scheduled_gates_but_none_open(store: MissionStore):
    payload = asyncio.run(srv.get_mission_progress("m-progress"))

    assert payload["deliverables"] == []
    assert payload["gates"]
    assert {gate["lifecycle_status"] for gate in payload["gates"]} == {"scheduled"}
    assert all(gate["is_open"] is False for gate in payload["gates"])


def test_hypothesis_gate_opens_only_after_hypotheses_exist(store: MissionStore):
    store.save_hypothesis(
        Hypothesis(
            id="hyp-progress",
            mission_id="m-progress",
            text="Target can sustain a differentiated market position",
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["hypothesis_confirmation"]["lifecycle_status"] == "scheduled"

    now = datetime.now(UTC).isoformat()
    store.save_mission_brief(
        MissionBrief(
            mission_id="m-progress",
            raw_brief="Assess whether Target can sustain differentiated growth.",
            ic_question="Should IC invest?",
            mission_angle="Market position and competitive durability",
            brief_summary="Assess differentiated growth.",
            workstream_plan_json='[{"id":"W1","label":"Market","focus":"Market"}]',
            created_at=now,
            updated_at=now,
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["hypothesis_confirmation"]["lifecycle_status"] == "open"
    assert gates["hypothesis_confirmation"]["is_open"] is True
    assert gates["manager_review"]["lifecycle_status"] == "scheduled"
    assert gates["final_review"]["lifecycle_status"] == "scheduled"


def test_progress_never_marks_placeholder_artifact_ready(store: MissionStore, tmp_path: Path):
    path = tmp_path / "engagement_brief.md"
    path.write_text("# Engagement Brief\n\n- No hypotheses yet\n", encoding="utf-8")
    store.save_deliverable(
        Deliverable(
            id="deliverable-placeholder",
            mission_id="m-progress",
            deliverable_type="engagement_brief",
            status="ready",
            file_path=str(path.resolve()),
            file_size_bytes=path.stat().st_size,
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))

    assert payload["deliverables"] == [
        {
            "id": "deliverable-placeholder",
            "deliverable_type": "engagement_brief",
            "status": "pending",
            "file_path": None,
            "created_at": payload["deliverables"][0]["created_at"],
        }
    ]


def test_manager_review_opens_after_research_finding(store: MissionStore):
    store.save_finding(
        Finding(
            id="f-research",
            mission_id="m-progress",
            workstream_id="W1",
            claim_text="Market evidence is ready for manager review",
            confidence="REASONED",
            agent_id="dora",
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["manager_review"]["lifecycle_status"] == "open"
    assert gates["manager_review"]["is_open"] is True
    assert gates["final_review"]["lifecycle_status"] == "scheduled"


def test_final_review_opens_after_merlin_verdict_and_redteam_finding(store: MissionStore):
    store.save_merlin_verdict(
        MerlinVerdict(
            id="mv-progress",
            mission_id="m-progress",
            verdict="SHIP",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    store.save_finding(
        Finding(
            id="f-redteam",
            mission_id="m-progress",
            workstream_id="W4",
            claim_text="Adversus identified and bounded the weakest link",
            confidence="REASONED",
            agent_id="adversus",
            created_at=datetime.now(UTC).isoformat(),
        )
    )

    payload = asyncio.run(srv.get_mission_progress("m-progress"))
    gates = {gate["gate_type"]: gate for gate in payload["gates"]}

    assert gates["final_review"]["lifecycle_status"] == "open"
    assert gates["final_review"]["is_open"] is True
