"""Phase 1A: ToolMessage -> SSE event mapper, pure-function unit tests.

Covers the centralized mapping layer in marvin_ui.server. The mapper must be
defensive: unknown tools, malformed JSON, non-dict content, and missing
required fields all yield None — never raise.
"""
from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from marvin_ui.server import (
    _emit_for_update,
    _is_trace_only_tool,
    _is_user_facing_tool_text,
    map_tool_to_sse_event,
)


# --- happy path ----------------------------------------------------------------

def test_add_finding_tool_no_longer_mapped_here():
    """finding_added emission moved to the marvin.events listener registered by
    _stream_chat. The mapper must NOT emit for add_finding_to_mission, otherwise
    the event would fire twice when the LLM picks the tool directly. See
    tests/test_finding_event_emission.py for the listener-based contract."""
    content = json.dumps({"finding_id": "f-1", "claim": "Market grew 22% YoY", "confidence": "REASONED"})
    assert map_tool_to_sse_event("add_finding_to_mission", content) is None


def test_mark_milestone_delivered_no_longer_mapped_here():
    """milestone_done emission moved to the marvin.events listener registered by
    _stream_chat. The mapper must NOT emit for mark_milestone_delivered, otherwise
    the event would fire twice when the LLM picks the tool directly while the
    persistence chokepoint also emits. See tests/test_milestone_event_emission.py
    for the listener-based contract."""
    content = json.dumps({"milestone_id": "W1.1", "status": "delivered", "label": "Market sizing"})
    assert map_tool_to_sse_event("mark_milestone_delivered", content) is None


def test_papyrus_tools_no_longer_mapped_here():
    """deliverable_ready emission moved to the marvin.events listener registered
    by _stream_chat. The mapper must NOT emit for any papyrus generate_* tool,
    otherwise the event would fire twice when the LLM picks the tool directly
    while runner-driven calls also persist via the chokepoint. See
    tests/test_deliverable_event_emission.py for the listener-based contract."""
    for tool_name in (
        "generate_engagement_brief",
        "generate_workstream_report",
        "generate_report_pdf",
        "generate_exec_summary",
        "generate_data_book",
    ):
        content = json.dumps({
            "mission_id": "m-1",
            "deliverable_id": f"deliverable-m-1-x",
            "deliverable_type": "x",
            "file_path": "/tmp/x",
        })
        assert map_tool_to_sse_event(tool_name, content) is None


def test_dict_content_accepted_directly():
    """LangGraph may pass through a dict instead of a JSON string. Even with a
    well-formed dict, mapper returns None for tools whose events are owned by
    listeners — proving no double-fire path exists."""
    result = map_tool_to_sse_event(
        "mark_milestone_delivered",
        {"milestone_id": "W1.1", "label": "Market sizing"},
    )
    assert result is None


# --- defensive / malformed cases ----------------------------------------------

def test_unknown_tool_returns_none():
    assert map_tool_to_sse_event("some_random_tool", json.dumps({"foo": 1})) is None


def test_none_tool_name_returns_none():
    assert map_tool_to_sse_event(None, json.dumps({"claim": "x"})) is None


def test_empty_tool_name_returns_none():
    assert map_tool_to_sse_event("", json.dumps({"claim": "x"})) is None


def test_invalid_json_returns_none():
    assert map_tool_to_sse_event("add_finding_to_mission", "{not valid json}") is None


def test_non_string_non_dict_content_returns_none():
    assert map_tool_to_sse_event("add_finding_to_mission", 42) is None
    assert map_tool_to_sse_event("add_finding_to_mission", None) is None


def test_empty_string_content_returns_none():
    assert map_tool_to_sse_event("add_finding_to_mission", "") is None
    assert map_tool_to_sse_event("add_finding_to_mission", "   ") is None


def test_plain_string_content_returns_none():
    """Tool returns plain text (e.g. error summary) rather than JSON."""
    assert map_tool_to_sse_event("add_finding_to_mission", "Finding added · f-12345abc") is None


def test_internal_tool_results_are_not_user_facing_text():
    assert _is_trace_only_tool("search_company") is True
    assert _is_trace_only_tool("persist_source_for_mission") is True
    assert _is_trace_only_tool("get_recent_filings") is True
    assert _is_user_facing_tool_text('{"result": "raw payload"}') is False
    assert _is_user_facing_tool_text("Finding added · f-12345abc") is False
    assert _is_user_facing_tool_text("Cannot open Manager review: missing material") is False
    assert _is_user_facing_tool_text("BACK_TO_DRAWING_BOARD") is False
    assert _is_user_facing_tool_text("Review material is ready for the consultant.") is True


@pytest.mark.asyncio
async def test_raw_tool_calls_and_trace_results_do_not_reach_user_stream(monkeypatch):
    monkeypatch.delenv("MARVIN_SHOW_RAW_TOOL_EVENTS", raising=False)
    event = {
        "dora": {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_recent_filings",
                            "args": {"company_name": "Uber"},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content='{"filings": []}',
                    tool_call_id="call-1",
                    name="get_recent_filings",
                ),
            ]
        }
    }

    sse, _agent, _phase, _interrupt = await _emit_for_update(
        event,
        None,
        None,
        {},
        mission_id="m-test",
    )

    combined = "\n".join(sse)
    assert "tool_call" not in combined
    assert "tool_result" not in combined
    assert "get_recent_filings" not in combined
    assert "Fetching filings" not in combined


@pytest.mark.asyncio
async def test_worker_agent_stream_only_surfaces_latest_ai_message():
    event = {
        "adversus": {
            "messages": [
                AIMessage(content="Dora old research summary."),
                AIMessage(content="Calculus old financial summary."),
                ToolMessage(
                    content='{"findings": []}',
                    tool_call_id="call-old",
                    name="get_storyline_findings",
                ),
                AIMessage(content="Adversus current counter-finding summary."),
            ]
        }
    }

    sse, _agent, _phase, _interrupt = await _emit_for_update(
        event,
        None,
        None,
        {},
        mission_id="m-test",
    )

    combined = "\n".join(sse)
    assert "Adversus current counter-finding summary." in combined
    assert "Dora old research summary." not in combined
    assert "Calculus old financial summary." not in combined
    assert "get_storyline_findings" not in combined


def test_json_array_returns_none():
    """Tool returns a list — not a dict — must not crash."""
    assert map_tool_to_sse_event("add_finding_to_mission", json.dumps([1, 2, 3])) is None


def test_finding_added_missing_claim_returns_none():
    content = json.dumps({"finding_id": "f-1", "confidence": "REASONED"})
    assert map_tool_to_sse_event("add_finding_to_mission", content) is None

