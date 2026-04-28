# deer-flow → MARVIN Architecture Exploration

*Research date: 2026-04-27. deer-flow commit: 9dc25987. Read-only — no MARVIN code modified.*

---

## Section 1 — Architecture Mapping (10 concepts)

### 1. Skills System (YAML-driven capability injection)

**deer-flow location:** `backend/packages/harness/deerflow/skills/loader.py`, `skills/{public,custom}/*/SKILL.md`

Skills are YAML-fronted markdown files with `name`, `description`, and `allowed-tools` fields. `loader.py` reads `extensions_config.json` to know which are enabled, then injects them into the system prompt at runtime. Skills are mounted at `/mnt/skills` as a virtual path — add a file, reload, get a new capability. No code change needed.

MARVIN has no equivalent. Agent capabilities are hardcoded in node construction (`build_agent` in `common.py`). Adding a new research capability to dora or calculus means editing Python and redeploying.

**Relevant for MARVIN?** MAYBE — useful once MARVIN has more than 2 research workstreams; premature if CDD stays the only workflow for the next 6 months.

---

### 2. Sub-agent Executor (parallel bounded execution)

**deer-flow location:** `backend/packages/harness/deerflow/subagents/executor.py`

`SubagentExecutor` runs up to `MAX_CONCURRENT_SUBAGENTS=3` agents in two thread pools (scheduler + execution, 3 workers each). Each sub-agent gets a 15-minute timeout and a 5-second poll interval. SSE events (`task_started`, `task_running`, `task_completed`, `task_failed`, `task_timed_out`) surface sub-agent lifecycle to the UI.

MARVIN uses LangGraph's native parallelism for W1/W2 (`dora`/`calculus`) via `research_join`. There is no timeout enforcement or per-sub-agent SSE lifecycle. If a workstream hangs, the mission hangs silently.

**Relevant for MARVIN?** YES — the timeout + per-workstream SSE lifecycle directly addresses a real gap: MARVIN currently has no way to surface or recover from a stalled workstream agent.

---

### 3. Sandbox + Virtual Filesystem

**deer-flow location:** `backend/packages/harness/deerflow/sandbox/sandbox.py`

`LocalSandboxProvider` maps virtual paths `/mnt/user-data/{workspace,uploads,outputs}` to real backend paths under `.deer-flow/threads/{thread_id}/`. A Docker-backed `AioSandboxProvider` also exists. Per-(sandbox.id, path) write serialization prevents concurrent write corruption.

MARVIN has no concept of a per-mission filesystem. Deliverables are rows in SQLite (`deliverables` table), not files. MARVIN does not execute code or handle binary uploads. The consulting CDD workflow produces structured text, not notebooks or scripts.

**Relevant for MARVIN?** NO — MARVIN does not execute code, produce binary artifacts, or need filesystem isolation. Adding a sandbox layer would be pure complexity without a use case.

---

### 4. Long-term Memory (LLM-extracted user facts)

**deer-flow location:** `backend/packages/harness/deerflow/agents/memory/`

An async queue with a 30-second debounce triggers LLM extraction of user facts from conversation history. Facts are stored as JSON with confidence scores in `memory.json`. At conversation start, the top 15 facts (capped at 2000 tokens) are injected into the system prompt. Fact categories: work context, personal, top-of-mind.

MARVIN has no user memory. Every mission starts cold. A PE analyst running their 10th CDD must re-explain their firm's thesis, sector preferences, and red-flag criteria every time. MARVIN's `MemorySaver` is ephemeral — it does not survive server restart, let alone sessions.

**Relevant for MARVIN?** YES — user preference memory is a known gap that directly degrades analyst UX. The extraction + confidence-score pattern is sound and doesn't require adopting deer-flow's full stack.

---

### 5. Context Summarization Middleware

**deer-flow location:** `backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py`

Triggers when conversation reaches a configurable threshold (example: 80% of max input tokens, approximately 15,564 tokens). Summarizes older messages while preserving the 5 most recent skills (up to ~25k tokens, ~5k/skill cap). Recent context is kept verbatim; only older history is compressed.

MARVIN has no context management. Long CDD missions — framing → research → gate → adversarial → synthesis — can accumulate significant message history. LangGraph's `MemorySaver` holds everything in memory with no pruning. If a mission runs long, token counts and latency will grow unbounded.

