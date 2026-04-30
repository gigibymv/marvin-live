"""Expert-call transcript parsing.

Splits raw transcript text into speaker-tagged segments using common
formats:
  - "Speaker Name:" at line start
  - "[Name]" or "<Name>" at line start
  - Tegus-style "Q:" / "A:" markers
  - Timestamp prefixes "[00:01:23]"

Speaker tagging is heuristic by design — when the format is ambiguous,
the segment is tagged speaker=None and the text is preserved verbatim.
The agent-facing query_transcripts tool returns segments + line ranges
so findings can cite "Transcript {title}, line {N}-{M}".
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_SPEAKER_PATTERNS = [
    # "Q:" / "A:" — Tegus / interview style
    re.compile(r"^\s*(Q|A)\s*:\s*", re.IGNORECASE),
    # "[Speaker Name]" or "<Speaker Name>"
    re.compile(r"^\s*[\[<]([^\]>]+)[\]>]\s*:?\s*"),
    # "Speaker Name: ..."  (1-4 capitalized words, then colon)
    re.compile(r"^\s*((?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}|[A-Z]+))\s*:\s+"),
]
_TIMESTAMP_RE = re.compile(r"^\s*\[\d{1,2}:\d{2}(?::\d{2})?\]\s*")


@dataclass
class Segment:
    speaker: str | None
    text: str
    line_start: int
    line_end: int


def parse_transcript(raw: str) -> list[Segment]:
    """Split raw transcript text into speaker-tagged segments.

    A segment is a maximal run of lines attributed to the same speaker.
    Speakerless prologue lines become a single segment with speaker=None.
    """
    lines = raw.splitlines()
    segments: list[Segment] = []
    current_speaker: str | None = None
    current_lines: list[str] = []
    current_start = 1

    def flush(end_line: int) -> None:
        if not current_lines:
            return
        text = "\n".join(current_lines).strip()
        if text:
            segments.append(
                Segment(
                    speaker=current_speaker,
                    text=text,
                    line_start=current_start,
                    line_end=end_line,
                )
            )

    for idx, raw_line in enumerate(lines, start=1):
        # strip leading timestamp if any
        line = _TIMESTAMP_RE.sub("", raw_line)
        speaker = _detect_speaker(line)
        if speaker is not None:
            flush(idx - 1)
            current_speaker = speaker
            current_lines = [_strip_speaker_prefix(line, speaker)]
            current_start = idx
        else:
            current_lines.append(line)

    flush(len(lines))
    return segments


def _detect_speaker(line: str) -> str | None:
    for pat in _SPEAKER_PATTERNS:
        m = pat.match(line)
        if m:
            return m.group(1).strip()
    return None


def _strip_speaker_prefix(line: str, speaker: str) -> str:
    for pat in _SPEAKER_PATTERNS:
        m = pat.match(line)
        if m and m.group(1).strip() == speaker:
            return line[m.end():].strip()
    return line


def search_transcript(
    segments: list[Segment], query: str, max_hits: int = 5
) -> list[dict]:
    """Substring search across segments. Returns [{speaker, line_start,
    line_end, snippet}, ...]."""
    if not query.strip():
        return []
    needle = query.lower()
    out: list[dict] = []
    for seg in segments:
        if needle in seg.text.lower():
            snippet = seg.text[:280].replace("\n", " ")
            out.append({
                "speaker": seg.speaker,
                "line_start": seg.line_start,
                "line_end": seg.line_end,
                "snippet": snippet,
            })
            if len(out) >= max_hits:
                break
    return out
