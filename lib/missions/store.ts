"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { MissionPanel, MissionRunState, WorkspaceTab } from "@/lib/missions/types";

export interface MissionUiStore {
  isSidebarOpen: boolean;
  isChatPanelOpen: boolean;
  selectedPanel: MissionPanel;
  selectedWorkspaceTabByMissionId: Record<string, WorkspaceTab>;
  chatDrafts: Record<string, string>;
  runStateByMissionId: Record<string, MissionRunState>;
  setSidebarOpen: (value: boolean) => void;
  setChatPanelOpen: (value: boolean) => void;
  setSelectedPanel: (value: MissionPanel) => void;
  setWorkspaceTab: (missionId: string, tab: WorkspaceTab) => void;
  setChatDraft: (missionId: string, value: string) => void;
  setRunState: (missionId: string, patch: Partial<MissionRunState>) => void;
  resetMissionSession: (missionId: string) => void;
}

const DEFAULT_RUN_STATE: MissionRunState = {
  isStreaming: false,
};

const VALID_WORKSPACE_TABS: WorkspaceTab[] = ["brief", "ws1", "ws2", "ws3", "ws4", "final"];

function normalizeWorkspaceTab(value: unknown): WorkspaceTab {
  if (value === "ws5") return "final";
  return VALID_WORKSPACE_TABS.includes(value as WorkspaceTab) ? (value as WorkspaceTab) : "brief";
}

function migratePersistedUiState(persisted: unknown): unknown {
  if (!persisted || typeof persisted !== "object") return persisted;
  const state = persisted as Partial<MissionUiStore>;
  const selectedTabs = state.selectedWorkspaceTabByMissionId;
  if (!selectedTabs || typeof selectedTabs !== "object") return persisted;

  return {
    ...state,
    selectedWorkspaceTabByMissionId: Object.fromEntries(
      Object.entries(selectedTabs).map(([missionId, tab]) => [
        missionId,
        normalizeWorkspaceTab(tab),
      ]),
    ),
  };
}

export const useMissionUiStore = create<MissionUiStore>()(
  persist(
    (set) => ({
      isSidebarOpen: true,
      isChatPanelOpen: true,
      selectedPanel: "chat",
      selectedWorkspaceTabByMissionId: {},
      chatDrafts: {},
      runStateByMissionId: {},
      setSidebarOpen: (value) => set({ isSidebarOpen: value }),
      setChatPanelOpen: (value) => set({ isChatPanelOpen: value }),
      setSelectedPanel: (value) => set({ selectedPanel: value }),
      setWorkspaceTab: (missionId, tab) =>
        set((state) => ({
          selectedWorkspaceTabByMissionId: {
            ...state.selectedWorkspaceTabByMissionId,
            [missionId]: tab,
          },
        })),
      setChatDraft: (missionId, value) =>
        set((state) => ({
          chatDrafts: {
            ...state.chatDrafts,
            [missionId]: value,
          },
        })),
      setRunState: (missionId, patch) =>
        set((state) => ({
          runStateByMissionId: {
            ...state.runStateByMissionId,
            [missionId]: {
              ...(state.runStateByMissionId[missionId] ?? DEFAULT_RUN_STATE),
              ...patch,
            },
          },
        })),
      resetMissionSession: (missionId) =>
        set((state) => {
          const nextDrafts = { ...state.chatDrafts };
          const nextRunState = { ...state.runStateByMissionId };
          const nextTabs = { ...state.selectedWorkspaceTabByMissionId };

          delete nextDrafts[missionId];
          delete nextRunState[missionId];
          delete nextTabs[missionId];

          return {
            chatDrafts: nextDrafts,
            runStateByMissionId: nextRunState,
            selectedWorkspaceTabByMissionId: nextTabs,
          };
        }),
    }),
    {
      name: "marvin.missions.ui",
      version: 1,
      migrate: migratePersistedUiState,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        isSidebarOpen: state.isSidebarOpen,
        isChatPanelOpen: state.isChatPanelOpen,
        selectedPanel: state.selectedPanel,
        selectedWorkspaceTabByMissionId: state.selectedWorkspaceTabByMissionId,
        chatDrafts: state.chatDrafts,
      }),
    },
  ),
);
