"""Investment verdict routing regressions.

The old Merlin loop could re-run adversus -> merlin after non-SHIP verdicts.
The current product model treats every final investment recommendation as a
valid synthesis result: G3 opens after synthesis is complete, not after a retry
loop tries to force a "ready" label.
"""
from __future__ import annotations

from marvin.graph.runner import _next_phase_after_merlin


def test_all_investment_verdicts_advance_to_synthesis_done():
    for verdict in (
        "INVEST",
        "INVEST_WITH_CONDITIONS",
        "DO_NOT_INVEST",
        "INSUFFICIENT_EVIDENCE",
    ):
        decision = _next_phase_after_merlin(
            verdict=verdict,
            retry_count=0,
            current_finding_count=0,
            last_finding_count=0,
            adversus_finding_count=0,
        )

        assert decision == {"phase": "synthesis_done"}


def test_legacy_verdicts_do_not_reopen_retry_loop():
    for verdict in ("SHIP", "MINOR_FIXES", "BACK_TO_DRAWING_BOARD"):
        decision = _next_phase_after_merlin(
            verdict=verdict,
            retry_count=3,
            current_finding_count=12,
            last_finding_count=5,
            adversus_finding_count=12,
        )

        assert decision == {"phase": "synthesis_done"}
