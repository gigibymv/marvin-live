# Marvin Project Handoff Document

> **Last updated:** 2026-05-01 — end of Phase F live test, Phase G in flight.
> CLAUDE.md (root) is the source of truth on architecture invariants. Read it first.

## Current State Summary

MARVIN is an AI-enabled consulting OS. First implemented workflow: Commercial Due Diligence (CDD).
Stack: FastAPI + LangGraph + SQLite (backend), Next.js 15 + React 19 (frontend), SSE transport.
Agents: Dora (W1 market), Calculus (W2 financial), Adversus (W4 red-team), Merlin (W3 synthesis),
Papyrus (deliverable writer), MARVIN (orchestrator).

### Phase progression (where we are)

| Phase | Scope | Status |
|-------|-------|--------|
| A | P1 (gate safety), P11 (chat narration typo) | shipped |
| B | P2/P3/P4/P5/P6/P7/P8/P10/P12 (UI truthfulness + visual hierarchy) | shipped |
| C | mission complete ordering, hypothesis status, gate tab ✓ | shipped |
| D | P9 tab restructure (design only) | **deferred** — no implementation without design validation |
| E | P13 (mission stuck livelock), P14 (chat send corrupts), P15 (phase narration), P16 (gate requires deliverables), P17 (milestone OPEN gate) | shipped |
| F | P18a (G1 chat CTA), P18b (stale live bar), P19b (strict ws done), P19d (milestone OPEN gate), P20 (phantom Moat), P21 (progress formula), P14-bis | shipped (commits c98e7ee, 9d884c6, 48b1972) — **partial regressions found in live test** |
| G | Live test caught: gate G1 fires too early, P19b not actually fixed, chat ordering broken, P18a not fixed for live G1 path | **in flight** (background agent a423b71bb0787cdd7) |

### Known issues at handoff

1. **Gate G1 timing (live)** — gate becomes pending while Anomaly detection blocked + Public Filings Review still being drafted by Papyrus. Criterion in `marvin/graph/gate_material.py` is too lax: counts blocked milestones as terminal AND uses ≥1 ready deliverable. Must tighten to ALL expected deliverables ready per non-skipped W1+W2.
2. **Tab ✓ (P19b)** — `wsAllDeliverablesReady` in `MissionControl.tsx` only checks deliverables present in array, not against expected set. If Papyrus hasn't emitted yet, "all ready" passes trivially.
3. **Chat message ordering** — Papyrus milestone-report messages can appear above subsequent MARVIN messages. Likely sort-by-ts with collisions.
4. **G1 chat CTA missing on live path** — fix in commit c98e7ee only patched `_drive_detached_resume` (post-resume interrupts). Initial G1 in `_stream_chat` is unmodified. No Approve/Reject bubble in chat for first G1.

### Deploy state (Render)

- Backend service: `srv-d7p2l53bc2fs73c3lu80`
- Frontend service: `srv-d7p2l8vavr4c73d1gnvg`
- **Auto-deploy webhook is broken** (`gh api repos/gigibymv/marvin-live/hooks` returns []). Trigger manually:
  ```
  render deploys create <service-id> --commit <sha> --confirm
  ```
- Currently 3 commits ahead on `main` past last green Render deploy (8a9564a). Phase F + review fix commits pushed but **not yet deployed** (waiting on Phase G to land first).

### Local dev

- Backend: `set -a; source .env; set +a; PYTHONPATH=$PWD .venv/bin/python -m uvicorn marvin_ui.server:app --port 8095`
- Frontend: `npm run dev` → `http://localhost:3000`
- Mandatory smoke before commit when touching graph/server/checkpointer: `make smoke`
- Tests: `PYTHONPATH=$PWD .venv/bin/pytest tests/ -q`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ MissionDashboard │  │ MissionControl    │  │ View Components│  │
│  │ (components/)    │  │ (components/)    │  │ (UI Marvin/)   │  │
│  │ - lists missions │  │ - chat interface │  │ - presentation │  │
│  │ - creates mission│  │ - SSE streaming  │  │ - receives data│  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────────┘  │
│           │                     │                               │
│           └─────────────────────┼───────────────────────────────┤
│                                 │ HTTP/SSE                      │
└─────────────────────────────────┼───────────────────────────────┘
                                  │
