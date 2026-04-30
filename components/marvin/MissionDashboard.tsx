"use client";

import React, { useEffect, useState } from "react";
import type { ComponentType } from "react";
import { useRouter } from "next/navigation";
import RawMissionDashboardView from "../../UI Marvin/MissionDashboard.jsx";
import { toDashboardMissionBuckets } from "@/lib/missions/adapters";
import {
  type MissionRepository,
  isBackendOfflineError,
  httpMissionRepository,
  localMissionRepository,
} from "@/lib/missions/repository";
import { MISSIONS_STORAGE_KEY } from "@/lib/missions/repository";
import type {
  BackendConnectionState,
  CreateMissionInput,
  DashboardActiveMission,
  DashboardCompletedMission,
  Mission,
} from "@/lib/missions/types";

const STORAGE_VERSION = "marvin-v2";

const MissionDashboardView = RawMissionDashboardView as unknown as ComponentType<{
  activeMissions: DashboardActiveMission[];
  completedMissions: DashboardCompletedMission[];
  onOpenMission: (missionId: string) => void;
  onCreateMission: (input: CreateMissionInput) => Promise<Mission>;
  onDeleteMission: (missionId: string) => Promise<void>;
  backendNotice?: string;
}>;

export default function MissionDashboard({
  repository = httpMissionRepository,
}: {
  repository?: MissionRepository;
}) {
  const router = useRouter();
  const [missions, setMissions] = useState<Mission[]>([]);
  const [backendState, setBackendState] = useState<BackendConnectionState>(
    repository.kind === "local" ? "local" : "connecting",
  );
  const [backendNotice, setBackendNotice] = useState<string | undefined>();

  // Clear stale localStorage from old project versions
  useEffect(() => {
    if (typeof window === "undefined") return;
    
    const currentVersion = localStorage.getItem("marvin_storage_version");
    if (currentVersion !== STORAGE_VERSION) {
      // Clear all marvin-related storage
      localStorage.removeItem(MISSIONS_STORAGE_KEY);
      localStorage.removeItem("marvin.missions.ui");
      // Set new version
      localStorage.setItem("marvin_storage_version", STORAGE_VERSION);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadMissions() {
      try {
        const nextMissions = await repository.listMissions();

        if (cancelled) {
          return;
        }

        setMissions(nextMissions);
        setBackendState(repository.kind === "local" ? "local" : "ready");
        setBackendNotice(undefined);
      } catch (error) {
        if (cancelled) {
          return;
        }

        if (isBackendOfflineError(error)) {
          setBackendState("offline");
          setBackendNotice("Backend offline. Start the backend server on port 8095 to use real data.");
          setMissions([]);
          return;
        }

        throw error;
      }
    }

    void loadMissions();

    return () => {
      cancelled = true;
    };
  }, [repository]);

  const { activeMissions, completedMissions }: {
    activeMissions: DashboardActiveMission[];
    completedMissions: DashboardCompletedMission[];
  } = toDashboardMissionBuckets(missions);

  const handleOpenMission = (missionId: string) => {
    router.push(`/missions/${missionId}`);
  };

  const handleDeleteMission = async (missionId: string) => {
    await repository.deleteMission(missionId);
    const nextMissions = await repository.listMissions();
    setMissions(nextMissions);
  };

  const handleCreateMission = async (input: CreateMissionInput) => {
    try {
      const mission = await repository.createMission(input);
      const nextMissions = await repository.listMissions();
      setMissions(nextMissions);
      setBackendState(repository.kind === "local" ? "local" : "ready");
      setBackendNotice(undefined);
      router.push(`/missions/${mission.id}`);
      return mission;
    } catch (error) {
      if (isBackendOfflineError(error)) {
        setBackendState("offline");
        setBackendNotice("Backend offline. Cannot create mission.");
        throw error;
      }
      throw error;
    }
  };

  return (
    <MissionDashboardView
      activeMissions={activeMissions}
      completedMissions={completedMissions}
      onOpenMission={handleOpenMission}
      onCreateMission={handleCreateMission}
      onDeleteMission={handleDeleteMission}
      backendNotice={backendState === "offline" ? backendNotice : undefined}
    />
  );
}