**Relevant for MARVIN?** YES — CDD missions have a defined, multi-hour arc. Without summarization, late-phase nodes (adversus, merlin) operate on bloated context, increasing cost and degrading reasoning quality.

---

### 6. Observability / Tracing (LangSmith + Langfuse)

**deer-flow location:** `backend/packages/harness/deerflow/tracing/factory.py`

`build_tracing_callbacks()` returns either a `LangChainTracer` (LangSmith) or a `LangfuseCallbackHandler` (Langfuse) based on which env vars are present. Both are passed as `callbacks` to every LangGraph/LangChain invocation. Zero code change required to switch providers — just rotate env vars.

MARVIN has no tracing. There is no way to answer: which node took the longest, which agent call failed, what did a specific mission cost in tokens. When a mission fails or produces low-quality output, diagnosis is reading SQLite rows and logs, not traces.

**Relevant for MARVIN?** YES — this is the highest signal-to-effort concept in this list. Langfuse is open-source and self-hostable; adding `callbacks` to MARVIN's graph invocations is a one-day change with immediate diagnostic value.

---

### 7. Per-model Configuration with Thinking Flags

**deer-flow location:** `backend/packages/harness/deerflow/models/factory.py`, `config.example.yaml`

`create_chat_model(name, thinking_enabled)` uses reflection to instantiate model classes from config. Each model entry in `config.example.yaml` declares `vision`, `thinking`, and API credentials independently. A "thinking" model can reason internally before responding; this is enabled per-call, not per-session.

MARVIN uses a flat role map in `llm_factory.py` — all 6 roles currently point to the same model (`openai/gpt-5.4-nano` via OpenRouter). There is no per-role model variation and no thinking-mode support.

**Relevant for MARVIN?** MAYBE — the multi-model config is overkill while MARVIN runs a single model. The `thinking_enabled` flag is interesting for adversus (adversarial red-team) and merlin (synthesis), where deeper reasoning matters most. Worth revisiting once base model quality is validated.

---

### 8. MCP Integration (MultiServerMCPClient)

**deer-flow location:** `backend/packages/harness/deerflow/mcp/`

`MultiServerMCPClient` (langchain-mcp-adapters) supports stdio, SSE, and HTTP transports. Config is lazy-loaded and cache-invalidated on `extensions_config.json` mtime changes. OAuth tokens are auto-refreshed.

MARVIN's tools are Python functions decorated with `@tool` and loaded at graph build time. There is no MCP surface. MARVIN does not currently integrate external services (CRM, data providers, web search) beyond Tavily.

**Relevant for MARVIN?** NO — not yet. MCP becomes relevant if MARVIN needs to connect to external PE data sources (PitchBook, Preqin, Bloomberg) without writing bespoke tool adapters. That is a feature decision, not an architecture gap. Do not add MCP complexity ahead of that decision.

---

### 9. Gateway Mode (embedded agent runtime)

**deer-flow location:** `backend/packages/harness/deerflow/runtime/` (Gateway mode), `client.py`

Standard mode uses a separate LangGraph Server process (port 2024) proxied via Nginx — 4 processes total. Gateway mode (experimental) embeds the agent runtime in the main server process using `RunManager` and `StreamBridge` — 3 processes. `DeerFlowClient` (`client.py`) abstracts both modes with `chat()` (sync) and `stream()` (yields `StreamEvent`).

MARVIN already runs everything in a single FastAPI process with SSE streaming. `_stream_chat` in `marvin_ui/server.py` is effectively the same pattern as deer-flow's Gateway mode — without the multi-process overhead. MARVIN made the simpler choice by default.

**Relevant for MARVIN?** NO — MARVIN already has the simpler architecture. Do not introduce process separation or a client abstraction layer that solves a problem MARVIN does not have.

---

### 10. Reflection / Self-critique Loop

**deer-flow location:** `backend/packages/harness/deerflow/reflection/`

deer-flow agents can trigger self-critique passes where a separate LLM call evaluates the agent's output before it is returned. This is a quality gate internal to the agent, not a human gate.

MARVIN handles this at the workflow level: `adversus` is a dedicated red-team node, and gate nodes enforce human validation. The architecture consciously separates adversarial challenge from synthesis. Embedding reflection inside individual agent nodes would blur that separation and potentially cause synthesis-retry loops (`synthesis_retry → adversus → merlin`) to collide with internal reflection cycles.

