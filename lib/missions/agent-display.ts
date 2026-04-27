// Bug 5: agent name casing safety net for the UI rail.
//
// The backend now emits Title Case via get_display_name, but the /progress
// endpoint and any pre-fix persisted findings carry raw lowercase agent_id.
// This helper produces a single source of truth for display: "Dora",
// "Calculus", "Adversus", "Merlin", "Papyrus" in Title Case; "MARVIN" in
// uppercase as a brand exception.

export const AGENT_DISPLAY_MAP: Record<string, string> = {
  dora: "Dora",
  calculus: "Calculus",
  adversus: "Adversus",
  merlin: "Merlin",
  marvin: "MARVIN",
  papyrus: "Papyrus",
  papyrus_phase0: "Papyrus",
  papyrus_delivery: "Papyrus",
  orchestrator: "MARVIN",
  orchestrator_qa: "MARVIN",
  framing: "MARVIN",
  framing_orchestrator: "MARVIN",
};

export function normalizeAgentName(raw: unknown): string {
  const text = String(raw ?? "").trim();
  if (!text) return "MARVIN";
  const lower = text.toLowerCase();
  if (AGENT_DISPLAY_MAP[lower]) return AGENT_DISPLAY_MAP[lower];
  if (text[0] === text[0].toUpperCase() && text !== text.toUpperCase()) return text;
  return text
    .split(/[_\s]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}
