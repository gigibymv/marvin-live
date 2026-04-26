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
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        isSidebarOpen: state.isSidebarOpen,
        isChatPanelOpen: state.isChatPanelOpen,
        selectedPanel: state.selectedPanel,
        selectedWorkspaceTabByMissionId: state.selectedWorkspaceTabByMissionId,
        chatDrafts: state.chatDrafts,
        runStateByMissionId: state.runStateByMissionId,
      }),
    },
  ),
);
