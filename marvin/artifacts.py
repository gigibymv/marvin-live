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

# Legacy markers — accepted when the deterministic Python generators are still
# the source of truth for a deliverable type. Each generator emits these
# substrings verbatim. Once a generator is converted to LLM-driven output,
# its body switches to the new structural markers below.
LEGACY_REFERENCE_MARKERS = {
    "engagement_brief": ("Hypothesis ID:",),
    "workstream_report": ("Finding ID:",),
    "exec_summary": ("Finding ID:",),
    "data_book": ("Finding ID:",),
}

# New structural markers — required when the body is produced by Papyrus LLM.
# Detection is "all markers present" → treat as new-mode; otherwise the body
# is checked against the legacy markers above.
DELIVERABLE_REQUIRED_STRUCTURE = {
    "engagement_brief": (
        "# Engagement Brief",
        "## IC Question",
        "## Hypotheses to Test",
    ),
    "exec_summary": (
        "## Recommendation",
    ),
    "data_book": (
        "## H1",
    ),
    "workstream_report": (
        "## Findings",
        "## Coverage Gaps",
    ),
}

# When a body is in new-mode (structural markers detected), these patterns
# must NOT appear — they leak internal database IDs into client deliverables.
FORBIDDEN_PATTERNS = (
    re.compile(r"\bf-[a-f0-9]{6,}\b"),
    re.compile(r"\bhyp-[a-f0-9]{6,}\b"),
    re.compile(r"Source ID:\s*unassigned", re.IGNORECASE),
    re.compile(r"Agent:\s*(dora|calculus|adversus|merlin|papyrus)", re.IGNORECASE),
)

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


def _has_all_markers(body: str, markers: tuple[str, ...]) -> bool:
    return all(marker in body for marker in markers)


def _body_is_new_structure(body: str, deliverable_type: str | None) -> bool:
    """True when the body matches the LLM-produced structural format."""
    structure = DELIVERABLE_REQUIRED_STRUCTURE.get(deliverable_type or "")
    if not structure:
        return False
    return _has_all_markers(body, structure)


def _body_is_legacy_structure(body: str, deliverable_type: str | None) -> bool:
    markers = LEGACY_REFERENCE_MARKERS.get(deliverable_type or "")
    if not markers:
        return False
    return _has_all_markers(body, markers)


def artifact_body_has_required_references(body: str, deliverable_type: str | None = None) -> bool:
    """Body is valid if it matches EITHER the legacy ID-marker format OR the
    new LLM structural format. Types not registered in either map pass by
    default (e.g., framing_memo)."""
    has_legacy_rules = bool(LEGACY_REFERENCE_MARKERS.get(deliverable_type or ""))
    has_new_rules = bool(DELIVERABLE_REQUIRED_STRUCTURE.get(deliverable_type or ""))
    if not (has_legacy_rules or has_new_rules):
        return True
    return _body_is_legacy_structure(body, deliverable_type) or _body_is_new_structure(body, deliverable_type)


def artifact_body_has_forbidden_ids(body: str, deliverable_type: str | None = None) -> bool:
    """Forbidden ID/agent leakage is enforced when the body is in new-mode
    (LLM structural format). Legacy deterministic outputs are exempt because
    they intentionally embed the IDs as traceability anchors."""
    if not _body_is_new_structure(body, deliverable_type):
        return False
    return any(pattern.search(body) for pattern in FORBIDDEN_PATTERNS)


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
    if artifact_body_has_forbidden_ids(body, deliverable_type):
        errors.append("contains forbidden internal IDs")
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
