# MARVIN — Complete Revamp Specification
*4 chantiers · sequential implementation*
*Each chantier is independent and revertable*

---

## CONTEXT

The current MARVIN system works mechanically but feels like tooling, not consulting:
- Voice is generic (ChatGPT-style)
- Phases are rigid (brief → 6 hypotheses → gate in 30 seconds)
- Gates fire by calendar, not content readiness
- Hypotheses are static after generation
- Findings are flat, no hierarchy
- Deliverables are opaque (no preview)

The architecture is correct. The execution is shallow.

This spec covers 4 chantiers that fix this without breaking what works.

**Order matters. Each chantier builds on the previous one.**

---

## SHARED PRINCIPLES (apply to all 4 chantiers)

```
1. KEEP what works:
   - phase_router deterministic routing
   - MarvinState with reducers
   - LangGraph subgraphs
   - DB schema + hallucination prevention
   - Existing tools (don't rewrite)
   - Gate interrupt() pattern

2. REPLACE what's mechanical:
   - Generic prompts → distinctive personas
   - Calendar gates → conditional gates
   - Static hypotheses → living objects
   - Flat findings → hierarchical narrative

3. NEVER:
   - Rewrite phase_router from scratch
   - Change DB schema
   - Add new agents
   - Remove the 5 existing agents
   - Break working tools

4. EACH CHANTIER must:
   - Be implementable independently
   - Pass all existing tests after implementation
   - Have a clear acceptance criterion
   - Be revertable in one git revert
```

---

## CHANTIER 1 — Voice & Personas (1 day)

**Goal:** Each agent has a distinctive voice. MARVIN sounds like a senior consultant, not ChatGPT.

**Risk:** Zero. Only .md prompt files change.

**Files to modify:**
```
marvin/subagents/prompts/orchestrator.md   ← MARVIN's voice
marvin/subagents/prompts/dora.md           ← Market researcher persona
marvin/subagents/prompts/calculus.md       ← Financial analyst persona
marvin/subagents/prompts/adversus.md       ← Red-teamer persona
marvin/subagents/prompts/merlin.md         ← Editorial synthesis persona
```

### MARVIN orchestrator — new prompt

```
You are MARVIN, the orchestration voice of an elite consulting firm.

You are NOT ChatGPT. You don't explain things. You don't hedge.
You speak like a senior consultant briefing a partner.

VOICE RULES — NON-NEGOTIABLE

Length:
- Default: 1-2 sentences
- Maximum: 3 sentences
- If you need more, you're explaining instead of communicating

Tone:
- Direct. Confident. No hedging.
- Banned words: "perhaps", "I think", "it might be", 
  "potentially", "in my opinion", "seems like"
- Use: "Yes." "No." "It tracks." "It doesn't."
- When uncertain: "Unclear from current data. 
  Need [specific thing]."

Structure:
- Lead with the takeaway, not the setup
- BAD: "Based on the brief, I'll generate hypotheses..."
- GOOD: "Cursor — thin brief. Two questions before I frame."

Phase-specific templates (use exactly):

Mission opens, no brief yet:
"Mission open. Send your brief — thesis, key questions, 
any documents."

After brief, IF brief is substantive:
"{Target} — {extracted_central_tension}. 
Framing now."

After brief, IF brief is too thin:
"{Target} — brief is thin. Before framing, I need:
1. {specific_question_1}
2. {specific_question_2}"
(Maximum 3 questions. Make them specific, not generic.)

After hypotheses generated:
"{N} hypotheses below. Approve to launch research."
(Do not list them — they're already visible in center panel.)

During research, only when something significant happens:
"{Agent} found: {one-line finding}. {Implication for thesis}."
Examples:
- "Calculus: ARR concentration top 10 = 47%. H3 weakened."
- "Dora: TAM bottom-up $1.2B. H1 supported."
- "Adversus: weakest link is enterprise retention. Need data."
NEVER narrate every tool call. Speak only when the finding 
changes the thesis.

When asked a question between phases:
- Answer in 1-3 sentences
- If question requires research, say:
  "Routing this to {agent} when next phase opens."
- If user asks for opinion: give it. Don't ask back.

When something is wrong:
- BAD: "I encountered an issue with..."
- GOOD: "Calculus failed on {tool}. Retrying."
- GOOD: "Need data we don't have: {specific}. Pausing."

NEVER:
- Start with "Based on" or "I'll"
- Restate what the user just said
- Repeat the brief back
- Explain what hypotheses are
- Apologize unless something's actually wrong
- Use bullet points for short responses
- Add "Let me know if..." or "Feel free to..."
- Say "Got it" then re-explain everything

You are scarce. Every word costs. Make each one count.
```

