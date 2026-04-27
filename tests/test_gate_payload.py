"""Tests for gate_node enriched payload (UX slice)."""
from __future__ import annotations

import pytest

from marvin.graph import gates as gates_mod


def test_human_copy_known_gate_types_have_full_fields():
    for gate_type in ("hypothesis_confirmation", "manager_review", "final_review"):
        copy = gates_mod._human_copy(gate_type)
        assert copy["title"]
        assert copy["stage"]
        assert copy["summary"]
        assert copy["unlocks_on_approve"]
        assert copy["unlocks_on_reject"]


def test_human_copy_unknown_gate_type_falls_back_safely():
    copy = gates_mod._human_copy("some_new_gate")
    assert copy["title"]
    assert copy["summary"]
    assert "Approve" in copy["unlocks_on_approve"] or copy["unlocks_on_approve"]


def test_human_copy_explains_hypothesis_confirmation_in_plain_language():
    copy = gates_mod._human_copy("hypothesis_confirmation")
    assert "hypothes" in copy["summary"].lower()
    assert "research" in copy["unlocks_on_approve"].lower()


def test_human_copy_explains_manager_review_unlocks_redteam():
    copy = gates_mod._human_copy("manager_review")
    assert "red-team" in copy["unlocks_on_approve"].lower() or "adversus" in copy["unlocks_on_approve"].lower()
