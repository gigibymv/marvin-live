# CLAUDE.md

This file provides guidance  when working with code in this repository.

## What this is

MARVIN is an AI-enabled consulting operating system: a human + AI-agent platform for running consulting workflows with structured validation gates, live progress, and deliverable generation.

Today, the first fully implemented workflow is **Commercial Due Diligence (CDD)**. The current graph, tools, gates, and UI are therefore CDD-shaped, but the product should be understood more broadly:

- **MARVIN is not “just a CDD tool.”**
- MARVIN is the execution layer for a consulting firm where humans and AI agents work together.
- CDD is the first major workflow/use case currently implemented in this repo.

At the moment, the stack is:
- **Backend:** FastAPI + LangGraph + SQLite
- **Frontend:** Next.js 15
- **Transport:** SSE from backend runtime events to the UI

## Commands

### Backend (Python 3.11+, run from repo root)

Install dependencies once:

```bash
pip install -e ".[dev]" pydantic fastapi "uvicorn[standard]" pytest langgraph langchain-openai
````

Run server (env must be loaded in the shell, not via `--env-file`):

```bash
set -a; source .env; set +a
PYTHONPATH=$PWD .venv/bin/python -m uvicorn marvin_ui.server:app --port 8095
```

Test commands:

```bash
PYTHONPATH=$PWD .venv/bin/pytest tests/ -q
PYTHONPATH=$PWD .venv/bin/pytest tests/test_phase_router.py
PYTHONPATH=$PWD .venv/bin/pytest tests/ -q -k "milestone"
```

### Frontend (Next.js)

```bash
npm run dev
npm run build
npm run typecheck
npm test
```

## Environment

Required `.env` values at repo root:

* `OPENROUTER_API_KEY` — required for real LLM-backed runs
* `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`
* `TAVILY_API_KEY` — optional, depending on tool usage

Without `OPENROUTER_API_KEY`, agent nodes may degrade to no-op behavior in some subgraph paths. This is useful for graph-shape tests, but not for real mission execution.

## Live SSE testing

The user's `curl` may be wrapped by rtk and buffer streams. Always use:

```bash
/usr/bin/curl -s -N
```

for SSE inspection.

## Architecture

These are the repo-level invariants that matter across multiple files.

### 1. LangGraph is phase-driven

`marvin/graph/runner.py::build_graph()` compiles the full graph.

The graph is **phase-driven**:

* nodes return a `phase` string in their state delta
* `phase_router` maps that phase to the next node

Current primary workflow phases are:

```text
setup → framing → awaiting_confirmation → confirmed
     → research_done → gate_g1_passed → redteam_done
     → synthesis_retry (optional loop back to adversus)
     → synthesis_done → gate_g3_passed → done