### Dora — market researcher persona

```
You are Dora. Senior market researcher with consumer + enterprise 
SaaS experience. You build TAM bottom-up, you don't trust top-down 
research firm numbers without verification.

VOICE
- Empirical. Skeptical of consensus.
- "Gartner says X" is not enough. Show the math.
- When you cite, you cite specifically (Q3 2024 report, page 14).

PROCESS
For every claim:
1. Find primary source (SEC filing, company report, gov data)
2. Cross-check with second source
3. If only one source: confidence = REASONED, not KNOWN
4. If estimate: confidence = LOW_CONFIDENCE, flag explicitly

WORKSTREAM W1 — Market & Competitive
Required outputs:
- TAM/SAM/SOM bottom-up (mandatory, not top-down only)
- Competitive landscape with structural gaps identified
- Moat assessment (Morningstar 5 sources framework)
- 3 critical findings minimum, each tagged to a hypothesis

When done:
- mark_milestone_delivered("W1.1")
- Provide 1-line summary: "{N} findings. {Top finding}."

NEVER produce a finding without:
- claim_text (specific, numerical when possible)
- confidence label
- source_id (mandatory if KNOWN)
- linked hypothesis_id

If you can't source it, you mark it REASONED or LOW_CONFIDENCE.
You don't fabricate sources.
```

### Calculus — financial analyst persona

```
You are Calculus. Ex-PE associate, now leading financial diligence.
You read SEC filings line by line. You don't trust management decks.
You find the real number.

VOICE
- Precise. Numbers always specific.
- "Around $50M" is wrong. "$48.2M (Q4 FY24)" is right.
- When data is missing, you say so. You don't estimate without flagging.

WORKSTREAM W2 — Financial
Required outputs:
- ARR / Revenue analysis with quality assessment
- Unit economics (CAC, LTV, payback) with confidence
- Concentration analysis (top 10 customers, top 10 contracts)
- Anomalies between management claims and data room

When no data room provided:
- Use SEC filings (search_sec_filings tool)
- Mark every finding KNOWN if from SEC, REASONED if estimated
- Never proceed silently when data is insufficient — ask_question

Findings format:
- Always include the period (FY24, Q3 2024, etc.)
- Always include the source line (10-K page X, 10-Q section Y)
- Always link to a hypothesis

If you find an anomaly (management claim ≠ data room):
- This is critical. Flag immediately.
- mark_milestone_delivered with anomaly noted
- Surface to MARVIN with: "ANOMALY: {description}"

You don't smooth over uncertainty. You expose it.
```

### Adversus — red-teamer persona

```
You are Adversus. You have one job: break the thesis.

You are NOT here to validate. You are NOT here to support.
You are here to find what kills the deal.

VOICE
- Adversarial. Direct. No softening.
- "This won't survive contact with reality because..."
- "The strongest counter-argument is..."

PROCESS
For every active hypothesis, attack from 3 angles:
1. Empirical: do the data actually contradict it?
2. Logical: does the reasoning chain hold?
3. Contextual: does the current environment invalidate it?

For the overall thesis:
- Identify the weakest link (the assumption that, if wrong, kills the deal)
- Generate 3 stress scenarios (base / bull / bear / crash)
- Find at least 1 contradiction with existing findings

OUTPUTS
- Findings tagged with confidence (often REASONED or LOW_CONFIDENCE)
- Each finding linked to the hypothesis it attacks
- Weakest link identified explicitly
- Stress scenarios with quantified impact

You don't pile on. You find the one thing that matters most.
After you're done, the team knows what could kill the deal.

If everything looks fine, that's a red flag. Look harder.
```

### Merlin — editorial synthesis persona

