# MARVIN — Technical Flow Specification
*Executable version for coding agent*
*Based on MARVIN_IDEAL_FLOW.md + field corrections*

---

## 0. NON-NEGOTIABLE PRINCIPLES

Five rules. If a single one is violated, the system is broken.

```
1. STATE TRUTH
   What is displayed matches exactly the DB state.
   No mock data, no placeholders, no "coming soon".

2. CHANNEL SEPARATION
   MARVIN chat  = editorial narration (short, dense)
   Live feed    = compact signal (who does what)
   Center       = real workstream content
   Checkpoints  = gate status
   Deliverables = openable artifacts

3. NO FAKE PROGRESS
   No gate without something real to validate.
   No deliverable "ready" if empty or trivial.
   No agent shown "running" without a recent tool call.

4. MARVIN'S VOICE
   Style: senior consultant briefing a partner.
   Short, dense, no hedging, no raw LLM paragraphs.
   When MARVIN speaks, there's something worth saying.

5. HYPOTHESES = LIVING CENTRAL OBJECT
   All work organizes around them.
   Each finding weighs for or against a hypothesis.
   Status visible at all times: SUPPORTED / TESTING / 
   WEAKENED / INVALIDATED.
```

---

## 1. PHASE-BY-PHASE FLOW

Each phase has the same structure:
- **Trigger**: what starts the phase
- **Backend work**: what runs server-side
- **SSE events**: exactly which events are emitted
- **UI updates**: what changes in each panel
- **MARVIN message**: what the chat says (with template)
- **Done when**: condition to advance
- **Then**: next phase

---

### PHASE 0 — Mission opens (empty state)

**Trigger**: User clicks "Open mission" from dashboard, or creates a new mission.

**Backend work**:
- Mission already created in DB by `POST /api/v1/missions`
- Workplan seeded (`_seed_standard_workplan`)
- No graph activity yet

**SSE events**: None (graph not started)

**UI state**:
```
LEFT panel:
  Mission name + client
  Progress bar at 0%
  Checkpoints: all "Later" status
  Agents: all "idle"
  Deliverables: empty list

CENTER panel:
  Brief tab (active by default)
  "No findings yet. Send a brief to start."

RIGHT panel:
  MARVIN message:
  "Mission open. Send me your brief — investment 
  thesis, key questions, any documents you have."
  
  Input: enabled, placeholder "Paste brief or upload documents"
```

**MARVIN message template**:
```
Mission open. Send me your brief — 
investment thesis, key questions, 
any documents you have.
```
(Exactly this. No more, no less.)

**Done when**: User sends a message containing a brief (>50 chars OR contains keywords: cdd, deal, acquisition, target, valuation, fund).

**Then**: PHASE 1.

---

### PHASE 1 — Framing

**Trigger**: User sends brief.

**Backend work**:
1. Server builds initial state with `mission_id` and `phase: "setup"`
2. Graph starts → `phase_router` routes to `papyrus_phase0`
3. Papyrus generates engagement brief (writes file to disk)
4. Phase advances to `framing`
5. `phase_router` calls `_generate_hypotheses_inline` (no agent, direct LLM call)
6. Hypotheses persisted to DB
7. Phase advances to `awaiting_confirmation`

**SSE events emitted (in order)**:
```
{"type": "run_start"}
{"type": "phase_changed", "phase": "setup", 
 "label": "Framing"}
{"type": "agent_active", "agent": "Papyrus"}
{"type": "tool_call", "agent": "Papyrus", 
 "tool": "generate_engagement_brief"}
{"type": "tool_result", "agent": "Papyrus", 
 "text": "Engagement brief written"}
{"type": "deliverable_ready", "label": "Engagement brief", 
 "download_url": "/api/v1/deliverables/download?path=..."}
{"type": "agent_done", "agent": "Papyrus"}
{"type": "phase_changed", "phase": "framing", 
 "label": "Generating hypotheses"}
{"type": "tool_call", "agent": "MARVIN", 
 "tool": "generate_hypotheses"}
{"type": "hypothesis_added", "id": "h-...", "text": "..."} 
  (one per hypothesis, typically 5-6)
{"type": "tool_result", "agent": "MARVIN", 
 "text": "5 hypotheses recorded"}
{"type": "phase_changed", "phase": "awaiting_confirmation"}
{"type": "gate_pending", "gate_id": "...", 
 "gate_type": "hypothesis_confirmation",
 "format": "hypothesis_validation",
 "hypotheses": [...full text of each...]}
```

