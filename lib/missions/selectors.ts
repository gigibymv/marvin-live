import type { MissionUiStore } from "@/lib/missions/store";
import type { MissionRunState, WorkspaceTab } from "@/lib/missions/types";

const DEFAULT_TAB: WorkspaceTab = "ws1";
const DEFAULT_RUN_STATE: MissionRunState = {
  isStreaming: false,
};

export function selectSidebarOpen(state: MissionUiStore): boolean {
  return state.isSidebarOpen;
}

export function selectChatPanelOpen(state: MissionUiStore): boolean {
  return state.isChatPanelOpen;
}

export function selectSelectedPanel(state: MissionUiStore) {
  return state.selectedPanel;
}

export function selectWorkspaceTab(state: MissionUiStore, missionId: string): WorkspaceTab {
  return state.selectedWorkspaceTabByMissionId[missionId] ?? DEFAULT_TAB;
}

export function selectChatDraft(state: MissionUiStore, missionId: string): string {
  return state.chatDrafts[missionId] ?? "";
}

export function selectRunState(state: MissionUiStore, missionId: string): MissionRunState {
  return state.runStateByMissionId[missionId] ?? DEFAULT_RUN_STATE;
}
