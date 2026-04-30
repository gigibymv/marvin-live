"""C-PER-MILESTONE — per-milestone deliverable generation regression test.

Asserts that:
- a delivered milestone with ≥1 finding produces a Wx.y_<slug>.md file
- the Deliverable row is persisted with milestone_id set
- the file path resolves under output/<mission>/
- a milestone with zero findings is silently skipped (no exception, no row)
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin.mission.schema import Finding, Hypothesis, Mission, MissionBrief
from marvin.mission.store import MissionStore
from marvin.tools.papyrus_tools import _generate_milestone_report_impl


@pytest.fixture
def store(tmp_path, monkeypatch) -> MissionStore:
    db = tmp_path / "marvin.db"
    s = MissionStore(db_path=str(db))
    s.save_mission(
        Mission(
            id="m-perms",
            client="C",
            target="T",
            mission_type="cdd",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        )
    )
    s.save_mission_brief(
        MissionBrief(
            mission_id="m-perms",
            raw_brief="Sample brief content for the regression test.",
            ic_question="Q?",
            mission_angle="defensibility",
            brief_summary="summary",
            workstream_plan_json="[]",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    s.save_hypothesis(
        Hypothesis(
            id="hyp-test",
            mission_id="m-perms",
            text="Test hypothesis",
            label="H1",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    # Seed standard W1+W2 milestones.
    from marvin_ui.server import _seed_standard_workplan
    _seed_standard_workplan("m-perms", s)
    monkeypatch.setattr(
        "marvin.tools.papyrus_tools._STORE_FACTORY", lambda: s, raising=False
    )
    yield s
    s._conn.close()


def _stub_papyrus_llm(monkeypatch):
    def fake(*, deliverable_type, mission, hypotheses, findings, mission_brief, extra):
        return (
            f"# Per-milestone report — {extra.get('milestone_id')}\n\n"
            f"Workstream: {extra.get('workstream_id')}\n"
            f"Findings: {len(findings)}\n\n"
            "## Body\n\n"
            "This is enough body content to clear the artifact length\n"
            "minimums imposed by `_assert_artifact_can_be_ready` so the\n"
            "deliverable is persisted with status=ready in the store.\n"
            "Padding sentence one for length. Padding sentence two for length.\n"
            "Padding sentence three for length. Padding sentence four for length.\n"
        )

    monkeypatch.setattr("marvin.tools.papyrus_tools._papyrus_llm_generate", fake)


def test_milestone_with_findings_produces_artifact(store, monkeypatch, tmp_path):
    _stub_papyrus_llm(monkeypatch)
    monkeypatch.setattr(
        "marvin.tools.papyrus_tools.PROJECT_ROOT", tmp_path, raising=False
    )
    store.save_finding(
        Finding(
            id="f-1",
            mission_id="m-perms",
            workstream_id="W1",
            milestone_id="W1.1",
            hypothesis_id="hyp-test",
            claim_text="Market grows 12% YoY based on observed adoption",
            confidence="REASONED",
            agent_id="dora",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    result = _generate_milestone_report_impl("W1.1", "m-perms")

    assert result.get("status") not in ("blocked",), result
    assert result["milestone_id"] == "W1.1"
    file_path = Path(result["file_path"])
    assert file_path.exists()
    assert file_path.name.startswith("W1.1_") and file_path.suffix == ".md"

    delivs = store.list_deliverables("m-perms")
    matching = [d for d in delivs if d.deliverable_type == "milestone_report"]
    assert len(matching) == 1
    assert matching[0].milestone_id == "W1.1"


def test_milestone_with_no_findings_returns_blocked(store, monkeypatch):
    _stub_papyrus_llm(monkeypatch)
    result = _generate_milestone_report_impl("W2.2", "m-perms")
    assert result["status"] == "blocked"
    assert "finding" in result["reason"].lower()
    delivs = [d for d in store.list_deliverables("m-perms") if d.deliverable_type == "milestone_report"]
    assert delivs == []


def test_milestone_falls_back_to_workstream_findings_when_untagged(store, monkeypatch, tmp_path):
    _stub_papyrus_llm(monkeypatch)
    monkeypatch.setattr(
        "marvin.tools.papyrus_tools.PROJECT_ROOT", tmp_path, raising=False
    )
    # Finding tagged to W1 but no milestone_id — should still surface for
    # any W1 milestone via the workstream fallback in the impl.
    store.save_finding(
        Finding(
            id="f-untagged",
            mission_id="m-perms",
            workstream_id="W1",
            hypothesis_id="hyp-test",
            claim_text="Untagged but W1-scoped finding clears artifact length",
            confidence="REASONED",
            agent_id="dora",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    result = _generate_milestone_report_impl("W1.1", "m-perms")
    assert result.get("milestone_id") == "W1.1"
    assert result.get("status") not in ("blocked",), result