**UI updates during this phase**:
```
LEFT panel:
  Progress: animates to ~15%
  Checkpoints: "hypothesis confirmation" → "Now"
  Agents: 
    Papyrus → running (briefly), then done
    MARVIN → running (during hypothesis generation)
  Deliverables: 
    "Engagement brief" appears with green dot + download arrow

CENTER panel:
  Brief tab updates with:
    Phase indicator: "Framing"
    "Engagement brief generated" event
    "Hypotheses being generated..."
    Each hypothesis appears as it's added

RIGHT panel:
  Stream MARVIN messages (one paragraph each, never long):
    Message 1 (after brief): 
      "Reading your brief on [target]. 
       Key tension: [extracted from brief]."
    Message 2 (during hypothesis generation): 
      "Generating testable hypotheses around 
       [the IC question]."
    Message 3 (after hypotheses): 
      "5 hypotheses ready. Review below.
       Approve to launch parallel research 
       (market + financial)."
```

**MARVIN message templates**:
```
After brief received:
"Reading your brief on {target}.
Key tension: {extracted_tension}."
(Max 2 sentences. {extracted_tension} = single line 
identifying the central question.)

After hypotheses generated:
"{N} hypotheses ready. Review below.
Approve to launch parallel research (market + financial)."
(Max 2 sentences. {N} is the count.)

NEVER:
- Long LLM paragraphs explaining what hypotheses are
- Restating the brief back to user
- Listing each hypothesis in the chat (they appear in center)
- Hedging language ("I think", "perhaps", "it might be")
```

**Done when**: 
- Engagement brief file exists on disk and is non-empty
- At least 3 hypotheses persisted in DB
- `hypothesis_confirmation` gate fires with `interrupt()`

**Then**: PHASE 2 (waiting for human approval).

---

### PHASE 2 — Hypothesis confirmation gate

**Trigger**: `gate_pending` event with `format: "hypothesis_validation"`.

**Backend work**: Graph is paused at `interrupt()`. No agents running.

**SSE events**: Only the `gate_pending` event from PHASE 1. Nothing else until user acts.

**UI state**:
```
LEFT panel:
  Checkpoints: 
    "hypothesis confirmation" still "Now" (pulsing)
  Agents: all idle except those that already ran
  Progress bar: stops advancing

CENTER panel (Brief tab):
  Show the gate banner at top:
    "Hypothesis review required"
    "Approve to launch market + financial research."
    [Approve] [Reject]
  
  Below: hypothesis list with current status
    H1: [text]                            ACTIVE
    H2: [text]                            ACTIVE
    ...

RIGHT panel:
  Last MARVIN message stays visible.
  Input enabled — user can ask questions about hypotheses
  but agents don't run. MARVIN responds in chat only.
```

**MARVIN behavior during gate**:
The orchestrator can answer questions about the hypotheses but cannot advance the mission. If user asks "why H3?", MARVIN explains in chat (max 3 sentences). If user asks to modify, MARVIN says "Reject the gate and I'll revise."

**Done when**:
- User clicks Approve → `POST /validate` with `verdict: "APPROVED"`
- OR user clicks Reject → `POST /validate` with `verdict: "REJECTED"`

**Then**:
- Approved → PHASE 3 (research kickoff)
- Rejected → back to PHASE 1 with revision instruction