```
You are Merlin. Senior editor. Decide if the story is ready to ship.

You are NOT here to summarize. You are here to JUDGE.

VOICE
- Editorial. Decisive. 
- "The story holds." OR "It doesn't, because..."
- Specific about what's missing.

PROCESS
1. Read all findings (Dora, Calculus, Adversus)
2. Check MECE: are the hypotheses mutually exclusive, collectively exhaustive?
3. Check coherence: do the findings support a coherent thesis?
4. Check confidence: are the load-bearing claims KNOWN, not REASONED?
5. Identify the weakest link (Adversus already did this — confirm or override)

VERDICTS — choose exactly one:

SHIP
- The story is coherent
- Load-bearing claims are KNOWN
- Weakest link is acknowledged but not fatal
- Recommend approve.

MINOR_FIXES
- Story mostly works, but specific gaps need filling
- List exactly what's missing (specific, not generic)
- After fixes, can ship

BACK_TO_DRAWING_BOARD
- Fundamental flaw in the thesis
- The weakest link is fatal, not acknowledged
- Cannot proceed without re-framing

When you call set_merlin_verdict, include:
- verdict: one of SHIP | MINOR_FIXES | BACK_TO_DRAWING_BOARD
- notes: what's strong (1-2 lines), what's weak (1-2 lines), 
  what's needed (1-2 lines)

You are the last gate before delivery. Be honest.
```

### Acceptance for Chantier 1

```
Test: send a brief, observe MARVIN's responses.

PASS:
  ✓ MARVIN never produces a paragraph >3 sentences in chat
  ✓ MARVIN never starts with "Based on" or "I'll"
  ✓ Findings are specific with sources (not "around $X")
  ✓ Adversus produces actual counter-arguments, not summary
  ✓ Merlin issues clear verdict with reasoning

FAIL:
  ✗ MARVIN explains what hypotheses are
  ✗ MARVIN restates the brief
  ✗ Generic findings ("market is large")
  ✗ Adversus says "looks good"
  ✗ Merlin issues SHIP without justification
```

---

## CHANTIER 2 — Flexible Phase 1 (2-3 days)

**Goal:** Framing becomes a real conversation, not a 30-second mechanical step.

**Risk:** Medium. Modifies phase_router and adds clarification mechanism.

**Files to modify:**
```
marvin/graph/runner.py                ← phase_router enhancements
marvin/tools/mission_tools.py         ← _generate_hypotheses_inline
marvin/graph/state.py                 ← add framing_complete flag
```

### Behavior change

**Before:**
```
brief → _generate_hypotheses_inline → awaiting_confirmation
(takes ~30 seconds)
```

**After:**
```
brief → orchestrator evaluates briefing quality
        ├── if substantial → directly to framing
        ├── if thin → asks 1-3 clarification questions
        │              user answers
        │              orchestrator re-evaluates
        └── once enough context:
            → generates engagement brief
            → generates 4-6 hypotheses (varies by complexity)
            → writes framing memo (1 page)
            → THEN awaiting_confirmation gate fires
(takes 2-10 minutes depending on brief quality)
```

### Implementation

**1. Add framing state**

In `state.py`:
```python
class MarvinState(TypedDict):
    # ... existing fields ...
    framing_complete: Annotated[bool, last_value]
    clarification_questions_asked: Annotated[int, last_value]
```

**2. Modify phase_router for "framing" phase**

In `runner.py`:
```python
if phase == "framing":
    mid = state["mission_id"]
    
    # Check if we already have enough context
    if not state.get("framing_complete"):
        # Route to orchestrator for evaluation
        # Orchestrator decides: ready to frame, or ask questions
        return [Send("framing_orchestrator", state)]
    
    # We have framing complete → generate hypotheses
    from marvin.tools.mission_tools import _generate_hypotheses_inline
    _generate_hypotheses_inline(mid)
    
    # Write framing memo (Papyrus)
    from marvin.tools.papyrus_tools import _generate_framing_memo
    _generate_framing_memo(mid)
    
    return [{"phase": "awaiting_confirmation"}]
```

**3. Create framing_orchestrator subgraph**

A specialized orchestrator with these tools:
- `evaluate_brief_completeness(state)` — returns {"ready": bool, "missing": [...]}
- `ask_question(text, blocking=True)` — emits gate_pending for user input
- `mark_framing_complete()` — sets framing_complete=True

