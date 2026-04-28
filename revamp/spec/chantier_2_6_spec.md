# CHANTIER 2.6 — Finding Quality Gates
*Insert between Chantier 2.5 and Chantier 4*
*Estimated time: 1-2 days*
*Risk: Low (additive validation, no flow changes)*

---

## WHY THIS CHANTIER EXISTS

Live testing on Mistral after Chantier 2.5 revealed that the 
system accepts and persists absurd findings as legitimate analysis:

```
Finding logged by Calculus (REASONED confidence):
  "LTV/CAC ratio is 0.00x (CAC $0, LTV $0)"
  "Adjusted EBITDA is 0.00 (revenue 0.0, cogs 0.0, opex 0.0, 
   add-backs 0.0) [missing inputs: revenue, cogs, opex, 
   add_backs]"
```

These are not findings. They are math operations on missing data. 
The system persisted them with REASONED confidence and surfaced 
them in the manager review gate as if they were legitimate claims.

This is a regression of the same class of bug seen on Vinted 
(Calculus produced 0 findings because target was private). The 
system has no quality gate on what gets persisted.

Additional issues observed:
- Findings persisted without valid hypothesis_id linking
- No pre-flight check on data availability before agent runs
- Gate validation throws 409 errors on legitimate user actions
- MARVIN Q&A doesn't read findings before answering questions
- Workstream tabs show meta-events instead of finding content

This chantier adds quality gates and content-driven displays 
without changing the flow architecture. After this, Chantier 4 
can build UI on findings that are actually meaningful.

---

## SHARED PRINCIPLES

```
1. Quality at write time, not display time.
   - Reject absurd findings before they enter DB
   - Force LOW_CONFIDENCE when data is missing
   - Don't let agents claim KNOWN/REASONED on empty inputs

2. Pre-flight before parallelism.
   - Check data availability before launching agents
   - Surface "we won't find financials" early, not at G1
   - Let user decide: proceed qualitatively or load data room

3. Q&A reads from DB, not from memory.
   - MARVIN must call get_findings before answering
   - Reference findings by content, not by count
   - Never invent agent attribution (e.g., "Merlin logged findings")

4. UI shows findings, not events.
   - Workstream tabs display persisted findings from DB
   - Meta-events (step complete, milestone delivered) go in live feed
   - Two distinct channels, no mixing
```

---

## BUG 1 — Absurd findings accepted as REASONED (CRITICAL)

### Symptom

Calculus persisted findings with REASONED confidence even though:
- All numeric inputs were 0 or missing
- The claim text explicitly stated "[missing inputs: ...]"
- The "computation" was math on empty values

In the gate review modal:
```
RECENT CLAIMS (SHOWING 2 OF 2)
  • LTV/CAC ratio is 0.00x (CAC $0, LTV $0)  calculus · REASONED
  • Adjusted EBITDA is 0.00 (revenue 0.0, cogs 0.0, opex 0.0, 
    add-backs 0.0) [missing inputs: revenue, cogs, opex, 
    add_backs]  calculus · REASONED
```

These are unusable. They falsely signal "real analysis happened" 
to the user.

### Root cause

`add_finding_to_mission` accepts any string as `claim_text` and 
any value as `confidence`. There's no validator on the relationship 
between content and confidence level.

### Fix

Add a `validate_finding_quality()` function in `marvin/tools/mission_tools.py`:

