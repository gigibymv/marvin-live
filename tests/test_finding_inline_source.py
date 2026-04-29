"""Inline source persistence on add_finding_to_mission.

Dora gets real URLs from tavily_search and should pass them via
`source_url` + `source_quote` so the finding lands as KNOWN with a
real Source row in one tool call (no separate persist_source step).
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marvin.mission.schema import Hypothesis, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import mission_tools


@pytest.fixture
def store(monkeypatch):
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-src",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-src", s)
    s.save_hypothesis(
        Hypothesis(
            id="hyp-1",
            mission_id="m-src",
            text="Doctolib is structurally profitable in France.",
            label="H1",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: s)
    yield s
    s.close()


def _state():
    return {"mission_id": "m-src"}


def test_inline_source_url_creates_source_row_and_links_finding(store):
    out = mission_tools.add_finding_to_mission(
        claim_text=(
            "Doctolib reported €600M revenue in FY2024 across France, "
            "Germany and Italy with ~150k healthcare professionals."
        ),
        confidence="KNOWN",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-1",
        source_url="https://www.doctolib.fr/about",
        source_quote="Doctolib operates across France, Germany and Italy ...",
        state=_state(),
    )
    assert out["status"] == "saved"

    findings = store.list_findings("m-src")
    assert len(findings) == 1
    assert findings[0].source_id is not None
    assert findings[0].source_type == "web"

    sources = store.list_sources("m-src")
    assert len(sources) == 1
    assert sources[0].id == findings[0].source_id
    assert sources[0].url_or_ref == "https://www.doctolib.fr/about"
    assert sources[0].quote.startswith("Doctolib operates")
    assert sources[0].retrieved_at is not None


def test_known_finding_without_source_url_or_id_is_rejected(store):
    """Schema validator on Finding requires source_id for KNOWN. Without
    inline source_url, the validator surfaces ValueError up to the caller."""
    with pytest.raises(ValueError, match="source_id required"):
        mission_tools.add_finding_to_mission(
            claim_text="A specific claim that should be KNOWN.",
            confidence="KNOWN",
            agent_id="dora",
            workstream_id="W1",
            hypothesis_id="hyp-1",
            state=_state(),
        )


def test_explicit_source_id_wins_over_source_url(store):
    pre = mission_tools.persist_source_for_mission(
        url_or_ref="https://www.doctolib.fr/about",
        quote="primary fact",
        state=_state(),
    )
    explicit_id = pre["source_id"]

    out = mission_tools.add_finding_to_mission(
        claim_text="Specific claim grounded by primary fact.",
        confidence="KNOWN",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-1",
        source_id=explicit_id,
        source_url="https://other-domain.com/should-be-ignored",
        source_quote="ignored",
        state=_state(),
    )
    assert out["status"] == "saved"

    findings = store.list_findings("m-src")
    assert len(findings) == 1
    assert findings[0].source_id == explicit_id
    sources = store.list_sources("m-src")
    assert len(sources) == 1  # only the pre-persisted one, no second row
    assert sources[0].url_or_ref == "https://www.doctolib.fr/about"


def test_source_quote_truncated_to_2000_chars(store):
    out = mission_tools.add_finding_to_mission(
        claim_text="A claim grounded by a long excerpt.",
        confidence="KNOWN",
        agent_id="dora",
        workstream_id="W1",
        hypothesis_id="hyp-1",
        source_url="https://example-real.com/long",
        source_quote="x" * 5000,
        state=_state(),
    )
    assert out["status"] == "saved"
    sources = store.list_sources("m-src")
    assert len(sources[0].quote) == 2000
