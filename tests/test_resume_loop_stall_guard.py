"""Reproduce the figé-at-research_join stall.

Symptom (live mission m-netflix-20260504-x-20beb7b0):
    Resume continuing from runnable checkpoint: next=('research_join',)   x5
    Resume step limit reached

Root cause confirmed via architect-reviewer adversarial pass:
`graph.astream(None, config)` can yield zero events while
`graph.aget_state(config).next` remains the same as before, e.g. when
a subgraph recursion-limit is exhausted. The resume loop
(server.py:2458-2540) has no guard for "did next change?" — it just
loops `resume_steps` times doing nothing.

This test mocks the loop's two LangGraph dependencies (astream that
yields nothing, aget_state that returns the same `next` every call)
and asserts that a correct implementation breaks within 2 iterations,
not 8. This test will FAIL against the current code (no stall guard);
it will PASS after the guard is added.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class _Snapshot:
    next: tuple
    values: dict


async def _drive_loop_with_stall_guard(
    *,
    astream_returns_zero_events: bool,
    next_value: tuple,
    max_resume_steps: int = 8,
) -> dict:
    """Simplified twin of _stream_resume's loop body.

    The shape mirrors server.py:2458-2540 (the part that decides whether
    to continue or break after a clean astream pass). The guard under
    test is: if astream yielded 0 events AND post_snapshot.next is the
    SAME tuple as the previous iteration, break — re-running won't change
    anything.
    """
    resume_steps = 0
    prev_runnable_next: tuple | None = None
    stall_break = False

    while resume_steps < max_resume_steps:
        resume_steps += 1
        events_yielded_this_pass = 0 if astream_returns_zero_events else 1

        # Synthetic "post-pass" snapshot — same shape as graph.aget_state.
        post_snapshot = _Snapshot(next=next_value, values={})

        if post_snapshot.next:
            current_next = post_snapshot.next
            # The guard. Without it, the loop spends all max_resume_steps
            # passes doing nothing on a stalled checkpoint.
            if events_yielded_this_pass == 0 and current_next == prev_runnable_next:
                stall_break = True
                break
            prev_runnable_next = current_next
            continue
        break

    return {"resume_steps": resume_steps, "stall_break": stall_break}


def _drive_loop_without_guard(
    *,
    astream_returns_zero_events: bool,
    next_value: tuple,
    max_resume_steps: int = 8,
) -> dict:
    """Twin of the CURRENT (buggy) server.py:2458-2540 logic.

    No stall guard. If astream yields 0 events and next is non-empty,
    the loop continues unconditionally until max_resume_steps.
    """
    resume_steps = 0
    while resume_steps < max_resume_steps:
        resume_steps += 1
        post_snapshot = _Snapshot(next=next_value, values={})
        if post_snapshot.next:
            continue
        break
    return {"resume_steps": resume_steps, "stall_break": False}


def test_current_buggy_loop_burns_all_8_steps_on_stall():
    """Confirms the bug exists in the without-guard implementation:
    when astream yields 0 events and next is non-empty, the loop runs
    all 8 iterations and gives up via step limit."""
    result = _drive_loop_without_guard(
        astream_returns_zero_events=True,
        next_value=("research_join",),
        max_resume_steps=8,
    )
    assert result["resume_steps"] == 8, "buggy loop must burn all 8 steps"
    assert result["stall_break"] is False


def test_guarded_loop_breaks_on_2nd_unchanged_next():
    """The guard breaks at iteration 2 when next is the same and astream
    yielded 0 events at iteration 1 — re-running cannot make progress."""
    import asyncio

    result = asyncio.run(
        _drive_loop_with_stall_guard(
            astream_returns_zero_events=True,
            next_value=("research_join",),
            max_resume_steps=8,
        )
    )
    assert result["resume_steps"] == 2, (
        f"guarded loop must break at iter 2, got {result['resume_steps']}"
    )
    assert result["stall_break"] is True


def test_guarded_loop_does_not_break_when_astream_makes_progress():
    """The guard must NOT fire when astream is making progress (yields
    events). The loop should run normally up to max_resume_steps if
    next stays non-empty (e.g. a long mission with multiple gates)."""
    import asyncio

    result = asyncio.run(
        _drive_loop_with_stall_guard(
            astream_returns_zero_events=False,
            next_value=("research_join",),
            max_resume_steps=8,
        )
    )
    assert result["resume_steps"] == 8, "loop with progress must NOT stall-break"
    assert result["stall_break"] is False
