# MARVIN — Complete Revamp Specification
*4 chantiers + pivot mechanism · sequential implementation*
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
- No mechanism to pivot if a finding kills the thesis mid-mission

The architecture is correct. The execution is shallow.

This spec covers 4 chantiers + a pivot mechanism that fix this without breaking what works.

**Order matters. Each chantier builds on the previous one.**

---

## SHARED PRINCIPLES (apply to all chantiers)

```
1. KEEP what works:
   - phase_router deterministic routing
   - MarvinState with reducers
   - LangGraph subgraphs
   - DB schema + hallucination prevention
   - Existing tools (don't rewrite)
   - Gate interrupt() pattern

2. REPLACE what's mechanical:
   - Generic prompts → distinctive personas (5 separate files)
   - Calendar gates → conditional gates
   - Static hypotheses → living objects
   - Flat findings → hierarchical narrative

3. ADD what's missing:
   - Pivot mechanism (thesis-killing finding detection)
   - Re-framing path mid-mission
   - Special "pivot review" gate

4. NEVER:
   - Rewrite phase_router from scratch
   - Change DB schema (except minor additions noted explicitly)
   - Add new agents
   - Remove the 5 existing agents
   - Break working tools

5. EACH CHANTIER must:
   - Be implementable independently
   - Pass all existing tests after implementation
   - Have a clear acceptance criterion
   - Be revertable in one git revert
```

---

## CHANTIER 1 — Voice & Personas (1 day)

**Goal:** Each agent has a distinctive voice. MARVIN sounds like a senior consultant, not ChatGPT.

**Risk:** Zero. Only .md prompt files change.

**CRITICAL — File structure:**

Each agent has its OWN file. Do not merge prompts into a single file. The current structure must be preserved:

```
marvin/subagents/prompts/
  ├── orchestrator.md   ← MARVIN's voice (this file is shipped separately)
  ├── dora.md           ← Market researcher persona
  ├── calculus.md       ← Financial analyst persona
  ├── adversus.md       ← Red-teamer persona
  └── merlin.md         ← Editorial synthesis persona
```

The 5 prompt files to ship are provided separately as attachments:
- `prompt_orchestrator.md`
- `prompt_dora.md`
- `prompt_calculus.md`
- `prompt_adversus.md`
- `prompt_merlin.md`

**Implementation:**

Replace the entire content of each file in `marvin/subagents/prompts/` with the corresponding attached file. Do NOT merge them. Do NOT keep old content. Do NOT add comments referencing the old prompts.

After replacement:
```bash
ls -la marvin/subagents/prompts/
# Should show 5 .md files, each one matching the attached version
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

Test the prompts also pass existing tests:
  pytest tests/ -q              # must show 0 failures
  npm run test                  # must show 0 failures
```

---

## CHANTIER 2 — Flexible Phase 1 + Pivot Mechanism (3-4 days)

**Goal:** Framing becomes a real conversation. Mid-mission pivot is possible if a thesis-killing finding emerges.

**Risk:** Medium. Modifies phase_router and adds pivot detection.

**Files to modify:**
```
marvin/graph/runner.py                ← phase_router enhancements
marvin/tools/mission_tools.py         ← _generate_hypotheses_inline
marvin/tools/arbiter_tools.py         ← thesis-killing detection
marvin/graph/state.py                 ← add framing_complete + pivot fields
marvin/graph/subgraphs/orchestrator.py ← framing_orchestrator
marvin/subagents/prompts/orchestrator.md ← add framing mode + pivot mode
```

### Part A — Flexible Phase 1 (framing)

**Behavior change:**

Before:
```
brief → _generate_hypotheses_inline → awaiting_confirmation
(takes ~30 seconds)
```

After:
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

**1. Add framing state**

In `state.py`:
```python
class MarvinState(TypedDict):
    # ... existing fields ...
    framing_complete: Annotated[bool, last_value]
    clarification_questions_asked: Annotated[int, last_value]
    pivot_required: Annotated[bool, last_value]
    pivot_reason: Annotated[str | None, last_value]
```

