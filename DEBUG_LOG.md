# Debug Log

Bugs found and fixed during development. Most recent first.

---

## 2026-05-04 — Live runtime hardening (Phase G)

Five bugs surfaced during a live Netflix CDD run. Each diagnosed from runtime evidence (Render logs, SQLite checkpoint inspection, /progress endpoint poll), then fixed with the smallest-possible change. Adversarial review pass via `architect-reviewer` rejected three larger refactors before they were attempted — see `docs/graph-advance-paths.md`.

### G1 loop: gate spun forever waiting for missing workstream report

**Symptom:** Live Render mission `m-netflix-20260504-x-5922d6e1` froze at 33% with chat banner "Deliverable writing in progress." Backend logs (every ~3s):
```
gate_node: gate gate-...-G1 not opened after 3 attempts;
missing material: deliverable_writing_in_progress; returning to phase=research_done
```

**Root cause:** `research_join` runs Papyrus to generate W1/W2 workstream reports. If the LLM call silently failed (caught by bare `except Exception` at `runner.py:504`), the deliverable was never persisted as `ready`. Phase advanced to `research_done` regardless. `evaluate_gate_material` for `manager_review` requires a ready `workstream_report` per workstream (`gate_material.py:200-208`); missing → `missing_material=['deliverable_writing_in_progress']`. The retry path (`_gate_to_retry_phase("manager_review") → "research_done"`) routed straight back to `gate_entry`, never re-running Papyrus → infinite loop.

**Fix:** Added `papyrus_recover_workstreams_node` (one-shot) and `papyrus_recovery_attempts` counter in `MarvinState`. On first G1 failure with `deliverable_writing_in_progress`, gate routes to recovery instead of looping; recovery re-runs `_generate_workstream_report_impl` for W1+W2 idempotently, then back through gate_entry. Cap = 1 attempt. Second failure → `phase=blocked_terminal` with `phase_blocked` SSE so the user sees a real error instead of a 33% spinner.

**Files touched:** `marvin/graph/runner.py`, `marvin/graph/gates.py`, `marvin/graph/state.py`. Regression tests in `tests/test_gate_papyrus_recovery.py`. **Commit:** `65f8022`.

### Stale "Gate pending — Manager review" banner persisted across page reload

**Symptom:** After approving G1 in the UI, reloading the page resurrected the gate-pending message with active APPROVE/REJECT buttons. `progress.gates` returned correctly (gate `completed`/`failed`, not `open`), but the chat panel still rendered buttons against the resolved gate.

**Root cause:** `mission_chat_messages` rows persist `gate_action='pending'` from when the gate was first opened. The frontend's live state correctly transitions via `markGateChatMessageResolved` on the user's click, but the persisted row was never updated. On reload, `getMissionChatMessages` returned the original `pending` row → `RightRail.tsx:213` rendered buttons whenever `m.gateAction === "pending"`.

**Fix:** Added `MissionStore.resolve_persisted_gate_chat(mission_id, gate_id, verdict)` which UPDATEs `gate_action` to approved/rejected and rewrites the row text to match the live in-memory transition. Called from `validate_gate` before `_deliver_resume`.

**Files touched:** `marvin/mission/store.py`, `marvin_ui/server.py`. **Commit:** `eefc307`.

### TypeError "Failed to fetch" promoted to Next.js dev-mode runtime overlay

**Symptom:** Restarting the backend mid-mission crashed the frontend with a red Next.js error overlay: `Console TypeError: Failed to fetch` at `lib/missions/api.ts:240` in `getMissionProgress`.

**Root cause:** `getMissionProgress` only caught HTTP status errors (`!response.ok`). Network-layer rejection (`fetch()` throws `TypeError`) propagated raw. `MissionControl.tsx:534` caught it and called `console.error`, which Next.js dev mode promotes to a runtime overlay.

**Fix:** Wrapped `fetch()` in try/catch, converted `TypeError` to existing `BackendOfflineError`. `refreshProgress` skips `console.error` when `isBackendOfflineError(error)` returns true → silent recovery on next poll tick.

**Files touched:** `lib/missions/api.ts`, `components/marvin/MissionControl.tsx`. **Commit:** `eefc307`.

### Dead-air window between gate approval and first agent narration

**Symptom:** After approving a gate, ~10–30s of silence before any agent message appeared. The agent IS running its first LLM call; UI shows nothing.

