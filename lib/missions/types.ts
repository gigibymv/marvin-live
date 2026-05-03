export type MissionTemplate = "cdd" | "redteam" | "strategy" | "board";
export type MissionStatus = "active" | "completed";
export type WorkspaceTab = "brief" | "ws1" | "ws2" | "ws3" | "ws4" | "final";
export type MissionPanel = "feed" | "chat";
export type MissionMessageAuthor = "u" | "m";
export type BackendConnectionState = "local" | "connecting" | "ready" | "offline";
export type MissionGateVerdict = "APPROVED" | "REJECTED";

export interface Mission {
  id: string;
  name: string;
  client: string;
  target: string;
  template: MissionTemplate;
  status: MissionStatus;
  checkpoint: string;
  progress: number;
  createdAt: string;
  fileAttached: boolean;
  briefReceived: boolean;
}

export interface CreateMissionInput {
  client: string;
  target: string;
  template: MissionTemplate;
  fileAttached?: boolean;
  briefReceived?: boolean;
}

export interface MissionChatMessage {
  id: string;
  from: MissionMessageAuthor;
  text: string;
  // Optional deep-link to a deliverable. When present, the chat bubble
  // renders an "Open" affordance so the user can jump straight to the
  // file from the message.
  deliverableId?: string;
  deliverableLabel?: string;
  gateId?: string;
  gateAction?: "pending";
  // Monotonic insertion counter for stable sort. Added by makeMessageId.
  seq?: number;
}

export interface MissionRunState {
  isStreaming: boolean;
}

export interface MissionGateHypothesis {
  id: string;
  text: string;
  status: string;
}

export interface MissionGateFinding {
  id?: string;
  workstream_id?: string | null;
  hypothesis_id?: string | null;
  claim_text: string;
  confidence: string | null;
  agent_id: string | null;
}

export interface MissionGateFraming {
  icQuestion?: string;
  missionAngle?: string;
  briefSummary?: string;
  workstreamPlan?: Array<Record<string, unknown>>;
}

export interface MissionGateCoverageWorkstream {
  id: string;
  label: string;
  assigned_agent?: string | null;
  status: string;
  milestones_delivered: number;
  milestones_total: number;
  findings_total: number;
  has_material: boolean;
}

export interface MissionGateCoverage {
  findings_total: number;
  workstreams_total: number;
  workstreams_with_material: number;
  milestones_delivered: number;
  milestones_total: number;
  workstreams: MissionGateCoverageWorkstream[];
}

export interface MissionGateMerlinVerdict {
  id: string;
  verdict: string;
  label?: string | null;
  recommendedAction?: string | null;
  notes?: string | null;
  shipRisk?: string | null;
  hypothesisUpdates?: Array<{
    hypothesisLabel: string;
    nextStatus: string;
    why: string;
  }>;
  recommendedActions?: string[];
  synthesisCompleteAt?: string | null;
  created_at?: string | null;
}

export interface MissionGateModalState {
  gateId: string;
  gateType?: string;
  format?: string;
  title: string;
  stage?: string;
  summary?: string;
  unlocksOnApprove?: string;
  unlocksOnReject?: string;
  hypotheses?: MissionGateHypothesis[];
  researchFindings?: MissionGateFinding[];
  redteamFindings?: MissionGateFinding[];
  arbiterFlags?: string[];
  findingsTotal?: number;
  framing?: MissionGateFraming | null;
  coverage?: MissionGateCoverage | null;
  merlinVerdict?: MissionGateMerlinVerdict | null;
  weakestLinks?: MissionGateFinding[];
  openRisks?: string[];
  missingMaterial?: string[];
  questions?: string[];
  round?: number;
  maxRounds?: number;
  options?: Array<{ value: string; label: string; consequence: string }>;
}

export interface DashboardActiveMission {
  id: string;
  name: string;
  client: string;
  type: string;
  checkpoint: string;
  progress: number;
}

export interface DashboardCompletedMission {
  id: string;
  name: string;
  client: string;
  type: string;
  outcome: string;
  date: string;
}
