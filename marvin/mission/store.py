from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


def _decode_json_list(value: object) -> list[str]:
    """Decode a JSON-encoded TEXT column into a list of strings, defensively."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return []
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
    return []

from marvin.mission.schema import (
    DataRoomFile,
    DealTerms,
    Deliverable,
    Finding,
    Gate,
    Hypothesis,
    MerlinVerdict,
    Milestone,
    Mission,
    MissionBrief,
    Source,
    Transcript,
    TranscriptSegment,
    Workstream,
)


def _default_db_path() -> Path:
    if env_path := os.getenv("MARVIN_DB_PATH"):
        return Path(env_path).expanduser().resolve()
    return Path.home() / ".marvin" / "marvin.db"


def _seed_standard_workplan(mission_id: str, store: "MissionStore") -> None:
    workstreams = (
        Workstream(
            id="W1",
            mission_id=mission_id,
            label="Market and competitive analysis",
            assigned_agent="dora",
        ),
        Workstream(
            id="W2",
            mission_id=mission_id,
            label="Financial analysis",
            assigned_agent="calculus",
        ),
        Workstream(
            id="W3",
            mission_id=mission_id,
            label="Storyline synthesis",
            assigned_agent="merlin",
        ),
        Workstream(
            id="W4",
            mission_id=mission_id,
            label="Red-team and stress testing",
            assigned_agent="adversus",
        ),
    )
    milestones = (
        Milestone(
            id="W1.1",
            mission_id=mission_id,
            workstream_id="W1",
            label="Market size and growth",
            scheduled_day=3,
        ),
        Milestone(
            id="W1.2",
            mission_id=mission_id,
            workstream_id="W1",
            label="Competitive mapping",
            scheduled_day=3,
        ),
        Milestone(
            id="W1.3",
            mission_id=mission_id,
            workstream_id="W1",
            label="Moat assessment",
            scheduled_day=3,
        ),
        Milestone(
            id="W2.1",
            mission_id=mission_id,
            workstream_id="W2",
            label="Unit economics and QoE",
            scheduled_day=3,
        ),
        Milestone(
            id="W2.2",
            mission_id=mission_id,
            workstream_id="W2",
            label="Public filings review",
            scheduled_day=3,
        ),
        Milestone(
            id="W2.3",
            mission_id=mission_id,
            workstream_id="W2",
            label="Anomaly detection",
            scheduled_day=3,
        ),
        Milestone(
            id="W3.1",
            mission_id=mission_id,
            workstream_id="W3",
            label="Storyline synthesis",
            scheduled_day=10,
        ),
        Milestone(
            id="W3.2",
            mission_id=mission_id,
            workstream_id="W3",
            label="SHIP verdict",
            scheduled_day=10,
        ),
        Milestone(
            id="W4.1",
            mission_id=mission_id,
            workstream_id="W4",
            label="Red-team hypotheses",
            scheduled_day=10,
        ),
        Milestone(
            id="W4.2",
            mission_id=mission_id,
            workstream_id="W4",
            label="Stress scenarios and PESTEL",
            scheduled_day=10,
        ),
    )
    gates = (
        Gate(
            id=f"gate-{mission_id}-hyp-confirm",
            mission_id=mission_id,
            gate_type="hypothesis_confirmation",
            scheduled_day=0,
            format="review_claims",
        ),
        Gate(
            id=f"gate-{mission_id}-G1",
            mission_id=mission_id,
            gate_type="manager_review",
            scheduled_day=3,
            format="review_claims",
        ),
        Gate(
            id=f"gate-{mission_id}-G3",
            mission_id=mission_id,
            gate_type="final_review",
            scheduled_day=10,
            format="review_claims",
        ),
    )

    for workstream in workstreams:
        store.save_workstream(workstream)
    for milestone in milestones:
        store.save_milestone(milestone)
    for gate in gates:
        store.save_gate(gate)


class MissionStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        resolved_path = _default_db_path() if db_path is None else db_path
        self.db_path = str(resolved_path)
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        connection_target = ":memory:" if self.db_path == ":memory:" else str(Path(self.db_path).expanduser())
        self._conn = sqlite3.connect(connection_target)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._initialize_schema()

    def close(self) -> None:
        self._conn.close()

    def _initialize_schema(self) -> None:
        schema_path = Path(__file__).with_name("001_init.sql")
        self._conn.executescript(schema_path.read_text(encoding="utf-8"))
        self._conn.commit()
        self._apply_additive_migrations()

    def _apply_additive_migrations(self) -> None:
        """Add columns introduced after initial schema, idempotent for existing DBs."""
        for table, column, ddl in (
            ("missions", "active_agent", "ALTER TABLE missions ADD COLUMN active_agent TEXT"),
            ("deliverables", "status", "ALTER TABLE deliverables ADD COLUMN status TEXT DEFAULT 'pending'"),
            (
                "missions",
                "clarification_rounds_used",
                "ALTER TABLE missions ADD COLUMN clarification_rounds_used INTEGER DEFAULT 0",
            ),
            (
                "missions",
                "clarification_answers",
                "ALTER TABLE missions ADD COLUMN clarification_answers TEXT DEFAULT '[]'",
            ),
            ("gates", "questions", "ALTER TABLE gates ADD COLUMN questions TEXT"),
            ("hypotheses", "label", "ALTER TABLE hypotheses ADD COLUMN label TEXT"),
            ("missions", "data_room_path", "ALTER TABLE missions ADD COLUMN data_room_path TEXT"),
            ("findings", "impact", "ALTER TABLE findings ADD COLUMN impact TEXT"),
            ("findings", "source_type", "ALTER TABLE findings ADD COLUMN source_type TEXT"),
            (
                "findings",
                "corroboration_count",
                "ALTER TABLE findings ADD COLUMN corroboration_count INTEGER DEFAULT 1",
            ),
            (
                "findings",
                "corroboration_status",
                "ALTER TABLE findings ADD COLUMN corroboration_status TEXT",
            ),
            ("sources", "source_type", "ALTER TABLE sources ADD COLUMN source_type TEXT"),
            # C-PER-MILESTONE — link findings + deliverables to a milestone row.
            ("findings", "milestone_id", "ALTER TABLE findings ADD COLUMN milestone_id TEXT"),
            ("deliverables", "milestone_id", "ALTER TABLE deliverables ADD COLUMN milestone_id TEXT"),
        ):
            cols = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in cols:
                self._conn.execute(ddl)
        self._conn.commit()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cursor = self._conn.execute(sql, params)
        self._conn.commit()
        return cursor

    @staticmethod
    def _row_to_model(row: sqlite3.Row | None, model_cls):
        if row is None:
            return None
        data = dict(row)
        if model_cls is Mission:
            raw = data.get("clarification_answers")
            data["clarification_answers"] = _decode_json_list(raw)
        if model_cls is Gate:
            raw = data.get("questions")
            data["questions"] = _decode_json_list(raw) or None
        return model_cls.model_validate(data)

    def save_mission(self, mission: Mission) -> Mission:
        self._execute(
            """
            INSERT OR REPLACE INTO missions
            (id, client, target, mission_type, ic_question, status, active_agent, created_at, updated_at,
             clarification_rounds_used, clarification_answers, data_room_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mission.id,
                mission.client,
                mission.target,
                mission.mission_type,
                mission.ic_question,
                mission.status,
                mission.active_agent,
                mission.created_at,
                mission.updated_at,
                int(mission.clarification_rounds_used or 0),
                json.dumps(list(mission.clarification_answers or [])),
                mission.data_room_path,
            ),
        )
        return mission

    def update_mission_active_agent(self, mission_id: str, active_agent: str | None) -> None:
        """Set the currently-active agent on a mission row. No-op if mission missing."""
        self._execute(
            "UPDATE missions SET active_agent = ? WHERE id = ?",
            (active_agent, mission_id),
        )

    def update_mission_status(self, mission_id: str, status: str) -> None:
        """Transition mission status (e.g. active → complete). No-op if mission missing."""
        self._execute(
            "UPDATE missions SET status = ? WHERE id = ?",
            (status, mission_id),
        )

    def get_mission(self, mission_id: str) -> Mission:
        row = self._execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
        mission = self._row_to_model(row, Mission)
        if mission is None:
            raise KeyError(f"mission not found: {mission_id}")
        return mission

    def list_missions(self) -> list[Mission]:
        rows = self._execute("SELECT * FROM missions ORDER BY created_at, id").fetchall()
        return [self._row_to_model(row, Mission) for row in rows]

    def save_mission_brief(self, brief: MissionBrief) -> MissionBrief:
        try:
            self._conn.execute("BEGIN")
            result = self._conn.execute(
                "UPDATE missions SET ic_question = ?, updated_at = ? WHERE id = ?",
                (brief.ic_question, brief.updated_at, brief.mission_id),
            )
            if result.rowcount == 0:
                raise KeyError(f"mission not found: {brief.mission_id}")
            self._conn.execute(
                """
                INSERT OR REPLACE INTO mission_briefs
                (mission_id, raw_brief, ic_question, mission_angle, brief_summary,
                 workstream_plan_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    brief.mission_id,
                    brief.raw_brief,
                    brief.ic_question,
                    brief.mission_angle,
                    brief.brief_summary,
                    brief.workstream_plan_json,
                    brief.created_at,
                    brief.updated_at,
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return brief

    def get_mission_brief(self, mission_id: str) -> MissionBrief | None:
        row = self._execute(
            "SELECT * FROM mission_briefs WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()
        return self._row_to_model(row, MissionBrief)

    def save_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        self._execute(
            """
            INSERT OR REPLACE INTO hypotheses
            (id, mission_id, text, label, status, abandon_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hypothesis.id,
                hypothesis.mission_id,
                hypothesis.text,
                hypothesis.label,
                hypothesis.status,
                hypothesis.abandon_reason,
                hypothesis.created_at,
            ),
        )
        return hypothesis

    def list_hypotheses(self, mission_id: str, status: str | None = None) -> list[Hypothesis]:
        sql = "SELECT * FROM hypotheses WHERE mission_id = ?"
        params: list[str] = [mission_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at, id"
        rows = self._execute(sql, tuple(params)).fetchall()
        # Defensive: backfill labels for legacy rows that pre-date the column
        # so user-facing surfaces always show H1/H2/H3 (Bug 4).
        out: list[Hypothesis] = []
        for idx, row in enumerate(rows, start=1):
            data = dict(row)
            if not data.get("label"):
                data["label"] = f"H{idx}"
            out.append(Hypothesis.model_validate(data))
        return out

    def update_hypothesis(
        self,
        hypothesis_id: str,
        status: str,
        abandon_reason: str | None = None,
    ) -> Hypothesis:
        existing = self._execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone()
        if existing is None:
            raise KeyError(f"hypothesis not found: {hypothesis_id}")
        self._execute(
            "UPDATE hypotheses SET status = ?, abandon_reason = ? WHERE id = ?",
            (status, abandon_reason, hypothesis_id),
        )
        updated = self._execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone()
        return Hypothesis.model_validate(dict(updated))

    def save_workstream(self, workstream: Workstream) -> Workstream:
        self._execute(
            """
            INSERT OR REPLACE INTO workstreams
            (id, mission_id, label, assigned_agent, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                workstream.id,
                workstream.mission_id,
                workstream.label,
                workstream.assigned_agent,
                workstream.status,
            ),
        )
        return workstream

    def list_workstreams(self, mission_id: str) -> list[Workstream]:
        rows = self._execute(
            "SELECT * FROM workstreams WHERE mission_id = ? ORDER BY id",
            (mission_id,),
        ).fetchall()
        return [Workstream.model_validate(dict(row)) for row in rows]

    def mark_workstream_delivered(self, mission_id: str, workstream_id: str) -> Workstream:
        result = self._execute(
            "UPDATE workstreams SET status = 'delivered' WHERE mission_id = ? AND id = ?",
            (mission_id, workstream_id),
        )
        if result.rowcount == 0:
            raise KeyError(f"workstream not found: {mission_id}/{workstream_id}")
        row = self._execute(
            "SELECT * FROM workstreams WHERE mission_id = ? AND id = ?",
            (mission_id, workstream_id),
        ).fetchone()
        return Workstream.model_validate(dict(row))

    def save_milestone(self, milestone: Milestone) -> Milestone:
        self._execute(
            """
            INSERT OR REPLACE INTO milestones
            (id, mission_id, workstream_id, label, status, result_summary, scheduled_day)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                milestone.id,
                milestone.mission_id,
                milestone.workstream_id,
                milestone.label,
                milestone.status,
                milestone.result_summary,
                milestone.scheduled_day,
            ),
        )
        return milestone

    def list_milestones(self, mission_id: str) -> list[Milestone]:
        rows = self._execute(
            "SELECT * FROM milestones WHERE mission_id = ? ORDER BY id",
            (mission_id,),
        ).fetchall()
        return [Milestone.model_validate(dict(row)) for row in rows]

    def mark_milestone_delivered(
        self,
        milestone_id: str,
        result_summary: str,
        mission_id: str | None = None,
    ) -> Milestone:
        if mission_id is None:
            row = self._execute("SELECT * FROM milestones WHERE id = ?", (milestone_id,)).fetchone()
            if row is None:
                raise KeyError(f"milestone not found: {milestone_id}")
            mission_id = row["mission_id"]
        # Idempotent contract: a milestone can be marked delivered by multiple
        # callers (LLM tool path AND deterministic research_join safety net).
        # The state transition pending → delivered happens at most once; treat
        # the redundant call as a no-op so listeners see one event per real
        # business transition, not one per write.
        existing = self._execute(
            "SELECT * FROM milestones WHERE mission_id = ? AND id = ?",
            (mission_id, milestone_id),
        ).fetchone()
        if existing is None:
            raise KeyError(f"milestone not found: {mission_id}/{milestone_id}")
        if existing["status"] == "delivered":
            return Milestone.model_validate(dict(existing))

        self._execute(
            """
            UPDATE milestones
            SET status = 'delivered', result_summary = ?
            WHERE mission_id = ? AND id = ?
            """,
            (result_summary, mission_id, milestone_id),
        )
        row = self._execute(
            "SELECT * FROM milestones WHERE mission_id = ? AND id = ?",
            (mission_id, milestone_id),
        ).fetchone()
        milestone = Milestone.model_validate(dict(row))
        from marvin.events import emit_milestone_persisted

        emit_milestone_persisted(
            mission_id,
            {
                "milestone_id": milestone.id,
                "label": milestone.label,
                "status": milestone.status,
                "workstream_id": milestone.workstream_id,
                "result_summary": milestone.result_summary,
            },
        )
        return milestone

    def mark_milestone_blocked(
        self,
        milestone_id: str,
        reason: str,
        mission_id: str,
    ) -> Milestone:
        """Mark a milestone as blocked because the responsible agent produced
        no findings. Distinct from 'delivered' (real progress) and 'pending'
        (not yet attempted). Research coverage reports the count separately
        so the UI can display "X delivered, Y blocked" honestly.
        """
        existing = self._execute(
            "SELECT * FROM milestones WHERE mission_id = ? AND id = ?",
            (mission_id, milestone_id),
        ).fetchone()
        if existing is None:
            raise KeyError(f"milestone not found: {mission_id}/{milestone_id}")
        # Idempotent: once blocked, stay blocked. A later finding could
        # legitimately flip a milestone from blocked → delivered, but that
        # transition belongs to mark_milestone_delivered, not here.
        if existing["status"] in ("blocked", "delivered"):
            return Milestone.model_validate(dict(existing))

        self._execute(
            """
            UPDATE milestones
            SET status = 'blocked', result_summary = ?
            WHERE mission_id = ? AND id = ?
            """,
            (reason, mission_id, milestone_id),
        )
        row = self._execute(
            "SELECT * FROM milestones WHERE mission_id = ? AND id = ?",
            (mission_id, milestone_id),
        ).fetchone()
        milestone = Milestone.model_validate(dict(row))
        from marvin.events import emit_milestone_persisted

        emit_milestone_persisted(
            mission_id,
            {
                "milestone_id": milestone.id,
                "label": milestone.label,
                "status": milestone.status,
                "workstream_id": milestone.workstream_id,
                "result_summary": milestone.result_summary,
            },
        )
        return milestone

    def save_finding(self, finding: Finding) -> Finding:
        if finding.confidence == "KNOWN" and not finding.source_id:
            raise ValueError("source_id required for KNOWN findings")
        self._execute(
            """
            INSERT OR REPLACE INTO findings
            (id, mission_id, workstream_id, hypothesis_id, claim_text, confidence,
             source_id, agent_id, human_validated, created_at, impact, source_type,
             corroboration_count, corroboration_status, milestone_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.id,
                finding.mission_id,
                finding.workstream_id,
                finding.hypothesis_id,
                finding.claim_text,
                finding.confidence,
                finding.source_id,
                finding.agent_id,
                int(finding.human_validated),
                finding.created_at,
                finding.impact,
                finding.source_type,
                finding.corroboration_count,
                finding.corroboration_status,
                finding.milestone_id,
            ),
        )
        # Mirror the primary source into finding_sources for uniform lookup,
        # but ONLY if the source_id actually exists in sources. The LLM
        # occasionally passes a URL string as source_id; we let the finding
        # save with that bogus id (back-compat), but we will not propagate
        # the bad ref into the join table where the FK would fire.
        if finding.source_id:
            row = self._conn.execute(
                "SELECT 1 FROM sources WHERE id = ? LIMIT 1", (finding.source_id,)
            ).fetchone()
            if row is not None:
                self._conn.execute(
                    "INSERT OR IGNORE INTO finding_sources (finding_id, source_id) VALUES (?, ?)",
                    (finding.id, finding.source_id),
                )
                self._conn.commit()
        return finding

    def add_finding_source(self, finding_id: str, source_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO finding_sources (finding_id, source_id) VALUES (?, ?)",
            (finding_id, source_id),
        )
        self._conn.commit()

    def list_finding_sources(self, finding_id: str) -> list[Source]:
        rows = self._execute(
            "SELECT s.* FROM sources s "
            "JOIN finding_sources fs ON fs.source_id = s.id "
            "WHERE fs.finding_id = ? ORDER BY s.retrieved_at, s.id",
            (finding_id,),
        ).fetchall()
        return [Source.model_validate(dict(r)) for r in rows]

    def get_finding(self, finding_id: str) -> Finding | None:
        row = self._execute(
            "SELECT * FROM findings WHERE id = ?", (finding_id,)
        ).fetchone()
        return Finding.model_validate(dict(row)) if row else None

    def update_finding_corroboration(
        self,
        finding_id: str,
        count: int,
        status: str,
        confidence: str | None = None,
    ) -> None:
        if confidence is None:
            self._execute(
                "UPDATE findings SET corroboration_count = ?, corroboration_status = ? "
                "WHERE id = ?",
                (count, status, finding_id),
            )
        else:
            self._execute(
                "UPDATE findings SET corroboration_count = ?, corroboration_status = ?, "
                "confidence = ? WHERE id = ?",
                (count, status, confidence, finding_id),
            )

    def list_findings(self, mission_id: str) -> list[Finding]:
        rows = self._execute(
            "SELECT * FROM findings WHERE mission_id = ? ORDER BY created_at, id",
            (mission_id,),
        ).fetchall()
        return [Finding.model_validate(dict(row)) for row in rows]

    def save_source(self, source: Source) -> Source:
        self._execute(
            """
            INSERT OR REPLACE INTO sources
            (id, mission_id, url_or_ref, quote, retrieved_at, source_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                source.mission_id,
                source.url_or_ref,
                source.quote,
                source.retrieved_at,
                source.source_type,
            ),
        )
        return source

    def list_sources(self, mission_id: str) -> list[Source]:
        rows = self._execute(
            "SELECT * FROM sources WHERE mission_id = ? ORDER BY retrieved_at, id",
            (mission_id,),
        ).fetchall()
        return [Source.model_validate(dict(row)) for row in rows]

    def save_data_room_file(self, f: DataRoomFile) -> DataRoomFile:
        self._execute(
            """
            INSERT OR REPLACE INTO data_room_files
            (id, mission_id, filename, file_path, mime_type, size_bytes,
             parsed_text, parse_error, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f.id, f.mission_id, f.filename, f.file_path, f.mime_type,
                f.size_bytes, f.parsed_text, f.parse_error, f.uploaded_at,
            ),
        )
        return f

    def list_data_room_files(self, mission_id: str) -> list[DataRoomFile]:
        rows = self._execute(
            "SELECT * FROM data_room_files WHERE mission_id = ? ORDER BY uploaded_at, id",
            (mission_id,),
        ).fetchall()
        return [DataRoomFile.model_validate(dict(r)) for r in rows]

    def get_data_room_file(self, file_id: str) -> DataRoomFile | None:
        row = self._execute(
            "SELECT * FROM data_room_files WHERE id = ?", (file_id,)
        ).fetchone()
        return DataRoomFile.model_validate(dict(row)) if row else None

    def delete_data_room_file(self, file_id: str) -> bool:
        cur = self._execute("DELETE FROM data_room_files WHERE id = ?", (file_id,))
        return cur.rowcount > 0

    def save_transcript(
        self, t: Transcript, segments: list[TranscriptSegment]
    ) -> Transcript:
        self._execute(
            """
            INSERT OR REPLACE INTO transcripts
            (id, mission_id, title, expert_name, expert_role, raw_text,
             line_count, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                t.id, t.mission_id, t.title, t.expert_name, t.expert_role,
                t.raw_text, t.line_count, t.uploaded_at,
            ),
        )
        # replace segments wholesale on each save
        self._execute(
            "DELETE FROM transcript_segments WHERE transcript_id = ?", (t.id,)
        )
        for seg in segments:
            self._execute(
                """
                INSERT INTO transcript_segments
                (id, transcript_id, speaker, text, line_start, line_end)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    seg.id, seg.transcript_id, seg.speaker, seg.text,
                    seg.line_start, seg.line_end,
                ),
            )
        return t

    def list_transcripts(self, mission_id: str) -> list[Transcript]:
        rows = self._execute(
            "SELECT * FROM transcripts WHERE mission_id = ? ORDER BY uploaded_at, id",
            (mission_id,),
        ).fetchall()
        return [Transcript.model_validate(dict(r)) for r in rows]

    def list_transcript_segments(self, transcript_id: str) -> list[TranscriptSegment]:
        rows = self._execute(
            "SELECT * FROM transcript_segments WHERE transcript_id = ? "
            "ORDER BY line_start, id",
            (transcript_id,),
        ).fetchall()
        return [TranscriptSegment.model_validate(dict(r)) for r in rows]

    def delete_transcript(self, transcript_id: str) -> bool:
        cur = self._execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
        return cur.rowcount > 0

    def save_deal_terms(self, terms: DealTerms) -> DealTerms:
        self._execute(
            """
            INSERT OR REPLACE INTO deal_terms
            (mission_id, entry_revenue, entry_ebitda, entry_multiple,
             entry_equity, leverage_x, hold_years, target_irr, target_moic,
             sector_multiple_low, sector_multiple_high, notes,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                terms.mission_id,
                terms.entry_revenue,
                terms.entry_ebitda,
                terms.entry_multiple,
                terms.entry_equity,
                terms.leverage_x,
                terms.hold_years,
                terms.target_irr,
                terms.target_moic,
                terms.sector_multiple_low,
                terms.sector_multiple_high,
                terms.notes,
                terms.created_at,
                terms.updated_at,
            ),
        )
        return terms

    def get_deal_terms(self, mission_id: str) -> DealTerms | None:
        row = self._execute(
            "SELECT * FROM deal_terms WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            return None
        return DealTerms.model_validate(dict(row))

    def save_gate(self, gate: Gate) -> Gate:
        questions_json = json.dumps(gate.questions) if gate.questions else None
        self._execute(
            """
            INSERT OR REPLACE INTO gates
            (id, mission_id, gate_type, scheduled_day, validator_role, status, completion_notes, format, questions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gate.id,
                gate.mission_id,
                gate.gate_type,
                gate.scheduled_day,
                gate.validator_role,
                gate.status,
                gate.completion_notes,
                gate.format,
                questions_json,
            ),
        )
        return gate

    def list_gates(self, mission_id: str) -> list[Gate]:
        rows = self._execute(
            "SELECT * FROM gates WHERE mission_id = ? ORDER BY scheduled_day, id",
            (mission_id,),
        ).fetchall()
        return [self._row_to_model(row, Gate) for row in rows]

    def update_gate_status(self, gate_id: str, status: str, notes: str | None = None) -> Gate:
        result = self._execute(
            "UPDATE gates SET status = ?, completion_notes = ? WHERE id = ?",
            (status, notes, gate_id),
        )
        if result.rowcount == 0:
            raise KeyError(f"gate not found: {gate_id}")
        row = self._execute("SELECT * FROM gates WHERE id = ?", (gate_id,)).fetchone()
        return self._row_to_model(row, Gate)

    # ------------------------------------------------------------------
    # Clarification state — persisted on the mission row so the framing
    # clarification flow survives uvicorn restarts and multi-worker setups.
    # ------------------------------------------------------------------
    def get_clarification_state(self, mission_id: str) -> dict:
        row = self._execute(
            "SELECT clarification_rounds_used, clarification_answers FROM missions WHERE id = ?",
            (mission_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"mission not found: {mission_id}")
        rounds = int(row["clarification_rounds_used"] or 0)
        answers = _decode_json_list(row["clarification_answers"])
        return {"rounds": rounds, "answers": answers}

    def increment_clarification_rounds(self, mission_id: str) -> int:
        existing = self.get_clarification_state(mission_id)
        new_rounds = existing["rounds"] + 1
        self._execute(
            "UPDATE missions SET clarification_rounds_used = ? WHERE id = ?",
            (new_rounds, mission_id),
        )
        return new_rounds

    def append_clarification_answer(self, mission_id: str, answer: str) -> list[str]:
        existing = self.get_clarification_state(mission_id)
        answers = list(existing["answers"])
        cleaned = (answer or "").strip()
        if cleaned:
            answers.append(cleaned)
        self._execute(
            "UPDATE missions SET clarification_answers = ? WHERE id = ?",
            (json.dumps(answers), mission_id),
        )
        return answers

    def reset_clarification_state(self, mission_id: str) -> None:
        self._execute(
            "UPDATE missions SET clarification_rounds_used = 0, clarification_answers = '[]' WHERE id = ?",
            (mission_id,),
        )

    def update_mission_status(self, mission_id: str, status: str) -> None:
        result = self._execute(
            "UPDATE missions SET status = ? WHERE id = ?",
            (status, mission_id),
        )
        if result.rowcount == 0:
            raise KeyError(f"mission not found: {mission_id}")

    def save_deliverable(self, deliverable: Deliverable) -> Deliverable:
        self._execute(
            """
            INSERT OR REPLACE INTO deliverables
            (id, mission_id, deliverable_type, status, file_path, file_size_bytes, created_at, milestone_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deliverable.id,
                deliverable.mission_id,
                deliverable.deliverable_type,
                deliverable.status,
                deliverable.file_path,
                deliverable.file_size_bytes,
                deliverable.created_at,
                deliverable.milestone_id,
            ),
        )
        return deliverable

    def list_deliverables(self, mission_id: str) -> list[Deliverable]:
        rows = self._execute(
            "SELECT * FROM deliverables WHERE mission_id = ? ORDER BY created_at, id",
            (mission_id,),
        ).fetchall()
        return [Deliverable.model_validate(dict(row)) for row in rows]

    def save_merlin_verdict(self, verdict: MerlinVerdict) -> MerlinVerdict:
        self._execute(
            """
            INSERT OR REPLACE INTO merlin_verdicts
            (id, mission_id, verdict, gate_id, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                verdict.id,
                verdict.mission_id,
                verdict.verdict,
                verdict.gate_id,
                verdict.notes,
                verdict.created_at,
            ),
        )
        return verdict

    def get_latest_merlin_verdict(self, mission_id: str) -> MerlinVerdict | None:
        row = self._execute(
            """
            SELECT * FROM merlin_verdicts
            WHERE mission_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (mission_id,),
        ).fetchone()
        return self._row_to_model(row, MerlinVerdict)