**2. Modify phase_router for "framing" phase**

In `runner.py`:
```python
if phase == "framing":
    mid = state["mission_id"]
    
    # Check if we already have enough context
    if not state.get("framing_complete"):
        # Route to orchestrator for evaluation
        return [Send("framing_orchestrator", state)]
    
    # We have framing complete → generate hypotheses
    from marvin.tools.mission_tools import _generate_hypotheses_inline
    _generate_hypotheses_inline(mid)
    
    # Write framing memo (Papyrus tool, no LLM)
    from marvin.tools.papyrus_tools import _generate_framing_memo
    _generate_framing_memo(mid)
    
    return [{"phase": "awaiting_confirmation"}]
```

**3. Create framing_orchestrator subgraph**

A specialized orchestrator with these tools:
- `evaluate_brief_completeness(state)` — returns {"ready": bool, "missing": [...]}
- `ask_question(text, blocking=True)` — emits gate_pending for user input
- `mark_framing_complete()` — sets framing_complete=True

System prompt addition (in `orchestrator.md`, see attached file).

### Part B — Pivot Mechanism

**Behavior:**

When a finding is detected as "thesis-killing" during research or red-team, the system pauses, presents a pivot review gate to the user. The user can:
- Pivot: re-frame hypotheses based on the finding
- Continue: acknowledge but proceed (note in audit trail)
- Abort: stop the mission

**1. Detection logic**

In `arbiter_tools.py`:
```python
def detect_thesis_killing_finding(mission_id: str) -> dict | None:
    """Check if any recent finding is thesis-killing."""
    store = MissionStore()
    findings = store.list_findings(mission_id)
    hypotheses = store.list_hypotheses(mission_id, status="active")
    
    # Recent findings (last 5 minutes)
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    recent = [f for f in findings if f.created_at > cutoff]
    
    # A thesis-killing finding meets ALL these criteria:
    # 1. Confidence is KNOWN (sourced fact, not speculation)
    # 2. It contradicts a load-bearing hypothesis
    # 3. The contradiction is direct (not just weakening)
    # 4. The hypothesis it contradicts is supported by 
    #    most other current findings (= central to thesis)
    
    for finding in recent:
        if finding.confidence != "KNOWN":
            continue
        
        if not finding.hypothesis_id:
            continue
            
        if not finding.contradicts:  # need to add this field
            continue
        
        # Find the hypothesis
        target_hyp = next((h for h in hypotheses 
                          if h.id == finding.hypothesis_id), None)
        if not target_hyp:
            continue
        
        # Count supporting findings for this hypothesis
        supporting = [f for f in findings 
                     if f.hypothesis_id == target_hyp.id 
                     and f.supports]
        
        # If hypothesis was strongly supported, this is a pivot
        if len(supporting) >= 3:
            return {
                "is_killing": True,
                "finding_id": finding.id,
                "finding_text": finding.claim_text,
                "hypothesis_id": target_hyp.id,
                "hypothesis_text": target_hyp.text,
                "supporting_count": len(supporting),
                "reason": (
                    f"Finding directly contradicts H{target_hyp.id} "
                    f"which had {len(supporting)} supporting findings. "
                    f"This invalidates the central thesis."
                )
            }
    
    return None
```

**2. Pivot trigger in research_join**

In `runner.py`:
```python
def research_join(state: MarvinState) -> dict:
    """Fan-in after parallel research."""
    mid = state.get("mission_id", "")
    store = MissionStore()
    
    # Check for thesis-killing finding BEFORE checking phase advance
    from marvin.tools.arbiter_tools import detect_thesis_killing_finding
    pivot_check = detect_thesis_killing_finding(mid)
    
    if pivot_check:
        return {
            "pivot_required": True,
            "pivot_reason": pivot_check["reason"],
            "phase": "pivot_review_pending"
        }
    
    # Normal logic continues...
    milestones = store.list_milestones(mid)
    w1_done = any(m.status == "delivered" and "W1.1" in m.id 
                  for m in milestones)
    w2_done = any(m.status == "delivered" and "W2.1" in m.id 
                  for m in milestones)
    
    if w1_done and w2_done:
        # ... existing logic
        return {"phase": "research_done"}
    
    return {}
```