**Root cause:** Heartbeat narration (`server.py:1320`, 15s interval) only fires AFTER the first node update. Long-running entry nodes (`adversus_node`, `merlin_node`, `papyrus_stress_report_node`, `papyrus_recover_workstreams_node`, `research_rebuttal_node`) called `log_node_entry` (logger only, not user-visible) then immediately invoked the LLM.

**Fix:** Added `_emit_entry_narration(mission_id, agent, intent)` helper in `runner.py` (mirrors `_join_narrate` shape from research_join). Called at the entry of each long-running node, emits a `narration` SSE event before the LLM call.

**Files touched:** `marvin/graph/runner.py`. **Commit:** `eefc307`.

### Resume loop figé at next=('research_join',) — burned all 8 steps doing nothing

**Symptom:** Live mission `m-netflix-20260504-x-20beb7b0` stalled at 50% with `next=('research_join',)`. Backend logs:
```
Resume continuing from runnable checkpoint: next=('research_join',)   x5
Resume step limit reached
```
Manually invoking `graph.astream(None, config)` from a script ran `research_join` successfully on the first pass — so the graph itself worked.

**Root cause:** The resume loop in `_stream_resume` (`server.py:2458-2540`) had no guard for "did `next` change?" between iterations. When `astream(None)` yields zero events on a runnable checkpoint (subgraph recursion-limit exhausted, or any other condition that prevents the queued node from executing), the loop saw `post_snapshot.next` non-empty, logged `Resume continuing from runnable checkpoint`, and re-entered with `next_input=None` — same state, same outcome, 8 times. Step limit reached without progress.

**Investigation discipline:** First diagnosis ("lock contention from concurrent `_stream_chat` / `_drive_detached_resume`") was wrong. The architect-reviewer adversarial pass against `docs/graph-advance-paths.md` proved the real cause was the zero-event loop, not lock contention. The 8-step limit was a symptom amplifier, not the source.

**Fix:** Track `prev_runnable_next` + `events_yielded_in_pass` per iteration. If a pass yields 0 events AND `post_snapshot.next` equals the previous iteration's `next`, log at ERROR level and break. The user sees a visible stall instead of a silent 33% spinner; re-running cannot make progress on this state, so retry burns budget for nothing.

**Files touched:** `marvin_ui/server.py`. Test in `tests/test_resume_loop_stall_guard.py` (3 cases: confirms current loop burns 8 steps, guarded loop breaks at iter 2, guard does NOT fire when astream is making progress). **Commit:** `a6cc35c`.

**Lessons captured in `docs/graph-advance-paths.md`:** the resume/recovery layer has accumulated 8 overlapping mechanisms (3 lock-holders + 5 ancillary). Three larger refactors (remove detached driver, drop step limit, drop sync `evaluate_gate_material`) were rejected by the adversarial review — the simple stall guard was the only operation that addressed the confirmed bug without introducing new ones.

---

## 2026-05-03 — Investment-decision migration runtime regressions

Surfaced live while testing the new verdict enums (`INVEST / INVEST_WITH_CONDITIONS / DO_NOT_INVEST / INSUFFICIENT_EVIDENCE`). Three real bugs and one pre-existing schema drift.

### `database is locked` blocking framing_node and all writes

**Symptom:** After restarting the backend post-migration, the brief stayed at 0% indefinitely. uvicorn log showed `sqlite3.OperationalError: database is locked` raised from `save_mission_brief` during `framing_node`. Subsequent writes from any path failed the same way.

**Root cause:** `~/.marvin/marvin.db` was in `journal_mode = delete`, which serializes all writers and blocks readers during a write. With `MissionStore` (sync) and `AsyncSqliteSaver` (async, via LangGraph) competing on the same file, contention was already at the limit; the merlin_verdicts rebuild inside `_apply_additive_migrations` pushed it over. A leftover `marvin.db-journal` file confirmed an aborted transaction holding the lock. Default 5s `busy_timeout` was too short for the rebuild window.

**Fix:** Switched the DB to `journal_mode = WAL` (concurrent reader + writer), bumped connection `timeout` to 30s, and pinned `busy_timeout = 30000` in `MissionStore.__init__`. Setting is persistent at the database level. Ran a one-off `PRAGMA journal_mode = WAL` to fix the existing file.

