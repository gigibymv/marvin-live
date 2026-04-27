from __future__ import annotations

import re
from pathlib import Path

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


def artifact_file_is_ready(file_path: str | Path | None) -> bool:
    if not file_path:
        return False
    path = Path(file_path)
    try:
        if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
            return False
        body = path.read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        return False
    return not artifact_body_has_placeholder(body)
