# CHANTIERS — MARVIN execution log

Persistent record of the chantiers (work packages) shipped against the
MARVIN audit & roadmap. Authoritative source-of-truth is `git log`; this
file exists so a fresh session can read the state of play without
re-discovering it.

**Conventions**
- Chantier IDs (C1..C13) match the proposals in Deliverable 3 of the
  audit (April 2026).
- Bucket: Foundational (raises KNOWN evidence base) / Conditional
  (depends on Bucket 1) / Independent (delivers value at any base).
- Status: `shipped` (committed + tests + smoke), `validated` (live
  mission confirmed), `deferred`, `in-progress`.
- "Files" lists the primary surfaces touched; not exhaustive — `git
  show <sha>` for the full diff.

---

## Sequencing actually executed

```
Wave 1     C1 + C10               parallel (~1 session)
Wave 1.5   C1 hotfix              after live SNOW validation
Wave 2     C2 + C3                after C1 validated
Wave 2     C4 → C7                after C2/C3 stable
Wave 2     C4 hotfix              after live validation caught regression
Wave 2.5   LangGraph audit fixes  hygiene before Wave 3

Wave 3     C5 → C9 → C6 → C8      pending (later)
Wave 4     C11 / C12 / C13        pending (when core is solid)
```

User-decided sequencing in conversation; tri-bucket from Deliverable 3.

---

## C1 — SEC EDGAR full-text retrieval

- **Bucket:** Foundational
- **Status:** validated (live SNOW mission produced 6 KNOWN findings
  with real `sec.gov/Archives/...` URLs)
- **Commits:** `d0de678`, `d91d340`, `96d7862` (hotfix)

**Problem.** `search_sec_filings` returned hardcoded fake URLs
(`https://sec.gov/{company}-{year}`). Calculus had no way to fetch real
filing text, so it fabricated citations whenever asked for KNOWN
evidence — the root cause of source-pollution flagged in audit
Deliverable 1.

**Shipped.**
- New `marvin/tools/edgar_client.py`: ticker/name → CIK via
  `company_tickers.json`; submissions feed; primary-document fetch;
  Item 1/1A/7/8 section extractor (heuristic, returns longest
  body-chunk, ≥200 char threshold).
- Rewrote `search_sec_filings` to return real `{cik, ticker, filings:
  [{form, accession, filing_date, url, ...}]}` or `{error,
  filings: []}` on miss.
- New tool `fetch_filing_section(company, form, year, section)` —
  returns quotable text + real URL + accession; on `text=None` returns
  explicit error code so agents cannot fabricate.
- Calculus prompt updated: KNOWN requires fetched filing text; use
  `mark_milestone_blocked` on empty results.
- 9 wiring tests using `httpx.MockTransport` (no live SEC traffic in
  CI).
- Smoke duration bumped 8s → 25s (pre-existing flake).

**Hotfix (`96d7862`) — found via live validation:**
- Hardcoded `Host: www.sec.gov` header broke every `data.sec.gov`
  request with 404. Removed; httpx derives Host per-URL.
- `extract_sections` matched the table-of-contents header first
  (short body, rejected) and never tried later occurrences. Switched
  to `re.finditer` + longest-chunk.

---

## C10 — Deal economics module

- **Bucket:** Independent
- **Status:** shipped (component standalone, not yet wired into
  MissionControl tabs)
- **Commits:** `50140b4`

**Problem.** PE diligence without deal math is incomplete. MARVIN had
no place to capture entry multiple, leverage, target IRR/MOIC; no
sensitivity/scenarios; no required-exit math.

**Shipped.**
- Schema: `deal_terms (mission_id PK, entry_revenue, entry_ebitda,
  entry_multiple, entry_equity, leverage_x, hold_years, target_irr,
  target_moic, sector_multiple_low, sector_multiple_high, notes,
  created_at, updated_at)`.
- Pydantic `DealTerms`; store `save_deal_terms` / `get_deal_terms`.
- `marvin/economics/deal_math.py`: entry EV/debt/equity, required
  exit equity, bear/base/bull scenarios with IRR + MOIC. None-tolerant
  — partial captures render gracefully.
