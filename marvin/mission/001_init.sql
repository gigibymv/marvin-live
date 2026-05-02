PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    client TEXT NOT NULL,
    target TEXT NOT NULL,
    mission_type TEXT DEFAULT 'cdd',
    ic_question TEXT,
    status TEXT DEFAULT 'active',
    active_agent TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS mission_briefs (
    mission_id TEXT PRIMARY KEY REFERENCES missions(id) ON DELETE CASCADE,
    raw_brief TEXT NOT NULL,
    ic_question TEXT NOT NULL,
    mission_angle TEXT NOT NULL,
    brief_summary TEXT NOT NULL,
    workstream_plan_json TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    abandon_reason TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS workstreams (
    id TEXT NOT NULL,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    assigned_agent TEXT,
    status TEXT DEFAULT 'pending',
    PRIMARY KEY (mission_id, id)
);

CREATE TABLE IF NOT EXISTS milestones (
    id TEXT NOT NULL,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    workstream_id TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    result_summary TEXT,
    scheduled_day INTEGER,
    PRIMARY KEY (mission_id, id),
    FOREIGN KEY (mission_id, workstream_id) REFERENCES workstreams(mission_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    workstream_id TEXT,
    hypothesis_id TEXT,
    claim_text TEXT NOT NULL,
    confidence TEXT NOT NULL
        CHECK (confidence IN ('KNOWN','REASONED','LOW_CONFIDENCE')),
    source_id TEXT,
    agent_id TEXT,
    human_validated INTEGER DEFAULT 0,
    created_at TEXT,
    FOREIGN KEY (mission_id, workstream_id) REFERENCES workstreams(mission_id, id) ON DELETE SET NULL,
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    url_or_ref TEXT,
    quote TEXT,
    retrieved_at TEXT
);

CREATE TABLE IF NOT EXISTS finding_sources (
    finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    PRIMARY KEY (finding_id, source_id)
);

CREATE TABLE IF NOT EXISTS gates (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    gate_type TEXT NOT NULL,
    scheduled_day INTEGER NOT NULL,
    validator_role TEXT DEFAULT 'manager',
    status TEXT DEFAULT 'pending'
        CHECK (status IN ('pending','completed','failed')),
    completion_notes TEXT,
    format TEXT,
    failure_reason TEXT
);

CREATE TABLE IF NOT EXISTS deliverables (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    deliverable_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    file_path TEXT,
    file_size_bytes INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS data_room_files (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER,
    parsed_text TEXT,
    parse_error TEXT,
    uploaded_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_data_room_files_mission ON data_room_files(mission_id);

CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    title TEXT,
    expert_name TEXT,
    expert_role TEXT,
    raw_text TEXT NOT NULL,
    line_count INTEGER,
    uploaded_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_transcripts_mission ON transcripts(mission_id);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    speaker TEXT,
    text TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER
);
CREATE INDEX IF NOT EXISTS idx_transcript_segments_tx ON transcript_segments(transcript_id);

CREATE TABLE IF NOT EXISTS deal_terms (
    mission_id TEXT PRIMARY KEY REFERENCES missions(id) ON DELETE CASCADE,
    entry_revenue REAL,
    entry_ebitda REAL,
    entry_multiple REAL,
    entry_equity REAL,
    leverage_x REAL,
    hold_years INTEGER,
    target_irr REAL,
    target_moic REAL,
    sector_multiple_low REAL,
    sector_multiple_high REAL,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS merlin_verdicts (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL
        CHECK (verdict IN ('SHIP','MINOR_FIXES','BACK_TO_DRAWING_BOARD')),
    gate_id TEXT,
    notes TEXT,
    created_at TEXT
);

-- C-CONV: queue of mid-mission steering instructions from the user.
-- Consumed at the start of each agent node (dora/calculus/adversus/merlin)
-- and prepended as a HumanMessage so the next agent run sees the
-- instruction. `consumed_at` marks rows the agent has already received.
CREATE TABLE IF NOT EXISTS mission_steering (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    instruction TEXT NOT NULL,
    created_at TEXT,
    consumed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mission_steering_pending
    ON mission_steering(mission_id, consumed_at);

CREATE TABLE IF NOT EXISTS mission_chat_messages (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','marvin')),
    text TEXT NOT NULL,
    deliverable_id TEXT,
    deliverable_label TEXT,
    gate_id TEXT,
    gate_action TEXT,
    seq INTEGER,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mission_chat_messages_mission_seq
    ON mission_chat_messages(mission_id, seq, created_at);
