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

CREATE TABLE IF NOT EXISTS gates (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    gate_type TEXT NOT NULL,
    scheduled_day INTEGER NOT NULL,
    validator_role TEXT DEFAULT 'manager',
    status TEXT DEFAULT 'pending'
        CHECK (status IN ('pending','completed','failed')),
    completion_notes TEXT,
    format TEXT
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