**Relevant for MARVIN?** NO — MARVIN's adversus + human gate pattern is architecturally superior for a consulting use case where a human must sign off on the challenge, not just an LLM evaluating itself.

---

## Section 2 — Relevance Filtering

### Tier A — Directly fills a known MARVIN gap

- **Observability / Tracing (concept 6)** — MARVIN has zero visibility into per-node latency, token cost, or failure attribution. Today, debugging a failed mission means reading SQLite and uvicorn logs. Adding Langfuse callbacks fills this gap in under a day.
- **Long-term Memory (concept 4)** — MARVIN's MemorySaver is session-ephemeral. An analyst's firm thesis, sector preferences, and standard red-flag criteria must be re-entered every mission. This is not a nice-to-have; it is a workflow defect for repeat users.
- **Context Summarization (concept 5)** — CDD missions run multi-hour with accumulating message history. Without pruning, late-phase nodes (adversus, merlin) receive bloated context. This is currently invisible but will surface as token cost and reasoning degradation at scale.

### Tier B — Could improve a working part

- **Sub-agent Executor timeout + SSE lifecycle (concept 2)** — MARVIN's research parallelism works, but a stalled workstream produces no signal. Adding per-workstream timeout enforcement and `task_timed_out` SSE events would make failures visible and recoverable without changing the routing logic.
- **Skills System (concept 1)** — MARVIN's agent capabilities are hardcoded. If the CDD workflow expands to 4+ workstreams or other consulting workflows are added, a YAML-driven capability layer reduces deployment risk. Not needed for single-workflow operation.

### Tier C — Architecturally incompatible

- **Reflection / Self-critique Loop (concept 10)** — deer-flow's internal LLM self-critique conflicts with MARVIN's explicit adversus → human gate separation. MARVIN deliberately puts challenge and validation at the workflow level, not inside individual agents. Merging them would undermine the deterministic gate model.
- **Per-model Configuration / Thinking Flags (concept 7)** — Partially incompatible now. MARVIN routes all roles through a single model. Grafting a multi-model config layer before validating base model quality adds configuration surface area without runtime benefit. Defer until MARVIN has model-differentiated roles.

### Tier D — Irrelevant for PE consulting CDD

- **Sandbox + Virtual Filesystem (concept 3)** — CDD produces structured text deliverables stored in SQLite, not binary files or executable notebooks. A sandbox adds infrastructure complexity with zero use case in the current product.
- **MCP Integration (concept 8)** — No external data provider integration is planned. MCP is a solution for a feature decision that has not been made. Adding it now is speculative architecture.
- **Gateway Mode / DeerFlowClient (concept 9)** — MARVIN already uses the simpler single-process architecture that Gateway mode is trying to achieve. Copying the pattern would be regressing.

---

## Section 3 — Integration Plans

## Pattern 1 — Langfuse Tracing

**Source:** `backend/packages/harness/deerflow/tracing/factory.py`
**Target in MARVIN:** `marvin/graph/runner.py`, `marvin/llm_factory.py`
**Tier:** A
**Priority:** HIGH

### What to import

The concept is a `build_tracing_callbacks()` factory function that returns a list of LangChain-compatible callbacks based on available env vars. Those callbacks are passed to every LangGraph graph invocation and every LLM instantiation. No code path changes required — callbacks are additive.

### Files to add/modify in MARVIN

- `marvin/tracing.py` (new): thin factory — check `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` env vars, return `[LangfuseCallbackHandler()]` if set, else `[]`.
- `marvin/graph/runner.py`: pass `callbacks=build_tracing_callbacks()` to `graph.stream()` or `graph.invoke()`.
- `marvin/llm_factory.py`: pass same callbacks to each `ChatOpenAI` / `AzureChatOpenAI` instantiation.
- `.env.example`: add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (for self-hosted).

### Files NOT to touch

- `marvin_ui/server.py`: SSE event emission is unrelated to tracing. Do not conflate.
- `marvin/events.py`: event ownership is correct as-is. Tracing is observability, not business events.
- Any gate or persistence logic: tracing is read-only instrumentation.

### Effort

4–6 hours. `langfuse` Python SDK is a `pip install`. The factory is 20 lines. Wiring callbacks into `runner.py` and `llm_factory.py` is mechanical. Confidence: high — deer-flow's pattern is well-established LangChain boilerplate.

### Risk

