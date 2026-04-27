export type MissionTemplate = "cdd" | "redteam" | "strategy" | "board";
export type MissionStatus = "active" | "completed";
export type WorkspaceTab = "ws1" | "ws2" | "ws3" | "ws4" | "ws5";
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
  claim_text: string;
  confidence: string | null;
  agent_id: string | null;
}

export interface MissionGateModalState {
  gateId: string;
  gateType?: string;
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
