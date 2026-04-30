"""Agent-facing tools to query a mission's uploaded data room and transcripts.

These are read-only — uploads happen via API/UI, not via agents. Both
tools require InjectedState (mission_id) and return structured hits
that include the source file/transcript title and a snippet so the
agent can cite it directly: source_url=`data_room://<file_id>` or
`transcript://<id>:<line_start>-<line_end>`.
"""
from __future__ import annotations

from typing import Any

from marvin.ingestion.data_room import search_text
from marvin.ingestion.transcripts import Segment, search_transcript
from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, get_store, require_mission_id

_STORE_FACTORY = MissionStore


def query_data_room(
    query: str, max_files: int = 10, state: InjectedStateArg = None
) -> dict[str, Any]:
    """Search the mission's uploaded data-room files for `query`.

    Returns {hits: [{file_id, filename, line, snippet, ref}, ...], files_searched}.
    `ref` is the citation form to use in source_url. Use the returned
    snippet verbatim as source_quote in add_finding_to_mission.
    Empty result means the query string was not found — do NOT invent
    a quote in that case.
    """
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    files = store.list_data_room_files(mission_id)[:max_files]
    hits: list[dict[str, Any]] = []
    for f in files:
        if not f.parsed_text:
            continue
        for hit in search_text(f.parsed_text, query):
            hits.append({
                "file_id": f.id,
                "filename": f.filename,
                "line": hit["line"],
                "snippet": hit["snippet"],
                "ref": f"data_room://{f.id}#L{hit['line']}",
            })
    return {
        "query": query,
        "hits": hits,
        "files_searched": len(files),
    }


def query_transcripts(
    query: str, max_transcripts: int = 10, state: InjectedStateArg = None
) -> dict[str, Any]:
    """Search uploaded expert-call transcripts for `query`.

    Returns {hits: [{transcript_id, title, expert_name, speaker,
    line_start, line_end, snippet, ref}, ...]}. `ref` form:
    transcript://<id>:<line_start>-<line_end>.
    """
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    transcripts = store.list_transcripts(mission_id)[:max_transcripts]
    hits: list[dict[str, Any]] = []
    for t in transcripts:
        segs_db = store.list_transcript_segments(t.id)
        segs = [
            Segment(
                speaker=s.speaker,
                text=s.text,
                line_start=s.line_start or 0,
                line_end=s.line_end or 0,
            )
            for s in segs_db
        ]
        for hit in search_transcript(segs, query):
            hits.append({
                "transcript_id": t.id,
                "title": t.title,
                "expert_name": t.expert_name,
                "speaker": hit["speaker"],
                "line_start": hit["line_start"],
                "line_end": hit["line_end"],
                "snippet": hit["snippet"],
                "ref": f"transcript://{t.id}:{hit['line_start']}-{hit['line_end']}",
            })
    return {
        "query": query,
        "hits": hits,
        "transcripts_searched": len(transcripts),
    }