Low. Callbacks are additive. If `LANGFUSE_*` env vars are absent, the factory returns `[]` and nothing changes. The only failure mode is a misconfigured Langfuse host causing network errors on every LLM call — mitigated by catching exceptions in the factory and logging a warning rather than raising.

### Acceptance test

Run a full CDD mission. In the Langfuse dashboard, verify: (1) each node appears as a named span, (2) token counts are present, (3) the mission completes without error. If Langfuse is unreachable, verify the mission still completes normally (graceful degradation).

### Rollback

Remove `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` from `.env`. The factory returns `[]`, callbacks are empty, zero behavioral change.

---

## Pattern 2 — Context Summarization Gate

**Source:** `backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py`
**Target in MARVIN:** `marvin/graph/runner.py`, new `marvin/context.py`
**Tier:** A
**Priority:** MEDIUM

### What to import

The concept is a token-count check before each node invocation. If accumulated `messages` in `MarvinState` exceed a threshold (suggested: 12,000 tokens as a conservative start for GPT-class models), summarize all but the last N messages using a cheap LLM call. The summary replaces the older messages in state; recent messages are preserved verbatim.

This is not about copying deer-flow's middleware class. MARVIN's phase-driven graph means the natural checkpoints for summarization are after `research_join` (before gate) and after `gate_g1_passed` (before adversus) — moments where older framing/research messages are no longer needed in full detail.

### Files to add/modify in MARVIN

- `marvin/context.py` (new): `maybe_summarize(state: MarvinState, threshold_tokens: int = 12000) -> MarvinState` — token count check, LLM summarize call if over threshold, returns new state with messages replaced. Must return a new object (immutability rule).
- `marvin/graph/runner.py`: call `maybe_summarize` in `research_join` node body and optionally in `gate_entry_node` body before continuing.
- `marvin/llm_factory.py`: add a `summarizer` role pointing to a cheap/fast model (e.g., `openai/gpt-4o-mini` via OpenRouter) — do not use the same model as analysis roles.

### Files NOT to touch

- `marvin/graph/nodes/`: individual node logic stays unchanged. Summarization happens at join/gate points, not inside workstream nodes.
- `marvin/mission/store.py`: summarization is a runtime state transform, not a persistence operation. Do not write summaries to SQLite.
- `marvin/events.py`: no event needed for summarization — it is transparent to the UI.

### Effort

8–12 hours. Token counting requires `tiktoken` or a token estimation heuristic. The summarize call itself is simple. The tricky part is testing that important framing information survives summarization — requires a representative long CDD transcript as a test fixture. Confidence: medium (token estimation and summary quality need validation against real mission data).

### Risk

Medium. If the summarizer loses critical framing details, downstream nodes (adversus, merlin) will produce lower-quality output. Mitigation: set a conservative threshold (12k tokens), always keep the last 8 messages verbatim, and include a summary header like "Summary of prior research:" so the LLM treats it as context, not as messages.

### Acceptance test

Run a CDD mission that reaches `adversus`. Before Pattern 2: check token count of `state.messages` at adversus entry — record it. After Pattern 2: verify token count is below threshold, verify adversus output quality is not degraded (spot-check 3 missions), verify total mission cost in Langfuse (Pattern 1 required) drops by at least 15%.

### Rollback

Remove `maybe_summarize` calls from `runner.py`. Two-line revert. The `marvin/context.py` file can stay inert.

---

## Pattern 3 — Session-scoped User Memory

**Source:** `backend/packages/harness/deerflow/agents/memory/`
**Target in MARVIN:** new `marvin/memory.py`, `marvin_ui/server.py`
**Tier:** A
**Priority:** MEDIUM

### What to import

The concept is LLM-powered extraction of user-preference facts from conversation history, stored as JSON with confidence scores, and injected as a prefix into the system prompt at session start. deer-flow uses a 30-second async debounce queue; for MARVIN, a simpler synchronous extraction at mission completion is sufficient — consulting missions have a defined end, unlike open-ended chat.

Do not copy deer-flow's async queue architecture. MARVIN's missions are bounded. Extract facts at `done` phase, store in a per-user JSON file (`~/.marvin/memory/{user_id}.json`), inject top-10 facts into framing node system prompt on next mission start.

### Files to add/modify in MARVIN

