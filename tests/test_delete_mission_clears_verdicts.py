"""Regression: delete_mission must clear merlin_verdicts and other
mission-scoped tables. A leaked verdict from a previous run caused gate
G3 (final_review) to evaluate is_open=true on a freshly-recreated
mission with the same id, well before the new run reached synthesis.
"""

from __future__ import annotations

from marvin.mission.schema import MerlinVerdict, Mission
from marvin.mission.store import MissionStore


def _make_mission(mid: str = "m-test-delete-cascade") -> Mission:
    return Mission(
        id=mid,
        client="Acme PE",
        target="VerdictLeakTarget",
        mission_type="cdd",
        ic_question="Should we acquire?",
        status="active",
    )


def _make_verdict(mid: str) -> MerlinVerdict:
    return MerlinVerdict(
        id="v-test-1",
        mission_id=mid,
        verdict="SHIP",
        gate_id=None,
        notes="prior-run verdict",
    )


def test_delete_mission_clears_merlin_verdicts(tmp_path):
    store = MissionStore(db_path=str(tmp_path / "marvin.db"))
    mission = _make_mission()
    store.save_mission(mission)
    store.save_merlin_verdict(_make_verdict(mission.id))

    assert store.get_latest_merlin_verdict(mission.id) is not None, (
        "precondition: verdict should be present before delete"
    )

    deleted = store.delete_mission(mission.id)
    assert deleted is True

    assert store.get_latest_merlin_verdict(mission.id) is None, (
        "verdict from previous run leaked into freshly-recreated mission "
        "with the same id — delete_mission must clear merlin_verdicts"
    )


def test_delete_then_recreate_does_not_leak_verdict(tmp_path):
    """End-to-end: delete a mission with a verdict, recreate same id, the
    new mission must see no verdict (otherwise G3 opens prematurely)."""
    store = MissionStore(db_path=str(tmp_path / "marvin.db"))
    mid = "m-leak-cycle"

    store.save_mission(_make_mission(mid))
    store.save_merlin_verdict(_make_verdict(mid))
    store.delete_mission(mid)

    # Re-create with the same id, as the API does when a user starts a
    # new mission for the same target.
    store.save_mission(_make_mission(mid))

    assert store.get_latest_merlin_verdict(mid) is None, (
        "stale verdict from prior run is visible on the new mission — "
        "this is the bug that opened G3 at ~42% during Adversus"
    )
