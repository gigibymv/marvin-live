# MARVIN — Lessons Learned

## 2026-04-29 — Multi-mode astream breaks `interrupt()` traversal

**Attempted change:** Switch `graph.astream(stream_mode="updates")` to
`stream_mode=["updates","messages"]` to deliver per-token `AIMessageChunk`
streaming to the live feed. (Commit `f976440`, reverted in `eb4fac5`.)

**Failure mode:** Multi-mode astream broke the `interrupt()` pattern that
gates depend on:

- `gate_pending` SSE events stopped firing on G0 / G1 / G3.
- The graph parked at the gate (the gate row was created in the DB) but
  the `__interrupt__` frame did not surface to `_emit_for_update`.
- `c12_fresh` and any UI client hung in a `/resume` loop receiving
  `run_end status=active` indefinitely. The gate never reached the user,
  so no verdict payload could be delivered to `_deliver_resume`.

**Root cause hypothesis (not fully validated — reverted before deep dive):**
Multi-mode wraps every astream item as a `(mode, data)` tuple. The
`__interrupt__` frame either does not come through the `"updates"` channel
in this format, or LangGraph routes interrupts through a third path that
multi-mode hides. Either way, the existing `_emit_for_update` interrupt
detection (`if "__interrupt__" in event`) never matched.

**Why our checks missed it:**

- Unit tests for `_emit_for_message` exercised the helper in isolation.
  They never exercised an actual `astream` call against a graph that
  parks on `interrupt()`.
- The `make smoke` runtime test runs for 8 seconds — it captures the
  first `gate_pending` in single-mode, but in multi-mode the gate had not
  yet fired within the window, so the smoke run still emitted other
  progress events and PASSed. Smoke was not strong enough to catch this.
- The Step 1 investigation rated the change as risk 3/10 based on
  documentation review. The doc-derived claim that
  `"checkpointer/interrupt: __interrupt__ flows via updates stream —
  unaffected"` was not validated against real behavior before committing.

**Decision:** Reverted to single-mode `"updates"` for stability.

**For true per-token streaming in the future:** Multi-mode `astream` is
not a path forward. Options to revisit when the need is real:

1. **`graph.astream_events()`** — a different LangGraph API that exposes
   per-callback events including `on_chat_model_stream`. May or may not
   preserve `interrupt()` semantics; needs validation under a real gate
   firing before committing.
2. **Custom callback handler** — register a LangChain callback that
   captures `on_llm_new_token` and pipes tokens to the SSE channel
   independently of astream. Does not change `stream_mode`, so gates
   remain unaffected.
3. **Upstream LangGraph fix** — file an issue if multi-mode is supposed
   to preserve interrupt traversal but does not.

**What was kept:** `Chantier A` (commit `1b8d179`, W4 workstream report
wired into `papyrus_delivery_node`) — independent of the stream_mode
change and verified post-revert.

**Verification gate for any future streaming attempt:**
1. Smoke timeout extended to cover at least one full G0 cycle (≥30s).
2. End-to-end `c12_fresh` run on a real Doctolib mission must PASS all
   six acceptance criteria before push.
3. Unit test for `_astream_with_heartbeat` that mocks an astream
   yielding an `__interrupt__` frame and asserts `gate_pending` reaches
   the consumer.