- `marvin/memory.py` (new): `extract_user_facts(messages: list, existing_facts: list) -> list` — LLM call to merge new observations with existing facts, deduplicate, score confidence. `load_user_facts(user_id) -> list`, `save_user_facts(user_id, facts)`.
- `marvin/graph/nodes/papyrus.py` (or wherever `done` phase is finalized): call `extract_user_facts` and `save_user_facts` asynchronously after deliverable generation.
- `marvin/graph/nodes/framing.py`: prepend top-10 user facts to the framing system prompt.
- `marvin_ui/server.py`: resolve `user_id` from session/request context and pass into `_stream_chat`. (This requires MARVIN to have a user identity concept — see Risk.)

### Files NOT to touch

- `marvin/mission/store.py`: user facts are separate from mission data. Do not add a `user_facts` table to the missions schema.
- Any gate or routing logic: memory injection is a prompt concern, not a control-flow concern.

### Effort

12–16 hours. The extraction LLM call is straightforward. The blocking item is that MARVIN currently has no user identity concept — `mission_id` exists, but there is no `user_id` threading through the stack. Either add a simple `user_id` (e.g., from a query param or hardcoded for single-user mode) or treat it as a single-user system writing to `~/.marvin/memory/default.json`. The single-user shortcut reduces effort to 6–8 hours. Confidence: medium.

### Risk

Medium. Two risks: (1) user identity — if MARVIN is single-user for now, hardcode `default` and revisit; (2) fact quality — LLM extraction can hallucinate preferences not expressed. Mitigate with a confidence threshold (only inject facts with score ≥ 0.7) and a human-readable fact file at `~/.marvin/memory/default.json` that the analyst can manually edit.

### Acceptance test

Run two consecutive CDD missions. In the second mission's framing node, verify the system prompt contains extracted facts from mission one (e.g., "User works at [firm], focuses on SaaS, flags high churn as critical"). Verify framing output reflects those preferences without the analyst re-stating them.

### Rollback

Remove fact injection from `framing.py` system prompt construction. Memory file stays on disk but is no longer read. Two-line revert.

---

## Pattern 4 — Workstream Timeout + SSE Lifecycle

**Source:** `backend/packages/harness/deerflow/subagents/executor.py`
**Target in MARVIN:** `marvin/graph/nodes/dora.py`, `marvin/graph/nodes/calculus.py`, `marvin_ui/server.py`
**Tier:** B
**Priority:** LOW

### What to import

The concept is wrapping each workstream agent invocation in a timeout-bounded executor with explicit SSE events for `task_started`, `task_running`, and `task_timed_out`. If a workstream exceeds the timeout, the mission surfaces a recoverable error rather than hanging.

deer-flow uses thread pools; MARVIN should use `asyncio.wait_for` with a configurable timeout (suggested: 10 minutes per workstream). The SSE events already flow through `marvin_ui/server.py`'s `map_tool_to_sse_event` — add `workstream_timeout` as a new SSE event type.

### Files to add/modify in MARVIN

- `marvin/graph/nodes/dora.py`, `marvin/graph/nodes/calculus.py`: wrap agent invocation in `asyncio.wait_for(agent.ainvoke(...), timeout=600)`. On `asyncio.TimeoutError`, set `state.phase = "workstream_timeout"` and emit an error finding.
- `marvin/graph/runner.py` (`phase_router`): add `"workstream_timeout"` → `gate_entry` or a new error-surfacing path.
- `marvin_ui/server.py` (`map_tool_to_sse_event`): handle `workstream_timeout` phase transition → emit `{ type: "workstream_timeout", workstream: "W1" }` SSE event.
- Frontend `MissionControl.tsx`: display a timeout warning with retry affordance.

### Files NOT to touch

- `marvin/events.py`: workstream timeout is a phase event, not a business fact event. Do not add it to the EventRegistry.
- Gate logic: a timeout is not a gate failure. Do not route through `gate_node`.

### Effort

10–14 hours including frontend. The Python side is 2 hours. The harder part is deciding what happens after a timeout: retry, skip, or fail the mission. That product decision needs to be made before implementation. Confidence: medium (effort depends on chosen recovery path).

### Risk

Low to medium. `asyncio.wait_for` is standard library. The risk is silently swallowing a timeout that should have been retried — mitigate by surfacing the timeout explicitly in the UI and requiring analyst action (retry or proceed with partial research).

### Acceptance test

Mock a workstream that sleeps for longer than the timeout. Verify: (1) mission does not hang, (2) SSE emits `workstream_timeout` within the timeout window, (3) UI displays a timeout warning, (4) analyst can retry or proceed.