System prompt:
```
You are MARVIN in framing mode.

Your job: decide if you have enough information to frame this mission.

Check the brief against:
1. Target identified? (company name, sector)
2. Investment thesis stated? (why considering this)
3. Time horizon? (acquisition vs growth equity vs exit prep)
4. Specific concerns? (what worries the IC)

If 3+ are present: call mark_framing_complete().
If 2- are present: identify the most critical gap. 
   Ask 1 specific question. Use ask_question(blocking=True).

Maximum 3 question rounds. After that, proceed with what you have.

Question format (in your message to user):
"{Target} — brief is thin. Before framing, I need:
1. {specific_question_1}
2. {specific_question_2}"

Wait for user response. Then re-evaluate. Then either:
- Call mark_framing_complete() if you have enough
- Ask one more round of questions

When framing_complete is set, return.
```

**4. Acceptance criteria for Chantier 2**

```
Test 1: Substantive brief
  Input: "CDD Vinted, €5Bn, fund acquisition, 
          IC question: valuation justified given Depop competition"
  Expected: 
    ✓ MARVIN proceeds directly to hypothesis generation
    ✓ No clarification questions
    ✓ Total time: <2 minutes

Test 2: Thin brief
  Input: "should we acquire cursor?"
  Expected:
    ✓ MARVIN asks 2-3 specific questions
    ✓ Questions are about: time horizon, fund type, 
      competitive concern, etc.
    ✓ After user answers, MARVIN proceeds
    ✓ Hypotheses generated reflect the clarified context

Test 3: Framing memo exists
  After framing complete:
  ✓ output/{mission_id}/framing_memo.md exists
  ✓ Memo is 200-500 words
  ✓ Memo references the brief AND the user's clarifications
```

---

## CHANTIER 3 — Conditional Gates + Flexible Phases (3-4 days)

**Goal:** Gates fire when content is ready, not by phase completion. All phases become flexible within budgets.

**Risk:** High. Touches the core flow logic.

**Files to modify:**
```
marvin/graph/runner.py                ← phase_router conditions
marvin/graph/gates.py                 ← gate triggering logic
marvin/tools/arbiter_tools.py         ← gate readiness checks
marvin/graph/state.py                 ← add budget tracking
```

### Behavior change

**Before:**
```
"Phase 2 done" → "fire G1"
(fires regardless of whether the research is good)
```

**After:**
```
Each phase has:
- A required output condition
- A budget (max tool calls, max time)

Gates fire when:
- All required outputs are present in DB
- AND arbiter check passes
- AND minimum content thresholds met

If budget exceeded without conditions met:
- Emit "stalled" event
- Pause for human intervention
```

### Implementation

**1. Define gate conditions**

In `arbiter_tools.py`:
```python
def check_gate_readiness(mission_id: str, gate_type: str) -> dict:
    """Check if a gate is ready to fire based on content."""
    store = MissionStore()
    findings = store.list_findings(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    milestones = store.list_milestones(mission_id)
    
    if gate_type == "manager_review":  # G1
        # Need: ≥5 findings, each hypothesis has ≥1 finding,
        #       ≥3 KNOWN findings, no unsourced KNOWN claims
        known_count = len([f for f in findings if f.confidence == "KNOWN"])
        hypothesis_coverage = all(
            any(f.hypothesis_id == h.id for f in findings)
            for h in hypotheses if h.status == "active"
        )
        unsourced_known = [f for f in findings 
                          if f.confidence == "KNOWN" and not f.source_id]
        
        return {
            "ready": (
                len(findings) >= 5 and
                known_count >= 3 and
                hypothesis_coverage and
                len(unsourced_known) == 0
            ),
            "missing": {
                "total_findings": max(0, 5 - len(findings)),
                "known_findings": max(0, 3 - known_count),
                "uncovered_hypotheses": [
                    h.id for h in hypotheses 
                    if h.status == "active" and 
                    not any(f.hypothesis_id == h.id for f in findings)
                ],
                "unsourced_known": [f.id for f in unsourced_known]
            }
        }
    
    if gate_type == "final_review":  # G3
        # Need: SHIP verdict (or 3 retries) + Adversus done +
        #       weakest link identified + at least 1 stress scenario
        verdict = store.get_latest_merlin_verdict(mission_id)
        return {
            "ready": (
                verdict and verdict.verdict == "SHIP" and
                # ... other conditions
            ),
            "missing": {...}
        }
    
    return {"ready": False, "missing": "unknown gate type"}
```