- API: `GET/PUT /api/v1/missions/{id}/deal-terms`, `GET
  /api/v1/missions/{id}/deal-math`.
- `components/marvin/DealEconomics.tsx`: standalone client component,
  form + computed table.
- 5 tests (math, store, API roundtrip, 404).

**Open follow-up.**
- Component is not yet integrated as a MissionControl tab.
- **Agent path missing.** No `set_deal_terms` tool exists anywhere
  in the repo (verified 2026-04-30). Calculus has no autonomous way
  to populate `deal_terms` — only the UI's PUT endpoint can. DASH
  live run confirmed: `deal_terms` row never created. Fix needed:
  add agent-callable tool in `calculus_tools.py` + prompt paragraph.

---

## C2 — Data room upload + parser

- **Bucket:** Foundational
- **Status:** shipped (parsers + tool + API + component); not yet
  validated end-to-end live
- **Commits:** `27a87a3`

**Problem.** Private-target CDD requires a data room. MARVIN could only
work on public targets (where C1 covers SEC). Without ingestion, every
private deal was a non-starter.

**Shipped.**
- Schema: `data_room_files (id, mission_id, filename, file_path,
  mime_type, size_bytes, parsed_text, parse_error, uploaded_at)`.
- `marvin/ingestion/data_room.py::parse_file`: pypdf, openpyxl,
  python-docx, csv, txt; 25 MB cap; `ValueError` on unsupported or
  parse failure.
- Agent tool `query_data_room(query)` → `{hits: [{file_id, filename,
  line, snippet, ref="data_room://<id>#L<line>"}, ...]}`. Wired into
  Calculus, Dora, Adversus.
- API: `POST /missions/{id}/data-room/upload` (multipart),
  `GET /data-room`, `DELETE /data-room/{file_id}`.
- `components/marvin/DataRoomUpload.tsx`.
- Deps added: `pypdf`, `openpyxl`, `python-docx`, `python-multipart`.

**Open follow-up.** Component not yet integrated as a tab. End-to-end
live test (upload → Calculus query → finding cited from data room)
not yet performed.

---

## C3 — Expert-call transcript ingestion

- **Bucket:** Foundational
- **Status:** shipped; not yet validated end-to-end live
- **Commits:** `27a87a3` (combined with C2)

**Problem.** Real CDD is ~60% expert calls. MARVIN had no qualitative
evidence channel — desk research only.

**Shipped.**
- Schema: `transcripts (id, mission_id, title, expert_name,
  expert_role, raw_text, line_count, uploaded_at)` +
  `transcript_segments (id, transcript_id, speaker, text, line_start,
  line_end)`.
- `marvin/ingestion/transcripts.py::parse_transcript`: speaker tagging
  for Q/A, `[Name]:`, `Name:` formats; timestamp prefix stripping;
  ambiguous lines → `speaker=None` rather than guessed.
- Agent tool `query_transcripts(query)` → hits with speaker +
  `ref="transcript://<id>:<a>-<b>"`. Wired into Calculus, Dora,
  Adversus.
- API: `POST /missions/{id}/transcripts` (multipart OR text form),
  `GET /transcripts`, `DELETE /transcripts/{id}`.
- `components/marvin/TranscriptUpload.tsx`.

**Open follow-up.** Component not yet integrated. Live end-to-end not
yet tested.

---

## C4 — Source corroboration gate

- **Bucket:** Conditional (depends on C1/C2/C3 evidence base)
- **Status:** validated (SNOW + DASH live runs); rebuttal-pass gap
  closed 2026-04-30 — pending re-validation
- **Commits:** `13972e1`, `af0306d` (hotfix), latest (rebuttal recompute)

**Problem.** A single-source KNOWN finding is partner-grade vulnerable.
Pre-C4, every claim cited from one URL was treated as evidenced.

**Shipped.**
- Schema: `finding_sources (finding_id, source_id)` join table;
  `findings.corroboration_count`, `findings.corroboration_status`;
  `sources.source_type`.
- `marvin/quality/corroboration.py`:
  - `extract_domain` handles http/https + special schemes
    (`data_room://`, `transcript://`).
  - `independent_source_count` groups by `(domain, source_type)`.
  - `evaluate_corroboration` returns `CorroborationResult` with
    `final_confidence` (KNOWN downgraded to REASONED if `<2`
    independent sources) + status `corroborated | single_source |
    downgraded`.