### Rollback

Remove `asyncio.wait_for` wrappers. Workstreams return to unbounded execution. Two-line revert per node.

---

## Section 4 — Executive Summary

# deer-flow → MARVIN — Recommendation

## TL;DR

deer-flow is a general-purpose AI assistant platform with 61.5k stars earned by being useful to a broad audience. MARVIN is a consulting operating system with hard correctness requirements. Most of deer-flow's complexity exists to solve problems MARVIN does not have (sandbox, MCP, multi-process runtime, filesystem virtualization). Three patterns are worth importing: observability, context management, and user memory — in that order. Everything else is noise for this use case.

## Patterns to import (priority order)

1. **Langfuse Tracing** — Zero behavioral change, immediate diagnostic value, 4–6 hours, high confidence. Do this first. Every subsequent decision about model costs, phase latency, and failure rates becomes data-driven instead of guesswork.
2. **Context Summarization** — Prevents token bloat in long CDD missions. Implement after tracing so you can measure the before/after cost delta with real data, not estimates.
3. **Session-scoped User Memory** — Highest analyst UX impact. Start single-user with a JSON file. Add `user_id` threading only when multi-user is required.
4. **Workstream Timeout + SSE lifecycle** — Implement after the above three. The product decision about recovery (retry vs. skip vs. fail) should be made before writing code.

## Patterns NOT to import (and why)

1. **Sandbox / Virtual Filesystem** — CDD produces text deliverables in SQLite, not binary files. Adds infrastructure complexity with zero current use case.
2. **MCP Integration** — No external data provider integration is planned. Premature abstraction.
3. **Gateway Mode / DeerFlowClient** — MARVIN already uses the simpler single-process architecture. Copying this would be a regression.
4. **Reflection / Self-critique Loop** — MARVIN's adversus + human gate model is architecturally superior for a use case where humans must validate adversarial challenge, not just an LLM evaluating itself.
5. **Skills System (now)** — Useful at 4+ workstreams or multiple consulting workflows. Premature for single-workflow operation.

## What MARVIN already has, comparable to deer-flow

- **Deterministic phase routing** — MARVIN's `phase_router` in Python is more robust than LLM-driven routing for a high-stakes consulting workflow. deer-flow does not offer this guarantee.
- **Idempotent gate persistence** — MARVIN's `validate` endpoint is idempotent (no 409 on double-click, per recent commit). deer-flow has no equivalent gate model.
- **Event ownership at persistence chokepoints** — MARVIN's `EventRegistry` ties SSE emission to Python-owned business facts, not to opportunistic LLM tool calls. This is correct and should not be changed.
- **Single-process SSE streaming** — MARVIN's `_stream_chat` is effectively deer-flow's Gateway mode, without the experimental flag. MARVIN made the right call by default.
- **Structured deliverable persistence** — Findings, hypotheses, gates, and deliverables are fully persisted in SQLite with proper foreign key enforcement. deer-flow has no equivalent structured output model.

## Architectural decisions NOT to revisit

- **Python phase routing** — deer-flow uses LLM-driven routing in some paths. MARVIN should not. Correctness in a CDD gate workflow requires determinism.
- **Single-process architecture** — deer-flow's Standard mode runs 4 processes with Nginx proxying. MARVIN's single FastAPI process is simpler and sufficient. Do not introduce process separation.
- **Gate model with human validation** — deer-flow's reflection loop is an LLM evaluating itself. MARVIN requires human sign-off. This is a product correctness requirement, not a limitation.
- **Persistence in SQLite** — deer-flow uses JSON files for memory and config. MARVIN's structured SQLite schema is more robust for multi-entity CDD data (hypotheses, findings, gates, milestones). Do not migrate to file-based storage.

## Suggested sequencing

**Now (before scaling current CDD workflow):** Langfuse Tracing. No behavior changes, pure instrumentation. Enables all subsequent decisions to be data-driven. This should be done before the next milestone cycle.

**After first real multi-mission usage:** Context Summarization. Once Langfuse shows actual token counts per mission phase, tune the summarization threshold against real data rather than estimates.

**After multi-user is a requirement:** User Memory. Start with single-user JSON, add `user_id` threading only when a second analyst needs the system simultaneously.

**Defer indefinitely:** Skills System, MCP, Sandbox, Reflection Loop, Gateway Mode.
