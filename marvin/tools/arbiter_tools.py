from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from marvin.mission.store import MissionStore

_STORE_FACTORY = MissionStore
_MOVING_TOPIC_TERMS = ("market", "growth", "revenue", "gmv", "pricing", "share")


def check_internal_consistency(mission_id: str) -> dict[str, Any]:
    store = _STORE_FACTORY()
    findings = store.list_findings(mission_id)
    sources = {source.id: source for source in store.list_sources(mission_id)}
    inconsistencies: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []

    for finding in findings:
        if finding.confidence == "KNOWN" and not finding.source_id:
            inconsistencies.append({"type": "missing_source", "finding_id": finding.id, "claim_text": finding.claim_text})

    by_claim: dict[str, list[Any]] = defaultdict(list)
    for finding in findings:
        by_claim[finding.claim_text.strip().lower()].append(finding)
    for claim, claim_findings in by_claim.items():
        source_ids = {finding.source_id for finding in claim_findings}
        confidences = {finding.confidence for finding in claim_findings}
        if len(claim_findings) > 1 and (len(source_ids) > 1 or len(confidences) > 1):
            inconsistencies.append(
                {
                    "type": "contradiction",
                    "claim_text": claim,
                    "finding_ids": [finding.id for finding in claim_findings],
                }
            )

    freshness_cutoff = datetime.now(UTC) - timedelta(days=18 * 30)
    for finding in findings:
        if not finding.source_id or not any(term in finding.claim_text.lower() for term in _MOVING_TOPIC_TERMS):
            continue
        source = sources.get(finding.source_id)
        if source is None or source.retrieved_at is None:
            continue
        try:
            retrieved_at = datetime.fromisoformat(source.retrieved_at)
        except ValueError:
            continue
        if retrieved_at.tzinfo is None:
            retrieved_at = retrieved_at.replace(tzinfo=UTC)
        if retrieved_at < freshness_cutoff:
            flags.append({"type": "stale_source", "finding_id": finding.id, "source_id": source.id})

    return {"mission_id": mission_id, "inconsistencies": inconsistencies, "flags": flags}