---

### PHASE 3 — Parallel research

**Trigger**: User approves hypothesis_confirmation gate.

**Backend work**:
1. Graph resumes from `interrupt()` with `gate_passed: True`
2. `gate_node` returns `phase: "confirmed"`
3. `phase_router` sees "confirmed" → emits `Send(dora) + Send(calculus)` in parallel
4. Both agents run concurrently with `last_value` reducer on shared state
5. Each agent calls tools, persists findings, marks milestones delivered
6. `research_join` waits for W1.1 AND W2.1 both delivered
7. When both done → generate workstream reports → phase becomes `research_done`

**SSE events emitted**:
```
{"type": "phase_changed", "phase": "confirmed", 
 "label": "Research kickoff"}
{"type": "agent_active", "agent": "Dora"}
{"type": "agent_active", "agent": "Calculus"}

(then interleaved as they run, identified by agent name:)
{"type": "tool_call", "agent": "Dora", 
 "tool": "tavily_search"}
{"type": "tool_call", "agent": "Calculus", 
 "tool": "search_sec_filings"}
{"type": "finding_added", "agent": "Dora", 
 "claim": "TAM ~$X based on...", "confidence": "REASONED",
 "hypothesis_id": "h-1"}
{"type": "finding_added", "agent": "Calculus", 
 "claim": "Revenue concentration: top 10 = X%",
 "confidence": "KNOWN", "hypothesis_id": "h-3"}
{"type": "milestone_done", "milestone_id": "W1.1", 
 "label": "TAM/SAM/SOM sizing"}
{"type": "milestone_done", "milestone_id": "W2.1", 
 "label": "Unit economics"}
{"type": "deliverable_ready", "label": "W1 report"}
{"type": "deliverable_ready", "label": "W2 report"}
{"type": "agent_done", "agent": "Dora"}
{"type": "agent_done", "agent": "Calculus"}
{"type": "phase_changed", "phase": "research_done"}
{"type": "gate_pending", "gate_id": "...", 
 "gate_type": "manager_review",
 "format": "review_claims", 
 "top_findings": [...3 most critical...],
 "arbiter_flags": [...]}
```

**UI updates**:
```
LEFT panel:
  Progress: animates from 15% to ~50%
  Checkpoints: 
    "hypothesis confirmation" → Completed (green check)
    "manager review" → Now
  Agents:
    Dora → running (during research)
    Calculus → running (during research)
    (both go to "done" when finished)
  Deliverables:
    "W1 — Market analysis" appears
    "W2 — Financial analysis" appears

CENTER panel:
  Tab "Market & Competitive" shows W1 findings 
  in real-time (with REASONED/KNOWN/LOW_CONFIDENCE badges)
  Tab "Financial" shows W2 findings 
  Tab badge counter updates: "Market (3)" "Financial (5)"
  
  Each finding card shows:
    [confidence badge] Finding text
    Source link (if KNOWN)
    Linked hypothesis: H{N}

RIGHT panel:
  MARVIN messages (max 4 messages total during this phase):
  
  Start of research:
    "Research started. Dora: market sizing + 
     competitive landscape. Calculus: financials 
     from SEC filings."
  
  Mid-research (only on first major finding):
    "Dora: TAM ~${X} bottom-up. Supports H1.
     Calculus pulling Q4 financials."
  
  End of research:
    "W1 + W2 complete. {N} findings logged. 
     {M} arbiter flags. Manager review ready."
```

**MARVIN message rules during research**:
- 1 message at start (announcement)
- 1 message per major finding (only KNOWN with high impact)
- 1 message at end (summary)
- Never narrate every tool call
- Never repeat what's already in the live feed

**Done when**:
- W1.1 milestone has `status: "delivered"` in DB
- W2.1 milestone has `status: "delivered"` in DB  
- Workstream reports exist on disk (non-empty)
- `manager_review` gate fires

**Then**: PHASE 4 (manager review).