- New tool `add_source_to_finding(finding_id, source_url,
  source_quote, source_type)`.
- `recompute_mission_corroboration(mission_id)` runs in
  `research_join` deterministically before phase advances to
  `research_done`.
- `add_finding_to_mission` auto-derives `source_type` from URL
  (`sec_filing` / `data_room` / `transcript` / `web`); returns
  `corroboration_warning` when KNOWN has only 1 source.
- Calculus prompt updated with corroboration discipline.
- 9 tests.

**Hotfix (`af0306d`) — found via live validation:**
- LLM occasionally passed a URL string as `source_id` (not a real
  `s-...` id). `save_finding`'s auto-mirror into `finding_sources`
  blew up the entire research phase with `FOREIGN KEY constraint
  failed`. Now `save_finding` verifies source row exists before
  mirroring.
- `add_finding_to_mission` detects URL-shaped `source_id` (anything
  not starting with `s-`) and reroutes to `source_url`.

**Gap fix (2026-04-30) — found via DASH live validation:**
- DoorDash mission produced 2 KNOWN findings from Adversus rebuttal
  pass (post-G1) with `corroboration_status=single_source` and
  `corroboration_count=1` — C4 didn't downgrade them. Root cause:
  `recompute_mission_corroboration` runs only in `research_join`
  before G1; rebuttal-pass findings created in
  `research_rebuttal_node` bypass that chokepoint.
- Fix: call `recompute_mission_corroboration` at the exit of
  `research_rebuttal_node` after Calculus + Dora finish.
- Re-validation pending (next live mission).

---

## C7 — Iterative finding pushback (rebuttal pass)

- **Bucket:** Conditional (depends on C1/C2/C3)
- **Status:** shipped (8 unit tests); live behavior not yet
  validated end-to-end
- **Commits:** `d389cc2`

**Problem.** Single-pass research feels like a freshman analyst.
Adversus produces attacks but Calculus/Dora never get to find
counter-evidence — the verdict bypasses the rebuttal.

**Shipped.**
- New phase `rebuttal_done`, new node `research_rebuttal_node`.
- Routing: `redteam_done → research_rebuttal → merlin` (was:
  `redteam_done → merlin` directly).
- Kill switch: `MARVIN_REBUTTAL_ENABLED=0` env var.
- Selection rule: only Adversus findings with `impact=load_bearing`
  OR claim_text containing `anomaly` / `contradicts` / `weakest`;
  capped at 8 attacks per pass.
- Prompt names three honest outcomes:
  1. Counter-evidence falsifies the attack → submit a finding.
  2. Attack is partly right → qualify with a narrowed finding.
  3. Attack stands → corroborate via `add_source_to_finding`.
- Hard cap: 5 new findings per rebuttal pass.
- Sequential Calculus → Dora (no fan-out, no nested rebuttal).
  Subagent failures logged but non-blocking.
- 8 tests (selection, prompt content, router maps, no-targets
  short-circuit).

**Open follow-up.** Live mission has not yet been driven through G1 →
Adversus → rebuttal → Merlin → G3.

---

## Wave 2.5 — LangGraph audit hardening

- **Bucket:** Hygiene (not a chantier; pre-Wave-3 hardening pass)
- **Status:** shipped
- **Commits:** `0aa6315`

**Problem.** Independent LangGraph audit identified 2 HIGH + 4 MED
risks not exercised by the existing test surface but real under
runtime conditions.

**Shipped.**
- **HIGH #1** — `framing` edge map missing `"framing"` self-loop key
  caused `KeyError` if `framing_node` returned `phase="setup"` (no
  human brief yet).
- **HIGH #2** — `_evaluate_brief_via_llm` was sync (`llm.invoke`)
  inside async `framing_orchestrator_node`; blocked the event loop
  for 2-15s per evaluation, stalling SSE keepalives and detached
  resume drivers. Now `await llm.ainvoke(...)`.
- **MED #3** — `asyncio.get_event_loop().create_future()` →
  `get_running_loop()` (deprecation; correct here because called from
  async only).
