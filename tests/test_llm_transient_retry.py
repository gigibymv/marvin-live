"""C-RESUME-RECOVERY tests — bounded LLM retry + structured gate failure."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from marvin.llm.transient import (
    DEFAULT_BACKOFFS,
    LLMTransientFailure,
    _classify,
    async_invoke_with_retry,
)
from marvin.mission.schema import Gate, Mission
from marvin.mission.store import MissionStore


def _mission() -> Mission:
    return Mission(
        id="m-tx",
        client="C",
        target="T",
        status="active",
        created_at=datetime.now(UTC).isoformat(),
    )


def _gate(id_: str = "gate-g2", gate_type: str = "manager_review") -> Gate:
    return Gate(
        id=id_,
        mission_id="m-tx",
        gate_type=gate_type,
        scheduled_day=2,
    )


# ---------------------------------------------------------------------------
# _classify
# ---------------------------------------------------------------------------

def test_classify_jsondecodeerror_is_transient():
    err = json.JSONDecodeError("Expecting value", "<html>500</html>", 0)
    assert _classify(err) is not None
    assert "non-JSON" in _classify(err)


def test_classify_random_error_is_not_transient():
    assert _classify(ValueError("boom")) is None
    assert _classify(KeyError("x")) is None


# ---------------------------------------------------------------------------
# async_invoke_with_retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_succeeds_on_first_attempt():
    calls = {"n": 0}

    async def func():
        calls["n"] += 1
        return "ok"

    result = await async_invoke_with_retry(func, agent="adversus")
    assert result == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds(monkeypatch):
    # Speed up backoff to keep the test fast.
    async def _no_sleep(_delay):
        return None
    monkeypatch.setattr("marvin.llm.transient.asyncio.sleep", _no_sleep)
    calls = {"n": 0}

    async def func():
        calls["n"] += 1
        if calls["n"] < 3:
            raise json.JSONDecodeError("Expecting value", "html", 0)
        return "recovered"

    result = await async_invoke_with_retry(func, agent="adversus")
    assert result == "recovered"
    assert calls["n"] == 3  # 2 retries + final success


@pytest.mark.asyncio
async def test_exhausted_retries_raise_typed_failure(monkeypatch):
    async def _no_sleep(_delay):
        return None
    monkeypatch.setattr("marvin.llm.transient.asyncio.sleep", _no_sleep)

    async def func():
        raise json.JSONDecodeError("Expecting value", "html", 0)

    with pytest.raises(LLMTransientFailure) as exc_info:
        await async_invoke_with_retry(func, agent="merlin")

    failure = exc_info.value
    assert failure.agent == "merlin"
    assert failure.attempts == len(DEFAULT_BACKOFFS) + 1  # 3
    assert "non-JSON" in failure.cause
    assert failure.error == "JSONDecodeError"

    # Failure reason payload matches the contract used by the UI card.
    reason = failure.to_failure_reason()
    assert reason["agent"] == "merlin"
    assert reason["retries_exhausted"] == 3
    assert reason["error"] == "JSONDecodeError"


@pytest.mark.asyncio
async def test_non_transient_error_propagates_immediately():
    calls = {"n": 0}

    async def func():
        calls["n"] += 1
        raise RuntimeError("real bug")

    with pytest.raises(RuntimeError, match="real bug"):
        await async_invoke_with_retry(func, agent="adversus")
    # No retry on non-transient.
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Store: save_gate_failure / clear_gate_failure / failure_reason persistence
# ---------------------------------------------------------------------------

def test_save_gate_failure_persists_structured_reason():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_gate(_gate())

    updated = store.save_gate_failure(
        "gate-g2",
        agent="adversus",
        error="JSONDecodeError",
        cause="OpenRouter non-JSON response (likely 5xx HTML)",
        retries_exhausted=3,
    )
    assert updated.status == "failed"
    assert updated.failure_reason == {
        "agent": "adversus",
        "error": "JSONDecodeError",
        "cause": "OpenRouter non-JSON response (likely 5xx HTML)",
        "retries_exhausted": 3,
    }

    # round-trip through list_gates → re-decoded from JSON column
    [round_tripped] = store.list_gates("m-tx")
    assert round_tripped.status == "failed"
    assert round_tripped.failure_reason["agent"] == "adversus"

    store.close()


def test_clear_gate_failure_resets_to_pending():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_gate(_gate())
    store.save_gate_failure(
        "gate-g2",
        agent="adversus",
        error="JSONDecodeError",
        cause="upstream",
        retries_exhausted=3,
    )
    store.clear_gate_failure("gate-g2")

    [gate] = store.list_gates("m-tx")
    assert gate.status == "pending"
    assert gate.failure_reason is None
    store.close()


def test_save_gate_with_no_failure_reason_round_trips():
    store = MissionStore(":memory:")
    store.save_mission(_mission())
    store.save_gate(_gate())
    [gate] = store.list_gates("m-tx")
    assert gate.failure_reason is None
    assert gate.status == "pending"
    store.close()