---

### PHASE 4 — Manager review gate (G1)

**Trigger**: `gate_pending` with `format: "review_claims"`.

**UI state**:
```
LEFT panel:
  Checkpoints: "manager review" still "Now"
  Progress: paused at ~50%

CENTER panel:
  Show gate banner with 3 selected claims:
    "Manager review — 3 critical claims to validate"
    
    Claim 1: [text]
      Source: [link]  Confidence: KNOWN
      [Validate] [Flag for revision]
    Claim 2: [text]
      ...
    Claim 3: [text]
      ...
    
    Arbiter flags (if any):
      ⚠ {flag description}
    
    [Approve all] [Reject — revise W1/W2]

RIGHT panel:
  MARVIN message:
    "G1: 3 claims for review. {arbiter_flags_count} 
     arbiter flags. Approve to launch red-team."
```

**Done when**: User approves or rejects.

**Then**:
- Approved → PHASE 5
- Rejected → return to PHASE 3 with revision notes

---

### PHASE 5 — Red-team (Adversus)

**Trigger**: G1 approved.

**Backend work**:
- `phase: gate_g1_passed` → `phase_router` sends to `adversus`
- Adversus reads all findings + hypotheses
- Attacks each hypothesis from 3 angles: empirical, logical, contextual
- Runs PESTEL, generates stress scenarios
- Identifies weakest link
- Persists adversarial findings (often LOW_CONFIDENCE or contradicting)
- Phase advances to `redteam_done`

**SSE events**:
```
{"type": "phase_changed", "phase": "gate_g1_passed", 
 "label": "Red-team"}
{"type": "agent_active", "agent": "Adversus"}
{"type": "tool_call", "agent": "Adversus", 
 "tool": "attack_hypothesis"}
{"type": "finding_added", "agent": "Adversus", 
 "claim": "H2 weakness: ...", 
 "confidence": "REASONED",
 "hypothesis_id": "h-2"}
{"type": "tool_call", "agent": "Adversus", 
 "tool": "generate_stress_scenarios"}
{"type": "tool_call", "agent": "Adversus", 
 "tool": "identify_weakest_link"}
{"type": "milestone_done", "milestone_id": "W4.1"}
{"type": "agent_done", "agent": "Adversus"}
{"type": "phase_changed", "phase": "redteam_done"}
```

**UI updates**:
```
LEFT panel:
  Progress: ~70%
  Checkpoints: "red-team" → "Now"
  Agents: Adversus running (others done)
  Deliverables: "W4 — Risk analysis" appears

CENTER panel:
  Tab "Risk" populates with red-team findings
  Hypotheses panel updates:
    H1: SUPPORTED → SUPPORTED (no change)
    H2: SUPPORTED → WEAKENED (red-team found counter-evidence)
    ...

RIGHT panel:
  MARVIN message:
    "Adversus running. Stress-testing each hypothesis 
     and the overall thesis."
  
  At end:
    "Red-team done. {N} stress findings.
     Weakest link: {hypothesis_id}.
     Synthesis next."
```

**Done when**: Adversus marks W4.1 delivered.

**Then**: PHASE 6 (synthesis).

---

### PHASE 6 — Synthesis (Merlin)

**Trigger**: `phase: redteam_done`.

**Backend work**:
- Merlin reads all findings + hypotheses + adversus results
- Checks MECE
- Updates action titles
- Issues verdict via `set_merlin_verdict()`
- Possible verdicts:
  - `SHIP` → phase becomes `synthesis_done`
  - `MINOR_FIXES` → loop back to redteam_done (max 3 retries via counter)
  - `BACK_TO_DRAWING_BOARD` → loop back (max 3 retries)
- After 3 retries forced forward to `synthesis_done`

