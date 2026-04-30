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

## Pending — backlog

### Wave 3 — Plus tard
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
