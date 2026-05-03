# Debug Log

Bugs found and fixed during development. Most recent first.

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