**Files touched:** `marvin/mission/store.py`

### Merlin verdict never persisted; G3 never opened; Papyrus never ran

**Symptom:** A live Netflix mission emitted "Merlin — Verdict · Do not invest" via SSE narration but the verdict row never appeared in the DB. Mission stayed at `synthesis_state = running` with `active_agent = research_rebuttal`. G3 `final_review` gate stayed `pending` indefinitely; Papyrus never produced an exec summary.

**Root cause:** Existing `~/.marvin/marvin.db` still had the legacy `CHECK (verdict IN ('SHIP','MINOR_FIXES','BACK_TO_DRAWING_BOARD'))` constraint on `merlin_verdicts.verdict`. The investment-decision migration updated `001_init.sql` for fresh DBs but SQLite has no `ALTER TABLE ... DROP CHECK`, so existing DBs kept the old constraint. `set_merlin_verdict()` raised `sqlite3.IntegrityError` on every insert, the LangGraph tool retry exhausted, and the mission silently parked at the rebuttal phase.

**Fix:** Added a table-rebuild step at the end of `_apply_additive_migrations` that detects the legacy CHECK (`'BACK_TO_DRAWING_BOARD' in sql and 'INVEST' not in sql`), drops FKs temporarily, recreates the table with a CHECK accepting both new (4) and legacy (3) enums, copies non-orphan rows (filter by `EXISTS missions`), drops the old table, renames. Idempotent; runs once per DB.

**Files touched:** `marvin/mission/store.py`

### Pre-existing schema drift: `parent_mission_id` and `channel_id`

**Symptom:** `GET /api/v1/missions` returned HTTP 500 with `pydantic_core.ValidationError: Extra inputs are not permitted` on `parent_mission_id`. Backend log spam from chat persistence: `chat message persistence failed: 1 validation error for MissionChatMessage / channel_id / Extra inputs are not permitted`.

**Root cause:** Previous schema work added DB columns (`missions.parent_mission_id`, `mission_chat_messages.channel_id`) without adding the corresponding fields to the Pydantic models. With `model_config = ConfigDict(extra="forbid")`, every read raised. The migration didn't introduce the columns but surfaced the warnings on every chat write because the new flow exercised more chat persistence paths.

**Fix:** Added `parent_mission_id: str | None = None` to `Mission` and `channel_id: str | None = None` to `MissionChatMessage`.

**Files touched:** `marvin/mission/schema.py`

### G1 chat showed "Approve recommendation" instead of "Approve"

**Symptom:** At G0 (hypothesis confirmation) and G1 (manager review), the chat-bubble CTAs showed "Approve recommendation →" / "Request review" — investment-decision branding that belongs only to G3 (final review).

**Root cause:** During the migration, `RightRail.tsx` chat-bubble buttons were renamed unconditionally for all gates. The component has no `gate_type` context for chat-bubble gates.

**Fix:** Reverted the chat-bubble labels to generic "Approve →" / "Reject". The investment-decision branding ("Approve recommendation", final_thesis / conditions / deal_breakers display) remains in the G3 full-screen modal in `MissionControl.tsx`, which is G3-scoped by construction.

**Files touched:** `components/marvin/v2/RightRail.tsx`

---

## 2026-05-02 — Worktree `codex/mission-flow-hardening` bug ledger

Scope reconstructed from commits:

- `847365d fix(phase-h): harden mission flow truthfulness`
- `3701bba fix(phase-h): harden mission flow recovery`
- `303c6c1 fix(phase-h): align gate timing and agent visibility`

I found the fixes below in commits/tests. I did not find a single pre-existing debug document that listed them all, so this section is the consolidated ledger.

### Mission page crashed with React error #310

**Symptom:** Opening a mission page could fall into the generic "Something went wrong" screen with minified React error `#310`.

**Root cause:** A new `useMemo` for hypothesis enrichment in `MissionControl.tsx` had been added below `if (!hasLoaded) return null`, so hook count varied across renders.

**Fix:** Moved the `hypotheses` `useMemo` back into the hook-safe zone above all early returns, preserving stable hook order across renders.

**Files touched:** `components/marvin/MissionControl.tsx`

### Final deliverables tab showed Red Team / Merlin content

