"""Orchestrator Q&A mode.

Read-only responder for chat messages that arrive while a mission is paused
at a gate or completed. Bypasses the LangGraph mission flow entirely so a
casual user message ("Approved", "what's the verdict?") does not replay
framing/research/synthesis.

Returns a short string. Never modifies mission state. Never triggers agents.
"""
from __future__ import annotations

import logging
from pathlib import Path

from marvin.mission.store import MissionStore

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "subagents" / "prompts" / "orchestrator_qa.md"

_PHASE_LABEL = {
    "setup": "setup",
    "framing": "framing",
    "awaiting_clarification": "Clarification",
    "awaiting_confirmation": "Hypothesis review",
    "confirmed": "research",
    "research_done": "Manager review",
    "gate_g1_passed": "research",
    "redteam_done": "synthesis",
    "synthesis_retry": "synthesis",
    "synthesis_done": "Final review",
    "gate_g3_passed": "delivery",
    "done": "complete",
}


def _summarize_state(mission_id: str) -> dict:
    store = MissionStore()
    try:
        mission = store.get_mission(mission_id)
    except KeyError:
        return {"error": "mission not found"}

    findings = store.list_findings(mission_id)
    hypotheses = store.list_hypotheses(mission_id, status="active")
    gates = store.list_gates(mission_id)
    pending_gates = [g for g in gates if g.status == "pending"]
    verdict = store.get_latest_merlin_verdict(mission_id)
    deliverables = store.list_deliverables(mission_id)

    # Bug 5 (chantier 2.6): Q&A must read findings, not just count them.
    # Surface claim_text + correct agent attribution so MARVIN never says
    # "Merlin logged findings" (Merlin doesn't — Calculus / Dora / Adversus do).
    finding_details = [
        {
            "claim_text": f.claim_text,
            "confidence": f.confidence,
            "agent_id": f.agent_id,
            "hypothesis_id": f.hypothesis_id,
        }
        for f in findings
    ]
    by_agent: dict[str, list[dict]] = {}
    for fd in finding_details:
        by_agent.setdefault(fd["agent_id"] or "unknown", []).append(fd)

    return {
        "mission": {
            "client": mission.client,
            "target": mission.target,
            "status": mission.status,
        },
        "findings_count": len(findings),
        "findings": finding_details,
        "findings_by_agent": by_agent,
        "hypotheses_count": len(hypotheses),
        "hypotheses": [
            {"id": h.id, "label": h.label, "text": h.text} for h in hypotheses
        ],
        "pending_gate": (
            {"id": pending_gates[0].id, "type": pending_gates[0].gate_type}
            if pending_gates
            else None
        ),
        "verdict": (
            {"verdict": verdict.verdict, "notes": verdict.notes}
            if verdict
            else None
        ),
        "deliverables": [
            {"type": d.deliverable_type, "status": d.status} for d in deliverables
        ],
    }


def _gate_label(gate_type: str) -> str:
    return {
        "hypothesis_confirmation": "Hypothesis review",
        "manager_review": "Manager review (G1)",
        "final_review": "Final review (G3)",
        "clarification_request": "Clarification",
    }.get(gate_type, gate_type)


def _deterministic_response(state: dict, user_text: str) -> str:
    """Pure-Python Q&A fallback for environments without an LLM key.
    Emits a single short sentence that reflects current mission state."""
    if state.get("error"):
        return "Mission state unavailable."

    text_lower = (user_text or "").lower().strip()
    pending = state.get("pending_gate")

    # User trying to advance without using gate UI
    advance_words = ("approve", "approved", "go", "ship", "proceed", "next", "ok")
    if pending and any(word in text_lower for word in advance_words):
        return f"{_gate_label(pending['type'])} is pending. Click 'Review now' to advance."

    # Verdict question
    if "verdict" in text_lower:
        verdict = state.get("verdict")
        if verdict:
            return f"Merlin's verdict: {verdict['verdict']}."
        return "No verdict yet."

    # Findings question — Bug 5: cite actual content + correct attribution.
    if "finding" in text_lower or "claim" in text_lower or "poor" in text_lower or "weak" in text_lower:
        findings = state.get("findings") or []
        if not findings:
            return "No findings logged yet."
        by_agent = state.get("findings_by_agent") or {}
        # Single-agent case: cite the specific agent + a representative claim.
        if len(by_agent) == 1:
            (agent, agent_findings), = by_agent.items()
            low = [f for f in agent_findings if f["confidence"] == "LOW_CONFIDENCE"]
            if low:
                sample = low[0]["claim_text"][:120]
                return (
                    f"{agent.title()} logged {len(agent_findings)} finding(s); "
                    f"{len(low)} are LOW_CONFIDENCE. Example: \"{sample}\"."
                )
            sample = agent_findings[0]["claim_text"][:120]
            return f"{agent.title()} logged {len(agent_findings)} finding(s). Example: \"{sample}\"."
        attribution = ", ".join(
            f"{a.title()}: {len(fs)}" for a, fs in by_agent.items()
        )
        return f"Findings by agent — {attribution}."

    # Hypotheses question
    if "hypothes" in text_lower:
        return f"{state['hypotheses_count']} active hypotheses."

    # Memo / deliverable
    if "memo" in text_lower or "deliverable" in text_lower or "report" in text_lower:
        ready = [d for d in state["deliverables"] if d["status"] == "ready"]
        if ready:
            return f"{len(ready)} deliverable(s) ready."
        return "No deliverables generated yet."

    # Default
    if pending:
        return f"{_gate_label(pending['type'])} is pending. Click 'Review now' to advance."
    return "Mission paused. Use the gate panel to continue."


