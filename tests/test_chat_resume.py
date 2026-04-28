"""Chantier 2.7 FIX 3: chat-driven gate approval in _stream_chat."""
from __future__ import annotations

import pytest

from marvin_ui import server as srv


@pytest.mark.parametrize("text,expected", [
    ("approved", True),
    ("Approved.", True),
    ("approve", True),
    ("yes", True),
    ("Yes!", True),
    ("ok", True),
    ("okay", True),
    ("go ahead", True),
    ("proceed", True),
    ("LGTM", True),
    ("confirmed", True),
    # Negatives — anything ambiguous routes to QA, not approval.
    ("what's the verdict?", False),
    ("approve, but only because we're behind", False),
    ("reject", False),
    ("no", False),
    ("approved by whom?", False),
    ("", False),
    ("   ", False),
])
def test_is_approval_text(text: str, expected: bool) -> None:
    assert srv._is_approval_text(text) is expected
