"""Bug 3 regression tests: every emitted node has an attributable display
name (Dora/Calculus/Adversus/Merlin/MARVIN/Papyrus). System/internal nodes
return None so the live rail doesn't show "AGENT" or raw identifiers."""
from __future__ import annotations

from marvin.graph.runner import build_graph
from marvin_ui.server import _DISPLAY_NAME, get_display_name


SYSTEM_NODES = {"phase_router", "research_join", "gate", "gate_node", "gate_entry"}


def test_no_anonymous_AGENT_label_for_known_agents():
    """Working agents must resolve to a Title Case (or MARVIN) string."""
    for node, expected in (
        ("dora", "Dora"),
        ("calculus", "Calculus"),
        ("adversus", "Adversus"),
        ("merlin", "Merlin"),
        ("synthesis_critic", "Merlin"),
        ("orchestrator", "MARVIN"),
        ("orchestrator_qa", "MARVIN"),
        ("framing", "MARVIN"),
        ("framing_orchestrator", "MARVIN"),
        ("papyrus_phase0", "Papyrus"),
        ("papyrus_delivery", "Papyrus"),
    ):
        assert get_display_name(node) == expected, f"{node} -> {get_display_name(node)!r}"


def test_system_nodes_return_none():
    for node in SYSTEM_NODES:
        if node in _DISPLAY_NAME:
            assert get_display_name(node) is None, f"{node} should be hidden"


def test_unknown_node_falls_back_to_title_case_not_AGENT():
    """A future agent without a mapping must not show as 'AGENT' or as a
    raw snake_case identifier."""
    assert get_display_name("new_agent") == "New Agent"
    assert get_display_name(None) is None
    assert get_display_name("") is None


def test_every_compiled_graph_node_has_a_known_mapping():
    """Walk the compiled graph; every node must either map to a display name
    or be explicitly hidden via None. No silent 'AGENT' fallbacks."""
    graph = build_graph()
    nodes = set(graph.get_graph().nodes.keys())
    # Built-in LangGraph internals
    nodes.discard("__start__")
    nodes.discard("__end__")
    for node in nodes:
        display = get_display_name(node)
        # Either a real label or None — never empty string, never "AGENT"
        assert display is None or (isinstance(display, str) and display and display != "AGENT"), (
            f"node {node!r} resolved to invalid display {display!r}"
        )


def test_casing_consistent_title_case():
    """Bug 5 backstop: every visible display name is Title Case (or MARVIN)."""
    for raw, display in _DISPLAY_NAME.items():
        if display is None:
            continue
        assert display[0].isupper(), f"{raw} -> {display!r} not capitalized"
        assert display == display.strip()