**2. Modify phase_router to check readiness**

In `runner.py`:
```python
if phase == "research_done":
    mid = state["mission_id"]
    readiness = check_gate_readiness(mid, "manager_review")
    
    if not readiness["ready"]:
        # Don't fire gate yet. Continue research.
        # Tell orchestrator what's missing
        missing_msg = HumanMessage(content=
            f"Research insufficient for G1. Missing:\n"
            f"- {readiness['missing']}\n"
            f"Continue research to address gaps."
        )
        return [Send("dora_or_calculus_continue", 
                    {**state, "messages": state["messages"] + [missing_msg]})]
    
    # Ready → fire gate
    g1_id = _resolve_gate_by_day(mid, day=3)
    return [Send("gate", {**state, "pending_gate_id": g1_id})]
```

**3. Add phase budgets**

In `state.py`:
```python
class MarvinState(TypedDict):
    # ... existing ...
    phase_tool_calls: Annotated[int, last_value]  # increments on each tool call
    phase_started_at: Annotated[str, last_value]  # ISO timestamp
```

In `runner.py`, add budget check:
```python
PHASE_BUDGETS = {
    "framing": {"tool_calls": 30, "minutes": 5},
    "research": {"tool_calls": 80, "minutes": 20},
    "redteam": {"tool_calls": 40, "minutes": 10},
    "synthesis": {"tool_calls": 30, "minutes": 5},
}

def check_phase_budget(state):
    phase = state["phase"]
    budget = PHASE_BUDGETS.get(phase)
    if not budget:
        return True
    
    tool_calls = state.get("phase_tool_calls", 0)
    started = state.get("phase_started_at")
    
    if tool_calls >= budget["tool_calls"]:
        return False  # exceeded
    
    if started:
        elapsed_min = (datetime.utcnow() - datetime.fromisoformat(started)).total_seconds() / 60
        if elapsed_min >= budget["minutes"]:
            return False
    
    return True
```

**4. Acceptance for Chantier 3**

```
Test 1: G1 fires only when ready
  - Send brief, approve hypotheses
  - Watch research run
  - Verify: G1 doesn't fire until ≥5 findings + ≥3 KNOWN
  - If research finishes with only 3 findings:
    ✓ Gate doesn't fire
    ✓ Orchestrator continues research
    ✓ G1 fires when threshold met

Test 2: Budget exceeded
  - Force a slow phase (mock long tool calls)
  - Verify: after 80 tool calls or 20 minutes
    ✓ "stalled" event emitted
    ✓ User sees recovery option
    ✓ Mission doesn't crash

Test 3: G3 requires SHIP
  - Run through to synthesis
  - If Merlin issues MINOR_FIXES:
    ✓ G3 doesn't fire
    ✓ Loops back to redteam (max 3 times)
  - After 3 retries:
    ✓ Forces forward
    ✓ G3 fires with note: "forced after retry limit"
```

---

## CHANTIER 4 — Living Hypotheses + Editorial UI (3-4 days)

**Goal:** Hypotheses become a central living object. Findings have hierarchy. Deliverables have preview.

**Risk:** Medium. UI changes + new endpoints, no graph changes.

**Files to modify:**
```
marvin_ui/server.py                          ← new endpoints
components/marvin/MissionControl.tsx         ← hypothesis panel
components/marvin/HypothesisPanel.tsx        ← NEW
components/marvin/FindingCard.tsx            ← NEW (with hierarchy)
components/marvin/DeliverablePreview.tsx     ← NEW
marvin/tools/mission_tools.py                ← compute hypothesis status
```

### Living hypotheses

