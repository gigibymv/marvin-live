from __future__ import annotations

import re
from pathlib import Path

# These thresholds are intentionally low: they catch empty/template-only output
# without pretending to be a writing-quality score.
MIN_ARTIFACT_CHARS = 220
DELIVERABLE_MIN_CHARS = {
    "engagement_brief": 320,
    "workstream_report": 240,
    "exec_summary": 260,
    "data_book": 240,
}
DELIVERABLE_REFERENCE_MARKERS = {
    "engagement_brief": ("Hypothesis ID:",),
    "workstream_report": ("Finding ID:",),
    "exec_summary": ("Finding ID:",),
    "data_book": ("Finding ID:",),
}
PLACEHOLDER_LINE_MARKERS = frozenset(
    {
        "- no hypotheses yet",
        "- no findings yet",
        "% marvin generated placeholder report",
    }
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"^ic question:\s*n/a\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bgenerated placeholder\b", re.IGNORECASE),
    re.compile(r"\bplaceholder (report|artifact|deliverable|content)\b", re.IGNORECASE),
)


def artifact_body_has_placeholder(body: str) -> bool:
    lines = {line.strip().lower() for line in body.splitlines()}
    if PLACEHOLDER_LINE_MARKERS.intersection(lines):
        return True
    return any(pattern.search(body) for pattern in PLACEHOLDER_PATTERNS)


def artifact_body_has_required_references(body: str, deliverable_type: str | None = None) -> bool:
    markers = DELIVERABLE_REFERENCE_MARKERS.get(deliverable_type or "")
    if not markers:
        return True
    return all(marker in body for marker in markers)


def artifact_body_meets_minimum_length(body: str, deliverable_type: str | None = None) -> bool:
    min_chars = DELIVERABLE_MIN_CHARS.get(deliverable_type or "", MIN_ARTIFACT_CHARS)
    return len(body.strip()) >= min_chars


def artifact_body_is_ready(body: str, deliverable_type: str | None = None) -> bool:
    return not artifact_body_readiness_errors(body, deliverable_type)


def artifact_body_readiness_errors(body: str, deliverable_type: str | None = None) -> list[str]:
    errors: list[str] = []
    if not artifact_body_meets_minimum_length(body, deliverable_type):
        errors.append("too short")
    if artifact_body_has_placeholder(body):
        errors.append("contains placeholder content")
    if not artifact_body_has_required_references(body, deliverable_type):
        errors.append("missing required references")
    return errors


def artifact_file_readiness_errors(file_path: str | Path | None, deliverable_type: str | None = None) -> list[str]:
    if not file_path:
        return ["missing file path"]
    path = Path(file_path)
    try:
        if not path.exists() or not path.is_file():
            return ["file does not exist"]
        if path.stat().st_size <= 0:
            return ["empty file"]
        body = path.read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        return ["file cannot be read"]
    return artifact_body_readiness_errors(body, deliverable_type)


def artifact_file_is_ready(file_path: str | Path | None, deliverable_type: str | None = None) -> bool:
    return not artifact_file_readiness_errors(file_path, deliverable_type)