Same check in adversus_node wrapper:
```python
async def adversus_node(state: MarvinState) -> dict:
    result = await adversus_agent.ainvoke(state)
    
    # After Adversus runs, check for thesis-killing
    pivot_check = detect_thesis_killing_finding(state["mission_id"])
    if pivot_check:
        return {
            **result,
            "pivot_required": True,
            "pivot_reason": pivot_check["reason"],
            "phase": "pivot_review_pending"
        }
    
    return {**result, "phase": "redteam_done"}
```

**3. Pivot review gate**

Add a new gate type in `gates.py`:
```python
if phase == "pivot_review_pending":
    mid = state["mission_id"]
    pivot_reason = state.get("pivot_reason", "Unknown")
    
    # Create pivot gate
    gate_id = f"gate-{mid}-pivot-{uuid4().hex[:6]}"
    store.save_gate(Gate(
        id=gate_id,
        mission_id=mid,
        gate_type="pivot_review",
        scheduled_day=999,  # special: not on calendar
        validator_role="manager",
        status="pending",
        format="pivot_decision"
    ))
    
    return [Send("gate", {**state, "pending_gate_id": gate_id})]
```

**4. Pivot gate handling**

In `gate_node`, add handling for `pivot_review`:
```python
if gate.format == "pivot_decision":
    payload = {
        "gate_id": gate_id,
        "gate_type": "pivot_review",
        "format": "pivot_decision",
        "pivot_reason": state.get("pivot_reason"),
        "thesis_killing_finding": findings[-1].claim_text if findings else "",
        "options": [
            {"action": "pivot", 
             "label": "Pivot — re-frame hypotheses",
             "consequence": "Returns to framing phase with insights from research"},
            {"action": "continue", 
             "label": "Continue — acknowledge but proceed",
             "consequence": "Note added to audit trail. Research continues."},
            {"action": "abort", 
             "label": "Abort — stop mission",
             "consequence": "Mission marked completed with no-deal verdict"}
        ]
    }
    
    if config:
        await adispatch_custom_event("gate_pending", payload, config=config)
        await asyncio.sleep(0.1)
    
    decision = interrupt(payload)
    
    action = decision.get("action", "continue")
    
    if action == "pivot":
        # Mark current hypotheses as "abandoned with reason"
        for h in store.list_hypotheses(mid, status="active"):
            store.update_hypothesis(
                h.id, 
                status="abandoned", 
                abandon_reason=f"Pivot: {state.get('pivot_reason')}"
            )
        return {
            "pivot_required": False,
            "pivot_reason": None,
            "framing_complete": False,  # restart framing
            "phase": "framing"
        }
    
    if action == "abort":
        store.update_mission_status(mid, "completed_no_deal")
        return {
            "pivot_required": False,
            "phase": "done"
        }
    
    # action == "continue"
    return {
        "pivot_required": False,
        "pivot_reason": None,
        "phase": "research_done"  # proceed with original phase
    }
```

**5. UI handling**

In MissionControl, handle the new gate format:
```typescript
case "gate_pending":
  if (event.format === "pivot_decision") {
    setPivotModal({
      reason: event.pivot_reason,
      finding: event.thesis_killing_finding,
      options: event.options
    });
  } else {
    setGateModal(event);
  }
  break;
```