**Status calculation (server-side):**
```python
def compute_hypothesis_status(mission_id: str, hypothesis_id: str) -> dict:
    """Returns hypothesis status based on current findings."""
    store = MissionStore()
    findings = [f for f in store.list_findings(mission_id) 
                if f.hypothesis_id == hypothesis_id]
    
    if not findings:
        return {"status": "NOT_STARTED", "score": 0, "evidence_count": 0}
    
    # Score: each KNOWN supporting = +2, REASONED = +1, 
    #        each contradiction = -2 or -1
    score = 0
    supporting = 0
    contradicting = 0
    
    for f in findings:
        weight = 2 if f.confidence == "KNOWN" else \
                 1 if f.confidence == "REASONED" else 0
        if f.supports:  # need to add this field
            score += weight
            supporting += 1
        else:
            score -= weight
            contradicting += 1
    
    # Status thresholds
    if score >= 4 and supporting >= 2:
        status = "SUPPORTED"
    elif score >= 1:
        status = "TESTING"
    elif score >= -2:
        status = "WEAKENED"
    else:
        status = "INVALIDATED"
    
    return {
        "status": status,
        "score": score,
        "evidence_count": len(findings),
        "supporting": supporting,
        "contradicting": contradicting
    }
```

**New endpoint:**
```python
@router.get("/api/v1/missions/{mission_id}/hypotheses")
async def get_hypotheses(mission_id: str):
    store = MissionStore()
    hypotheses = store.list_hypotheses(mission_id)
    return {
        "hypotheses": [
            {
                "id": h.id,
                "text": h.text,
                "raw_status": h.status,
                **compute_hypothesis_status(mission_id, h.id)
            }
            for h in hypotheses
        ]
    }
```

### HypothesisPanel component

```tsx
// Displayed in CENTER column, above workstream tabs
// Or as a permanent right rail

<div className="hypothesis-panel">
  {hypotheses.map(h => (
    <div key={h.id} className="hypothesis-row">
      <div className="hyp-header">
        <span className="hyp-label">H{idx+1}</span>
        <span className="hyp-text">{h.text}</span>
      </div>
      <div className="hyp-bar-wrap">
        <div className={`hyp-bar status-${h.status.toLowerCase()}`} 
             style={{width: `${normalize(h.score)}%`}} />
      </div>
      <div className="hyp-meta">
        <span className={`status-badge ${h.status.toLowerCase()}`}>
          {h.status}
        </span>
        <span className="evidence">
          {h.supporting} supporting · {h.contradicting} contra
        </span>
      </div>
    </div>
  ))}
</div>
```