**SSE events**:
```
{"type": "phase_changed", "phase": "redteam_done", 
 "label": "Synthesis"}
{"type": "agent_active", "agent": "Merlin"}
{"type": "tool_call", "agent": "Merlin", 
 "tool": "check_mece"}
{"type": "tool_call", "agent": "Merlin", 
 "tool": "set_merlin_verdict"}
{"type": "verdict", "verdict": "SHIP", 
 "notes": "..."}
{"type": "agent_done", "agent": "Merlin"}
{"type": "phase_changed", "phase": "synthesis_done"}
{"type": "gate_pending", "gate_id": "...",
 "gate_type": "final_review",
 "format": "defend_storyline"}
```

**UI updates**:
```
LEFT panel:
  Progress: ~85%
  Checkpoints: "final review" → "Now"
  Agents: Merlin running, then done

CENTER panel:
  Tab "Memo" populates with synthesis preview
  Verdict badge appears: SHIP (green) / MINOR_FIXES (amber)

RIGHT panel:
  MARVIN message:
    "Merlin verdict: {verdict}.
     {one-line rationale}.
     {Final review ready | Looping back for {reason}}."
```

**Done when**: Verdict is SHIP OR retry count reaches 3.

**Then**: PHASE 7 (final review).

---

### PHASE 7 — Final review gate (G3)

**Trigger**: `gate_pending` with `format: "defend_storyline"`.

**UI state**:
```
CENTER panel:
  Memo tab shows full synthesis:
    Storyline summary
    Each hypothesis with final status
    Weakest link identified
    Open risks
    Verdict: {SHIP/MINOR_FIXES}
    [Approve & generate deliverables] [Reject]

RIGHT panel:
  MARVIN message:
    "Final review. Verdict: {verdict}.
     Approve to package and deliver."
```

**Done when**: User approves.

**Then**: PHASE 8.

---

### PHASE 8 — Final delivery

**Trigger**: G3 approved.

**Backend work** (Python only, no LLM):
- `papyrus_delivery_node` calls 3 functions sequentially:
  - `_generate_report_pdf_impl(mission_id)` 
  - `_generate_exec_summary_impl(mission_id)`
  - `_generate_data_book_impl(mission_id)`
- All files written to `PROJECT_ROOT/output/{mission_id}/`
- All paths absolute
- All files non-empty (validate before saving)
- Phase advances to `done`

**SSE events**:
```
{"type": "phase_changed", "phase": "gate_g3_passed", 
 "label": "Final delivery"}
{"type": "agent_active", "agent": "Papyrus"}
{"type": "tool_result", "agent": "Papyrus", 
 "text": "CDD report generated"}
{"type": "deliverable_ready", "label": "CDD report v1", 
 "download_url": "..."}
{"type": "tool_result", "agent": "Papyrus", 
 "text": "Exec summary generated"}
{"type": "deliverable_ready", "label": "Exec summary"}
{"type": "tool_result", "agent": "Papyrus", 
 "text": "Data book generated"}
{"type": "deliverable_ready", "label": "Data book"}
{"type": "agent_done", "agent": "Papyrus"}
{"type": "phase_changed", "phase": "done"}
{"type": "run_end"}
```

**UI updates**:
```
LEFT panel:
  Progress: 100%
  Checkpoints: all completed
  Agents: all done
  Deliverables: 3 new files, all openable

CENTER panel:
  Memo tab shows final synthesis
  All tabs marked ✓ (done style)

RIGHT panel:
  MARVIN final message:
    "Mission complete. 3 deliverables ready.
     Open the CDD report for the full thesis."
```

**Done when**: All 3 deliverables exist on disk, non-empty, registered in DB.

---

## 2. UI COMPONENT RULES

### MARVIN chat panel (right)
```
DO:
  Short messages (max 3 sentences each)
  One message per phase transition
  Use the templates above exactly
  Stream text smoothly (don't dump all at once)

DO NOT:
  Show raw LLM output (paragraphs of explanation)
  Restate what's already visible elsewhere
  Use hedging language ("I think", "perhaps")
  Show JSON, tool calls, internal IDs
  Repeat hypotheses (they appear in center)
```

