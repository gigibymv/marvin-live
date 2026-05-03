import type {
  DashboardActiveMission,
  DashboardCompletedMission,
  Mission,
  MissionChatMessage,
  MissionTemplate,
  WorkspaceTab,
} from "@/lib/missions/types";

export const DEFAULT_WORKSPACE_TAB: WorkspaceTab = "brief";

const TEMPLATE_LABELS: Record<MissionTemplate, string> = {
  cdd: "Commercial Due Diligence",
  redteam: "Red-team Review",
  strategy: "Strategy",
  board: "Board Preparation",
};

const TEMPLATE_SUFFIXES: Record<MissionTemplate, string> = {
  cdd: "CDD",
  redteam: "Red-team",
  strategy: "Strategy",
  board: "Board Prep",
};

export function getMissionTemplateLabel(template: MissionTemplate): string {
  return TEMPLATE_LABELS[template];
}

export function buildMissionName(target: string, template: MissionTemplate): string {
  return `${target.trim()} ${TEMPLATE_SUFFIXES[template]}`;
}

export function buildOpeningMessage(mission: Mission): string {
  return `${mission.client} · ${mission.target} mission is open. Paste or upload your brief — the investment thesis, key questions, any available documents. I'll use it to generate the initial hypotheses and orient the team before the first checkpoint.`;
}

export function buildInitialMessages(mission: Mission): MissionChatMessage[] {
  return [
    {
      id: `${mission.id}-opening`,
      from: "m",
      text: buildOpeningMessage(mission),
    },
  ];
}

export function toDashboardMissionBuckets(missions: Mission[]): {
  activeMissions: DashboardActiveMission[];
  completedMissions: DashboardCompletedMission[];
} {
  const activeMissions = missions
    .filter((mission) => mission.status === "active")
    .map((mission) => ({
      id: mission.id,
      name: mission.name,
      client: mission.client,
      type: getMissionTemplateLabel(mission.template),
      checkpoint: mission.checkpoint,
      progress: mission.progress,
    }));

  const completedMissions = missions
    .filter((mission) => mission.status === "completed")
    .map((mission) => ({
      id: mission.id,
      name: mission.name,
      client: mission.client,
      type: getMissionTemplateLabel(mission.template),
      outcome: "Completed",
      date: formatMissionDate(mission.createdAt),
    }));

  return { activeMissions, completedMissions };
}

// --- Gate presentation helpers ---------------------------------------------
// Pure, side-effect-free formatters for the chat-first gate UX. Extracted
// here so the chat-message text and the live-event signal can be unit-tested
// without rendering MissionControl.
//
// Source of truth for gate state remains the backend `progress.gates` API.
// These helpers only translate a `gate_pending` SSE payload into surface text.

export interface GatePendingPresentationInput {
  gate_type?: string | null;
  gateType?: string | null;
  title?: string | null;
  stage?: string | null;
  summary?: string | null;
  unlocks_on_approve?: string | null;
  unlocks_on_reject?: string | null;
  unlocksOnApprove?: string | null;
  unlocksOnReject?: string | null;
}

const TYPE_FALLBACKS: Record<string, { title: string; summary: string }> = {
  hypothesis_confirmation: {
    title: "Confirm initial hypotheses",
    summary: "MARVIN has framed the deal into testable hypotheses. Approve to start parallel research workstreams. Reject to revise the framing before any research runs.",
  },
  manager_review: {
    title: "Manager review of research claims",
    summary: "Initial research is complete. Review the claims surfaced so far for soundness, sourcing, and confidence before red-team challenges them.",
  },
  final_review: {
    title: "IC sign-off",
    summary: "Synthesis is complete. Review Merlin's verdict and the supporting deliverables before signing off.",
  },
};

export function formatGatePendingChatMessage(event: GatePendingPresentationInput): string {
  const lines: string[] = [];
  const gateType = (event.gateType ?? event.gate_type ?? "").toString();
  const fallback = TYPE_FALLBACKS[gateType];
  const heading = event.title?.trim() || fallback?.title || "Validation requested";
  const summary = event.summary?.trim() || fallback?.summary || null;
  const unlocksOnApprove = event.unlocksOnApprove ?? event.unlocks_on_approve;
  const unlocksOnReject = event.unlocksOnReject ?? event.unlocks_on_reject;
  lines.push(`🔔 Gate pending — ${heading}`);
  if (event.stage?.trim()) lines.push(`Stage: ${event.stage.trim()}`);
  if (summary) lines.push(summary);
  if (unlocksOnApprove?.trim()) lines.push(`Approve → ${unlocksOnApprove.trim()}`);
  if (unlocksOnReject?.trim()) lines.push(`Reject → ${unlocksOnReject.trim()}`);
  lines.push("Use the actions below to review the claims, approve, or reject.");
  return lines.join("\n\n");
}

export function formatGatePendingFeedSignal(event: GatePendingPresentationInput): string {
  const label = (event.title || event.gateType || event.gate_type || "validation").toString().replace(/_/g, " ").trim();
  return `Gate pending · ${label}`;
}

export function markGateChatMessageResolved(
  message: MissionChatMessage,
  gateId: string,
  verdict: "approved" | "rejected",
): MissionChatMessage {
  if (message.gateId !== gateId) return message;
  const statusText =
    verdict === "approved"
      ? "Gate approved. The mission is continuing."
      : "Gate rejected. MARVIN is revising the prior work.";
  return {
    ...message,
    text: message.text.replace(/^🔔 Gate pending[^\n]*(\n\n)?/, "").trim()
      ? `${statusText}\n\n${message.text.replace(/^🔔 Gate pending[^\n]*(\n\n)?/, "").trim()}`
      : statusText,
    gateAction: undefined,
  };
}