- **MED #5** — `gate_pending` SSE event fired twice on `Command(resume
  =...)` because LangGraph re-executes the node from the top.
  Process-local `_GATE_PENDING_NOTIFIED` set guards the dispatch;
  cleared after `interrupt()` so future re-opens of the same gate_id
  re-notify.
- **MED #6** — `phase_router` returned `"gate"` directly for
  `awaiting_clarification` and `awaiting_data_decision`, bypassing
  `gate_entry` (CLAUDE.md §4 invariant). Both routed through
  `gate_entry` now (passthrough — pending_gate_id set upstream).

**Skipped.** MED #4 multi-worker resume futures (out of scope until
`uvicorn --workers > 1`); LOW cleanup items.

---

## C-VERDICT — Plain-language Merlin synthesis

- **Bucket:** Output quality
- **Status:** shipped
- **Commits:** `66bf86c`

**Problem.** Synthesis tab read like an internal log: `MINOR_FIXES`,
MECE, `KNOWN`/`REASONED`, `hyp-XXXXX` UUIDs all leaked verbatim into
user-facing prose.

**Shipped.**
- `merlin.md` rewritten: explicit "writing for a managing partner"
  audience, banned-jargon list, plain-language verdict templates that
  drop the verdict enum from the prose (rendered as a badge instead).
- `MissionControl.tsx::synthesisOutputs` strips any leading
  `Verdict: <ENUM>` line and `hyp-` UUIDs as a safety net.

---

## C-TAB-SYNC — Tab check marks reflect terminal state

- **Bucket:** UX
- **Status:** shipped
- **Commits:** `7b6f6d3`

**Problem.** Tabs stayed `●` after gates passed because (a) blocked
milestones short-circuited `wsDelivered === wsMilestones.length`, (b)
stale `liveStatus === "active"` suppressed the completed fallback,
and (c) Synthesis (W3) was milestone-counted instead of verdict-driven.

**Shipped.** `wsTerminal` counts delivered + skipped + blocked; W3
reads `merlin_verdict` presence; active liveStatus no longer regresses
completion.

---

## C-NARRATION — Tool-tape live feed

- **Bucket:** UX
- **Status:** shipped
- **Commits:** `1eec719`

**Problem.** During long renders the right rail showed only "Still
working" — agent activity invisible.

**Shipped.** Tool calls render as a scrolling tape (already appended
via unique ids; the perceived overwriting was the absence of friendly
naming + persistence-tool noise drowning the rest). Friendly-name map
(`fetch_filing_section` → "reading SEC filing"), noisy-tool filter
(persistence echoes hidden), 60-entry cap.

---

## C-PER-MILESTONE — Per-milestone deliverables (Option B)

- **Bucket:** Output coverage
- **Status:** shipped (live validation pending)
- **Commits:** `033099e`

**Problem.** Milestone rows showed DONE but had no Open/Download
because only one aggregate `Wx_report.md` existed per workstream.

**Shipped.**
- Schema: additive `findings.milestone_id` + `deliverables.milestone_id`
  columns.
- Generation: `_generate_milestone_report_impl(milestone_id, ...)`
  mirrors workstream report writing standard, filtered by milestone_id
  (with workstream-level fallback when findings are untagged).
- `research_join` calls per-milestone gen for every delivered milestone
  after the workstream-level pass; failures are best-effort.
- `add_finding_to_mission` accepts optional `milestone_id`; Calculus +
  Dora prompts updated to tag findings when sub-milestone is clear.
- `routeDeliverableToSectionId` regex covers `Wx.y_<slug>.md`;
  `MissionControl::milestoneOutputs` pairs each delivered milestone row
  with its report (or falls back to the parent workstream report).
- `/progress` payload exposes `milestone_id` on deliverables so the UI
  can pair without a second round-trip.
- 3 unit tests + updated existing event-emission test.

---

## C-CONV — Mid-mission steering (conversational redirect)

- **Bucket:** UX / control
- **Status:** shipped (live validation pending)
- **Commits:** `db8b8e4`

**Problem.** "Ask MARVIN or redirect the mission…" input box was wired
only for read-only Q&A and gate approval keywords. There was no way to
steer the mission mid-flight.

**Shipped.**
- New `mission_steering` table queues user instructions during a
  running graph (additive migration).
- `marvin/conversational/steering.py` — heuristic classifier
  (`qa | steer`), English + French imperative cues, question-cue
  priority. `apply_pending_steering(mission_id)` drains rows into
  HumanMessage tape at the entry of every agent node
  (dora/calculus/adversus/merlin).
- `_stream_chat` classifies non-approval messages while graph is
  running: `steer` → queue + ack + `run_end` (no graph re-invoke);
  `qa` → existing `respond_qa` path.
- 19 unit tests; consumed_at guards against double-replay across
  agents.

**Open follow-up.** No LLM classifier yet — heuristic-only. If false
positives or negatives become a problem in live use, swap in a single
LLM call gated to remaining classifier ambiguity.

---

## Graph correctness pass (audit follow-up)

- **Bucket:** Foundational
- **Status:** shipped
- **Commits:** `dc61ce6`, `02f5286`

**Problem.** LangGraph audit identified a CRITICAL (`phase_router`
doing DB writes — replay-unsafe) plus four warnings/partials
(missing `gate_entry` route, silent rebuttal exception swallow,
data-availability fan-out bypass, unclosed checkpoint connection).

**Shipped.** Edge functions are now pure; gate row creation moved to
`gate_entry_node`. Framing orchestrator route map covers `gate_entry`.
`research_rebuttal_node` logs at error level + marks the responsible
workstream blocked when an agent fails. Data-availability route goes
through `gate_entry`. Lifespan handler closes `_checkpoint_conn` on
shutdown.

---

## Pending — backlog

### Wave 3 — Plus tard

#### C-RESUME-RECOVERY — Checkpointer recovery semantics on LLM-call failure

- **Bucket:** Foundational (graph reliability)
- **Effort:** M
- **Priority:** HIGH within Wave 3 — observed live, blocks any mission
  that hits an OpenRouter transient

**Problem.** When OpenRouter returns a transient 5xx with an HTML
body (rate limit, gateway error), `langchain-openai` raises
`json.JSONDecodeError` mid-`agent.ainvoke()`. The exception bubbles
out of the agent node, the detached resume driver catches it at the
top level, logs `Detached resume failed`, and exits. The
AsyncSqliteSaver checkpoint is left at the *entry* of the failed
node, not past it. Every subsequent `POST /resume` re-enters the
same node — adversus retries from scratch, accumulates fresh
findings, and the run never advances to merlin. Live evidence:
Snowflake mission `m-snowflake-20260430-x-d2ab5802` (2026-04-30) sat
in adversus replay after a single OpenRouter HTML response, even
across uvicorn restarts.

**Why this matters.** Any mission that hits a single transient
OpenRouter blip (1-in-N, but real) becomes effectively unrecoverable
without manual checkpointer surgery. The chantiers we just shipped
(C-CONV, C-PER-MILESTONE) are blocked from full live validation
because of this failure mode, not because of their own logic.

**Out of scope.** Replacing OpenRouter, retrying every LLM call
forever, or adding a global "best-effort silently skip the agent on
failure" — that would be silent degradation per CLAUDE.md §1.

**Approach (sketch — confirm before coding).**

1. **Detect the transient class explicitly.** Wrap the `ainvoke()` call
   in each agent node body (dora / calculus / adversus / merlin) with
   a narrow `except (json.JSONDecodeError, openai.APIError,
   httpx.HTTPStatusError)` translator. Re-raise everything else
   unchanged so real bugs still surface.

2. **Bounded retry inside the node.** On detected transient, retry the
   ainvoke up to N times (config: `MARVIN_LLM_TRANSIENT_RETRIES`,
   default 2) with exponential backoff (1s → 4s). Log each retry at
   warning level so the rail can render `agent retrying — transient
   upstream error`. After exhausting retries, raise a typed
   `LLMTransientFailure(agent=..., retries=...)`.

3. **Surface failure, advance phase.** Catch `LLMTransientFailure` at
   the agent-node boundary and convert to a state delta: persist a
   workstream-block (Adversus → W4 blocked, etc.) with a clear
   reason, append a HumanMessage-shaped diagnostic for downstream
   agents, and return `{"phase": "<expected_next_phase>", ...}`.
   This gives the checkpointer a clean post-node state to write so
   `/resume` can advance instead of replaying. Pattern to follow:
   the existing `research_rebuttal_node` "log + mark milestone
   blocked, never raise" path landed in `0aa6315`.

4. **Resume endpoint hygiene.** When a resume hits a node that
   previously raised but the checkpoint is at node-entry, run one
   forced step — i.e. invoke the node once and let its retry+block
   logic produce a successor checkpoint. Today the resume just
   re-streams from the broken checkpoint. Add a small audit-log
   line so we can trace recovery in production.

5. **Kill-switch.** Env flag `MARVIN_LLM_TRANSIENT_RETRIES=0` disables
   the retry layer for tests / debugging. Smoke + tests must still
   pass with retries=0 because the transient never fires there.

**Files (expected).**
- `marvin/llm_factory.py` (typed exception, retry wrapper)
- `marvin/graph/subgraphs/{dora,calculus,adversus,merlin}.py`
  (wrap ainvoke; convert to state-delta on failure)
- `marvin/graph/runner.py` (`adversus_node` + `merlin_node` post-call
  surfaces; same pattern as research_rebuttal_node)
- `marvin_ui/server.py` (resume endpoint forced-step on
  pre-execution checkpoint; typed audit log)
- New `tests/test_llm_transient_recovery.py` covering: (a) HTML body
  triggers retry not crash, (b) repeated failure marks block + still
  advances phase, (c) resume after agent failure does not replay
  the same node twice.

**Verification.**
- `pytest -q` clean
- `make smoke` clean
- Live mission with a stubbed OpenRouter that returns HTML for the
  first request and JSON afterwards — must complete past the agent
  on first call (retry succeeds) without re-running the node on a
  separate `/resume`.
- Live mission with a stubbed OpenRouter that returns HTML for ALL
  requests — must surface "Adversus blocked: upstream LLM transient"
  in the rail and still advance the graph to merlin (best-effort).

**Open question for the user before coding.**
- Default retry count (2 vs 3)?
- On exhausted retries, do we want the run to **block at G3 with a
  visible diagnostic and force a manual rerun**, or **synthesize
  partial results with the verdict template flagged "incomplete due
  to upstream LLM failure"**? Both are defensible — preference
  decides the merlin_node behavior.

---

### Other Wave 3 chantiers
- **C5** — DCF + sensitivity engine. M effort. Depends on C1 (filings)
  + ideally C2 (data room).
- **C9** — Adversus kill-list ranking. S–M. **Out of scope per user
  constraint** ("don't modify Adversus"); reopen needed.
- **C6** — Knowledge graph + contradiction detection. L. Depends on
  C1+C2+C3 claim density.
- **C8** — Cross-mission memory. L. Depends on C1+C2+C3+C4 producing
  KNOWN findings worth remembering.

### Wave 4 — Quand le core est solide
- **C11** — Output customization + chart rendering. M. Independent.
- **C12** — Founder/key-person risk attack workstream. M. Independent.
- **C13** — Slide-deck generator. M. Brand guidelines provided at
  `UI Marvin/ui guidelines/H&AI - Deck-print.html` (also reusable for
  Markdown→PDF memo rendering).

### Side debt
- DealEconomics, DataRoomUpload, TranscriptUpload components are
  standalone files — not yet wired into MissionControl tabs.
- Tavily API returning HTTP 432 for all calls (pre-existing,
  unrelated to any chantier).
- Live end-to-end validation pending for C2, C3, C7 (only their
  unit-test surface has been exercised).

---

## How to keep this file honest

- Update **immediately** when a chantier ships, not in batch.
- Format per chantier: Bucket / Status / Commits / Problem / Shipped /
  Hotfix (if any) / Open follow-up.
- Status is one of: `in-progress`, `shipped`, `validated`,
  `deferred`. Promote `shipped` → `validated` only after a live
  mission has confirmed the behavior end-to-end.
- Drift check: `git log --oneline` for chantier commits should match
  the `Commits` lines here. If they diverge, this file is wrong.
