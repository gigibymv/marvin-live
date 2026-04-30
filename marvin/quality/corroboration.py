"""C4 — source corroboration policy.

Rule: a KNOWN finding must be backed by at least 2 independent sources.
"Independent" means the (domain, source_type) pair differs between the
sources. Two SEC filings of the same company are NOT independent (same
issuer); two web pages from the same domain are NOT independent.
Two pages from different domains are independent. A SEC filing and a
data-room file are independent.

When a finding is KNOWN with <2 independent sources, downgrade to
REASONED and record `corroboration_status='downgraded'`. When ≥2,
mark `corroboration_status='corroborated'`. Single-source findings
that started as REASONED/LOW_CONFIDENCE keep their confidence and
get `corroboration_status='single_source'`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse


def extract_domain(url_or_ref: str | None) -> str:
    if not url_or_ref:
        return ""
    s = url_or_ref.strip()
    # special schemes used by data-room and transcript refs
    if s.startswith("data_room://"):
        return "data_room"
    if s.startswith("transcript://"):
        return "transcript"
    try:
        netloc = urlparse(s).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


@dataclass
class CorroborationResult:
    independent_count: int
    status: str   # 'corroborated' | 'single_source'
    final_confidence: str
    downgrade_reason: str | None


def _key(source) -> tuple[str, str]:
    return (extract_domain(getattr(source, "url_or_ref", None)),
            (getattr(source, "source_type", None) or "unknown"))


def independent_source_count(sources: Iterable) -> int:
    """Count distinct (domain, source_type) groups across sources.

    Sources lacking both url and type don't count toward independence.
    """
    seen: set[tuple[str, str]] = set()
    for s in sources:
        k = _key(s)
        if k == ("", "unknown"):
            continue
        seen.add(k)
    return len(seen)


def evaluate_corroboration(
    confidence: str, sources: Iterable
) -> CorroborationResult:
    """Return the corroboration verdict for a finding.

    KNOWN with <2 independent sources is downgraded to REASONED and
    flagged 'downgraded'. KNOWN with >=2 is 'corroborated'. Anything
    else is 'single_source' (current confidence preserved).
    """
    sources_list = list(sources)
    n = independent_source_count(sources_list)
    if confidence == "KNOWN" and n < 2:
        return CorroborationResult(
            independent_count=n,
            status="downgraded",
            final_confidence="REASONED",
            downgrade_reason=(
                f"KNOWN requires ≥2 independent sources; found {n}. "
                "Auto-downgraded to REASONED."
            ),
        )
    if n >= 2:
        return CorroborationResult(
            independent_count=n, status="corroborated",
            final_confidence=confidence, downgrade_reason=None,
        )
    return CorroborationResult(
        independent_count=n, status="single_source",
        final_confidence=confidence, downgrade_reason=None,
    )
