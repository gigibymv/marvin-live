"""H2 hypothesis_id normalization slice.

Recoverable formatting noise around an otherwise-valid hyp ID is normalized
before validation. Truly invalid / ambiguous IDs are still rejected by the
unchanged allowed-set FK guard. No similarity matching, no fallback.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from marvin.mission.schema import Hypothesis, Mission
from marvin.mission.store import MissionStore, _seed_standard_workplan
from marvin.tools import adversus_tools, mission_tools
from marvin.tools.common import normalize_hypothesis_id


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MissionStore:
    s = MissionStore(":memory:")
    s.save_mission(
        Mission(
            id="m-h",
            client="C",
            target="T",
            ic_question="Q?",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    _seed_standard_workplan("m-h", s)
    s.save_hypothesis(
        Hypothesis(
            id="hyp-79a14102",
            mission_id="m-h",
            text="AcmeH2 has a durable competitive advantage",
            status="active",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    monkeypatch.setattr(mission_tools, "_STORE_FACTORY", lambda: s)
    monkeypatch.setattr(adversus_tools, "_STORE_FACTORY", lambda: s)
    yield s
    s.close()


# --- pure normalizer unit tests ----------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("hyp-79a14102", "hyp-79a14102"),
    ("  hyp-79a14102  ", "hyp-79a14102"),
    ("[hyp-79a14102]", "hyp-79a14102"),
    ("(hyp-79a14102)", "hyp-79a14102"),
    ("<hyp-79a14102>", "hyp-79a14102"),
    ('"hyp-79a14102"', "hyp-79a14102"),
    ("'hyp-79a14102'", "hyp-79a14102"),
    ("`hyp-79a14102`", "hyp-79a14102"),
    ("[hyp-79a14102] AcmeH2 has durable competitive advantage", "hyp-79a14102"),
    ("hyp-79a14102.", "hyp-79a14102"),
    ("[hyp-79a14102],", "hyp-79a14102"),
])
def test_normalize_accepts_recoverable_noise(raw, expected):
    assert normalize_hypothesis_id(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "   ",
    "hypothesis 1",                       # first token has no hyp- shape
    "the first hypothesis hyp-79a14102",  # leading text — not recoverable
    "hyp-bad!@#",                         # malformed body
])
def test_normalize_does_not_invent_valid_ids(raw):
    """Normalizer never produces a `hyp-[a-f0-9]+` from non-hyp inputs."""
    out = normalize_hypothesis_id(raw)
    assert out == raw.strip() or not out.startswith("hyp-") or out == ""


# --- end-to-end through add_finding_to_mission --------------------------------

def _state() -> dict:
    return {"mission_id": "m-h"}


def test_add_finding_accepts_bracketed_id_with_trailing_text(store: MissionStore):
    result = mission_tools.add_finding_to_mission(
        claim_text="Generic market claim under evidence test.", confidence="REASONED",
        hypothesis_id="[hyp-79a14102] AcmeH2 has a durable competitive advantage",
        state=_state(),
    )
    assert result["finding_id"]
    findings = store.list_findings("m-h")
    assert findings[-1].hypothesis_id == "hyp-79a14102"


def test_add_finding_accepts_quoted_id(store: MissionStore):
    result = mission_tools.add_finding_to_mission(
        claim_text="Generic market claim under evidence test.", confidence="REASONED",
        hypothesis_id='"hyp-79a14102"',
        state=_state(),
    )
    assert store.list_findings("m-h")[-1].hypothesis_id == "hyp-79a14102"


def test_add_finding_rejects_truly_invalid_id(store: MissionStore):
    result = mission_tools.add_finding_to_mission(
        claim_text="Generic market claim under evidence test.", confidence="REASONED",
        hypothesis_id="hyp-99999999",
        state=_state(),
    )
    assert result["status"] == "rejected"
    assert "not a valid hypothesis" in result["reason"]


def test_add_finding_rejects_ambiguous_string(store: MissionStore):
    result = mission_tools.add_finding_to_mission(
        claim_text="Generic market claim under evidence test.", confidence="REASONED",
        hypothesis_id="the first hypothesis hyp-79a14102",
        state=_state(),
    )
    # normalization extracts hyp-79a14102 which is not in the seeded set, so reject.
    assert result["status"] == "rejected"


def test_add_finding_no_hypothesis_path_rejected(store: MissionStore):
    """Bug 2 (chantier 2.6): missing hypothesis_id is now a rejection."""
    result = mission_tools.add_finding_to_mission(
        claim_text="general market claim with sustained content.", confidence="REASONED",
        state=_state(),
    )
    assert result["status"] == "rejected"
    assert store.list_findings("m-h") == []


# --- attack_hypothesis (adversus) ---------------------------------------------

def test_attack_hypothesis_accepts_bracketed_id(store: MissionStore):
    result = adversus_tools.attack_hypothesis(
        hypothesis_id="[hyp-79a14102]", angle="demand", state=_state(),
    )
    assert result["hypothesis_id"] == "hyp-79a14102"


def test_attack_hypothesis_rejects_invalid_id(store: MissionStore):
    with pytest.raises(ValueError, match="not a valid hypothesis"):
        adversus_tools.attack_hypothesis(
            hypothesis_id="hyp-99999999", angle="demand", state=_state(),
        )