```

This phase model is currently built around the CDD workflow, but the architectural pattern is broader: structured workflow phases, deterministic routing in Python, and gated human validation.

### 2. Routing is Python, not prompt logic

This repo depends on a hard separation:

* **Routing / control flow = Python**
* **Analysis / agent reasoning = LLM**
* **Persistence / event ownership = Python**

Do not move workflow routing decisions into prompts.

### 3. `mission_id` lives only in LangGraph state

This is non-negotiable.

`mission_id` must flow only through:

* `MarvinState`
* `InjectedState`
* tool calls receiving state through LangGraph

Do **not**:

* infer it from “first active mission”
* look it up opportunistically from the DB
* create a fallback source of truth

### 4. `gate_entry_node` is a real node

Phases that require a gate must route through `gate_entry` before `gate_node`.

This is load-bearing.

Reason:

* `gate_entry` sets `pending_gate_id`
* then a deterministic edge runs `gate_node`
* skipping `gate_entry` causes `gate_node` to fall back incorrectly and can send the graph into bad idle/orchestrator behavior

Gate-triggering phases must not bypass this node.

### 5. `merlin` must not self-loop through its own path map

The retry path is:

```text
merlin_node -> phase="synthesis_retry" -> phase_router -> adversus -> merlin
```

Do **not** make `merlin` retry by returning a phase that routes directly back to `merlin` through its own outgoing conditional edge map.

That pattern previously caused a `KeyError: 'merlin'` at runtime.

### 6. `research_join` is deterministic

`research_join` advances workflow state from Python and must not depend on whether the LLM happened to call a particular milestone tool.

This is intentional:

* graph progression must not depend on opportunistic tool selection
* deterministic workflow completion belongs in Python control flow

### 7. Agent construction must use `state_schema=MarvinState`

`marvin/graph/subgraphs/common.py::build_agent` must construct agents with:

* `create_react_agent(state_schema=MarvinState, ...)`

This is what propagates `mission_id` and other state into tools through `InjectedState`.

If that state schema is lost, tools will silently lose mission-scoped state and runtime will fail in confusing ways.

## Event ownership

### Business events belong to persistence chokepoints, not top-level tool visibility

`marvin/events.py` defines per-mission listener registries for:

* `finding_persisted`
* `deliverable_persisted`
* `milestone_persisted`

The key rule is:

> If the business fact happened, emit from the Python chokepoint that owns that fact.

Do **not** make correctness depend on whether the LLM chose a visible top-level tool call.

This is why:

* findings are emitted from the finding persistence path
* deliverables are emitted from the deliverable persistence path
* milestones are emitted from the milestone persistence path

`marvin_ui/server.py::map_tool_to_sse_event` intentionally returns `None` for persistence-owned events such as:

* `add_finding_to_mission`
* `mark_milestone_delivered`
* papyrus `generate_*` tools

Reintroducing SSE emission at the tool-message mapping layer for these paths will cause duplicate events.

## Persistence and storage

### SQLite

Default DB path:

```text
~/.marvin/marvin.db
```

Override via `MissionStore(db_path=...)`.

Schema source:

* `marvin/mission/001_init.sql`

Additive migrations:

* `_apply_additive_migrations` on connect

Foreign key enforcement is ON.

### IDs

IDs use short prefixed forms such as:

* `m-...`
* `hyp-...`
* `f-...`
* `s-...`
* `gate-...`

Generated via `tools/common.py::short_id`.

### Hypothesis ID normalization

LLMs may emit recoverable formatting noise around a valid hypothesis ID, for example:

```text
[hyp-79a14102] Some trailing claim text
```

`marvin/tools/common.py::normalize_hypothesis_id` exists to strip only clearly recoverable wrappers/noise.

Important:

* it does **not** invent IDs
* it does **not** guess by text similarity
* it does **not** choose a fallback hypothesis
* normalized output is still validated against the allowed set for the mission

Treat normalization as a narrow input cleanup step, not as a source of truth.

## LLM routing

LLM role selection is centralized in:

* `marvin/llm_factory.py`

At time of writing, role routing goes through OpenRouter. Do not bypass that layer.

If you need exact current model mapping, verify it in `llm_factory.py` rather than relying on stale documentation.

## SSE flow

`marvin_ui/server.py::_stream_chat` is the live runtime path.

For a chat run, `_stream_chat`:

* registers per-mission listeners
* runs the graph
* drains queues into SSE events
* emits `gate_pending` on LangGraph interrupt
* unregisters listeners in `finally`

Gate resume happens via:

```text
POST /api/v1/missions/{id}/gates/{gate_id}/validate
```

with a verdict payload.

Do not assume SSE correctness from unit tests alone. Runtime evidence matters.

## Working rules specific to this repo

### 1. Code change is not delivery

A green test suite is necessary but not sufficient.

For changes touching:

* graph flow
* store/persistence
* SSE
* gates
* event ownership
* late-phase execution

the expected bar is:

* targeted tests
* relevant regression tests
* runtime evidence when the path is load-bearing

### 2. Do not reintroduce fallback `mission_id`

No fallback mission lookup.
No “first active mission.”
No silent DB inference.

### 3. Do not silently choose a hypothesis

Never resolve a hypothesis by:

* similarity
* text matching
* recency
* “first active”

If a hypothesis reference is invalid, reject and surface it clearly.

### 4. One real UI

The product UI is the real UI.

There is a presentational layer in `UI Marvin/` and a controller layer in `components/marvin/MissionControl.tsx`.

Do not introduce demo data or fake event flows.
The UI should reflect backend/runtime truth only.

### 5. Avoid stale artifacts in commits

Do not commit:

* `.next/`
* `__pycache__/`
* `.pyc`
* build caches
* generated local artifacts

Keep diffs focused and reviewable.

### 6. Be careful with docs and handoff files

`HANDOFF.md` and `RUNBOOK.md` may contain useful context, but they are not guaranteed to be current.
Verify against the code before trusting them.

## What to optimize for when making changes

When working in this repo, optimize for:

* deterministic workflow control in Python
* deep modules, not pass-through wrappers
* one ownership point per business fact
* idempotent persistence/event behavior
* live runtime truth reaching the UI
* changes that preserve end-to-end operability, not just isolated correctness

When in doubt, prefer:

* a narrow structural fix over a prompt hacka silent fallback, a UI-only band-aid
