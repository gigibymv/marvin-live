# CHANTIER 2.5 — Critical Bug Cleanup
*Insert between Chantier 2 Part A and Part B*
*Estimated time: 2-3 days*
*Risk: Medium (touches core flow + state management)*

---

## WHY THIS CHANTIER EXISTS

Live testing on Mistral AI mission revealed structural bugs that 
make the experience untrustworthy:

1. Sending any chat message ("Approved", "show the memo") replays 
   the entire mission from setup, producing 3-4 duplicate verdicts 
   in the chat.

2. The original brief gets overwritten by user messages mid-mission. 
   The framing memo for Mistral now shows "Brief: but aren't we at 
   the memo stage?" instead of the actual Mistral brief.

3. System nodes (framing_orchestrator, papyrus, gate_node) display 
   as anonymous "AGENT" in the live feed, with no way to know what 
   produced the output.

4. Agents and findings reference hypotheses by UUID 
   (e.g., "hyp-85a6485f") instead of human-readable labels (H1/H2).

5. Agent display names are inconsistent: "DORA" vs "Dora" vs "dora" 
   in different contexts.

6. When an agent hits a terminal state (cap reached), retry loops 
   continue producing identical outputs without circuit breakers.

These are not new features. These are bugs that prevent the existing 
system from being usable. Fix them first.

Pivot mechanism (Chantier 2 Part B) and other new features must wait 
until the foundation is stable.

---

## SHARED PRINCIPLES

```
1. Fix the bug, don't mask it.
   - Tests must verify root cause is fixed
   - Defensive logging is fine, try/except masking is not

2. No new features in this chantier.
   - No new agents, no new gate types, no new endpoints
   - Just stabilization of what exists

3. After this chantier:
   - Sending the Mistral brief produces ONE verdict, not 4
   - Subsequent messages don't overwrite the brief
   - Every line in the live feed has an attributable agent name
   - Hypotheses are referenced as H1/H2 in user-facing text
   - When an agent finishes (cap or milestone), system advances
     instead of retrying infinitely
```

---

## BUG 1 — Mission replay on every chat message (CRITICAL)

### Symptom

In the Mistral chat log, after the initial framing, the user typed:
- "Approved"
- "approve show the memo"  
- "but aren't we at the memo stage?"

Each of these messages triggered a full mission replay, producing:
- 3 identical "Mistral AI — a defendable 36-month..." messages
- 4 identical "Verdict: MINOR_FIXES" messages
- 2 identical "Cannot comply..." messages
- 3 identical "Hypotheses for Mistral AI are already framed" messages

The chat became unreadable. Tokens were burned re-running agents 
that hit caps immediately.

### Root cause

In `marvin_ui/server.py`, the `_stream_chat` endpoint constructs 
`initial_state` with `phase="setup"` (or similar starting phase) 
on every chat call. When the graph runs, `phase_router` interprets 
this as "start mission" and re-routes through framing → research 
→ synthesis even when the mission is already in `awaiting_*` or 
`done` state.

The graph has no concept of "resume from where we left off" vs 
"start fresh".

### Fix

Two-part fix in `marvin_ui/server.py`:

**Part 1 — Read current state before constructing initial_state**

```python
async def _stream_chat(body: ChatRequest):
    mid = body.mission_id
    store = MissionStore()
    mission = store.get_mission(mid)
    
    if not mission:
        yield await _emit_error("Mission not found")
        return
    
    # Read current phase from DB
    current_phase = store.get_current_phase(mid) or "setup"
    
    # Determine if this is a fresh brief or a continuation
    is_initial_brief = (
        current_phase == "setup" 
        and not mission.brief
        and len(body.text) > 50  # heuristic: brief is substantial
    )
    
    if is_initial_brief:
        # First message — treat as brief
        store.update_mission_brief(mid, body.text)
        initial_state = {
            "messages": [HumanMessage(content=body.text)],
            "mission_id": mid,
            "phase": "setup",
        }
    else:
        # Continuation — preserve current phase
        initial_state = {
            "messages": [HumanMessage(content=body.text)],
            "mission_id": mid,
            "phase": current_phase,
            "framing_complete": store.get_framing_complete(mid),
            # ... other state fields preserved from DB
        }
    
    # Stream the graph
    async for event in graph.astream(initial_state, config, stream_mode="updates"):
        ...
```

