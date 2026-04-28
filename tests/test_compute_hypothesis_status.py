"""Chantier 4: tests for compute_hypothesis_status (pure function)."""
from __future__ import annotations

from marvin.mission.schema import Finding
from marvin.tools.mission_tools import compute_hypothesis_status


def _f(*, conf: str, agent: str = "calculus", source: str | None = "src-1", _id: str = "f") -> Finding:
    return Finding(
        id=_id,
        mission_id="m",
        hypothesis_id="hyp-1",
        claim_text="claim",
        confidence=conf,
        source_id=source if conf == "KNOWN" else None,
        agent_id=agent,
    )


def test_not_started_when_empty() -> None:
    r = compute_hypothesis_status([])
    assert r["status"] == "NOT_STARTED"
    assert r["total"] == 0


def test_supported_with_two_known_and_no_contradicting() -> None:
    findings = [_f(conf="KNOWN", _id=f"f{i}") for i in range(2)]
    r = compute_hypothesis_status(findings)
    assert r["status"] == "SUPPORTED"
    assert r["known"] == 2
    assert r["contradicting"] == 0


def test_weakened_when_adversus_contradicts() -> None:
    findings = [
        _f(conf="KNOWN", _id="f1"),
        _f(conf="KNOWN", _id="f2"),
        _f(conf="REASONED", agent="adversus", source=None, _id="f3"),
    ]
    r = compute_hypothesis_status(findings)
    assert r["status"] == "WEAKENED"
    assert r["contradicting"] == 1


def test_weakened_when_majority_low_confidence() -> None:
    findings = [
        _f(conf="LOW_CONFIDENCE", source=None, _id="f1"),
        _f(conf="LOW_CONFIDENCE", source=None, _id="f2"),
        _f(conf="REASONED", source=None, _id="f3"),
    ]
    r = compute_hypothesis_status(findings)
    assert r["status"] == "WEAKENED"
    assert r["low_confidence"] == 2


def test_testing_when_only_reasoned() -> None:
    findings = [_f(conf="REASONED", source=None, _id="f1")]
    r = compute_hypothesis_status(findings)
    assert r["status"] == "TESTING"


def test_testing_when_one_known_only() -> None:
    findings = [
        _f(conf="KNOWN", _id="f1"),
        _f(conf="REASONED", source=None, _id="f2"),
    ]
    r = compute_hypothesis_status(findings)
    assert r["status"] == "TESTING"