PivotModal component:
```tsx
<div className="pivot-modal">
  <div className="pivot-header">
    <span className="pivot-marker">⚠ PIVOT REVIEW</span>
    <h2>Thesis-killing finding detected</h2>
  </div>
  
  <div className="pivot-reason">
    {pivotModal.reason}
  </div>
  
  <div className="pivot-finding">
    <label>Finding:</label>
    <p>"{pivotModal.finding}"</p>
  </div>
  
  <div className="pivot-options">
    {pivotModal.options.map(opt => (
      <button 
        key={opt.action}
        className={`pivot-option pivot-${opt.action}`}
        onClick={() => handlePivotDecision(opt.action)}
      >
        <span className="pivot-label">{opt.label}</span>
        <span className="pivot-consequence">{opt.consequence}</span>
      </button>
    ))}
  </div>
</div>
```

**6. Schema updates**

Add to `Finding` model in `schema.py`:
```python
class Finding(BaseModel):
    # ... existing ...
    supports: bool | None = None  # True = supports hypothesis, False = contradicts
    contradicts: bool = False     # Explicit flag for thesis-killing detection
```

Migration `002_add_finding_flags.sql`:
```sql
ALTER TABLE findings ADD COLUMN supports INTEGER DEFAULT NULL;
ALTER TABLE findings ADD COLUMN contradicts INTEGER DEFAULT 0;
```

### Acceptance for Chantier 2

```
Test 1: Substantive brief flows to framing
  Input: "CDD Vinted, €5Bn, fund acquisition, 
          IC question: valuation justified given Depop competition"
  Expected: 
    ✓ MARVIN proceeds directly to hypothesis generation
    ✓ No clarification questions
    ✓ Total time: <2 minutes
    ✓ Framing memo file exists at output/{mid}/framing_memo.md

Test 2: Thin brief triggers questions
  Input: "should we acquire cursor?"
  Expected:
    ✓ MARVIN asks 2-3 specific questions
    ✓ Questions are about: time horizon, fund type, competitive concern
    ✓ After user answers, MARVIN proceeds
    ✓ Hypotheses generated reflect the clarified context

Test 3: Pivot detection during research
  Setup: Mock a KNOWN finding that contradicts H1 
         where H1 has 3 supporting findings
  Expected:
    ✓ research_join detects pivot_required
    ✓ Phase becomes "pivot_review_pending"
    ✓ pivot_review gate fires with format="pivot_decision"
    ✓ UI shows PivotModal with 3 options
    ✓ "Pivot" → returns to framing, hypotheses marked abandoned
    ✓ "Continue" → returns to research_done as normal
    ✓ "Abort" → mission marked completed_no_deal

Test 4: No false positive pivot
  Setup: A LOW_CONFIDENCE finding that contradicts H1
  Expected:
    ✓ NOT detected as thesis-killing
    ✓ Mission proceeds normally
```

---

## CHANTIER 3 — Conditional Gates + Flexible Phases (3-4 days)

**Goal:** Gates fire when content is ready, not by phase completion. All phases become flexible within budgets.

**Risk:** High. Touches the core flow logic.

### Empirical findings from Chantier 1.5 verification

Runtime evidence on the Vinted brief (E2E with the new prompts):

- **Mission duration:** Mission ran > 10 minutes E2E. The G3 gate
  fired but the SSE stream max-time was hit before user approval.
  Confirms phase budgets are needed.

- **Finding volume per mission:** ~91 findings on a single Vinted
  brief (W1=8 dora, W4=83 adversus, W2=0 calculus when no data
  room is provided). Original Chantier 3 spec proposed 80 tool
  calls / 20 minutes per phase — this needs adjustment.

  Suggested revised budgets:
  - Research phase: 60 findings, 15 min, 80 tool_calls
  - Red-team phase: 15 findings/pass, 10 min/pass, 50 tool_calls/pass
  - Synthesis retry cap: 2 retries max (current loop runs 3)