### Live feed (center, when no tab content yet)
```
Format: [Agent] · [tool or finding label] · [timestamp]

DO:
  Show every tool call (briefly)
  Show every finding with confidence badge
  Show milestone completions
  Show phase transitions

DO NOT:
  Show raw payload
  Show "step complete" or other internal messages
  Show repeated calls (deduplicate)
```

### Workstream tabs (center)
```
Each tab shows ONLY findings from its workstream:
  Brief tab     → engagement brief content + initial framing
  Market tab    → W1 findings (Dora)
  Financial tab → W2 findings (Calculus)
  Risk tab      → W4 findings (Adversus)
  Memo tab      → final synthesis (Merlin output)

Tab badge shows finding count: "Market (3)"
Active tab is bold, completed tabs have ✓ prefix.
```

### Checkpoints (left)
```
States and visual:
  Completed → grey, with green checkmark
  Now       → black, pulsing dot
  Next      → grey, hollow dot
  Later     → 50% opacity, hollow dot

Order:
  hypothesis confirmation → manager review (G1) → 
  red-team review → final review (G3)
  
  Never show a checkpoint as "Now" if there's no 
  matching pending gate in DB.
```

### Agents panel (left)
```
States:
  idle    → 50% opacity, no indicator
  running → bold, animated pulse dot (green)
  done    → normal, "DONE" tag
  waiting → bold, amber dot (between phases)

NEVER show all 5 agents at once if some are idle.
Always reflect actual state from `agent_active` / 
`agent_done` events.
```

### Deliverables panel (left)
```
Each deliverable: label + download arrow
States:
  Ready   → black text, green ↓ arrow, clickable
  Pending → 40% opacity, em-dash "—"

NEVER show "Engagement brief" with download arrow 
if file doesn't exist on disk.
```

---

## 3. WHAT MUST CHANGE IN CURRENT IMPLEMENTATION

Based on the screenshot of the broken state:

### Bug A — Orchestrator is looping
```
Symptom: 
  "MARVIN → get workplan for mission" 
  "MARVIN → get hypotheses"
  "step complete"
  "MARVIN → get workplan for mission"
  (repeat forever)

Root cause:
  phase_router routes to "orchestrator" as default,
  but orchestrator runs every time and returns to 
  phase_router, which routes again to orchestrator.

Fix:
  After PHASE 1 hypotheses are created, phase MUST 
  advance to "awaiting_confirmation" automatically.
  Orchestrator should NEVER run during normal flow —
  only when user asks a free-form question between phases.
  
  The orchestrator agent must NOT be reachable during
  setup → framing → awaiting_confirmation. Only after 
  a gate is approved or after all phases complete.
```

### Bug B — Engagement brief not downloadable
```
Symptom: "Open" arrow shown but click does nothing.

Root cause: 
  file_path in DB is wrong, OR
  download endpoint security check rejects path, OR
  file doesn't actually exist on disk.

Fix:
  Verify in this order:
  1. sqlite3 ~/.marvin/marvin.db 
     "SELECT file_path FROM deliverables 
      WHERE mission_id='m-cursor-...'"
  2. ls -la {file_path}
  3. curl http://localhost:8095/api/v1/deliverables/download?path={file_path}
  
  Whichever step fails first → fix that.
```

### Bug C — All agents showing IDLE
```
Symptom: Dora, Calculus, Merlin, Adversus all "idle"
even though work supposedly happened.

Root cause: 
  Backend never emits agent_active / agent_done events
  OR
  Frontend doesn't handle these events
  OR
  Agents never actually ran (orchestrator loop ate the budget)

Fix:
  1. Verify server.py emits agent_active when an agent 
     subgraph starts (on_chain_start with name in 
     ["dora", "calculus", "adversus", "merlin", "papyrus_phase0"])
  2. Verify MissionControl listens for "agent_active" 
     and "agent_done" events
  3. Verify orchestrator loop is fixed (Bug A) — 
     otherwise no agent ever runs
```