```python
import re
from typing import Tuple

# Patterns that indicate empty / missing data masquerading as findings
ABSURD_PATTERNS = [
    # Numeric values all zero
    (r"\$0[^\d]", "all-zero dollar values"),
    (r"\$0\.00", "zero-dollar value"),
    (r"\b0\.0+\b", "zero numeric value"),
    (r"\b0\.00x\b", "zero ratio"),
    
    # Explicit missing data declarations
    (r"\[missing inputs:", "explicit missing inputs"),
    (r"missing inputs:", "missing inputs declaration"),
    (r"cannot be verified", "verification failure"),
    (r"unable to extract", "extraction failure"),
    (r"data not available", "data unavailability"),
    (r"no usable .* found", "no usable data"),
    (r"placeholder", "placeholder data"),
    (r"non-extractable", "non-extractable data"),
]

def validate_finding_quality(
    claim_text: str, 
    confidence: str
) -> Tuple[bool, str | None, str | None]:
    """
    Returns (is_valid, suggested_confidence, rejection_reason).
    
    If finding is absurd: (False, None, reason)
    If finding should be downgraded: (True, "LOW_CONFIDENCE", reason)
    If finding is fine: (True, None, None)
    """
    
    if not claim_text or len(claim_text.strip()) < 20:
        return False, None, "Claim text too short (<20 chars)"
    
    # Detect absurd patterns
    detected = []
    for pattern, label in ABSURD_PATTERNS:
        if re.search(pattern, claim_text, re.IGNORECASE):
            detected.append(label)
    
    if not detected:
        return True, None, None
    
    # Findings with absurd patterns CANNOT be KNOWN or REASONED
    if confidence in ["KNOWN", "REASONED"]:
        if len(detected) >= 2:
            # Multiple absurd patterns → reject entirely
            return False, None, (
                f"Finding rejected: claim contains "
                f"{', '.join(detected)} but is marked {confidence}. "
                f"Findings on missing/zero data must be LOW_CONFIDENCE "
                f"or not persisted at all."
            )
        else:
            # Single pattern → downgrade to LOW_CONFIDENCE
            return True, "LOW_CONFIDENCE", (
                f"Confidence downgraded to LOW_CONFIDENCE because "
                f"claim contains {detected[0]}."
            )
    
    return True, None, None


def add_finding_to_mission(state, ...):
    """Existing function, with new validation."""
    
    # ... existing code ...
    
    # NEW: validate quality before persist
    is_valid, suggested_conf, reason = validate_finding_quality(
        claim_text, confidence
    )
    
    if not is_valid:
        return {
            "status": "rejected",
            "reason": reason,
            "guidance": (
                "If you don't have data to make a claim, don't fabricate "
                "one. Either skip this hypothesis, or write a finding "
                "explicitly stating what data is missing using "
                "LOW_CONFIDENCE. Do not pad with zero values."
            )
        }
    
    if suggested_conf and suggested_conf != confidence:
        confidence = suggested_conf
        # Append note to claim text
        claim_text += f" [confidence auto-adjusted: {reason}]"
    
    # ... rest of existing persist logic ...
```

Update agent prompts to acknowledge this guard rail:

In `calculus.md`, add to the OUTPUTS section:
```
SYSTEM-LEVEL QUALITY GUARD

The system validates findings before persisting. If you submit:
- A claim where all numeric inputs are 0 or missing → REJECTED
- A claim with "[missing inputs: ...]" + REASONED confidence → REJECTED
- A claim that says "cannot be verified" + REASONED → DOWNGRADED to LOW_CONFIDENCE

If you have insufficient data to make a real claim:
  Option A: Skip the hypothesis entirely. Don't fabricate a finding.
  Option B: Submit a finding explicitly describing what data is 
           missing, with LOW_CONFIDENCE.

Example of REJECTED:
  "Adjusted EBITDA is 0.00 (revenue 0.0, cogs 0.0)" — REASONED

Example of ACCEPTED (alternative):
  "Adjusted EBITDA cannot be computed — Mistral is private, 
   no audited financials available, no data room provided." 
  — LOW_CONFIDENCE
```

Same updates in `dora.md` and `adversus.md`.

### Acceptance test

