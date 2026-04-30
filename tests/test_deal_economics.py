"""Wiring tests for C10 deal-economics module: math + store + API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_compute_deal_math_full_inputs():
    from marvin.economics.deal_math import compute_deal_math

    out = compute_deal_math({
        "entry_revenue": 200.0,
        "entry_ebitda": 50.0,
        "entry_multiple": 10.0,
        "entry_equity": None,
        "leverage_x": 5.0,
        "hold_years": 5,
        "target_irr": 0.20,
        "target_moic": 2.5,
        "sector_multiple_low": 8.0,
        "sector_multiple_high": 12.0,
    })
    assert out["entry"]["ev"] == 500.0
    assert out["entry"]["debt"] == 250.0
    assert out["entry"]["equity"] == 250.0
    # required exit equity = 250 * 2.5 = 625
    assert out["required_exit_equity"] == 625.0
    # all 3 scenarios present, with numeric IRR/MOIC
    for name in ("bear", "base", "bull"):
        s = out["scenarios"][name]
        assert s["exit_equity"] is not None
        assert s["moic"] is not None
        assert s["irr"] is not None
    # bull > base > bear in MOIC
    assert (
        out["scenarios"]["bull"]["moic"]
        > out["scenarios"]["base"]["moic"]
        > out["scenarios"]["bear"]["moic"]
    )
    assert out["missing_inputs"] == []


def test_compute_deal_math_missing_inputs():
    from marvin.economics.deal_math import compute_deal_math

    out = compute_deal_math({"entry_revenue": 100.0})
    assert "entry_ebitda" in out["missing_inputs"]
    assert out["entry"]["ev"] is None
    assert out["entry"]["debt"] is None
    # Scenarios should still exist as keys but with None numerics.
    for name in ("bear", "base", "bull"):
        assert out["scenarios"][name]["exit_equity"] is None


def test_store_save_and_get_deal_terms(tmp_path, monkeypatch):
    monkeypatch.setenv("MARVIN_DB_PATH", str(tmp_path / "marvin.db"))
    import importlib
    import marvin.mission.store as store_mod
    importlib.reload(store_mod)
    from marvin.mission.schema import DealTerms, Mission as MissionModel

    s = store_mod.MissionStore(str(tmp_path / "marvin.db"))
    s.save_mission(MissionModel(id="m1", client="c", target="t", mission_type="cdd"))
    assert s.get_deal_terms("m1") is None

    terms = DealTerms(
        mission_id="m1", entry_ebitda=50.0, entry_multiple=10.0,
        leverage_x=5.0, hold_years=5, target_moic=2.5,
    )
    s.save_deal_terms(terms)
    fetched = s.get_deal_terms("m1")
    assert fetched is not None
    assert fetched.entry_ebitda == 50.0
    assert fetched.target_moic == 2.5

    # Upsert overwrites.
    terms2 = terms.model_copy(update={"entry_ebitda": 60.0})
    s.save_deal_terms(terms2)
    assert s.get_deal_terms("m1").entry_ebitda == 60.0


def test_api_deal_terms_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MARVIN_DB_PATH", str(tmp_path / "marvin.db"))
    import importlib
    import marvin.mission.store as store_mod
    importlib.reload(store_mod)
    import marvin_ui.server as srv
    importlib.reload(srv)
    from marvin.mission.schema import Mission as MissionModel

    store = store_mod.MissionStore(str(tmp_path / "marvin.db"))
    store.save_mission(MissionModel(id="m-api", client="c", target="t", mission_type="cdd"))

    client = TestClient(srv.app)
    # Empty before any save.
    r = client.get("/api/v1/missions/m-api/deal-terms")
    assert r.status_code == 200
    assert r.json()["terms"] is None

    # Upsert.
    payload = {
        "entry_revenue": 200, "entry_ebitda": 50, "entry_multiple": 10,
        "leverage_x": 5, "hold_years": 5, "target_moic": 2.5,
        "sector_multiple_low": 8, "sector_multiple_high": 12,
    }
    r = client.put("/api/v1/missions/m-api/deal-terms", json=payload)
    assert r.status_code == 200
    assert r.json()["terms"]["entry_ebitda"] == 50.0

    # Re-fetch.
    r = client.get("/api/v1/missions/m-api/deal-terms")
    assert r.json()["terms"]["target_moic"] == 2.5

    # Math view.
    r = client.get("/api/v1/missions/m-api/deal-math")
    body = r.json()
    assert body["math"]["entry"]["ev"] == 500.0
    assert body["math"]["scenarios"]["base"]["irr"] is not None


def test_api_deal_terms_unknown_mission_returns_404(tmp_path, monkeypatch):
    monkeypatch.setenv("MARVIN_DB_PATH", str(tmp_path / "marvin.db"))
    import importlib
    import marvin.mission.store as store_mod
    importlib.reload(store_mod)
    import marvin_ui.server as srv
    importlib.reload(srv)

    client = TestClient(srv.app)
    r = client.get("/api/v1/missions/m-missing/deal-terms")
    assert r.status_code == 404
    r = client.put("/api/v1/missions/m-missing/deal-terms", json={"entry_ebitda": 10})
    assert r.status_code == 404
