"""Bug 6 regression tests: synthesis retry loop must respect circuit breakers.

Live testing on Mistral revealed Adversus hit cap (12 findings), Merlin
issued MINOR_FIXES, and the loop kept re-running adversus -> merlin without
generating new findings, saturating chat with duplicates. The fix forces
synthesis_done with forced_advance when any breaker fires.
"""
from __future__ import annotations

from marvin.graph.runner import (
    ADVERSUS_FINDING_CAP,
    SYNTHESIS_MAX_RETRIES,
    _next_phase_after_merlin,
)


def test_ship_advances_cleanly():
    decision = _next_phase_after_merlin(
        verdict="SHIP",
        retry_count=0,
        current_finding_count=5,
        last_finding_count=0,
        adversus_finding_count=3,
    )
    assert decision == {"phase": "synthesis_done"}
    assert "forced_advance" not in decision


def test_synthesis_advances_when_cap_reached():
    decision = _next_phase_after_merlin(
        verdict="MINOR_FIXES",
        retry_count=0,
        current_finding_count=ADVERSUS_FINDING_CAP,
        last_finding_count=0,
        adversus_finding_count=ADVERSUS_FINDING_CAP,
    )
    assert decision["phase"] == "synthesis_done"
    assert decision["forced_advance"] is True
    assert decision["force_reason"] == "adversus_cap_reached"


def test_synthesis_advances_when_no_new_findings():
    decision = _next_phase_after_merlin(
        verdict="MINOR_FIXES",
        retry_count=1,
        current_finding_count=8,
        last_finding_count=8,
        adversus_finding_count=8,
    )
    assert decision["phase"] == "synthesis_done"
    assert decision["forced_advance"] is True
    assert decision["force_reason"] == "no_new_findings"


def test_synthesis_max_retries_enforced():
    decision = _next_phase_after_merlin(
        verdict="MINOR_FIXES",
        retry_count=SYNTHESIS_MAX_RETRIES,
        current_finding_count=10,
        last_finding_count=5,
        adversus_finding_count=5,
    )
    assert decision["phase"] == "synthesis_done"
    assert decision["forced_advance"] is True
    assert decision["force_reason"] == "max_retries"


def test_legitimate_retry_with_new_findings_allowed():
    """First retry pass with new findings since last verdict — keep iterating."""
    decision = _next_phase_after_merlin(
        verdict="MINOR_FIXES",
        retry_count=1,
        current_finding_count=10,
        last_finding_count=5,
        adversus_finding_count=5,
    )
    assert decision["phase"] == "synthesis_retry"
    assert decision["synthesis_retry_count"] == 2
    assert decision["last_verdict_at_finding_count"] == 10
    assert "forced_advance" not in decision


def test_first_pass_no_breaker_fires_below_cap():
    """retry_count=0 — no-new-findings breaker must not fire (it would block
    even the very first pass through merlin)."""
    decision = _next_phase_after_merlin(
        verdict="MINOR_FIXES",
        retry_count=0,
        current_finding_count=0,
        last_finding_count=0,
        adversus_finding_count=0,
    )
    assert decision["phase"] == "synthesis_retry"
    assert decision["synthesis_retry_count"] == 1


def test_back_to_drawing_board_treated_like_minor_fixes():
    decision = _next_phase_after_merlin(
        verdict="BACK_TO_DRAWING_BOARD",
        retry_count=0,
        current_finding_count=ADVERSUS_FINDING_CAP,
        last_finding_count=0,
        adversus_finding_count=ADVERSUS_FINDING_CAP,
    )
    assert decision["phase"] == "synthesis_done"
    assert decision["force_reason"] == "adversus_cap_reached"