```python
def test_absurd_finding_rejected_when_reasoned():
    """All-zero finding marked REASONED is rejected."""
    result = add_finding_to_mission(
        state={"mission_id": "m-test"},
        claim_text="LTV/CAC ratio is 0.00x (CAC $0, LTV $0)",
        confidence="REASONED",
        hypothesis_id="hyp-1",
        agent_id="calculus",
    )
    assert result["status"] == "rejected"
    assert "missing" in result["reason"].lower() or \
           "zero" in result["reason"].lower()


def test_partial_zero_finding_downgraded_to_low_confidence():
    """Single absurd pattern → downgrade, not reject."""
    result = add_finding_to_mission(
        state={"mission_id": "m-test"},
        claim_text="Cannot be verified due to placeholder URLs",
        confidence="REASONED",
        hypothesis_id="hyp-1",
        agent_id="calculus",
    )
    # Should succeed but with LOW_CONFIDENCE
    assert result["status"] != "rejected"
    # Read back from DB and verify
    findings = list_findings("m-test")
    assert findings[-1].confidence == "LOW_CONFIDENCE"


def test_legitimate_finding_passes():
    """Real finding with sourced data passes through."""
    result = add_finding_to_mission(
        state={"mission_id": "m-test"},
        claim_text=(
            "Mistral's enterprise contracts show 12-month minimum "
            "commitments with 87% renewal rate based on Q3 2024 "
            "investor disclosure."
        ),
        confidence="REASONED",
        hypothesis_id="hyp-1",
        agent_id="calculus",
    )
    assert result["status"] != "rejected"
```

---

## BUG 2 — Findings without hypothesis_id (DATA INTEGRITY)

### Symptom

