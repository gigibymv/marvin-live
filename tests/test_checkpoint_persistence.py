"""Chantier 2.7 FIX 1: AsyncSqliteSaver persists graph state across process restart.

The contract: a mission paused at a gate must survive a uvicorn SIGTERM. We
simulate that by writing a checkpoint via one AsyncSqliteSaver instance, closing
the connection, opening a new connection at the same path, and verifying the
checkpoint can be read back.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@pytest.mark.asyncio
async def test_sqlite_checkpoint_survives_reconnect(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    thread_id = "m-test-survive"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    # Write a checkpoint with one connection (simulates running uvicorn).
    conn1 = await aiosqlite.connect(db)
    saver1 = AsyncSqliteSaver(conn1)
    await saver1.setup()
    checkpoint = {
        "v": 4,
        "id": "cp-1",
        "ts": "2026-04-27T00:00:00Z",
        "channel_values": {"phase": "awaiting_g1", "mission_id": thread_id},
        "channel_versions": {"phase": 1, "mission_id": 1},
        "versions_seen": {},
    }
    await saver1.aput(config, checkpoint, {"source": "input", "step": 0, "writes": {}}, {})
    await conn1.close()

    # Reconnect (simulates fresh uvicorn process).
    conn2 = await aiosqlite.connect(db)
    saver2 = AsyncSqliteSaver(conn2)
    tup = await saver2.aget_tuple(config)
    await conn2.close()

    assert tup is not None, "Checkpoint must persist across connection close"
    assert tup.checkpoint["channel_values"]["phase"] == "awaiting_g1"
    assert tup.checkpoint["channel_values"]["mission_id"] == thread_id


@pytest.mark.asyncio
async def test_build_checkpointer_honors_memory_override(monkeypatch, tmp_path: Path) -> None:
    """MARVIN_CHECKPOINT_BACKEND=memory disables persistence (used by tests)."""
    from langgraph.checkpoint.memory import MemorySaver

    from marvin_ui import server as srv

    monkeypatch.setenv("MARVIN_CHECKPOINT_BACKEND", "memory")
    saver = await srv._build_checkpointer()
    assert isinstance(saver, MemorySaver)


@pytest.mark.asyncio
async def test_build_checkpointer_default_is_sqlite(monkeypatch, tmp_path: Path) -> None:
    from marvin_ui import server as srv

    db = tmp_path / "cp.db"
    monkeypatch.delenv("MARVIN_CHECKPOINT_BACKEND", raising=False)
    monkeypatch.setenv("MARVIN_CHECKPOINT_DB", str(db))
    saver = await srv._build_checkpointer()
    # Close the aiosqlite connection stored globally to avoid ResourceWarning.
    if srv._checkpoint_conn is not None:
        await srv._checkpoint_conn.close()
        srv._checkpoint_conn = None
    assert isinstance(saver, AsyncSqliteSaver)
    assert db.exists()
