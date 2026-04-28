"""Chantier 2.7 FIX 1: SqliteSaver persists graph state across process restart.

The contract: a mission paused at a gate must survive a uvicorn SIGTERM. We
simulate that by writing a checkpoint via one SqliteSaver instance, closing
the connection, opening a new connection at the same path, and verifying the
checkpoint can be read back.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


def test_sqlite_checkpoint_survives_reconnect(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    thread_id = "m-test-survive"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    # Write a checkpoint with one connection (simulates running uvicorn).
    conn1 = sqlite3.connect(db, check_same_thread=False)
    saver1 = SqliteSaver(conn1)
    saver1.setup()
    checkpoint = {
        "v": 4,
        "id": "cp-1",
        "ts": "2026-04-27T00:00:00Z",
        "channel_values": {"phase": "awaiting_g1", "mission_id": thread_id},
        "channel_versions": {"phase": 1, "mission_id": 1},
        "versions_seen": {},
    }
    saver1.put(config, checkpoint, {"source": "input", "step": 0, "writes": {}}, {})
    conn1.close()

    # Reconnect (simulates fresh uvicorn process).
    conn2 = sqlite3.connect(db, check_same_thread=False)
    saver2 = SqliteSaver(conn2)
    tup = saver2.get_tuple(config)
    conn2.close()

    assert tup is not None, "Checkpoint must persist across connection close"
    assert tup.checkpoint["channel_values"]["phase"] == "awaiting_g1"
    assert tup.checkpoint["channel_values"]["mission_id"] == thread_id


def test_build_checkpointer_honors_memory_override(monkeypatch, tmp_path: Path) -> None:
    """MARVIN_CHECKPOINT_BACKEND=memory disables persistence (used by tests)."""
    from langgraph.checkpoint.memory import MemorySaver

    from marvin_ui import server as srv

    monkeypatch.setenv("MARVIN_CHECKPOINT_BACKEND", "memory")
    saver = srv._build_checkpointer()
    assert isinstance(saver, MemorySaver)


def test_build_checkpointer_default_is_sqlite(monkeypatch, tmp_path: Path) -> None:
    from marvin_ui import server as srv

    db = tmp_path / "cp.db"
    monkeypatch.delenv("MARVIN_CHECKPOINT_BACKEND", raising=False)
    monkeypatch.setenv("MARVIN_CHECKPOINT_DB", str(db))
    saver = srv._build_checkpointer()
    assert isinstance(saver, SqliteSaver)
    assert db.exists()