**Symptom:** The `Final deliverables` tab showed the same synthesis verdict content as `Red team & verdict`; `Exec summary` and `Data book` appeared in the left rail but not as the primary final-tab content.

**Root cause:** `components/marvin/MissionControl.tsx` injected a synthetic Merlin verdict row into both W3 and `final` (`synthesis-verdict-final-*`). That made the final tab look like a duplicate of red-team synthesis.

**Fix:** Keep the synthetic Merlin verdict only on W3 / Red Team & Verdict. Route final artifacts by deliverable type only. Added routing support for both `exec_summary` and `executive_summary`.

**Files touched:** `components/marvin/MissionControl.tsx`, `lib/missions/adapters.ts`, `tests/mission-control-ux.test.ts`

### Terminal milestone rows still displayed `WRITING`

**Symptom:** After a gate was approved or the mission completed, milestone rows such as `Red-team hypotheses` and `Stress scenarios and PESTEL` could still show `WRITING`.

**Root cause:** `CenterPane.MilestoneRow` accepted `isTerminal` but did not use it. A delivered milestone without a dedicated per-milestone file was rendered as if writing was still in progress.

**Fix:** Terminal milestone rows without a dedicated file are hidden instead of showing `WRITING`. The workstream deliverable remains the user-facing artifact.

**Files touched:** `components/marvin/v2/CenterPane.tsx`

### G1 opened while optional financial reports were still being written

**Symptom:** `Public filings review` / `Anomaly detection` could be visible or even drafting while the manager review gate appeared.

**Root cause:** G1 material evaluation excluded W2.2/W2.3 as internal optional milestones even when they had actually been delivered and Papyrus was drafting files for them.

**Fix:** G1 now includes all W1/W2 milestones in terminal/material checks. Blocked/skipped optional milestones do not block; delivered visible milestones require ready milestone reports.

**Files touched:** `marvin/graph/gate_material.py`, `tests/test_gate_material.py`

### W2.2/W2.3 hidden from tab completion but visible in deliverables

**Symptom:** Financial analysis could show a checkmark while W2.2/W2.3 deliverables were still visible in the left rail.

**Root cause:** Frontend `isVisibleMilestone` hid W2.2/W2.3, so tab completion ignored milestones the user could still see as deliverables.

**Fix:** W2.2/W2.3 are now considered visible when present. If backend produces them, completion waits for them.

**Files touched:** `components/marvin/MissionControl.tsx`

### Merlin / Adversus appeared `RUNNING` late

**Symptom:** The activity feed showed Merlin or Adversus work, but the left rail still showed them idle/done until later.

**Root cause:** Tool callback narrations were marked `destination=trace` and hidden from chat, but the UI did not use those trace narrations as agent-status signals.

**Fix:** Any non-MARVIN narration with an agent now marks that agent active in the rail while preserving trace filtering from the chat.

**Files touched:** `components/marvin/MissionControl.tsx`

### Merlin took too long and replayed stale context

**Symptom:** Merlin could spend multiple minutes reviewing findings; live output sometimes felt like it was re-reading old mission prose.

**Root cause:** Merlin received the full accumulated LangGraph message history on every verdict pass. Long missions therefore sent a large, stale context bundle in addition to the tools Merlin can use to read persisted mission truth.

**Fix:** Merlin now receives only the current verdict instruction plus pending steering context; persisted data remains accessible via mission-scoped tools. Adversus received the same treatment for red-team passes.

**Files touched:** `marvin/graph/runner.py`

### Hypotheses changed badge without explaining why

**Symptom:** Sidebar hypotheses could become `WEAKENED` without the consultant seeing a concrete reason.

**Root cause:** Computed rationale existed in `/progress`, but the left rail only showed it on selected hypotheses and collapsed it otherwise.

**Fix:** `WEAKENED` / `CHALLENGED` hypotheses now show the rationale directly in the sidebar. Contradicting red-team evidence maps to `CHALLENGED`, while low-confidence weakness remains `WEAKENED`.

**Files touched:** `marvin/tools/mission_tools.py`, `components/marvin/v2/LeftRail.tsx`, `components/marvin/MissionControl.tsx`, `tests/test_compute_hypothesis_status.py`

### Clicking a hypothesis did not open the Brief tab

**Symptom:** The vision target says clicking a hypothesis should display it in Brief, but the UI only toggled sidebar selection.

