import type {
  DashboardActiveMission,
  DashboardCompletedMission,
  Mission,
  MissionChatMessage,
  MissionTemplate,
  WorkspaceTab,
} from "@/lib/missions/types";

export const DEFAULT_WORKSPACE_TAB: WorkspaceTab = "ws1";

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
  gateType?: string | null;
  title?: string | null;
  stage?: string | null;
  summary?: string | null;
  unlocksOnApprove?: string | null;
  unlocksOnReject?: string | null;
}

export function formatGatePendingChatMessage(event: GatePendingPresentationInput): string {
  const lines: string[] = [];
  const heading = event.title?.trim() || "Validation requested";
  lines.push(`🔔 Gate pending — ${heading}`);
  if (event.stage?.trim()) lines.push(`Stage: ${event.stage.trim()}`);
  if (event.summary?.trim()) lines.push(event.summary.trim());
  if (event.unlocksOnApprove?.trim()) lines.push(`Approve → ${event.unlocksOnApprove.trim()}`);
  if (event.unlocksOnReject?.trim()) lines.push(`Reject → ${event.unlocksOnReject.trim()}`);
  lines.push(
    "Take your time. Click \u201cReview now\u201d in the banner above to approve, reject, or come back later.",
  );
  return lines.join("\n\n");
}

export function formatGatePendingFeedSignal(event: GatePendingPresentationInput): string {
  const label = (event.title || event.gateType || "validation").toString().replace(/_/g, " ").trim();
  return `Gate pending · ${label}`;
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