async def respond_qa(mission_id: str, user_text: str) -> str:
    """Generate a Q&A reply. Never modifies mission state.

    Tries LLM first; falls back to deterministic response if no API key.
    """
    state = _summarize_state(mission_id)

    try:
        from marvin.llm_factory import get_chat_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = get_chat_llm("orchestrator")
        # CP5 (chantier 2.6.1): cap Q&A at ~2-4 sentences. Backend hard
        # cap matches the prompt-level instruction.
        try:
            llm = llm.bind(max_tokens=160)
        except Exception:  # noqa: BLE001 - bind not always supported
            pass
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY" in str(exc):
            return _deterministic_response(state, user_text)
        raise

    try:
        system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return _deterministic_response(state, user_text)

    pending = state.get("pending_gate")
    pending_label = _gate_label(pending["type"]) if pending else "none"
    verdict = state.get("verdict")
    verdict_str = verdict["verdict"] if verdict else "none yet"

    # Bug 5 (chantier 2.6): pass findings text + correct agent attribution
    # into the LLM context so it never says "Merlin logged findings".
    findings_block_lines: list[str] = []
    for fd in (state.get("findings") or [])[:20]:
        findings_block_lines.append(
            f"- [{fd['agent_id']} · {fd['confidence']}] {fd['claim_text']}"
        )
    findings_block = "\n".join(findings_block_lines) or "(none persisted)"

    hypotheses_block_lines = [
        f"- {h.get('label') or '?'}: {h['text']}"
        for h in (state.get("hypotheses") or [])
    ]
    hypotheses_block = "\n".join(hypotheses_block_lines) or "(none active)"

    context = (
        f"Mission: {state['mission'].get('client', '')} - {state['mission'].get('target', '')}\n"
        f"Pending gate: {pending_label}\n"
        f"Verdict: {verdict_str}\n"
        f"Deliverables ready: {sum(1 for d in state['deliverables'] if d['status'] == 'ready')}\n"
        f"\nActive hypotheses ({state['hypotheses_count']}):\n{hypotheses_block}\n"
        f"\nPersisted findings ({state['findings_count']}):\n{findings_block}\n"
        f"\nAgent attribution rule: Dora/Calculus/Adversus log findings; "
        "Merlin issues a verdict (no findings); Papyrus generates deliverables.\n"
        f"\nUser said: {user_text}"
    )

    try:
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=context)]
        )
        text = (response.content or "").strip()
        if not text:
            return _deterministic_response(state, user_text)
        # CP5 (chantier 2.6.1): enforce a 2-4 sentence cap server-side.
        # If the LLM returns more, trim to the first 4 sentences.
        return _enforce_sentence_cap(text, max_sentences=4)
    except Exception as exc:  # noqa: BLE001 - never let Q&A crash the chat
        logger.warning("orchestrator_qa LLM call failed: %s", exc)
        return _deterministic_response(state, user_text)


def _enforce_sentence_cap(text: str, *, max_sentences: int = 4) -> str:
    """Trim text to at most `max_sentences` sentences. Preserves trailing
    punctuation. Pure: no side effects, no mutation."""
    import re

    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    parts = [p for p in parts if p]
    if len(parts) <= max_sentences:
        return text.strip()
    return " ".join(parts[:max_sentences]).strip()
