"""Per-mission domain event listeners.

The persistence chokepoint (`add_finding_to_mission`) emits a `finding_persisted`
event after every successful insert. The SSE stream registers a listener for
the lifetime of a chat run and forwards those events to the client.

Centralizing emission here means `finding_added` fires whether the LLM calls
`add_finding_to_mission` directly or invokes a wrapper tool (e.g. `moat_analysis`)
that calls it as a Python function. Event ownership lives in the persistence
path, not in LLM tool-selection behavior.

Listeners may be invoked from a thread other than the event loop (LangGraph
tools run in `run_in_executor`), so listener implementations must be thread-safe.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

FindingListener = Callable[[dict[str, Any]], None]
DeliverableListener = Callable[[dict[str, Any]], None]

_lock = threading.Lock()
_listeners: dict[str, list[FindingListener]] = {}
_deliverable_listeners: dict[str, list[DeliverableListener]] = {}


def register_finding_listener(mission_id: str, listener: FindingListener) -> None:
    with _lock:
        _listeners.setdefault(mission_id, []).append(listener)


def unregister_finding_listener(mission_id: str, listener: FindingListener) -> None:
    with _lock:
        bucket = _listeners.get(mission_id)
        if not bucket:
            return
        try:
            bucket.remove(listener)
        except ValueError:
            return
        if not bucket:
            _listeners.pop(mission_id, None)


def emit_finding_persisted(mission_id: str, payload: dict[str, Any]) -> None:
    """Notify every listener registered for this mission. Listener exceptions
    are swallowed so a buggy listener cannot break the persistence path."""
    with _lock:
        bucket = list(_listeners.get(mission_id, ()))
    for listener in bucket:
        try:
            listener(payload)
        except Exception:  # noqa: BLE001 — defensive boundary
            pass


def register_deliverable_listener(mission_id: str, listener: DeliverableListener) -> None:
    with _lock:
        _deliverable_listeners.setdefault(mission_id, []).append(listener)


def unregister_deliverable_listener(mission_id: str, listener: DeliverableListener) -> None:
    with _lock:
        bucket = _deliverable_listeners.get(mission_id)
        if not bucket:
            return
        try:
            bucket.remove(listener)
        except ValueError:
            return
        if not bucket:
            _deliverable_listeners.pop(mission_id, None)


def emit_deliverable_persisted(mission_id: str, payload: dict[str, Any]) -> None:
    with _lock:
        bucket = list(_deliverable_listeners.get(mission_id, ()))
    for listener in bucket:
        try:
            listener(payload)
        except Exception:  # noqa: BLE001 — defensive boundary
            pass