- **Synthesis retry multiplier:** Each `synthesis_retry → adversus
  → merlin` cycle re-runs Adversus. v4 mission had 3 cycles → 83
  W4 findings (~28/cycle). Either:
  - Cap the retry count at 2 (Chantier 3 budget), AND/OR
  - Make Adversus delta-only on retry (prompt updated in Chantier
    1.5 to forbid duplicate attacks on retry)

- **Conditional G1 readiness logic:** Current G1 fires after
  `research_done` regardless of finding sufficiency. v4 had
  Calculus produce 0 W2 findings (no data room), yet G1 still
  fired. Confirms the need for `check_gate_readiness()`:
  - Require ≥3 findings per non-skipped workstream before G1
  - OR: explicit per-workstream "evidence-gap" finding that
    documents the missing material (Dora's pattern in v3/v4)


**Files to modify:**
```
marvin/graph/runner.py                ← phase_router conditions
marvin/graph/gates.py                 ← gate triggering logic
marvin/tools/arbiter_tools.py         ← gate readiness checks
marvin/graph/state.py                 ← add budget tracking
```

### Behavior change

**Before:** "Phase 2 done" → "fire G1" (regardless of content quality)

**After:** Each phase has required output conditions and budgets.

**1. Define gate conditions**

In `arbiter_tools.py`:
```python
def check_gate_readiness(mission_id: str, gate_type: str) -> dict:
    """Check if a gate is ready to fire based on content."""
    store = MissionStore()
    findings = store.list_findings(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    
    if gate_type == "manager_review":  # G1
        known_count = len([f for f in findings 
                          if f.confidence == "KNOWN"])
        active_hypotheses = [h for h in hypotheses if h.status == "active"]
        hypothesis_coverage = all(
            any(f.hypothesis_id == h.id for f in findings)
            for h in active_hypotheses
        )
        unsourced_known = [f for f in findings 
                          if f.confidence == "KNOWN" and not f.source_id]
        
        ready = (
            len(findings) >= 5 and
            known_count >= 3 and
            hypothesis_coverage and
            len(unsourced_known) == 0
        )
        
        missing = []
        if len(findings) < 5:
            missing.append(f"Need {5 - len(findings)} more findings")
        if known_count < 3:
            missing.append(f"Need {3 - known_count} more KNOWN findings")
        if not hypothesis_coverage:
            uncovered = [h.id for h in active_hypotheses 
                        if not any(f.hypothesis_id == h.id for f in findings)]
            missing.append(f"Hypotheses without findings: {uncovered}")
        if unsourced_known:
            missing.append(f"{len(unsourced_known)} KNOWN findings without source")
        
        return {"ready": ready, "missing": missing}
    
    if gate_type == "final_review":  # G3
        verdict = store.get_latest_merlin_verdict(mission_id)
        adversus_done = any(
            m.status == "delivered" and m.id.startswith("W4")
            for m in store.list_milestones(mission_id)
        )
        
        ready = (
            verdict and 
            verdict["verdict"] == "SHIP" and 
            adversus_done
        )
        
        missing = []
        if not verdict:
            missing.append("Merlin has not issued verdict")
        elif verdict["verdict"] != "SHIP":
            missing.append(f"Merlin verdict is {verdict['verdict']}, not SHIP")
        if not adversus_done:
            missing.append("Adversus has not completed W4")
        
        return {"ready": ready, "missing": missing}
    
    return {"ready": False, "missing": ["unknown gate type"]}
```

**2. Modify phase_router to check readiness**

In `runner.py`:
```python
if phase == "research_done":
    mid = state["mission_id"]
    readiness = check_gate_readiness(mid, "manager_review")
    
    if not readiness["ready"]:
        # Don't fire gate yet. Tell orchestrator what's missing.
        missing_msg = HumanMessage(content=
            f"Research insufficient for G1. Missing:\n"
            f"- " + "\n- ".join(readiness["missing"]) + "\n"
            f"Continue research to address gaps."
        )
        return [Send("dora", 
                    {**state, 
                     "messages": state["messages"] + [missing_msg]})]
    
    # Ready → fire gate
    g1_id = _resolve_gate_by_day(mid, day=3)
    return [Send("gate", {**state, "pending_gate_id": g1_id})]
```

**3. Add phase budgets**

In `state.py`:
```python
class MarvinState(TypedDict):
    # ... existing ...
    phase_tool_calls: Annotated[int, last_value]
    phase_started_at: Annotated[str, last_value]
```

In `runner.py`:
```python
PHASE_BUDGETS = {
    "framing": {"tool_calls": 30, "minutes": 5},
    "research": {"tool_calls": 80, "minutes": 20},
    "redteam": {"tool_calls": 40, "minutes": 10},
    "synthesis": {"tool_calls": 30, "minutes": 5},
}

def check_phase_budget(state) -> bool:
    """Returns True if budget remaining, False if exceeded."""
    phase = state.get("phase", "")
    budget = PHASE_BUDGETS.get(phase)
    if not budget:
        return True
    
    tool_calls = state.get("phase_tool_calls", 0)
    if tool_calls >= budget["tool_calls"]:
        return False
    
    started = state.get("phase_started_at")
    if started:
        from datetime import datetime
        elapsed_min = (
            datetime.utcnow() - datetime.fromisoformat(started)
        ).total_seconds() / 60
        if elapsed_min >= budget["minutes"]:
            return False
    
    return True
```

When budget exceeded, emit a stalled event:
```python
if not check_phase_budget(state):
    # Force exit
    if config:
        await adispatch_custom_event("stalled", {
            "phase": state.get("phase"),
            "reason": "budget_exceeded",
            "tool_calls": state.get("phase_tool_calls"),
        }, config=config)
    
    # Emit gate as fallback to let user decide
    return [Send("gate", {
        **state, 
        "pending_gate_id": f"gate-{state['mission_id']}-stalled"
    })]
```

### Acceptance for Chantier 3

```
Test 1: G1 fires only when ready
  - Send brief, approve hypotheses
  - Verify: G1 doesn't fire until ≥5 findings + ≥3 KNOWN + 
    coverage of all active hypotheses
  - If research finishes with only 3 findings:
    ✓ Gate doesn't fire
    ✓ Orchestrator continues research
    ✓ G1 fires when threshold met

Test 2: Budget exceeded → stalled
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

Test 4: Compatibility with Chantier 2 pivot
  - Trigger pivot during research
  - Verify pivot mechanism still works
  - After pivot resolution, gate readiness checks continue normally
```

---

## CHANTIER 4 — Living Hypotheses + Editorial UI (3-4 days)

**Goal:** Hypotheses become a central living object. Findings have hierarchy. Deliverables have preview.

**Risk:** Medium. UI changes + new endpoints, no graph changes.

**Files to modify:**
```
marvin_ui/server.py                          ← new endpoints
components/marvin/MissionControl.tsx         ← hypothesis panel integration
components/marvin/HypothesisPanel.tsx        ← NEW
components/marvin/FindingCard.tsx            ← NEW (with hierarchy)
components/marvin/DeliverablePreview.tsx     ← NEW
marvin/tools/mission_tools.py                ← compute hypothesis status
marvin/mission/schema.py                     ← add impact field
```

### Living hypotheses

**Schema update:**
```python
class Finding(BaseModel):
    # ... existing fields including supports/contradicts from Chantier 2 ...
    impact: Literal["critical", "important", "info"] = "info"
```

Migration `003_add_finding_impact.sql`:
```sql
ALTER TABLE findings ADD COLUMN impact TEXT DEFAULT 'info'
  CHECK (impact IN ('critical', 'important', 'info'));
```

**Status calculation:**
```python
def compute_hypothesis_status(mission_id: str, hypothesis_id: str) -> dict:
    """Returns hypothesis status based on current findings."""
    store = MissionStore()
    findings = [f for f in store.list_findings(mission_id) 
                if f.hypothesis_id == hypothesis_id]
    
    if not findings:
        return {"status": "NOT_STARTED", "score": 0, 
                "evidence_count": 0, "supporting": 0, "contradicting": 0}
    
    score = 0
    supporting = 0
    contradicting = 0
    
    for f in findings:
        weight = (
            2 if f.confidence == "KNOWN" else
            1 if f.confidence == "REASONED" else
            0  # LOW_CONFIDENCE
        )
        if f.supports:
            score += weight
            supporting += 1
        elif f.contradicts:
            score -= weight
            contradicting += 1
    
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
                "abandon_reason": h.abandon_reason,
                **compute_hypothesis_status(mission_id, h.id)
            }
            for h in hypotheses
        ]
    }
```

**HypothesisPanel component (always visible):**
```tsx
<div className="hypothesis-panel">
  <div className="panel-header">
    <h3>Hypotheses</h3>
    <span className="hypotheses-count">{hypotheses.length}</span>
  </div>
  
  {hypotheses.map((h, idx) => (
    <div key={h.id} className="hypothesis-row">
      <div className="hyp-header">
        <span className="hyp-label">H{idx+1}</span>
        <span className="hyp-text">{h.text}</span>
      </div>
      
      {h.raw_status === "abandoned" ? (
        <div className="hyp-abandoned">
          ABANDONED · {h.abandon_reason}
        </div>
      ) : (
        <>
          <div className="hyp-bar-wrap">
            <div 
              className={`hyp-bar status-${h.status.toLowerCase()}`} 
              style={{width: `${normalize(h.score)}%`}} 
            />
          </div>
          <div className="hyp-meta">
            <span className={`status-badge ${h.status.toLowerCase()}`}>
              {h.status}
            </span>
            <span className="evidence">
              {h.supporting} supporting · {h.contradicting} contra
            </span>
          </div>
        </>
      )}
    </div>
  ))}
</div>
```

### Finding hierarchy

In FindingCard:
```tsx
<div className={`finding-card impact-${finding.impact}`}>
  {finding.impact === "critical" && (
    <span className="impact-marker">⚠ CRITICAL</span>
  )}
  <div className="finding-claim">{finding.claim_text}</div>
  <div className="finding-meta">
    <ConfidenceBadge level={finding.confidence} />
    {finding.source_id && (
      <span className="finding-source">{finding.source_id}</span>
    )}
    <span className={`finding-hypothesis ${finding.supports ? 'supports' : 'contradicts'}`}>
      {finding.supports ? '→' : '⊥'} H{getHypothesisIndex(finding.hypothesis_id)}
    </span>
  </div>
</div>
```

Filter controls:
```tsx
<div className="finding-filters">
  <button onClick={() => setFilter("critical")}>Critical only</button>
  <button onClick={() => setFilter("all")}>All findings</button>
</div>
```

### Deliverable preview

New endpoint:
```python
@router.get("/api/v1/deliverables/{deliverable_id}/preview")
async def preview_deliverable(deliverable_id: str):
    store = MissionStore()
    deliverable = store.get_deliverable(deliverable_id)
    
    if not deliverable or not Path(deliverable.file_path).exists():
        raise HTTPException(404, "Deliverable not found")
    
    content = Path(deliverable.file_path).read_text(encoding="utf-8")
    
    if deliverable.file_path.endswith(".md"):
        import re
        headings = re.findall(r'^(#{1,3})\s+(.+)$', content, re.MULTILINE)
        return {
            "type": "markdown",
            "preview_text": content[:1000] + ("..." if len(content) > 1000 else ""),
            "headings": [{"level": len(h[0]), "text": h[1]} for h in headings],
            "word_count": len(content.split()),
            "char_count": len(content)
        }
    
    if deliverable.file_path.endswith(".pdf"):
        # Use pdfplumber
        import pdfplumber
        with pdfplumber.open(deliverable.file_path) as pdf:
            first_page = pdf.pages[0].extract_text() if pdf.pages else ""
            page_count = len(pdf.pages)
        return {
            "type": "pdf",
            "first_page_text": first_page[:1500],
            "page_count": page_count
        }
    
    return {"type": "unknown", "preview_text": content[:500]}
```

DeliverablePreview component:
```tsx
<div className="deliverable-preview">
  <div className="preview-header">
    <h3>{deliverable.label}</h3>
    <span className="word-count">
      {preview.word_count ? `${preview.word_count} words` : 
       preview.page_count ? `${preview.page_count} pages` : ''}
    </span>
  </div>
  
  {preview.headings && (
    <div className="preview-toc">
      <h4>Contents</h4>
      <ul>
        {preview.headings.map((h, i) => (
          <li key={i} className={`toc-h${h.level}`}>{h.text}</li>
        ))}
      </ul>
    </div>
  )}
  
  <div className="preview-text">
    <pre>{preview.preview_text || preview.first_page_text}</pre>
  </div>
  
  <div className="preview-actions">
    <button onClick={() => download(deliverable.id)}>Download full</button>
    <button onClick={() => openInline(deliverable.id)}>Open inline</button>
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
  - After pivot (Chantier 2):
    ✓ Abandoned hypotheses show "ABANDONED · {reason}"
    ✓ New hypotheses appear after re-framing

Test 2: Hierarchy
  - Critical findings show with red marker
  - Important findings show normally
  - Info findings show muted
  - Filter by impact works

Test 3: Preview
  - When engagement brief is ready
  - Click "preview" (not download)
  - See: word count, headings, first 1000 chars
  - Can decide whether to download full
  
Test 4: PDF preview
  - When CDD report PDF is generated
  - Preview shows first page + page count
  - Table of contents (if extractable)
```

---

## IMPLEMENTATION SEQUENCE

```
Day 1       — Chantier 1 (5 separate prompt files)
              Test by sending a brief, observe MARVIN voice
              
Day 2       — Verify Chantier 1 didn't break tests
              Begin Chantier 2 Part A (flexible framing)

Day 3-4     — Chantier 2 Part A complete
              Begin Chantier 2 Part B (pivot mechanism)

Day 5-6     — Chantier 2 Part B complete
              Test thin brief flow + thesis-killing detection
              Full Chantier 2 acceptance

Day 7-9     — Chantier 3 (conditional gates)
              Riskiest chantier. Allocate buffer.

Day 10-11   — Chantier 4 (living hypotheses + UI)

Day 12      — Full E2E test on Vinted + 1 thin brief + 1 pivot scenario
              All chantiers integrated
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
  ✓ If thesis-killing finding emerges → pivot gate fires

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
  ✓ Preview shows first 1000 chars + word count/page count
  ✓ Full download works

OVERALL
  ✓ MARVIN never produces paragraphs >3 sentences in chat
  ✓ Findings are hierarchized (critical / important / info)
  ✓ Hypotheses panel always visible, always live
  ✓ Pivot mechanism works on thesis-killing findings
  ✓ No mock data anywhere in UI
  ✓ All 8 phases pass within 30 minutes total
  ✓ npm run test → 0 failures
  ✓ pytest → 0 failures
```

---

## REVERT STRATEGY

```
Chantier 1: 
  git revert {commit_range}
  Only .md files affected. Safe revert.

Chantier 2:
  git revert {commit_range}
  Modifies phase_router + adds pivot. Test that revert restores
  Phase 1 mechanical behavior AND removes pivot gate.

Chantier 3:
  git revert {commit_range}
  This is the riskiest revert. Keep on feature branch, 
  merge only after full E2E pass.

Chantier 4:
  git revert {commit_range}
  UI + new endpoints + schema column additions.
  Backend graph unchanged. Safe revert (column adds are additive).
```

After any revert, run:
```bash
pytest tests/ -q              # backend tests
npm run test                  # frontend tests
# Manual: send Vinted brief, verify all phases work
```
