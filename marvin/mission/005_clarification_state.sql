-- Chantier 2: clarification rounds + answers persisted on the mission row,
-- and clarification questions persisted on the gate row so the gate-based
-- clarification flow survives uvicorn restarts and multi-worker deploys.
--
-- Applied additively in MissionStore._apply_additive_migrations. This file
-- exists for documentation and direct DB inspection; the runtime check is
-- the PRAGMA table_info loop in store.py.

ALTER TABLE missions ADD COLUMN clarification_rounds_used INTEGER DEFAULT 0;
ALTER TABLE missions ADD COLUMN clarification_answers TEXT DEFAULT '[]';
ALTER TABLE gates ADD COLUMN questions TEXT;