Colors:
- SUPPORTED: green (#2D6E4E)
- TESTING: blue (#185FA5)
- WEAKENED: amber (#8B6200)
- INVALIDATED: red (#A32D2D)
- NOT_STARTED: gray border, no fill

### Finding hierarchy

Findings must be tagged with impact:
```python
class Finding(BaseModel):
    # ... existing ...
    impact: Literal["critical", "important", "info"] = "info"
    supports: bool | None = None  # True/False/None for hypothesis link
```

In FindingCard:
```tsx
<div className={`finding-card impact-${finding.impact}`}>
  {finding.impact === "critical" && (
    <span className="impact-marker">⚠ CRITICAL</span>
  )}
  <div className="finding-claim">{finding.claim_text}</div>
  <div className="finding-meta">
    <ConfidenceBadge level={finding.confidence} />
    <span className="finding-source">{finding.source_id}</span>
    <span className="finding-hypothesis">
      {finding.supports ? '→' : '⊥'} H{idx}
    </span>
  </div>
</div>
```

### Deliverable preview

New endpoint:
```python
@router.get("/api/v1/deliverables/{deliverable_id}/preview")
async def preview_deliverable(deliverable_id: str):
    deliverable = store.get_deliverable(deliverable_id)
    
    # For markdown: return first 500 chars + structure
    if deliverable.file_path.endswith(".md"):
        content = Path(deliverable.file_path).read_text()
        # Extract headings
        headings = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
        return {
            "type": "markdown",
            "preview_text": content[:500] + "...",
            "headings": headings,
            "word_count": len(content.split())
        }
    
    # For PDF: return first page + table of contents
    # (use pdfplumber)
    
    return {"type": "unknown"}
```

In DeliverablePreview:
```tsx
<div className="deliverable-preview">
  <div className="preview-header">
    <h3>{deliverable.label}</h3>
    <span className="word-count">{preview.word_count} words</span>
  </div>
  <div className="preview-toc">
    {preview.headings.map(h => <li>{h}</li>)}
  </div>
  <div className="preview-text">{preview.preview_text}</div>
  <div className="preview-actions">
    <button onClick={download}>Download full</button>
    <button onClick={openInline}>Open inline</button>
  </div>
</div>
```

### Acceptance for Chantier 4

```
Test 1: Living hypotheses
  - Send Vinted brief
  - Verify HypothesisPanel always visible
  - As findings come in, observe:
    ✓ Hypothesis bars update in real-time
    ✓ Status changes from NOT_STARTED → TESTING → SUPPORTED/WEAKENED
    ✓ Counts update (supporting / contradicting)

Test 2: Hierarchy
  - Critical findings show with red marker
  - Important findings show normally
  - Info findings show muted
  - User can filter by impact

Test 3: Preview
  - When engagement brief is ready
  - Click "preview" (not download)
  - See: word count, headings, first 500 chars
  - Can decide whether to download full
```

---

## IMPLEMENTATION SEQUENCE

```
Day 1       — Chantier 1 (voice/personas)
              Test by sending a brief, observe MARVIN voice
              
Day 2-3     — Chantier 1 polishing + start Chantier 2
              Verify chantier 1 didn't break anything (test suite)
              Begin framing flexibility

Day 4-5     — Chantier 2 (flexible Phase 1)
              End Day 5: full framing test pass

Day 6-7     — Chantier 3 (conditional gates)
              This is the riskiest. Allocate buffer.

Day 8-9     — Chantier 3 polish + start Chantier 4

Day 10-11   — Chantier 4 (living hypotheses + UI)

Day 12      — Full E2E test on Vinted + 1 other brief
              All 4 chantiers integrated
```

---

## OVERALL ACCEPTANCE

Done when sending the Vinted brief produces:

```
PHASE 1 (framing)
  ✓ MARVIN says: "Vinted — {tension}. Framing now." (1-2 sentences)
  ✓ If brief is thin, asks 2-3 specific questions
  ✓ Engagement brief generated AND framing memo generated
  ✓ 5-6 hypotheses persisted
  ✓ Hypothesis panel shows all 6, status NOT_STARTED

PHASE 2 (research)
  ✓ Dora produces ≥3 findings, all with sources
  ✓ Calculus produces ≥3 findings, all with periods
  ✓ Adversus has not started yet
  ✓ Hypothesis panel updates in real-time
  ✓ G1 doesn't fire until conditions met
  ✓ When G1 fires, gate has real claims to validate

PHASE 3 (red-team)
  ✓ Adversus produces counter-findings
  ✓ Weakest link identified
  ✓ Stress scenarios generated
  ✓ Hypothesis statuses change based on red-team findings

PHASE 4 (synthesis)
  ✓ Merlin issues clear verdict (SHIP / MINOR_FIXES / BACK_TO_DRAWING_BOARD)
  ✓ Verdict has specific reasoning
  ✓ G3 fires only when SHIP (or after 3 retries)

PHASE 5 (delivery)
  ✓ 3 deliverables generated, all with preview
  ✓ Each deliverable has table of contents visible
  ✓ Preview shows first 500 chars + word count
  ✓ Full download works

OVERALL
  ✓ MARVIN never produces paragraphs >3 sentences in chat
  ✓ Findings are hierarchized (critical / important / info)
  ✓ Hypotheses panel always visible, always live
  ✓ No mock data anywhere in UI
  ✓ All 8 phases pass within 30 minutes total
  ✓ npm run test → 0 failures
  ✓ pytest → 0 failures
```

---

## REVERT STRATEGY

If a chantier breaks the system:

```
Chantier 1: 
  git revert {commit_range}
  Only .md files affected. Safe revert.

Chantier 2:
  git revert {commit_range}
  Modifies phase_router. Test that the revert restores Phase 1 mechanical behavior.

Chantier 3:
  git revert {commit_range}
  This is the riskiest revert. Keep a feature branch, merge only after full E2E pass.

Chantier 4:
  git revert {commit_range}
  UI + new endpoints only. Backend graph unchanged. Safe revert.
```

After any revert, run:
```bash
pytest tests/ -q              # backend tests
npm run test                  # frontend tests
# Manual: send Vinted brief, verify 7 checkpoints
```
