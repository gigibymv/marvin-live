"""Phase 1A: ToolMessage -> SSE event mapper, pure-function unit tests.

Covers the centralized mapping layer in marvin_ui.server. The mapper must be
defensive: unknown tools, malformed JSON, non-dict content, and missing
required fields all yield None — never raise.
"""
from __future__ import annotations

import json

from marvin_ui.server import map_tool_to_sse_event


# --- happy path ----------------------------------------------------------------

def test_add_finding_tool_no_longer_mapped_here():
    """finding_added emission moved to the marvin.events listener registered by
    _stream_chat. The mapper must NOT emit for add_finding_to_mission, otherwise
    the event would fire twice when the LLM picks the tool directly. See
    tests/test_finding_event_emission.py for the listener-based contract."""
    content = json.dumps({"finding_id": "f-1", "claim": "Market grew 22% YoY", "confidence": "REASONED"})
    assert map_tool_to_sse_event("add_finding_to_mission", content) is None


def test_milestone_done_full_payload():
    content = json.dumps({"milestone_id": "W1.1", "status": "delivered", "label": "Market sizing"})
    result = map_tool_to_sse_event("mark_milestone_delivered", content)
    assert result == ("milestone_done", {"milestoneId": "W1.1", "label": "Market sizing"})


def test_milestone_done_omits_label_when_missing():
    content = json.dumps({"milestone_id": "W1.1", "status": "delivered"})
    result = map_tool_to_sse_event("mark_milestone_delivered", content)
    assert result == ("milestone_done", {"milestoneId": "W1.1"})


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
    """LangGraph may pass through a dict instead of a JSON string."""
    result = map_tool_to_sse_event(
        "mark_milestone_delivered",
        {"milestone_id": "W1.1", "label": "Market sizing"},
    )
    assert result == ("milestone_done", {"milestoneId": "W1.1", "label": "Market sizing"})


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


def test_json_array_returns_none():
    """Tool returns a list — not a dict — must not crash."""
    assert map_tool_to_sse_event("add_finding_to_mission", json.dumps([1, 2, 3])) is None


def test_finding_added_missing_claim_returns_none():
    content = json.dumps({"finding_id": "f-1", "confidence": "REASONED"})
    assert map_tool_to_sse_event("add_finding_to_mission", content) is None


def test_milestone_done_missing_milestone_id_returns_none():
    content = json.dumps({"status": "delivered", "label": "x"})
    assert map_tool_to_sse_event("mark_milestone_delivered", content) is None