┌─────────────────────────────────┼───────────────────────────────┐
│                     Backend (FastAPI)                            │
│  ┌──────────────────┐  ┌────────┴─────────┐  ┌──────────────┐    │
│  │ /missions       │  │ /missions/{id}/ │  │ /missions/   │    │
│  │ - CRUD          │  │ /chat (SSE)     │  │ {id}/progress│    │
│  │ - list/create   │  │ - streaming     │  │ - full state │    │
│  └─────────────────┘  └─────────────────┘  └──────────────┘    │
│           │                     │                                 │
│           └─────────────────────┼───────────────────────────────┤
│                                 │                                │
│  ┌─────────────────────────────┴────────────────────────────┐  │
│  │                    LangGraph Agents                         │  │
│  │  ┌─────┐ ┌──────────┐ ┌─────────┐ ┌────────┐ ┌────────┐   │  │
│  │  │Dora │ │ Calculus │ │ Adversus│ │ Merlin │ │ Papyrus│   │  │
│  │  │     │ │          │ │         │ │        │ │        │   │  │
│  │  └──┬──┘ └────┬─────┘ └────┬────┘ └───┬────┘ └───┬────┘   │  │
│  │     └──────────┴───────────┴──────────┴─────────┘         │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                 │                                │
│           ┌─────────────────────┴────────────────────┐          │
│           │              SQLite Database              │          │
│           │         ~/.marvin/marvin.db              │          │
│           └───────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
marvin/
├── marvin/                      # Core Python package
│   ├── graph/                   # LangGraph agent definitions
│   │   ├── runner.py            # Graph builder and phase router
│   │   └── subgraphs/          # Agent implementations
│   │       ├── dora.py          # Market research agent
│   │       ├── calculus.py      # Financial analysis agent
│   │       ├── adversus.py      # Red team agent
│   │       ├── merlin.py       # Synthesis agent
│   │       ├── papyrus.py      # Document generation agent
│   │       └── common.py       # Agent factory utilities
│   ├── mission/                 # Mission data models
│   │   ├── schema.py           # Pydantic models
│   │   └── store.py            # SQLite persistence
│   ├── tools/                   # Agent tools
│   │   ├── common.py           # Shared utilities (InjectedStateArg)
│   │   ├── mission_tools.py    # Mission operations
│   │   ├── dora_tools.py       # Research tools
│   │   ├── calculus_tools.py   # Financial tools
│   │   ├── merlin_tools.py     # Synthesis tools
│   │   └── papyrus_tools.py    # Document tools
│   └── llm_factory.py          # LLM configuration
│
├── marvin_ui/                   # FastAPI backend
│   └── server.py               # API endpoints and SSE streaming
│
├── components/marvin/           # React components (controllers)
│   ├── MissionControl.tsx      # Main chat controller
│   └── MissionDashboard.tsx   # Mission list controller
│
├── UI Marvin/                   # React components (presentation)
│   ├── MissionControl.jsx      # Chat view (receives props)
│   └── MissionDashboard.jsx    # Dashboard view
│
├── lib/missions/                # Frontend utilities
│   ├── api.ts                  # HTTP client functions
│   ├── events.ts               # SSE event handling
│   ├── repository.ts           # Data fetching abstractions
│   └── store.ts                # Zustand state management
│
└── tests/                       # Python tests
    ├── test_agents.py
    ├── test_phase_router.py
    ├── test_store.py
    └── test_tools.py
