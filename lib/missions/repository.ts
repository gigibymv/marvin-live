import { buildMissionName } from "@/lib/missions/adapters";
import type { CreateMissionInput, Mission, MissionTemplate } from "@/lib/missions/types";
import {
  createMission as apiCreateMission,
  listMissions as apiListMissions,
  getMission as apiGetMission,
  BackendOfflineError,
  isBackendOfflineError,
} from "@/lib/missions/api";

export interface MissionRepository {
  kind: "local" | "http";
  listMissions(): Promise<Mission[]>;
  createMission(input: CreateMissionInput): Promise<Mission>;
  getMission(id: string): Promise<Mission | null>;
}

export { BackendOfflineError, isBackendOfflineError };

export const MISSIONS_STORAGE_KEY = "marvin.missions.records";

/**
 * Local storage-based repository for offline development/fallback.
 */
export function createLocalMissionRepository(): MissionRepository {
  return {
    kind: "local",
    async listMissions() {
      return readMissions().sort(
        (left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime(),
      );
    },
    async createMission(input) {
      const missions = readMissions();
      const client = input.client.trim();
      const target = input.target.trim();
      const mission: Mission = {
        id: createMissionId(),
        name: buildMissionName(target, input.template),
        client,
        target,
        template: input.template,
        status: "active",
        checkpoint: "No open checkpoint",
        progress: 0,
        createdAt: new Date().toISOString(),
        fileAttached: Boolean(input.fileAttached),
        briefReceived: Boolean(input.briefReceived),
      };

      writeMissions([mission, ...missions]);
      return mission;
    },
    async getMission(id) {
      return readMissions().find((mission) => mission.id === id) ?? null;
    },
  };
}

/**
 * HTTP-based repository that connects to the real backend.
 */
export function createHttpMissionRepository(basePath = "/api/v1"): MissionRepository {
  return {
    kind: "http",
    async listMissions() {
      const response = await apiListMissions();
      
      return response.missions.map((m) => ({
        id: m.id,
        name: buildMissionName(m.target, (m.mission_type as MissionTemplate) || "cdd"),
        client: m.client,
        target: m.target,
        template: (m.mission_type as MissionTemplate) || "cdd",
        status: m.status === "active" ? "active" : "completed",
        checkpoint: m.next_checkpoint ?? "No checkpoint",
        progress: m.progress,
        createdAt: m.created_at,
        fileAttached: false,
        briefReceived: false,
      }));
    },
    async createMission(input) {
      const response = await apiCreateMission({
        client: input.client,
        target: input.target,
        ic_question: "", // Will be asked in chat
        mission_type: input.template,
      });
      
      return {
        id: response.mission_id,
        name: buildMissionName(input.target, input.template),
        client: response.client,
        target: response.target,
        template: input.template,
        status: "active",
        checkpoint: "No open checkpoint",
        progress: 0,
        createdAt: new Date().toISOString(),
        fileAttached: Boolean(input.fileAttached),
        briefReceived: Boolean(input.briefReceived),
      };
    },
    async getMission(id) {
      try {
        const response = await apiGetMission(id);
        
        const template = (response.mission_type as MissionTemplate) || "cdd";
        
        return {
          id: response.id,
          name: buildMissionName(response.target, template),
          client: response.client,
          target: response.target,
          template,
          status: response.status === "active" ? "active" : "completed",
          checkpoint: "No open checkpoint",
          progress: 0,
          createdAt: response.created_at ?? new Date().toISOString(),
          fileAttached: false,
          briefReceived: false,
        };
      } catch (error) {
        if (error instanceof Error && error.message.includes("not found")) {
          return null;
        }
        throw error;
      }
    },
  };
}

export const localMissionRepository = createLocalMissionRepository();
export const httpMissionRepository = createHttpMissionRepository();

function createMissionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `mission-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function readMissions(): Mission[] {
  if (typeof window === "undefined") {
    return [];
  }

  const raw = window.localStorage.getItem(MISSIONS_STORAGE_KEY);

  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isMissionRecord) : [];
  } catch {
    return [];
  }
}

function writeMissions(missions: Mission[]) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(MISSIONS_STORAGE_KEY, JSON.stringify(missions));
}

function isMissionRecord(value: unknown): value is Mission {
  if (!value || typeof value !== "object") {
    return false;
  }

  const mission = value as Record<string, unknown>;

  return (
    typeof mission.id === "string" &&
    typeof mission.name === "string" &&
    typeof mission.client === "string" &&
    typeof mission.target === "string" &&
    typeof mission.template === "string" &&
    typeof mission.status === "string" &&
    typeof mission.checkpoint === "string" &&
    typeof mission.progress === "number" &&
    typeof mission.createdAt === "string" &&
    typeof mission.fileAttached === "boolean" &&
    typeof mission.briefReceived === "boolean"
  );
}
