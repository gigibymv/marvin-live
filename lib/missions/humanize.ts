// Single source of truth for "client-facing prose" sanitisation.
//
// Backend agents (merlin, adversus, calculus, dora, papyrus) emit text
// that contains workflow tokens — verdict enums, internal scaffolding
// section labels, finding/hypothesis IDs, and "kitchen" framing
// ("Rebuttal to attack", "load-bearing claim", "to reach SHIP"). None
// of that should reach the end-user. The proper fix is rewriting the
// agent prompts so they never produce this in the first place; this
// module is the frontend safety net until that ships (Phase C).
//
// Apply at every rendering boundary that displays agent prose: output
// rows (FindingRow, DeliverableRow, MilestoneRow), ActivityItem,
// chat bubbles, deliverable preview.

const VERDICT_LABELS: Record<string, string> = {
  SHIP: "Ready to present",
  MINOR_FIXES: "Additional diligence needed",
  MAJOR_FIXES: "Significant revisions needed",
  BACK_TO_DRAWING_BOARD: "Evidence gaps — not ready",
  READY_FOR_REVIEW: "Ready for review",
  BLOCKED: "Blocked",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

export function humanizeVerdict(raw: string | null | undefined): string {
  const v = String(raw ?? "").trim();
  if (!v) return "";
  if (VERDICT_LABELS[v]) return VERDICT_LABELS[v];
  return v
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Compound phrases must run BEFORE atomic enum replacements so
// "What's needed to reach SHIP" matches before bare "SHIP" does.
const REPLACEMENTS: Array<[RegExp, string]> = [
  // ── Compound phrases ────────────────────────────────────────────────
  [/What['\u2019]s\s+Needed\s+to\s+Reach\s+SHIP/gi, "What's needed before sign-off"],
  [/to\s+Reach\s+SHIP\b/gi, "to reach sign-off"],
  [/Reach\s+SHIP\b/gi, "reach sign-off"],

  // ── Verdict enums (uppercase tokens, bare or with underscores) ──────
  [/\bBACK[_\s]TO[_\s]DRAWING[_\s]BOARD\b/g, "Evidence gaps — not ready"],
  [/\bMAJOR[_\s]FIXES\b/g, "Significant revisions needed"],
  [/\bMINOR[_\s]FIXES\b/g, "Additional diligence needed"],
  [/\bREADY[_\s]FOR[_\s]REVIEW\b/g, "Ready for review"],
  [/\bSHIP\b/g, "Ready to present"],

  // ── Internal IDs (finding / hypothesis / mission / gate) ────────────
  // Strip the inline `[f-xxxxxxxx]` / `(f-xxxxxxxx)` / bare `f-xxxxxx`
  // wrappers; keep surrounding text.
  [/\[\s*f-[0-9a-f]{6,}\s*\]/gi, ""],
  [/\(\s*f-[0-9a-f]{6,}\s*\)/gi, ""],
  [/\bf-[0-9a-f]{6,}\b/gi, ""],
  [/\[\s*hyp-[0-9a-f]{6,}\s*\]/gi, ""],
  [/\(\s*hyp-[0-9a-f]{6,}\s*\)/gi, ""],
  [/\bhyp-[0-9a-f]{6,}\b/gi, ""],
  [/\[\s*m-[0-9a-f-]{6,}\s*\]/gi, ""],
  [/\bgate-[a-z0-9-]{6,}\b/gi, ""],

  // ── Adversarial / kitchen framing ───────────────────────────────────
  [/\bRebuttal\s+to\s+attack\b/gi, "Counter-argument"],
  [/\brebuttal\s+to\s+attack\b/gi, "counter-argument"],
  [/\bRebuttal\b/g, "Counter-argument"],
  [/\brebuttal\b/g, "counter-argument"],

  // ── Load-bearing → key (audit #4) ───────────────────────────────────
  [/\bload[-\s]bearing\s+(claim|claims|finding|findings|hypothes(?:is|es))\b/gi, "key $1"],

  // ── Internal scaffolding section labels (line-leading) ──────────────
  [/^\s*(Why|What['\u2019]?s\s+needed|Recommendation)\s*:\s*/gim, ""],
  // ── "Verdict: <ENUM>" prefix lines ──────────────────────────────────
  [/^\s*Verdict\s*:\s*[A-Z_]+\s*$/gim, ""],
];

// Catch-all snake_case identifiers (lowercase tokens with underscores) that
// agents occasionally leak as raw type names: `exec_summary`, `engagement_brief`,
// `framing_memo`, `data_book`. Title-cases them to "Exec summary" etc.
// Run AFTER REPLACEMENTS so explicit phrase mappings win, and only on
// identifier-shaped tokens to avoid mangling normal prose.
const SNAKE_IDENTIFIER = /\b([a-z]{2,}(?:_[a-z]{2,}){1,})\b/g;

export function humanizeText(raw: string | null | undefined): string {
  const text = String(raw ?? "");
  if (!text) return "";
  let out = text;
  for (const [pattern, replacement] of REPLACEMENTS) {
    out = out.replace(pattern, replacement);
  }
  // Title-case any remaining snake_case identifiers ("exec_summary" →
  // "Exec summary"). Sentence-position-aware: lowercase rest, capital first.
  out = out.replace(SNAKE_IDENTIFIER, (m) => {
    const spaced = m.replace(/_/g, " ");
    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
  });
  // Collapse the whitespace damage that ID-stripping leaves behind:
  //   "Rebuttal to attack [f-50c4]  (H3 ..." → "Counter-argument  (H3 ..."
  out = out.replace(/[ \t]{2,}/g, " ");
  out = out.replace(/\(\s+\)/g, "");
  out = out.replace(/\[\s+\]/g, "");
  out = out.replace(/\s+([.,;:!?])/g, "$1");
  out = out.replace(/\n{3,}/g, "\n\n");
  return out.trim();
}