export interface NarrationPresentationInput {
  agent?: string | null;
  intent?: string | null;
}

export function formatNarrationChatMessage(event: NarrationPresentationInput): string {
  const agent = event.agent?.trim() || "MARVIN";
  const intent = event.intent?.trim() || "Still working.";
  return `${agent} — ${intent}`;
}

export function formatDeliverableReadyChatMessage(label: unknown): string {
  const text = String(label ?? "deliverable").replace(/_/g, " ").trim() || "deliverable";
  return `MARVIN — I’ve generated the ${text} and added it to Deliverables.`;
}

const DELIVERABLE_LABELS: Record<string, string> = {
  market_brief: "Market brief",
  competitive_brief: "Competitive analysis",
  financial_brief: "Financial analysis",
  risk_brief: "Risk / Red-team",
  investment_memo: "Investment memo",
  engagement_brief: "Engagement brief",
  framing_memo: "Framing memo",
  exec_summary: "Exec summary",
  executive_summary: "Executive summary",
  data_book: "Data book",
};

function capitalizeFirst(text: string): string {
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const WORKSTREAM_REPORT_LABELS: Record<string, string> = {
  W1: "Market report",
  W2: "Financial report",
  W3: "Synthesis report",
  W4: "Stress testing report",
};

export function routeDeliverableToSectionId(deliverable: {
  deliverable_type?: unknown;
  deliverableType?: unknown;
  file_path?: unknown;
  filePath?: unknown;
}): string | null {
  const type = String(deliverable.deliverable_type ?? deliverable.deliverableType ?? "").toLowerCase();
  const filePath = String(deliverable.file_path ?? deliverable.filePath ?? "");
  const workstreamMatch = filePath.match(/(?:^|\/)(W\d+)_report\.md$/i);
  if (workstreamMatch?.[1]) return workstreamMatch[1].toUpperCase();
  // C-PER-MILESTONE: Wx.y_<slug>.md routes to its parent workstream tab.
  const milestoneMatch = filePath.match(/(?:^|\/)(W\d+)\.\d+_[^/]*\.md$/i);
  if (milestoneMatch?.[1]) return milestoneMatch[1].toUpperCase();

  const knownTypeRoutes: Record<string, string> = {
    market_brief: "W1",
    market_report: "W1",
    competitive_landscape: "W1",
    financial_snapshot: "W2",
    financial_model: "W2",
    risk_register: "W4",
    redteam_report: "W4",
    engagement_brief: "brief",
    framing_memo: "brief",
    investment_memo: "final",
    exec_summary: "final",
    executive_summary: "final",
    data_book: "final",
    report_pdf: "final",
  };

  return knownTypeRoutes[type] ?? null;
}

function humanizeSlug(slug: string): string {
  return slug
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatDeliverableDisplayName(deliverable: {
  deliverable_type?: unknown;
  deliverableType?: unknown;
  file_path?: unknown;
  filePath?: unknown;
}): string {
  const type = String(deliverable.deliverable_type ?? deliverable.deliverableType ?? "deliverable");
  const sectionId = routeDeliverableToSectionId(deliverable);
  const filePath = String(deliverable.file_path ?? deliverable.filePath ?? "");

  if (type.toLowerCase() === "workstream_report" && sectionId) {
    return WORKSTREAM_REPORT_LABELS[sectionId] ?? "Workstream report";
  }

  // C-PER-MILESTONE: extract the milestone slug from per-milestone files
  // like `W2.3_unit_economics.md` → "Unit economics" so the rail doesn't
  // show six identical "Milestone report" rows.
  const milestoneMatch = filePath.match(/(?:^|\/)W\d+\.\d+_([^/]+?)\.md$/i);
  if (milestoneMatch?.[1]) {
    return humanizeSlug(milestoneMatch[1]);
  }

  return DELIVERABLE_LABELS[type] ?? capitalizeFirst(type.replace(/_/g, " "));
}

export function routeDeliverableToWorkstreamId(deliverable: {
  deliverable_type?: unknown;
  deliverableType?: unknown;
  file_path?: unknown;
  filePath?: unknown;
}): string | null {
  const sectionId = routeDeliverableToSectionId(deliverable);
  return sectionId?.match(/^W\d+$/) ? sectionId : null;
}

export function routeWorkstreamToSectionId(workstreamId?: unknown): string | null {
  const id = String(workstreamId ?? "").trim().toUpperCase();
  if (/^W[1-4]$/.test(id)) return id;
  return null;
}

export function routeOutputToSectionId(output: {
  section_id?: unknown;
  sectionId?: unknown;
  workstream_id?: unknown;
  workstreamId?: unknown;
  agent_id?: unknown;
  agent?: unknown;
  ag?: unknown;
}): string | null {
  const explicitSection = String(output.section_id ?? output.sectionId ?? "").trim();
  if (explicitSection) return explicitSection;
  const workstreamSection = routeWorkstreamToSectionId(output.workstream_id ?? output.workstreamId);
  if (workstreamSection) return workstreamSection;
  const agent = String(output.agent_id ?? output.agent ?? output.ag ?? "").trim().toLowerCase();
  const agentRoutes: Record<string, string> = {
    dora: "W1",
    calculus: "W2",
    merlin: "W3",
    adversus: "W4",
  };
  return agentRoutes[agent] ?? null;
}

function formatMissionDate(createdAt: string): string {
  const date = new Date(createdAt);

  if (Number.isNaN(date.getTime())) {
    return createdAt;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
  }).format(date);
}