**Part 2 — phase_router handles "post-setup" messages**

In `marvin/graph/runner.py`:

```python
def phase_router(state: MarvinState):
    phase = state.get("phase", "setup")
    
    # If user sends a message during awaiting_* or done state,
    # route to orchestrator for free-form Q&A — DO NOT re-execute
    # the mission flow.
    if phase in [
        "awaiting_clarification",
        "awaiting_confirmation", 
        "manager_review_pending",
        "final_review_pending",
        "done",
    ]:
        # Check if this is a user message (not an internal continuation)
        last_msg = state["messages"][-1] if state["messages"] else None
        if last_msg and isinstance(last_msg, HumanMessage):
            return [Send("orchestrator_qa", state)]
        # Otherwise, the gate is being resumed — handle normally
        return _handle_gate_resume(state)
    
    # ... existing logic for setup/framing/confirmed/etc.
```

**Part 3 — Add `orchestrator_qa` subgraph**

A specialized orchestrator that:
- Reads current mission state via tools (get_findings, get_hypotheses, get_deliverables)
- Answers the user's question in 1-3 sentences
- Does NOT re-trigger any agents
- Does NOT modify mission state
- Returns to the same paused state after answering

System prompt (add to orchestrator.md or new file):

```
You are MARVIN in Q&A mode. The mission is paused at a gate or 
completed. The user asked a question or made a comment.

Read mission state via tools. Answer in 1-3 sentences.

Do NOT trigger any new work. Do NOT re-execute phases.
Do NOT generate new findings or hypotheses.

If the user is asking to continue the mission:
"The {gate_name} gate is pending. Click 'Review now' to advance."

If the user asks about findings:
"Calculus has logged {N} findings. {one-line summary}."

If the user asks about the verdict:
"Merlin's verdict was {verdict}: {one-line reasoning}."

If the question is unclear:
"Currently at {phase}. What would you like to know?"

Maximum 3 sentences. No paragraphs.
```

### Acceptance test

```
Setup: Mistral mission, completed through synthesis, gate G3 pending.

Test 1 — User says "Approved" without clicking gate:
  ✓ MARVIN responds: "G3 is pending. Click 'Review now' to advance."
  ✓ NO replay of Mistral framing
  ✓ NO duplicate Merlin verdicts
  ✓ NO chat saturation

Test 2 — User asks "what's the verdict?":
  ✓ MARVIN responds with one-line summary
  ✓ Mission state unchanged

Test 3 — User clicks gate "Approved" button (proper resume):
  ✓ Mission advances normally to next phase
  ✓ Gate marked completed in DB
```

---

## BUG 2 — Brief overwritten by chat messages (CRITICAL)

### Symptom

The framing_memo for Mistral mission shows:

```
Brief Recap: but aren't we at the memo stage?
Raw Brief: but aren't we at the memo stage?
```

Instead of:

```
Brief Recap: Mistral AI — European LLM provider, ~$1Bn estimated 
ARR, Series B at $6Bn valuation (2024). IC question: ...
```

The original brief was replaced by a later conversational message.

### Root cause

In `marvin/graph/subgraphs/framing_orchestrator.py` (or wherever 
the brief is concatenated), every user message gets appended to 
or replaces `Mission.brief`. This is done because the system uses 
`MissionBrief on every turn` to support clarification rounds.

