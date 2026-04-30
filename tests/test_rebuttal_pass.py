"""Wiring tests for C7 — iterative finding pushback (rebuttal pass).

Pure tests over selection + prompt building + routing. The full
async-graph integration is exercised by the smoke runner; these
tests guarantee:
  - target selection picks load_bearing + anomaly/contradict text
  - selection ignores non-Adversus findings
  - rebuttal message lists the targets
  - phase_router maps redteam_done → research_rebuttal when enabled,
    and → merlin when MARVIN_REBUTTAL_ENABLED=0
  - rebuttal_done routes to merlin
  - empty-attacks early exit returns rebuttal_done without invoking subagents
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _f(**kw):
    """Lightweight Finding-shaped namespace for selection tests."""
    return SimpleNamespace(
        id=kw.get("id", "f-x"),
        agent_id=kw.get("agent_id"),
        impact=kw.get("impact"),
        claim_text=kw.get("claim_text", ""),
        created_at=kw.get("created_at", ""),
    )


def test_select_rebuttal_targets_picks_load_bearing_first():
    from marvin.graph.runner import _select_rebuttal_targets

    findings = [
        _f(id="a1", agent_id="adversus", impact="supporting",
           claim_text="weakest link analysis: customer concentration"),
        _f(id="a2", agent_id="adversus", impact="load_bearing",
           claim_text="ANOMALY: deferred revenue growth lags ARR"),
        _f(id="c1", agent_id="calculus", impact="load_bearing",
           claim_text="this is a calculus finding, NOT an attack"),
    ]
    out = _select_rebuttal_targets(findings)
    assert [f.id for f in out] == ["a2", "a1"]
    assert "c1" not in [f.id for f in out]


def test_select_rebuttal_targets_filters_non_adversus():
    from marvin.graph.runner import _select_rebuttal_targets
    findings = [
        _f(id="d1", agent_id="dora", impact="load_bearing",
           claim_text="ANOMALY in TAM"),
    ]
    assert _select_rebuttal_targets(findings) == []


def test_select_rebuttal_targets_caps_at_limit():
    from marvin.graph.runner import _select_rebuttal_targets, REBUTTAL_MAX_ATTACKS
    findings = [
        _f(id=f"a{i}", agent_id="adversus", impact="load_bearing",
           claim_text="ANOMALY in metric")
        for i in range(REBUTTAL_MAX_ATTACKS + 5)
    ]
    out = _select_rebuttal_targets(findings)
    assert len(out) == REBUTTAL_MAX_ATTACKS


def test_build_rebuttal_message_lists_attacks():
    from marvin.graph.runner import _build_rebuttal_message
    attacks = [
        _f(id="a1", claim_text="ANOMALY: net retention 89%"),
        _f(id="a2", claim_text="contradicts management's 120% NRR claim"),
    ]
    msg = _build_rebuttal_message(attacks)
    assert "[a1]" in msg
    assert "[a2]" in msg
    assert "REBUTTAL PASS" in msg
    assert "fetch_filing_section" in msg


def test_phase_router_redteam_done_routes_to_rebuttal_when_enabled(monkeypatch):
    monkeypatch.delenv("MARVIN_REBUTTAL_ENABLED", raising=False)
    from marvin.graph.runner import phase_router
    out = phase_router({"phase": "redteam_done", "mission_id": "m"})
    assert out == "research_rebuttal"


def test_phase_router_redteam_done_routes_to_merlin_when_disabled(monkeypatch):
    monkeypatch.setenv("MARVIN_REBUTTAL_ENABLED", "0")
    from marvin.graph.runner import phase_router
    out = phase_router({"phase": "redteam_done", "mission_id": "m"})
    assert out == "merlin"


def test_phase_router_rebuttal_done_routes_to_merlin():
    from marvin.graph.runner import phase_router
    out = phase_router({"phase": "rebuttal_done", "mission_id": "m"})
    assert out == "merlin"


@pytest.mark.asyncio
async def test_research_rebuttal_node_no_targets_short_circuits(tmp_path, monkeypatch):
    monkeypatch.setenv("MARVIN_DB_PATH", str(tmp_path / "marvin.db"))
    import importlib
    import marvin.mission.store as store_mod
    importlib.reload(store_mod)
    import marvin.graph.runner as runner
    importlib.reload(runner)
    from marvin.mission.schema import Mission as MissionModel
    store = store_mod.MissionStore(str(tmp_path / "marvin.db"))
    store.save_mission(MissionModel(id="m1", client="c", target="t", mission_type="cdd"))

    # No findings → rebuttal node should skip subagent calls.
    called = {"calculus": 0, "dora": 0}

    async def _fake_cal(state):
        called["calculus"] += 1
        return state

    async def _fake_dora(state):
        called["dora"] += 1
        return state

    monkeypatch.setattr(runner, "calculus_agent_node", _fake_cal)
    monkeypatch.setattr(runner, "dora_agent_node", _fake_dora)

    out = await runner.research_rebuttal_node({"mission_id": "m1", "messages": []})
    assert out == {"phase": "rebuttal_done"}
    assert called == {"calculus": 0, "dora": 0}