The Mistral findings panel showed 2 findings ("LTV/CAC", "Adjusted 
EBITDA") that didn't appear linked to any hypothesis in the chat 
or in the gate modal. They surfaced as orphan findings.

### Root cause

`add_finding_to_mission` accepts `hypothesis_id=None` or invalid 
hypothesis_id without validation.

### Fix

In `add_finding_to_mission`:

```python
def add_finding_to_mission(
    state, 
    claim_text: str,
    confidence: str,
    hypothesis_id: str,  # required
    agent_id: str,
    # ... other params
):
    mid = require_mission_id(state)
    store = MissionStore()
    
    # Validate hypothesis_id is real and active
    if not hypothesis_id:
        return {
            "status": "rejected",
            "reason": "hypothesis_id is required",
            "guidance": (
                "Every finding must link to an active hypothesis. "
                "Call get_hypotheses() to see active hypotheses, "
                "then pick the one your finding addresses by id."
            )
        }
    
    hypotheses = store.list_hypotheses(mid)
    matching = [h for h in hypotheses if h.id == hypothesis_id]
    
    if not matching:
        active_ids = [
            f"{h.label}={h.id}" 
            for h in hypotheses if h.status == "active"
        ]
        return {
            "status": "rejected",
            "reason": f"hypothesis_id '{hypothesis_id}' not found",
            "guidance": (
                f"Active hypotheses: {active_ids}. "
                f"Use one of these IDs."
            )
        }
    
    if matching[0].status != "active":
        return {
            "status": "rejected",
            "reason": (
                f"Hypothesis {hypothesis_id} is "
                f"{matching[0].status}, not active"
            ),
        }
    
    # ... continue with persist
```

Update agent prompts to reflect that linking is mandatory:

```
EVERY finding MUST link to an active hypothesis.

Step 1: Call get_hypotheses() at start of your work.
Step 2: For each finding, identify which hypothesis it addresses.
Step 3: Use that hypothesis's id (not label) when calling 
        add_finding_to_mission.

If a finding doesn't naturally link to any hypothesis, it's not 
a finding — it's noise. Drop it.
```

### Acceptance test

```python
def test_finding_without_hypothesis_rejected():
    result = add_finding_to_mission(
        state={"mission_id": "m-test"},
        claim_text="Some legitimate claim with real data and sourcing.",
        confidence="KNOWN",
        hypothesis_id=None,
        agent_id="calculus",
    )
    assert result["status"] == "rejected"
    assert "hypothesis_id" in result["reason"]


def test_finding_with_invalid_hypothesis_rejected():
    result = add_finding_to_mission(
        state={"mission_id": "m-test"},
        claim_text="Real claim about real data with sourcing.",
        confidence="KNOWN",
        hypothesis_id="hyp-doesnotexist",
        agent_id="calculus",
    )
    assert result["status"] == "rejected"
    assert "not found" in result["reason"]


def test_finding_with_abandoned_hypothesis_rejected():
    """If hypothesis was abandoned (e.g. via pivot), reject."""
    # Setup: create hypothesis with status='abandoned'
    # ...
    result = add_finding_to_mission(
        state={"mission_id": "m-test"},
        claim_text="Real claim",
        confidence="KNOWN",
        hypothesis_id="hyp-abandoned",
        agent_id="calculus",
    )
    assert result["status"] == "rejected"
```

---

## BUG 3 — No pre-flight check on data availability (UX)

### Symptom

For Mistral (private European LLM provider), Calculus tried to 
search SEC filings, found nothing usable, and produced absurd 
findings rather than failing fast.

The user only learned this at G1 manager review, after wasted 
agent runs.

### Root cause

`phase_router` launches Calculus in parallel with Dora regardless 
of whether the target has accessible financial data. No upfront 
check.

### Fix

Add `_check_data_availability` before launching financial workstream:

```python
def _check_data_availability(mission_id: str) -> dict:
    """Pre-flight check before launching Calculus.
    
    Returns:
      {
        "calculus_viable": bool,
        "reason": str,
        "recommendation": str,
      }
    """
    store = MissionStore()
    mission = store.get_mission(mission_id)
    
    target = (mission.target or "").lower().strip()
    if not target:
        return {
            "calculus_viable": False,
            "reason": "no target specified",
            "recommendation": "Cannot run financial analysis without target.",
        }
    
    # Heuristic 1: known private companies / non-US
    # In production, use a proper SEC EDGAR check
    KNOWN_PRIVATE_KEYWORDS = [
        "mistral", "cursor", "anthropic", "openai", "perplexity",
        "vinted", "doctolib", "exotec", "stripe", "spacex",
    ]
    
    is_likely_private = any(
        kw in target for kw in KNOWN_PRIVATE_KEYWORDS
    )
    
    has_data_room = mission.data_room_path is not None
    
    if is_likely_private and not has_data_room:
        return {
            "calculus_viable": False,
            "reason": (
                f"{mission.target} appears private/non-US — "
                f"SEC filings unlikely to have material content"
            ),
            "recommendation": (
                "Skip W2 financial analysis or request data room. "
                "Calculus will produce LOW_CONFIDENCE findings only."
            ),
        }
    
    return {
        "calculus_viable": True,
        "reason": "data sources available",
        "recommendation": "proceed",
    }
```

Add a phase before research kickoff in `phase_router`:

```python
if phase == "confirmed":
    # Pre-flight check before launching parallel research
    mid = state["mission_id"]
    check = _check_data_availability(mid)
    
    if not check["calculus_viable"]:
        # Fire a clarification-style gate
        questions = [{
            "question": (
                f"Calculus cannot run financial analysis: "
                f"{check['reason']}. How should we proceed?"
            ),
            "options": [
                {
                    "value": "skip_calculus",
                    "label": "Skip W2 — qualitative analysis only",
                    "consequence": (
                        "Calculus is not run. W2 findings panel "
                        "stays empty. Diligence focuses on market "
                        "and competitive analysis."
                    ),
                },
                {
                    "value": "proceed_low_confidence",
                    "label": "Proceed — accept LOW_CONFIDENCE only",
                    "consequence": (
                        "Calculus runs but cannot produce KNOWN findings. "
                        "All financial claims will be LOW_CONFIDENCE."
                    ),
                },
                {
                    "value": "request_data_room",
                    "label": "Pause — I'll provide a data room",
                    "consequence": (
                        "Mission pauses. Add data room files via UI, "
                        "then resume."
                    ),
                },
            ]
        }]
        
        # Create a real gate (consistent with clarification gate pattern)
        gate_id = f"gate-{mid}-data-availability"
        # ... create gate row, route to gate node
        return [Send("gate", {
            **state, 
            "pending_gate_id": gate_id,
            "phase": "awaiting_data_decision",
        })]
    
    # Normal flow: launch parallel research
    return [Send("dora", state), Send("calculus", state)]
```

Add migration `008_data_room_path.sql`:
```sql
ALTER TABLE missions ADD COLUMN data_room_path TEXT;
```

### Acceptance test

```python
def test_private_target_triggers_data_check():
    mid = create_mission(target="Mistral AI")
    state = {"mission_id": mid, "phase": "confirmed"}
    
    routes = phase_router(state)
    
    # Should fire data-availability gate, not launch agents
    assert any(
        getattr(r, "phase", None) == "awaiting_data_decision"
        for r in routes
    )


def test_public_target_skips_data_check():
    mid = create_mission(target="Microsoft")
    state = {"mission_id": mid, "phase": "confirmed"}
    
    routes = phase_router(state)
    
    # Should launch dora + calculus directly
    sends = [r for r in routes if hasattr(r, 'node')]
    nodes = [s.node for s in sends]
    assert "dora" in nodes
    assert "calculus" in nodes


def test_data_check_skip_calculus_decision():
    """User chooses 'skip Calculus' → mission proceeds without W2."""
    # ... setup mission, hit data check gate
    # User submits decision = "skip_calculus"
    # Verify Calculus never runs, W1 (Dora) launches, mission proceeds
```

---

## BUG 4 — Gate validation 409 conflict (BUG)

### Symptom

```
Console error: Failed to validate gate: 409
File: lib/missions/api.ts (371:11) @ validateGate
```

User clicked "Reject" on G1, backend returned 409 Conflict.

### Root cause

The gate may have been in a non-rejectable state (already completed, 
already in transition, or double-clicked).

### Fix

In `marvin_ui/server.py`, the `validate_gate` endpoint:

```python
@router.post("/api/v1/missions/{mission_id}/gates/{gate_id}/validate")
async def validate_gate(
    mission_id: str, 
    gate_id: str, 
    body: GateValidationRequest
):
    store = MissionStore()
    gate = store.get_gate(gate_id)
    
    if not gate:
        raise HTTPException(404, "Gate not found")
    
    if gate.mission_id != mission_id:
        raise HTTPException(403, "Gate does not belong to mission")
    
    # Idempotency: if gate is already in target state, return success
    if gate.status == "completed" and body.verdict in ["APPROVED", "REJECTED"]:
        existing_verdict = gate.metadata.get("verdict")
        if existing_verdict == body.verdict:
            # User clicked the same button twice → idempotent success
            return {
                "gate_id": gate_id,
                "status": "completed",
                "verdict": existing_verdict,
                "idempotent": True,
                "message": "Gate already validated with this verdict",
            }
        else:
            # Conflicting verdict — but user-facing error, not 409
            return {
                "gate_id": gate_id,
                "status": "completed",
                "verdict": existing_verdict,
                "conflict": True,
                "message": (
                    f"Gate already completed with verdict "
                    f"'{existing_verdict}'. Cannot change after completion."
                ),
            }
    
    if gate.status not in ["pending", "in_review"]:
        raise HTTPException(400, (
            f"Gate in non-validatable state: {gate.status}"
        ))
    
    # ... existing validation logic
```

Update frontend `lib/missions/api.ts`:

```typescript
export async function validateGate(
  missionId: string, 
  gateId: string, 
  payload: GateValidationPayload
): Promise<GateValidationResponse> {
  const response = await fetch(...);
  
  if (response.status === 409) {
    // 409 should not happen anymore with idempotent backend
    // But handle gracefully if it does
    const body = await response.json().catch(() => ({}));
    return {
      idempotent: true,
      message: body.message || "Gate already validated",
      ...body,
    };
  }
  
  if (!response.ok) {
    if (response.status === 503) {
      throw new BackendOfflineError();
    }
    const body = await response.json().catch(() => ({}));
    // Don't throw — surface the message to user
    return {
      error: true,
      message: body.detail || `Gate validation failed (${response.status})`,
      ...body,
    };
  }
  
  return await response.json();
}
```

In MissionControl, handle the response gracefully:

```typescript
const result = await validateGate(missionId, gateId, { verdict });

if (result.idempotent) {
  // Show subtle toast: "Gate was already validated"
  showToast("Gate already validated", { variant: "info" });
  return;
}

if (result.error) {
  showToast(result.message, { variant: "warning" });
  return;
}

// Normal success path
```

### Acceptance test

```python
def test_double_click_gate_approve_idempotent():
    """Clicking approve twice returns success, not 409."""
    gate_id = create_pending_gate()
    
    # First approve
    r1 = validate_gate(gate_id, verdict="APPROVED")
    assert r1.status_code == 200
    
    # Second approve (same verdict)
    r2 = validate_gate(gate_id, verdict="APPROVED")
    assert r2.status_code == 200
    body = r2.json()
    assert body["idempotent"] is True


def test_change_verdict_after_complete_returns_conflict_message():
    """Approving then trying to reject returns user-facing message."""
    gate_id = create_pending_gate()
    validate_gate(gate_id, verdict="APPROVED")
    
    r = validate_gate(gate_id, verdict="REJECTED")
    assert r.status_code == 200  # Not 409
    body = r.json()
    assert body["conflict"] is True
    assert "already completed" in body["message"]
```

---

## BUG 5 — MARVIN Q&A doesn't read findings (UX)

### Symptom

User: "no i want to understand what to do, the claims aren't good"

MARVIN: "Final review (G3) is pending. What would you like to 
focus on: the 2 logged findings, one of the 4 active hypotheses, 
or why the claims are being rated poorly?"

MARVIN didn't read the findings. It only knew the count.

Worse: MARVIN said "Merlin currently has no verdict yet, with 2 
logged findings" — but Merlin doesn't log findings. Calculus did. 
MARVIN invented attribution.

### Root cause

`orchestrator_qa` system prompt doesn't enforce reading findings 
before answering questions about them.

### Fix

Update `orchestrator.md` Q&A section:

```
## Q&A mode rules

When user asks ANY question about findings, claims, or analysis 
quality, you MUST:

Step 1: Call get_findings() to see what was actually persisted.
Step 2: Call get_hypotheses() to know hypothesis labels (H1, H2...).
Step 3: Reference findings by content, not by count.
Step 4: Attribute findings to the correct agent (look at agent_id).

CORRECT Q&A:
User: "why are the claims poor?"
You: "Calculus persisted 2 findings, both showing zero values 
     because Mistral is private and SEC data isn't accessible. 
     LTV/CAC = 0 and Adjusted EBITDA = 0 because all inputs are 
     missing. These should be LOW_CONFIDENCE, not REASONED."

WRONG Q&A:
User: "why are the claims poor?"
You: "Final review (G3) is pending. Merlin has logged 2 findings 
     and there are 4 active hypotheses, but no verdict yet."
     
This wrong response:
- Doesn't read the findings
- Wrongly attributes findings to Merlin (Merlin doesn't log findings)
- Doesn't address the user's actual concern

If user asks about agent attribution:
- Dora: market and competitive findings (W1)
- Calculus: financial findings (W2)
- Adversus: counter-findings (W4)
- Merlin: verdict (no findings)
- Papyrus: deliverables (no findings)

Never invent attribution. Always check agent_id from get_findings().
```

Add explicit examples in the prompt covering common Q&A patterns:

```
EXAMPLE Q&A patterns:

"What's the verdict?"
→ Call get_merlin_verdict()
→ "Merlin's verdict is {verdict}: {one-line reasoning}."

"Why are findings weak?"
→ Call get_findings()
→ Identify low-confidence or absurd findings
→ "Calculus has 2 LOW_CONFIDENCE findings due to {specific reason}. 
   No KNOWN findings persisted. The thesis is fragile because..."

"What should we do?"
→ Look at current phase + findings state
→ "Reject G1, request data room for {target}. Without primary 
   financial data, Calculus produces only stub findings."

"Show me the memo"
→ Call get_deliverables()
→ "Deliverables: {list}. Click Open on any to download."
```

### Acceptance test

```python
def test_qa_reads_findings_before_answering():
    """When user asks about claims, orchestrator_qa calls get_findings."""
    # Setup mission with 2 findings
    # Trigger QA mode with user message "why are claims poor?"
    
    # Assert: get_findings was called in the trace
    # Assert: response mentions specific finding content
    # Assert: response doesn't invent attribution


def test_qa_correct_agent_attribution():
    """QA never says 'Merlin logged findings' since Merlin doesn't."""
    # Setup mission with Calculus findings
    # User asks: "who logged the findings?"
    
    response = qa_response("who logged the findings?")
    
    assert "Calculus" in response
    assert "Merlin logged" not in response
    assert "Merlin has logged" not in response
```

---

## BUG 6 — Workstream tabs show meta-events instead of findings (UX)

### Symptom

The "Market and Competitive Analysis" tab showed:
```
DORA  ✓ delivered
DORA  Dora → mark milestone delivered
DORA  ✓ delivered
DORA  Dora → mark milestone delivered
DORA  step complete
DORA  Dora → run pestel
DORA  step complete
```

These are workflow events, not findings. The user wanted to see:
"What did Dora actually find about the market?"

### Root cause

The workstream tab content is fed by SSE events (which include 
meta-events like step_complete, milestone_delivered) instead of 
reading findings from DB.

### Fix

In `components/marvin/MissionControl.tsx`, add a new endpoint and 
a new data source for workstream content:

**Backend new endpoint:**

```python
@router.get("/api/v1/missions/{mission_id}/workstreams/{ws_id}/findings")
async def get_workstream_findings(mission_id: str, ws_id: str):
    """Returns findings grouped by workstream for display in tabs."""
    
    store = MissionStore()
    findings = store.list_findings(mission_id)
    
    # Map workstream → findings
    # W1 = Dora, W2 = Calculus, W4 = Adversus
    AGENT_TO_WORKSTREAM = {
        "dora": "W1",
        "calculus": "W2",
        "adversus": "W4",
    }
    
    workstream_findings = [
        f for f in findings 
        if AGENT_TO_WORKSTREAM.get(f.agent_id) == ws_id
    ]
    
    # Get hypothesis labels for display
    hypotheses = {h.id: h.label for h in store.list_hypotheses(mission_id)}
    
    return {
        "workstream_id": ws_id,
        "findings": [
            {
                "id": f.id,
                "claim_text": f.claim_text,
                "confidence": f.confidence,
                "agent_id": f.agent_id,
                "hypothesis_label": hypotheses.get(f.hypothesis_id, "?"),
                "source_id": f.source_id,
                "supports": f.supports,
                "contradicts": f.contradicts,
                "created_at": f.created_at,
            }
            for f in workstream_findings
        ],
        "count": len(workstream_findings),
    }
```

**Frontend tab content split:**

```tsx
// In MissionControl.tsx workstream tab rendering

function WorkstreamTab({ wsId, missionId }: Props) {
  const { findings } = useWorkstreamFindings(missionId, wsId);
  
  if (!findings || findings.length === 0) {
    return (
      <div className="empty-state">
        <p>No findings yet for {wsId}.</p>
        <p className="muted">
          Findings appear here as agents persist them. 
          See live feed below for current activity.
        </p>
      </div>
    );
  }
  
  return (
    <div className="findings-list">
      {findings.map(f => (
        <FindingCard
          key={f.id}
          claim={f.claim_text}
          confidence={f.confidence}
          agent={f.agent_id}
          hypothesis={f.hypothesis_label}
          source={f.source_id}
          supports={f.supports}
        />
      ))}
    </div>
  );
}

// LiveFeed component (separate from tabs)
function LiveFeed({ events }: { events: SSEEvent[] }) {
  // Show meta-events: step complete, milestone delivered, etc.
  // This is a separate, compact panel
  return (
    <div className="live-feed compact">
      {events.map(e => <FeedRow event={e} />)}
    </div>
  );
}
```

The tab shows ONLY findings (content). The live feed (separate, 
maybe at bottom or sidebar) shows meta-events for transparency.

### Acceptance test

```typescript
test("workstream tab shows findings, not meta events", async () => {
  // Setup mission with 2 Dora findings
  // Render MissionControl
  
  const tab = screen.getByText("Market and Competitive Analysis");
  fireEvent.click(tab);
  
  // Findings should appear
  expect(screen.getByText(/finding text 1/)).toBeInTheDocument();
  expect(screen.getByText(/finding text 2/)).toBeInTheDocument();
  
  // Meta-events should NOT appear in tab
  expect(screen.queryByText("step complete")).not.toBeInTheDocument();
  expect(screen.queryByText(/mark milestone delivered/)).not.toBeInTheDocument();
});


test("empty workstream shows helpful message", async () => {
  // Mission with no findings yet
  
  const tab = screen.getByText("Financial Analysis");
  fireEvent.click(tab);
  
  expect(screen.getByText(/No findings yet for W2/)).toBeInTheDocument();
});
```

---

## OVERALL ACCEPTANCE FOR CHANTIER 2.6

```
Run Mistral mission end-to-end. Verify:

1. Quality gate enforcement
   ✓ Calculus does NOT persist findings with all-zero inputs as REASONED
   ✓ If Calculus tries: tool returns "rejected" with guidance
   ✓ Calculus produces fewer findings (or 0) for private targets
   ✓ All persisted findings are either KNOWN with sources OR honest 
     LOW_CONFIDENCE explaining what data is missing

2. Hypothesis linking
   ✓ Every persisted finding has a valid hypothesis_id
   ✓ No orphan findings in DB
   ✓ Tool rejects findings without hypothesis_id

3. Pre-flight check
   ✓ Mistral mission triggers data-availability gate after G0
   ✓ User sees 3 options (skip Calculus / proceed LOW_CONFIDENCE / 
     request data room)
   ✓ Choosing "skip Calculus" → mission proceeds without W2

4. Gate validation idempotency
   ✓ Double-click on Approve does NOT throw 409
   ✓ Console clean (no "Failed to validate gate" errors)
   ✓ Mismatched verdict (approve then reject) returns gentle message

5. Q&A reads findings
   ✓ User asks "why are claims poor?" → MARVIN cites specific findings
   ✓ MARVIN attributes findings correctly (Calculus, not Merlin)
   ✓ MARVIN never says "Merlin logged findings"

6. Workstream tabs show findings
   ✓ "Market and Competitive Analysis" tab shows Dora's findings 
     with confidence badges
   ✓ "Financial Analysis" tab shows Calculus's findings
   ✓ Meta-events (step complete, milestone delivered) NOT in tabs
   ✓ Empty workstream shows helpful "No findings yet" state

7. Tests
   ✓ pytest 0 failures (existing 235 + new tests for each bug)
   ✓ npm run test 0 failures
   ✓ tsc --noEmit clean
```

---

## REVERT STRATEGY

Each bug fix is on a separate commit:
- Commit 1: Fix Bug 1 (quality validator)
- Commit 2: Fix Bug 2 (hypothesis linking)
- Commit 3: Fix Bug 3 (pre-flight check)
- Commit 4: Fix Bug 4 (gate idempotency)
- Commit 5: Fix Bug 5 (Q&A reads findings)
- Commit 6: Fix Bug 6 (workstream tabs)

After any revert:
```bash
pytest tests/ -q
npm run test
# Manual: Mistral brief + intentional double-click + Q&A test
```

---

## REPORTING TEMPLATE

```
## Chantier 2.6 Status

### Bug 1 — Quality validator
- [ ] PASS / FAIL
- Tests added: N
- Mistral run: Calculus produced X findings (was 2 absurd, expect 0 or LOW_CONFIDENCE)

### Bug 2 — Hypothesis linking
- [ ] PASS / FAIL
- Tests added: N

### Bug 3 — Pre-flight check
- [ ] PASS / FAIL
- Mistral mission: data-availability gate fired? Y/N

### Bug 4 — Gate idempotency
- [ ] PASS / FAIL
- Console clean on double-click? Y/N

### Bug 5 — Q&A reads findings
- [ ] PASS / FAIL
- Sample Q&A: "why are claims poor?" response cites specific findings? Y/N

### Bug 6 — Workstream tabs
- [ ] PASS / FAIL
- Tabs show findings, meta-events in separate panel? Y/N

### Regression
- [ ] All Chantier 1, 1.5, 2A, 2.5 acceptance still pass
- [ ] pytest 0 failures
- [ ] npm test 0 failures

Awaiting approval to proceed with Chantier 4 (UI Revamp).
```