```

---

## Key Files Modified in This Session

### Backend

**`marvin_ui/server.py`**
- Extended `/api/v1/missions/{id}/progress` endpoint to include:
  - `hypotheses` - from `store.list_hypotheses()`
  - `deliverables` - from `store.list_deliverables()`
  - `workstreams` - from `store.list_workstreams()`
- Added `agent_active` SSE event emitted when agent starts processing
- Added logging for text events and state initialization

**`marvin/tools/*.py`**
- All tool functions updated to use `InjectedStateArg` type annotation
- Functions can receive LangGraph state automatically when called by agents
- Added docstrings for LangChain tool compatibility

**`marvin/tools/common.py`**
- Added `InjectedStateArg = Annotated[dict[str, Any] | None, InjectedState]` type alias

### Frontend

**`lib/missions/api.ts`**
- Added `getMissionProgress()` function to fetch full mission state

**`lib/missions/events.ts`**
- Added `agent_active` event type to `MissionStreamEvent` union
- Added event listener and mapping for `agent_active`

**`components/marvin/MissionControl.tsx`**
- Added state for progress data: `gates`, `milestones`, `findings`, `hypotheses`, `deliverables`, `workstreams`
- Added `activeAgent` and `agentStatuses` state to track running agents
- Added `useEffect` to fetch progress from backend
- Added event handlers for `agent_active` and `agent_done` events
- Computes `agents`, `checkpoints`, `hypotheses`, `findings`, `deliverables` from backend data
- Passes all data as props to view

**`UI Marvin/MissionControl.jsx`**
- Changed all hardcoded arrays to use props with empty defaults
- `AGENTS` - changed all `state` to `"idle"`
- `CHECKPOINTS` - changed all `status` to `"pending"`
- `HYP`, `LIVE`, `DONE` - changed to empty arrays `[]`
- `DELIVERABLES` - changed all `status` to `"pending"`
- All `.map()` calls now use `(props.X || DEFAULT).map()`

---

## Database Schema

Located at `~/.marvin/marvin.db`. Tables:
- `missions` - id, client, target, mission_type, ic_question, status, created_at, updated_at
- `hypotheses` - id, mission_id, text, status, created_at
- `workstreams` - id, mission_id, label, assigned_agent, status
- `milestones` - id, mission_id, workstream_id, label, status, result_summary
- `findings` - id, mission_id, workstream_id, hypothesis_id, claim_text, confidence, agent_id
- `gates` - id, mission_id, gate_type, scheduled_day, status, completion_notes
- `deliverables` - id, mission_id, deliverable_type, file_path, created_at
- `sources` - id, mission_id, url_or_ref, quote, retrieved_at
- `merlin_verdicts` - id, mission_id, verdict, gate_id, notes, created_at

---

## Running the Project

### Backend
```bash
cd /Users/mv/Desktop/AI/PROJECTS/marvin
.venv/bin/python -m uvicorn marvin_ui.server:app --host 127.0.0.1 --port 8095
```

### Frontend
```bash
cd /Users/mv/Desktop/AI/PROJECTS/marvin
npm run dev
```

### Environment Variables Required (`.env`)
```
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### Tests
```bash
export PYTHONPATH=/Users/mv/Desktop/AI/PROJECTS/marvin:$PYTHONPATH
.venv/bin/pytest tests/ -q
npm run test
```

---

## Known Issues

### 1. Test Failures (12 failing)
Most test failures are due to `InjectedStateArg` changes - tests call tools directly without LangGraph context.
- Tests need updates to pass `state={"mission_id": "m-test"}` parameter
- Some tests expect return values that differ from current implementation

### 2. Agent Status Initialization
- Agents show "idle" on initial load (correct)
- Status updates only during active SSE stream
- If user refreshes mid-execution, status resets to "idle"
- **Potential improvement**: Persist agent status in database and load on mount

### 3. No Historical Messages
- Chat messages are not persisted between sessions
- Each page load starts fresh
- **Potential improvement**: Add message persistence to database

### 4. Gate Modal
- Gate validation UI exists but is incomplete
- `gateModal` state is set but the modal UI is basic
- Gate approval/rejection handlers exist but may not be fully wired

---

## SSE Event Types

Events emitted by backend (`_stream_chat` in `server.py`):

| Event | Payload | When |
|-------|---------|------|
| `run_start` | `{}` | Stream starts |
| `text` | `{agent, text}` | AI generates text |
| `tool_call` | `{agent, tool}` | Agent calls a tool |
| `tool_result` | `{agent, text}` | Tool returns result |
| `finding_added` | `{text, badge?}` | Finding created |
| `milestone_done` | `{milestoneId?, label?}` | Milestone completed |
| `gate_pending` | `{gateId, title, summary?}` | Gate needs approval |
| `deliverable_ready` | `{deliverableId?, label?}` | Deliverable created |
| `agent_active` | `{agent}` | Agent starts processing |
| `agent_done` | `{agent}` | Agent finishes |
| `run_end` | `{}` | Stream ends |
| `error` | `{message}` | Error occurred |

---

## Unfinished Work

### 1. Real-time Agent Status Persistence
**File**: `marvin_ui/server.py`, `components/marvin/MissionControl.tsx`

Currently, agent status is tracked in-memory during SSE streaming. If user refreshes, status is lost.

**To implement**:
- Store `active_agent` in database (new column on `missions` table)
- Load agent status on `getMissionProgress()`
- Or store in LangGraph checkpoint state

### 2. Findings/Hypotheses Live Updates
**File**: `components/marvin/MissionControl.tsx`

Findings are fetched once on mount. New findings from SSE events should be appended.

**To implement**:
- Add `finding_added` event handler to append to `findings` state
- Add `hypothesis_added` event for new hypotheses

### 3. Checkpoint/Gate Status Updates
**File**: `components/marvin/MissionControl.tsx`

Gates are fetched once. When gate status changes, UI doesn't update.

**To implement**:
- Poll `/progress` periodically during active session
- Or add SSE event for gate status changes

### 4. Deliverables Status
**File**: `marvin/mission/store.py`, `marvin_ui/server.py`

Deliverables have `file_path` but no `status` field in database.

**To implement**:
- Add `status` column to `deliverables` table
- Update deliverable status when files are generated

---

## Verification Checklist

Run these commands to verify the system works:

```bash
# 1. Backend health
curl http://127.0.0.1:8095/health
# Expected: {"status":"ok"}

# 2. Create mission
curl -X POST http://127.0.0.1:8095/api/v1/missions \
  -H "Content-Type: application/json" \
  -d '{"client":"Test","target":"Acme","ic_question":"Viable?","mission_type":"cdd"}'
# Expected: {"mission_id":"m-acme-...","status":"active",...}

# 3. Get progress
curl http://127.0.0.1:8095/api/v1/missions/m-acme-YYYYMMDD/progress | jq .
# Expected: {mission, gates, milestones, findings, hypotheses, deliverables, workstreams}

# 4. Frontend
npm run dev
# Open http://localhost:3000
# Clear localStorage
# Create new mission
# Verify: Agents show "idle", no fake data
# Send brief: "Analyze Acme Corp"
# Verify: Backend logs "Starting stream with state: mission_id=..."
# Verify: Browser console shows "text event: {...}"
# Verify: Agent status shows active during execution
```

---

## Contact Points / Context

- **LLM Provider**: OpenRouter with `openai/gpt-5.4-nano` model
- **Database**: SQLite at `~/.marvin/marvin.db`
- **Frontend Port**: 3000
- **Backend Port**: 8095
- **SSE Endpoint**: POST `/api/v1/missions/{id}/chat`

---

## Recent Changes Log

1. **InjectedStateArg for tools** - All tools now use LangGraph's `InjectedState` to receive mission context
2. **Removed demo data** - UI no longer shows fake "Validating 34% penetration" etc.
3. **Extended progress endpoint** - Now returns hypotheses, deliverables, workstreams
4. **Agent status tracking** - SSE events for agent start/done
5. **LLM models updated** - All agents use `openai/gpt-5.4-nano` via OpenRouter
6. **Database reset** - Old schema deleted, fresh `marvin.db` created

---

## Potential Next Steps

1. **Persist agent status** - Store in DB and reload on page refresh
2. **Add message persistence** - Save chat history to database
3. **Implement gate approval UI** - Wire up approve/reject buttons
4. **Add file upload** - For engagement brief and data room
5. **Add real Tavily integration** - Currently stubbed in `dora_tools.py`
6. **Add tests for new progress endpoint** - Verify hypotheses/deliverables included

---

## Critical Traps (read before editing)

These are recurring footguns. Each has burned us at least once.

1. **React error #310 in MissionControl.tsx**
   ANY new hook (`useEffect`/`useMemo`/`useState`/`useCallback`) MUST go above line ~1670 (`if (!hasLoaded) return null`). Hit twice. Production-breaking.

2. **mission_id only flows via LangGraph state**
   Never infer from "first active mission", DB lookup, or fallback. Only via `MarvinState` → `InjectedState`. Hard rule in CLAUDE.md.

3. **Gate routing must go through `gate_entry_node`**
   Phases requiring a gate route through `gate_entry` (sets `pending_gate_id`), then deterministic edge to `gate_node`. Skipping causes orchestrator to fall back into bad idle.

4. **Merlin retry must NOT self-loop**
   Path: `merlin → phase="synthesis_retry" → phase_router → adversus → merlin`. Never make merlin route back to itself via its own conditional edge map. Causes `KeyError: 'merlin'`.

5. **`research_join` is deterministic, not LLM-driven**
   Workflow advancement does not depend on the LLM choosing a milestone tool. Owned in Python.

6. **Persistence-owned SSE events**
   `findings`, `deliverables`, `milestones` emit from the persistence chokepoint (`marvin/events.py` listener registries), NOT from `map_tool_to_sse_event`. Re-emitting at the tool-message layer causes duplicates.

7. **Render auto-deploy is broken**
   Webhook missing — verify via `gh api repos/gigibymv/marvin-live/hooks` (returns `[]`). Trigger deploys manually via `render deploys create <service-id> --commit <sha> --confirm`.

8. **Mandatory smoke for graph/server/checkpointer changes**
   `make smoke` (i.e. `.venv/bin/python scripts/smoke_runtime.py`) MUST pass before commit. Pre-commit hook enforces it. Catches sync-vs-async runtime divergences unit tests miss.

9. **Phase D (P9 tab restructure) deferred**
   No implementation without explicit design validation. Don't rebuild the tab layout proactively.

10. **Chat narration has subtle requirements**
    - Trailing periods on `_PHASE_NARRATION` entries (server.py)
    - `whiteSpace: "pre-wrap"` on chat span (RightRail.tsx) for `\n\n` to render
    - Both Approve/Reject/Review buttons require `m.gateId && m.gateAction === "pending"` on the message — backend must set both for G1 AND G3.

