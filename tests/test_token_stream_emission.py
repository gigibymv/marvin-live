"""Per-token streaming SSE contract.

Covers _emit_for_message, the dispatcher for graph.astream() "messages"-mode
events. Each (AIMessageChunk, metadata) tuple should produce a token_stream
SSE event tagged with the producing langgraph_node, or no event at all
when the chunk has no usable content. The helper must be defensive:
malformed payloads, missing metadata, and non-string content all yield
empty output rather than raising.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from langchain_core.messages import AIMessageChunk

from marvin_ui.server import _emit_for_message


def _run(coro):
    return asyncio.run(coro)


def _parse_event(sse: str) -> dict:
    # SSE frame: "event: token_stream\ndata: {...}\n\n"
    lines = [line for line in sse.split("\n") if line]
    event_type = next(l[len("event: "):] for l in lines if l.startswith("event: "))
    data_line = next(l[len("data: "):] for l in lines if l.startswith("data: "))
    return {"event_type": event_type, "data": json.loads(data_line)}


def test_token_stream_emits_one_sse_per_chunk():
    chunk = AIMessageChunk(content="Reviewing")
    metadata = {"langgraph_node": "merlin", "langgraph_step": 4}
    out = _run(_emit_for_message((chunk, metadata), current_agent=None))
    assert len(out) == 1
    parsed = _parse_event(out[0])
    assert parsed["event_type"] == "token_stream"
    assert parsed["data"] == {"agent": "merlin", "delta": "Reviewing"}


def test_token_stream_falls_back_to_current_agent_when_node_missing():
    chunk = AIMessageChunk(content=" findings on H1")
    metadata = {"langgraph_step": 7}  # no langgraph_node
    out = _run(_emit_for_message((chunk, metadata), current_agent="dora"))
    parsed = _parse_event(out[0])
    assert parsed["data"]["agent"] == "dora"


def test_token_stream_skips_empty_content():
    chunk = AIMessageChunk(content="")
    metadata = {"langgraph_node": "merlin"}
    assert _run(_emit_for_message((chunk, metadata), current_agent=None)) == []


def test_token_stream_handles_list_content_blocks():
    # Some providers emit list-of-blocks instead of plain str.
    chunk = AIMessageChunk(content=[{"text": "Hello "}, {"text": "world"}])
    metadata = {"langgraph_node": "calculus"}
    out = _run(_emit_for_message((chunk, metadata), current_agent=None))
    parsed = _parse_event(out[0])
    assert parsed["data"]["delta"] == "Hello world"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not a tuple",
        ("only one",),
        (AIMessageChunk(content="x"), "metadata-not-dict"),
    ],
)
def test_token_stream_defensive_against_malformed_payloads(payload):
    assert _run(_emit_for_message(payload, current_agent=None)) == []