The fix is to distinguish between:
- The initial brief (set ONCE on first user message)
- Clarification answers (appended to a separate field)
- Conversational messages (don't touch brief at all)

### Fix

**Part 1 — Schema clarification**

Mission already has `brief: str` field. Add:
- `clarification_answers: list[str]` (already added in Chantier 2 D2)

The brief field should be set ONCE and FROZEN.

**Part 2 — Update Mission.brief logic**

In server.py `_stream_chat`:

```python
if is_initial_brief:
    # First substantive message — this IS the brief
    store.update_mission_brief(mid, body.text)
elif current_phase == "awaiting_clarification":
    # Clarification answer — append to clarification_answers
    store.append_clarification_answer(mid, body.text)
else:
    # Conversational message — DO NOT modify brief or clarifications
    pass
```

**Part 3 — Add `update_mission_brief` with frozen check**

In `MissionStore`:

```python
def update_mission_brief(self, mission_id: str, brief: str) -> None:
    """Set brief. ONLY allowed if brief is currently empty."""
    mission = self.get_mission(mission_id)
    if mission.brief and mission.brief.strip():
        # Brief already set — refuse to overwrite
        logger.warning(f"Attempted to overwrite brief for {mission_id}")
        return
    
    # Set brief
    cursor = self.conn.execute(
        "UPDATE missions SET brief = ? WHERE id = ?",
        (brief, mission_id)
    )
    self.conn.commit()
```

**Part 4 — Audit existing data**

Add a migration script `006_recover_briefs.sql` (manual, run once):

```sql
-- Identify missions where brief looks like a conversational message
-- (heuristic: very short, ends with ?, or contains casual phrases)
SELECT id, brief, target FROM missions 
WHERE LENGTH(brief) < 100 
  OR brief LIKE '%?'
  OR brief LIKE '%aren''t we%'
  OR brief LIKE '%show the%';

-- For these, brief is likely corrupted. Manual review needed.
```

This is for diagnostics only. Existing missions with corrupted briefs 
won't be auto-fixed (data loss).

### Acceptance test

```
Test 1 — Brief set once, never overwritten:
  1. Create mission, send substantive Mistral brief
  2. Verify Mission.brief in DB matches Mistral brief
  3. Send "Approved"
  4. Verify Mission.brief UNCHANGED
  5. Send "what's the verdict?"
  6. Verify Mission.brief STILL UNCHANGED

Test 2 — Clarification answers go to right field:
  1. Create mission, send thin brief "should we acquire X?"
  2. System asks clarification questions
  3. User answers
  4. Verify Mission.brief = original thin brief
  5. Verify Mission.clarification_answers = [answer1, answer2]

Test 3 — Frozen brief enforcement:
  1. Try to call store.update_mission_brief() twice
  2. Second call must be no-op with warning logged
```

---

## BUG 3 — System nodes show as "AGENT" (UX)

### Symptom

In the live feed:
```
AGENT     Gate pending · Confirm initial hypotheses
AGENT     Deliverable ready · framing memo
AGENT     Deliverable ready · Engagement brief
MARVIN    MARVIN started
```

The "AGENT" lines are unattributed. User cannot identify who 
produced them.

### Root cause

In `marvin_ui/server.py`, the `_DISPLAY_NAME` mapping covers main 
agents but not system nodes:
- `framing_orchestrator` → not mapped → fallback "AGENT"
- `papyrus_phase0` → maybe mapped as "Papyrus" but inconsistent
- `gate_node` → not mapped → "AGENT"
- `research_join` → not mapped → "AGENT"

### Fix

Update `_DISPLAY_NAME` mapping in `marvin_ui/server.py`:

```python
_DISPLAY_NAME = {
    # Main agents
    "dora": "Dora",
    "calculus": "Calculus",
    "adversus": "Adversus",
    "merlin": "Merlin",
    
    # Orchestration
    "orchestrator": "MARVIN",
    "orchestrator_qa": "MARVIN",
    "framing_orchestrator": "MARVIN",
    
    # Document agents
    "papyrus_phase0": "Papyrus",
    "papyrus_delivery": "Papyrus",
    
    # System nodes — DON'T emit (skip in event filter)
    "gate_node": None,
    "phase_router": None,
    "research_join": None,
    "synthesis_critic": "Merlin",  # alias
}

def get_display_name(node_name: str) -> str | None:
    """Return display name, or None to skip the event."""
    return _DISPLAY_NAME.get(node_name, node_name.title())
```

In the event emission code, skip events where display_name is None:

```python
display = get_display_name(node_name)
if display is None:
    return  # Don't emit this event
yield _sse({"agent": display, ...})
```

### Acceptance test

```
Test: send Mistral brief, observe live feed.
  ✓ Every line has a real agent name (Dora, Calculus, Adversus, 
    Merlin, MARVIN, Papyrus)
  ✓ NO line shows "AGENT" generic label
  ✓ Casing is consistent (Title Case throughout)
  ✓ Internal nodes (gate_node, phase_router, research_join) 
    don't appear in feed at all
```

---

## BUG 4 — Hypothesis IDs in user-facing text (UX)

### Symptom

In the chat:
```
"Weakest link: hyp-85a6485f"
"hypothesis_id: hyp-b17b2f3e"
```

User cannot identify which hypothesis is being referenced.

### Root cause

Adversus and Merlin prompts reference hypotheses by `hypothesis_id` 
(the DB UUID) instead of by display label (H1/H2/H3).

### Fix

**Part 1 — Add display labels in DB**

When hypotheses are persisted in `_generate_hypotheses_inline`, 
add a `label` field:

```python
for idx, hyp_text in enumerate(generated_hypotheses, start=1):
    hyp = Hypothesis(
        id=f"hyp-{uuid4().hex[:8]}",
        label=f"H{idx}",  # ← add this
        mission_id=mission_id,
        text=hyp_text,
        status="active",
    )
    store.save_hypothesis(hyp)
```

Schema migration `007_add_hypothesis_label.sql`:

```sql
ALTER TABLE hypotheses ADD COLUMN label TEXT;
-- Backfill for existing data:
UPDATE hypotheses 
SET label = 'H' || (
    SELECT COUNT(*) FROM hypotheses h2 
    WHERE h2.mission_id = hypotheses.mission_id 
      AND h2.id <= hypotheses.id
)
WHERE label IS NULL;
```

**Part 2 — Update tools to return label**

`get_hypotheses` tool returns:
```python
{
    "id": h.id,
    "label": h.label,  # ← H1, H2, H3...
    "text": h.text,
    "status": h.status,
    ...
}
```

**Part 3 — Update agent prompts**

In `adversus.md`:
```
When referencing hypotheses in your output, ALWAYS use the label 
(H1, H2, etc.), NEVER the raw ID.

WRONG: "Weakest link: hyp-85a6485f"
RIGHT: "Weakest link: H1 (Mistral's differentiating capabilities...)"

When calling save_finding, the hypothesis_id field uses the DB id.
But your text/output to the user uses the label.
```

Same update in `merlin.md`, `dora.md`, `calculus.md`.

### Acceptance test

```
Test: Mistral mission run.
  ✓ Adversus output: "Weakest link: H1 (Mistral's differentiating...)"
  ✓ Merlin verdict: "Load-bearing claims H1 and H3 lack KNOWN..."
  ✓ NO occurrence of "hyp-XXXXX" in chat or workstream reports
  ✓ DB still uses UUID for hypothesis_id (foreign keys intact)
```

---

## BUG 5 — Inconsistent agent name casing (UX)

### Symptom

```
DORA finished       (uppercase)
Dora                (Title Case)
dora                (lowercase)
calculus            (lowercase)
```

Three different presentations for the same agent.

### Root cause

Different parts of the code emit agent names with different casing:
- Backend stores `agent_id` in lowercase
- Some SSE events use raw agent_id
- Some prompts mention "DORA" in ALL CAPS
- Frontend doesn't normalize

### Fix

**Part 1 — Normalize at emission point**

In `server.py`, ALL agent name emissions go through `get_display_name()` 
(from Bug 3 fix). This guarantees Title Case everywhere.

**Part 2 — Frontend safety net**

In components/marvin/MissionControl.tsx, add a normalization helper:

```typescript
function normalizeAgentName(raw: string): string {
  const map: Record<string, string> = {
    "dora": "Dora",
    "calculus": "Calculus", 
    "adversus": "Adversus",
    "merlin": "Merlin",
    "marvin": "MARVIN",  // exception: MARVIN stays uppercase
    "papyrus": "Papyrus",
  };
  const lower = raw.toLowerCase();
  return map[lower] || raw;
}
```

Apply in all rendering code that displays agent names.

### Acceptance test

```
Test: Mistral mission, scan all UI text for agent names.
  ✓ Every occurrence of Dora is "Dora" (not DORA, not dora)
  ✓ Every occurrence of MARVIN is "MARVIN" (special case: ALL CAPS)
  ✓ Calculus, Adversus, Merlin, Papyrus all in Title Case
```

---

## BUG 6 — No circuit breaker on terminal agent state

### Symptom

Adversus hits cap (12/12 findings). Then:
- Merlin re-runs verdict (same input, same output)
- Adversus re-attempted (returns "cannot comply")
- Merlin re-runs verdict again
- ... up to retry limit

Result: chat saturated with duplicate messages, tokens burned, 
mission stalls without producing new value.

### Root cause

Synthesis retry logic in `phase_router` triggers Adversus → Merlin 
loop without checking if anything has changed since last verdict.

### Fix

**Part 1 — Track verdict state**

In MarvinState:
```python
class MarvinState(TypedDict):
    # ... existing ...
    last_verdict_at_finding_count: Annotated[int, last_value]
    synthesis_retry_count: Annotated[int, last_value]
```

**Part 2 — Add no-change detection in retry decision**

In `phase_router`, when handling synthesis retry:

```python
if phase == "redteam_done":
    mid = state["mission_id"]
    findings = store.list_findings(mid)
    current_finding_count = len(findings)
    last_count = state.get("last_verdict_at_finding_count", 0)
    retry_count = state.get("synthesis_retry_count", 0)
    
    # Get latest verdict
    verdict = store.get_latest_merlin_verdict(mid)
    
    if verdict and verdict["verdict"] in ["MINOR_FIXES", "BACK_TO_DRAWING_BOARD"]:
        # Want to retry?
        
        # Circuit breaker 1: max 3 retries
        if retry_count >= 3:
            return [{"phase": "synthesis_done", 
                     "forced_advance": True}]
        
        # Circuit breaker 2: no new findings since last verdict
        if current_finding_count == last_count:
            return [{"phase": "synthesis_done",
                     "forced_advance": True,
                     "force_reason": "no_new_findings"}]
        
        # Circuit breaker 3: any agent has hit terminal state
        adversus_findings = [f for f in findings if f.agent_id == "adversus"]
        if len(adversus_findings) >= 12:  # cap reached
            return [{"phase": "synthesis_done",
                     "forced_advance": True,
                     "force_reason": "adversus_cap_reached"}]
        
        # OK to retry
        return [
            Send("adversus", state),
            {"synthesis_retry_count": retry_count + 1,
             "last_verdict_at_finding_count": current_finding_count}
        ]
    
    # SHIP verdict — proceed
    return [{"phase": "synthesis_done"}]
```

**Part 3 — Surface forced advance to user**

When `forced_advance` is True, MARVIN should say in chat (once):
```
"Synthesis advanced after {force_reason}. 
G3 ready with current verdict: {verdict}."
```

Not a panic. Just a transparent statement of what happened.

### Acceptance test

```
Test 1: cap-reached scenario
  1. Run mission, force Adversus to hit cap on first run
  2. Merlin issues MINOR_FIXES verdict
  3. Verify: synthesis ADVANCES (does not retry)
  4. Verify: G3 fires with note "advanced after adversus_cap_reached"
  5. Verify: NO duplicate Adversus run
  6. Verify: NO duplicate Merlin verdict

Test 2: no-change scenario
  1. Mission with Merlin issuing MINOR_FIXES
  2. Mock Adversus retry producing 0 new findings
  3. Verify: second retry skipped
  4. Verify: synthesis advances forced

Test 3: legitimate retry
  1. Mission with Merlin MINOR_FIXES
  2. Mock Adversus retry producing 2 new findings
  3. Verify: Merlin re-runs verdict
  4. If still MINOR_FIXES with new content, allow up to 3 retries
```

---

## OUT OF SCOPE — DEFER TO LATER CHANTIERS

These problems were identified but are NOT fixed in this chantier:

```
P3  — No proof of work visible        → Chantier 4 (live narration)
P7  — No answer to IC question        → Chantier 5 (Answer Memo)
P8  — Workstream tabs passive         → Chantier 4 (UI editorial)
P9  — No mission timeline             → Chantier 4
P11 — Hypotheses hidden in modal      → Chantier 4 (HypothesisPanel)
P12 — Findings flat, no hierarchy     → Chantier 4 (impact field)
P13 — Deliverables no preview         → Chantier 4 (DeliverablePreview)
P14 — No pre-flight feasibility check → New mini-chantier later
```

This chantier is strictly bug fixes. UI overhaul comes in Chantier 4.

---

## OVERALL ACCEPTANCE FOR CHANTIER 2.5

```
Run Mistral brief end-to-end. Then test:

1. Brief preserved
   ✓ Mission.brief in DB matches the original Mistral brief text
   ✓ framing_memo.md shows correct brief in "Raw Brief" section

2. No replay
   ✓ Send "Approved" without clicking gate → MARVIN responds 
     in 1 sentence, no agent re-runs
   ✓ Send "what's the verdict?" → 1-sentence answer
   ✓ Send "show me the memo" → 1-sentence pointer to deliverables
   ✓ Chat does NOT contain duplicate verdicts

3. Clean attribution
   ✓ Live feed: every line has a real agent name
   ✓ NO "AGENT" generic label anywhere
   ✓ All agents Title Case (Dora, not DORA or dora)
   ✓ MARVIN stays ALL CAPS

4. Hypothesis labels
   ✓ Chat references "H1", "H2", "H3" — never "hyp-XXXXX"
   ✓ Workstream reports use H-labels
   ✓ DB still uses UUID internally (foreign keys intact)

5. Circuit breaker
   ✓ Cap-reached scenario does NOT cause retry loop
   ✓ No-new-findings scenario forces advance
   ✓ Max 3 retries enforced
   ✓ Forced advance is transparent to user (one message)

6. Tests
   ✓ pytest 0 failures (existing 209 + new tests for each bug)
   ✓ npm run test 0 failures
   ✓ tsc --noEmit clean
```

---

## REVERT STRATEGY

Each bug fix is on a separate commit:
- Commit 1: Fix Bug 1 (replay)
- Commit 2: Fix Bug 2 (brief overwrite)
- Commit 3: Fix Bug 3 (display names)
- Commit 4: Fix Bug 4 (hypothesis labels)
- Commit 5: Fix Bug 5 (casing)
- Commit 6: Fix Bug 6 (circuit breaker)

Reverting any single commit returns to pre-fix behavior for that 
specific bug. Recommend reverting in reverse order if multiple 
issues arise.

After any revert:
```bash
pytest tests/ -q
npm run test
# Manual: Mistral brief end-to-end, verify no regression
```

---

## REPORTING TEMPLATE

After Chantier 2.5:

```
## Chantier 2.5 Status

### Bug 1 — Mission replay
- [ ] PASS / FAIL
- Mistral test: send "Approved" → no replay observed
- Notes:

### Bug 2 — Brief overwrite
- [ ] PASS / FAIL
- DB check: Mission.brief preserved across messages
- Notes:

### Bug 3 — Display names
- [ ] PASS / FAIL
- Live feed inspection: all attributed
- Notes:

### Bug 4 — Hypothesis labels
- [ ] PASS / FAIL
- Chat scan: H1/H2 used, no UUID
- Notes:

### Bug 5 — Casing
- [ ] PASS / FAIL
- All agents Title Case
- Notes:

### Bug 6 — Circuit breaker
- [ ] PASS / FAIL
- Cap scenario: no retry loop
- No-change scenario: forced advance
- Notes:

### Regression
- [ ] All Chantier 1, 1.5, 2 Part A acceptance still pass
- [ ] pytest 0 failures
- [ ] npm test 0 failures

### Tech debt added
- ...

Awaiting approval to proceed with Chantier 4 (UI revamp).
```