**Root cause:** `onSelectHypothesis` updated `selectedHypothesisId` only.

**Fix:** Hypothesis click now also selects the `brief` workspace tab.

**Files touched:** `components/marvin/MissionControl.tsx`

### Agents rail was too low in the left column

**Symptom:** Agent status required scrolling past deliverables, while the user expected it directly after hypotheses.

**Root cause:** Left rail order was `MissionCard → Hypotheses → Deliverables → Agents`.

**Fix:** Reordered to `MissionCard → Hypotheses → Agents → Deliverables`.

**Files touched:** `components/marvin/v2/LeftRail.tsx`

### Refresh / resume consumed an open gate instead of replaying it

**Symptom:** Refreshing or resuming a mission with an open checkpoint could make the gate invisible or relaunch graph work.

**Root cause:** Resume paths did not consistently treat an open persisted gate as the source of truth. Some paths attempted to continue graph execution to “rediscover” the gate.

**Fix:** Resume now emits `gate_pending` from the persisted gate and stops instead of relaunching Merlin/framing/Papyrus. Detached recovery also re-emits runnable checkpoints after client cancellation.

**Files touched:** `marvin_ui/server.py`, `tests/test_detached_resume_consumes_interrupt.py`, `tests/test_server_continuable_checkpoint.py`

### Historical chat replay lost order or omitted important bubbles

**Symptom:** Reload could preserve mission state but lose the original chat ordering or omit gate/deliverable bubbles.

**Root cause:** Replay did not consistently reconstruct bubbles from persisted events with the same monotonic sequence semantics as live SSE.

**Fix:** Persisted gates and deliverables now reconstruct into chat with stable ordering. Papyrus deliverable chat and gate pending chat are persisted/replayed.

**Files touched:** `marvin_ui/server.py`, `lib/missions/adapters.ts`, `tests/test_server_sse.py`, `tests/mission-control-ux.test.ts`

### Raw tool / JSON noise leaked into user surfaces

**Symptom:** Tool payloads such as SEC/Tavily/get_hypotheses details could appear in user-facing activity/chat.

**Root cause:** The SSE layer exposed too many tool events by default, even though business facts should be emitted from persistence chokepoints.

**Fix:** Raw tool events are hidden by default unless `MARVIN_SHOW_RAW_TOOL_EVENTS` is enabled. Known trace-only tools are filtered from chat while persistence-owned events still emit findings/deliverables/milestones from `marvin/events.py`.

**Files touched:** `marvin_ui/server.py`, `marvin/graph/tool_callbacks.py`, `tests/test_server_sse.py`

### Live findings appeared only after a section was done

**Symptom:** Agent conclusions showed in Activity but not in Outputs until deliverables or persisted progress refreshes landed.

**Root cause:** Live `finding_added` / agent prose events were not normalized with the same section-routing adapter as `/progress` hydration.

**Fix:** Live findings and long agent messages are routed through agent/workstream mapping into the active output sections, including W3/W4.

**Files touched:** `components/marvin/MissionControl.tsx`, `lib/missions/adapters.ts`, `tests/mission-control-ux.test.ts`

### Competitive mapping / Moat assessment blocked despite usable findings

**Symptom:** W1.2/W1.3 could block with “agent did not tag findings to this milestone” even when Dora produced relevant Nvidia/Uber-style findings.

**Root cause:** `research_join` depended too much on LLM-provided `milestone_id` tags.

**Fix:** Added deterministic Python coverage derivation so untagged findings can satisfy W1/W2 milestones when content/workstream is sufficient.

**Files touched:** `marvin/graph/runner.py`, `tests/test_gate_material.py`, `tests/test_graph_progression.py`

### Mission completion could fire before canonical deliverables were ready

**Symptom:** The UI could show completion/progress 100% before the final deliverable set was truly persisted.

**Root cause:** Completion used broad status/phase signals rather than the canonical CDD deliverable set.

**Fix:** Completion now checks canonical deliverables (`engagement_brief`, W1/W2/W4 reports, `exec_summary`, `data_book`) before marking the mission done.

**Files touched:** `marvin/graph/runner.py`, `tests/test_mission_system_contracts.py`, `scripts/smoke_runtime.py`

### Merlin duplicate verdicts on refresh/resume

**Symptom:** Resume could create repeated Merlin findings/verdict-like outputs instead of surfacing the existing final review.

