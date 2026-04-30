# MARVIN — Cost Analysis (2026-04-30)

## TL;DR

- **MARVIN's actual model bill is ~$14.50/month**, not $41.9. The $25.23 Gemini 2.5 Pro line on the OpenRouter dashboard does NOT come from this codebase — there is **zero** Gemini reference in `marvin/`. It is another project sharing the same OpenRouter key.
- MARVIN uses two models only: **GPT-5.4 Nano** for every reasoning agent ($4.20/mo) and **Claude Sonnet 4.6** for Papyrus deliverable drafting ($10.30/mo).
- "Why Sonnet" → Papyrus produces the client-facing IC documents (engagement brief, market report, financial report, exec summary, data book, stress-test report, IC memo). The factory comment says it explicitly: *"Papyrus produces client-facing IC documents — quality > cost."*
- Per-mission cost is roughly **$1–3** depending on workstream length. Sonnet-on-Papyrus dominates that bill (~70% of MARVIN's spend).

---

## 1. Current model-per-role mapping

Source of truth: `marvin/llm_factory.py`.

| Role | Model | Why |
|------|-------|-----|
| `dora` (research / Tavily-backed agent) | `openai/gpt-5.4-nano` | Cheap; tavily does the heavy lifting |
| `calculus` (financial analysis) | `openai/gpt-5.4-nano` | Cheap; structured output |
| `adversus` (red-team) | `openai/gpt-5.4-nano` | Cheap |
| `merlin` (synthesis verdict) | `openai/gpt-5.4-nano` | ⚠️ see "risks" — synthesis quality can suffer |
| `orchestrator` (chat QA + steering classification) | `openai/gpt-5.4-nano` | Cheap |
| `framing` (deal thesis → hypotheses) | `openai/gpt-5.4-nano` | Cheap |
| `papyrus` (IC documents) | `anthropic/claude-sonnet-4.6` | Quality > cost; client-facing prose |

Only TWO models in the entire codebase. No Gemini. No Opus. No Haiku.

---

## 2. OpenRouter spend (last month, from screenshot)

| Model | Spend | MARVIN? |
|-------|-------|---------|
| Gemini 2.5 Pro | **$25.23** | ❌ Not MARVIN — likely Simon or another project on the same key |
| Claude Sonnet 4.6 | $10.30 | ✅ Papyrus |
| GPT-5.4 Nano | $4.20 | ✅ all other roles |
| Others | $2.21 | likely Gemini Flash etc., not MARVIN |
| **Total dashboard** | **$41.94** | **MARVIN actual: ~$14.50** |

**Verification step:** filter the OpenRouter "View Logs" by API key or by request-tag prefix to confirm. If you have a dedicated MARVIN key the cleanest fix is one key per project.

---

## 3. Per-mission cost estimate

A full CDD mission goes through: framing → 4 workstreams (W1 market, W2 financial, W3 synthesis, W4 stress) → Papyrus deliverables (≈7–10 documents) → IC memo.

Rough breakdown (single full mission):

| Stage | Model | Tokens (est.) | Cost (est.) |
|-------|-------|---------------|-------------|
| Framing | gpt-5.4-nano | ~30k | $0.01 |
| Dora research × N rounds | gpt-5.4-nano + Tavily | ~150k | $0.05 |
| Calculus | gpt-5.4-nano | ~80k | $0.03 |
| Adversus stress | gpt-5.4-nano | ~100k | $0.04 |
| Merlin synthesis | gpt-5.4-nano | ~50k | $0.02 |
| Orchestrator/QA chats | gpt-5.4-nano | ~30k | $0.01 |
| **Papyrus × ~8 deliverables** | claude-sonnet-4.6 | ~500k–1M | **$1.50–$3.00** |
| **Mission total** | | | **~$1.65–$3.15** |

(Token estimates are order-of-magnitude. Sonnet 4.6 on OpenRouter ≈ $3/M input + $15/M output. Nano ≈ $0.05/M input + $0.40/M output.)

For a month at ~$10.30 Sonnet spend, that's **3–6 full missions** worth of Papyrus writing. Matches the live-test cadence on `marvin-frontend.onrender.com`.

---

## 4. Observations & risks in the current setup

1. **Merlin on Nano is the riskiest line.** Synthesis is the highest-leverage reasoning step in the entire pipeline — a single shaky verdict invalidates four workstreams of work. Nano is fine for routing/extraction but typically loses the thread on multi-claim reconciliation. Watch for shallow/contradictory verdicts.
2. **Adversus on Nano is borderline.** Stress-testing benefits from a model that can hold the full evidence chain in working memory and find non-obvious holes. Nano can do simple counter-attacks; Sonnet is markedly better at finding the actual logic gap.
3. **Framing on Nano is fine** — the input is a single brief, the output is a small structured set of hypotheses. Cheapest model wins here.
4. **Papyrus on Sonnet is the right call.** Deliverables are what the user pays for. Downgrading would directly degrade the product.

---

## 5. Recommended changes (proposal — not applied)

| Role | Current | Proposal | Reason | Estimated $/mo delta |
|------|---------|----------|--------|----------------------|
| `merlin` | nano | **claude-sonnet-4.6** | Verdict quality is load-bearing | +$1.00–$2.00 |
| `adversus` | nano | **claude-sonnet-4.6** | Better stress-test depth | +$0.50–$1.00 |
| `framing` | nano | nano (keep) | Cheapest is fine | 0 |
| `dora` | nano | nano (keep) | Tavily does the work | 0 |
| `calculus` | nano | nano (keep — but watch) | Structured numeric output | 0 |
| `orchestrator` | nano | nano (keep) | Chat QA, classification | 0 |
| `papyrus` | sonnet | sonnet (keep) | Right call | 0 |

Net: ~+$2–3/mo to upgrade the two reasoning roles that gate IC quality. Negligible compared to the overall bill, large impact on output quality.

**Alternative if the goal is to cut cost, not raise quality:**
- Keep everything as-is.
- Move framing/orchestrator from nano to **gemini-2.5-flash** (often even cheaper than nano for short context). Save ~$0.10–$0.30/mo.
- Not worth the swap unless you're scaling missions 10×.

---

## 6. Open questions for the user

1. Do you have a separate OpenRouter key for MARVIN vs Simon vs other projects? If not, one key per project would make this analysis trivially accurate going forward.
2. Are you willing to spend +$2–3/mo to put Merlin (and possibly Adversus) on Sonnet? My recommendation is yes.
3. How many missions per month do you target? At current spend (~$14.50 MARVIN-only) you can run ~5–8 missions; at the proposed Merlin-on-Sonnet bump you'd run ~4–6 for the same budget.

---

## 7. Verification commands (read-only)

```bash
# Confirm the model factory is the only source of truth.
grep -n "MODEL_BY_ROLE\|get_chat_llm" marvin/**/*.py

# Confirm no Gemini in MARVIN code.
grep -rn "gemini\|google/gemini" marvin/ marvin_ui/ --include="*.py"

# Sample mission cost from the DB (when missions exist).
sqlite3 ~/.marvin/marvin.db "SELECT COUNT(*) FROM missions;"
```
