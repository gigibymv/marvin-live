import type { MissionGateModalState } from "@/lib/missions/types";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function asStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const values = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  return values.length ? values : undefined;
}

export function mapGateReviewPayloadToModal(
  payloadLike: unknown,
  fallback?: { id?: string; gate_type?: string },
): MissionGateModalState {
  const payload = asRecord(payloadLike);
  const framing = asRecord(payload.framing);
  const merlinVerdict = asRecord(payload.merlin_verdict ?? payload.merlinVerdict);
  const gateId = asString(payload.gate_id) ?? asString(payload.gateId) ?? fallback?.id ?? "gate";
  const gateType = asString(payload.gate_type) ?? asString(payload.gateType) ?? fallback?.gate_type;
  const coverage = asRecord(payload.coverage);
  const coverageWorkstreams = Array.isArray(coverage.workstreams)
    ? coverage.workstreams as NonNullable<MissionGateModalState["coverage"]>["workstreams"]
    : [];
  const normalizedCoverage = Object.keys(coverage).length
    ? {
        findings_total: typeof coverage.findings_total === "number" ? coverage.findings_total : 0,
        workstreams_total: typeof coverage.workstreams_total === "number" ? coverage.workstreams_total : coverageWorkstreams.length,
        workstreams_with_material: typeof coverage.workstreams_with_material === "number" ? coverage.workstreams_with_material : 0,
        milestones_delivered: typeof coverage.milestones_delivered === "number" ? coverage.milestones_delivered : 0,
        milestones_total: typeof coverage.milestones_total === "number" ? coverage.milestones_total : 0,
        workstreams: coverageWorkstreams,
      } satisfies NonNullable<MissionGateModalState["coverage"]>
    : undefined;

  return {
    gateId,
    gateType,
    title: asString(payload.title) ?? gateType?.replace(/_/g, " ") ?? "Validation required",
    stage: asString(payload.stage),
    summary: asString(payload.summary),
    unlocksOnApprove: asString(payload.unlocks_on_approve) ?? asString(payload.unlocksOnApprove),
    unlocksOnReject: asString(payload.unlocks_on_reject) ?? asString(payload.unlocksOnReject),
    hypotheses: Array.isArray(payload.hypotheses) ? payload.hypotheses as MissionGateModalState["hypotheses"] : undefined,
    researchFindings: Array.isArray(payload.research_findings)
      ? payload.research_findings as MissionGateModalState["researchFindings"]
      : Array.isArray(payload.researchFindings)
        ? payload.researchFindings as MissionGateModalState["researchFindings"]
        : undefined,
    redteamFindings: Array.isArray(payload.redteam_findings)
      ? payload.redteam_findings as MissionGateModalState["redteamFindings"]
      : Array.isArray(payload.redteamFindings)
        ? payload.redteamFindings as MissionGateModalState["redteamFindings"]
        : undefined,
    arbiterFlags: asStringArray(payload.arbiter_flags) ?? asStringArray(payload.arbiterFlags),
    findingsTotal: typeof payload.findings_total === "number"
      ? payload.findings_total
      : typeof payload.findingsTotal === "number"
        ? payload.findingsTotal
        : undefined,
    framing: Object.keys(framing).length
      ? {
          icQuestion: asString(framing.ic_question) ?? asString(framing.icQuestion),
          missionAngle: asString(framing.mission_angle) ?? asString(framing.missionAngle),
          briefSummary: asString(framing.brief_summary) ?? asString(framing.briefSummary),
          workstreamPlan: Array.isArray(framing.workstream_plan)
            ? framing.workstream_plan as Array<Record<string, unknown>>
            : Array.isArray(framing.workstreamPlan)
              ? framing.workstreamPlan as Array<Record<string, unknown>>
              : undefined,
        }
      : undefined,
    coverage: normalizedCoverage,
    merlinVerdict: Object.keys(merlinVerdict).length ? {
      id: asString(merlinVerdict.id) ?? "merlin-verdict",
      verdict: asString(merlinVerdict.verdict) ?? "UNKNOWN",
      notes: asString(merlinVerdict.notes) ?? null,
      created_at: asString(merlinVerdict.created_at) ?? null,
    } : undefined,
    weakestLinks: Array.isArray(payload.weakest_links)
      ? payload.weakest_links as MissionGateModalState["weakestLinks"]
      : Array.isArray(payload.weakestLinks)
        ? payload.weakestLinks as MissionGateModalState["weakestLinks"]
        : undefined,
    openRisks: asStringArray(payload.open_risks) ?? asStringArray(payload.openRisks),
    missingMaterial: asStringArray(payload.missing_material) ?? asStringArray(payload.missingMaterial),
    format: asString(payload.format),
    questions: asStringArray(payload.questions),
    round: typeof payload.round === "number" ? payload.round : undefined,
    maxRounds: typeof payload.max_rounds === "number"
      ? payload.max_rounds
      : typeof payload.maxRounds === "number"
        ? payload.maxRounds
        : undefined,
    options: Array.isArray(payload.options)
      ? (payload.options as unknown[])
          .map((opt) => {
            const o = asRecord(opt);
            const value = asString(o.value);
            const label = asString(o.label);
            const consequence = asString(o.consequence);
            if (!value || !label) return null;
            return { value, label, consequence: consequence ?? "" };
          })
          .filter((o): o is { value: string; label: string; consequence: string } => o !== null)
      : undefined,
  };
}