**Root cause:** Merlin was used to rediscover gate state rather than treating the persisted final gate/verdict as authoritative.

**Fix:** Merlin node now skips duplicate passes when final review is already available or completed.

**Files touched:** `marvin/graph/runner.py`, `tests/test_mission_system_contracts.py`

### EDGAR fiscal-year matching missed relevant filings

**Symptom:** Calculus could report no filings for companies where filings existed.

**Root cause:** EDGAR fiscal-year matching used an overly narrow/year-derived criterion.

**Fix:** Matching now uses report dates more robustly.

**Files touched:** `marvin/tools/calculus_tools.py`, `marvin/tools/edgar_client.py`, `tests/test_edgar_client.py`

### `npm test` collected Playwright specs and failed

**Symptom:** Unit tests passed via direct Vitest command, but `npm test` failed because it picked up non-unit specs.

**Root cause:** Vitest config collected files outside the intended unit test set.

**Fix:** `vitest.config.ts` now scopes `npm test` to the intended unit tests.

**Files touched:** `vitest.config.ts`

### Papyrus model cost too high for writing

**Symptom:** Writing passes were routed through more expensive models.

**Root cause:** Role routing used expensive models for client-facing drafting.

**Fix:** `papyrus` now routes through `anthropic/claude-3.5-haiku` via OpenRouter, while reasoning-critical Merlin/Adversus remain on stronger models.

**Files touched:** `marvin/llm_factory.py`

---

## 2026-05-02 — `ic_question` required field breaks mission creation

**Symptom:** "Failed to fetch" on "Open mission" button in the New Mission modal.

**Root cause:** Codex commit `847365d` made `ic_question` a required field in `CreateMissionRequest` (`marvin_ui/server.py:715`). The frontend never sends it at creation time — the IC question is asked later in chat, then persisted via `persist_framing` → `_derive_ic_question`. The contract was always `ic_question: ""` at creation (see `lib/missions/repository.ts` comment: `// Will be asked in chat`).

**Fix:** `marvin_ui/server.py` — changed `ic_question: str` → `ic_question: str = ""` in `CreateMissionRequest`.

**Files touched:** `marvin_ui/server.py`

---

## 2026-05-02 — Render webhook disconnected, auto-deploy not triggering

**Symptom:** Push to `main` did not trigger Render redeploy.

**Root cause:** GitHub → Render webhook was disconnected (`gh api repos/.../hooks` returned `[]`).

**Fix:** Triggered manual deploys via Render CLI:
```bash
render deploys create srv-d7p2l53bc2fs73c3lu80  # backend
render deploys create srv-d7p2l8vavr4c73d1gnvg  # frontend
```

**Permanent fix needed:** Reconnect repo in Render dashboard → Settings → Build & Deploy for both services.

---

## 2026-05-03 — Netflix EDGAR false block from early filing limit

**Symptom:** `Financial Analysis` could block for Netflix with `no matching filings`, even though Netflix has a FY2024 10-K on EDGAR (`0001065280-25-000044`, report date `2024-12-31`).

**Root cause:** `list_filings_result` used one `limit` for both scanning recent EDGAR rows and returning filtered results. For active companies, many recent non-target filings can appear before the relevant annual report, so the FY2024 10-K was never inspected before fiscal-year filtering ran.

**Fix:** `list_filings_result` now separates `max_scan` from `limit`. `search_sec_filings` and `fetch_filing_section` scan up to 1000 recent EDGAR rows, apply form/year matching, then cap returned results. Error taxonomy remains honest: if no filing matches after the wider bounded scan, the result still returns `no_matching_filing`.

**Why it prevents repeats:** The fix is company-agnostic. It protects any high-volume filer where the relevant 10-K/10-Q appears deep in the submissions feed, not only Netflix.

**Regression coverage:** Added Netflix-like tests where the valid FY2024 10-K appears after 350 noisy recent filings; both `search_sec_filings` and `fetch_filing_section` must find it.

**Validation:** `tests/test_edgar_client.py` passed, typecheck passed, smoke passed, and a live SEC read confirmed Netflix FY2024 returns the correct 10-K.

**Files touched:** `marvin/tools/edgar_client.py`, `marvin/tools/calculus_tools.py`, `tests/test_edgar_client.py`

---
