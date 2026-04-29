from __future__ import annotations

import asyncio

import pytest

from marvin_ui import server


@pytest.mark.asyncio
async def test_spawn_detached_resume_queues_when_driver_is_already_running():
    mission_id = "m-queued-detached"
    existing = asyncio.create_task(asyncio.sleep(1))
    server._detached_drivers[mission_id] = existing
    server._queued_detached_resumes.pop(mission_id, None)

    try:
        status = server._spawn_detached_resume(
            mission_id,
            {"gate_id": "gate-next", "verdict": "APPROVED"},
        )

        assert status == "queued"
        assert server._detached_drivers[mission_id] is existing
        assert server._queued_detached_resumes[mission_id]["gate_id"] == "gate-next"
    finally:
        existing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await existing
        server._detached_drivers.pop(mission_id, None)
        server._queued_detached_resumes.pop(mission_id, None)