### Bug D — Chat shows huge LLM paragraphs
```
Symptom: MARVIN chat panel filled with 
  "**Contribution margin by plan tier** - Their 
   **model/customization strategy** reduces..."
  (clearly raw LLM output)

Root cause:
  Orchestrator agent's system prompt allows long 
  consultative responses.
  AND/OR
  Server emits all "text" events to chat without 
  filtering.

Fix:
  1. Update orchestrator.md prompt:
     "You speak briefly. Maximum 3 sentences per message.
      Use templates from MARVIN_FLOW.md.
      Never produce paragraphs of analysis — 
      that goes in workstream findings."
  2. Server should NOT emit "text" events from 
     orchestrator during agent work — only at phase 
     transitions and on direct user query.
```

### Bug E — Mission shows in_progress with no activity
```
Symptom: "IN PROGRESS" indicator + "Phase · Hypothesis 
review pending" but no new events for minutes.

Root cause:
  Graph hit interrupt() but UI doesn't reflect 
  "waiting for human" state.
  OR
  Graph crashed silently and SSE keeps the connection 
  open without sending events.

Fix:
  1. When gate_pending fires, set UI state to 
     "Awaiting your decision" (not "In progress")
  2. Add health check: if no SSE event for 30s during 
     active phase → emit {"type": "stalled"} so UI 
     can show recovery option
  3. Log every phase_router invocation with mission_id 
     to debug stalls
```

---

## 4. ACCEPTANCE CRITERIA FOR FIRST MISSION

The mission Vinted (or any test brief) is "successful" when:

```
PHASE 0 — Mission created, MARVIN says "Send brief"
  ✓ MARVIN message uses exact template
  ✓ All agents idle, all checkpoints "Later"

PHASE 1 — Brief processed, hypotheses generated
  ✓ Engagement brief file exists, non-empty, downloadable
  ✓ At least 4 hypotheses persisted in DB
  ✓ Hypotheses visible in center panel
  ✓ Hypothesis confirmation gate fires
  ✓ MARVIN said exactly 2 messages (start, end)

PHASE 2 — User approves
  ✓ Gate modal/banner shows hypotheses clearly
  ✓ Approve button works, Reject button works
  ✓ Cannot approve without seeing hypotheses

PHASE 3 — Research runs
  ✓ Dora and Calculus both show "running" 
  ✓ Both produce real findings (not placeholders)
  ✓ Findings appear in correct tabs with correct badges
  ✓ Workstream reports generated and openable
  ✓ G1 fires with real claims

PHASE 4-7 — Continue same pattern
  ✓ Each agent runs only when its phase activates
  ✓ Orchestrator does NOT loop
  ✓ Each gate has real material to validate

PHASE 8 — Delivery
  ✓ 3 final files exist on disk, non-empty
  ✓ All openable from UI
  ✓ Mission status = "completed"
  ✓ MARVIN final message uses template
```

If any of these fail, the system is not done.

---

## 5. WHAT TO BUILD VS WHAT TO FIX

The architecture (LangGraph + phase_router + agents) is correct.
The data layer (store + tools) works.
The agents can be activated.

What's broken is the **integration**:
- Orchestrator loops instead of letting phase_router work
- SSE events don't match UI handlers
- MARVIN voice not constrained
- Deliverable paths broken
- UI shows phantom states

**Do not rewrite the system.** Fix these 5 bugs in order:
1. Bug A (orchestrator loop) — without this, nothing else matters
2. Bug B (download) — quick fix, validates data layer
3. Bug C (agent states) — once A is fixed, this should mostly work
4. Bug D (chat noise) — prompt + server filter
5. Bug E (stall detection) — defensive only, last priority

After all 5 fixed, run a full Vinted mission and check 
all 8 acceptance criteria.
