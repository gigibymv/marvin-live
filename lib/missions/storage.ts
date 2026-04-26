import { buildMissionName } from "@/lib/missions/adapters";
import type { CreateMissionInput, Mission } from "@/lib/missions/types";

export const MISSIONS_STORAGE_KEY = "marvin.missions.records";

export function listMissions(): Mission[] {
  return readMissions().sort(
    (left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime(),
  );
}

export function getMissionById(id: string): Mission | null {
  return readMissions().find((mission) => mission.id === id) ?? null;
}

export function createMission(input: CreateMissionInput): Mission {
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
    checkpoint: "Hypothesis confirmation",
    progress: 0,
    createdAt: new Date().toISOString(),
    fileAttached: Boolean(input.fileAttached),
    briefReceived: Boolean(input.briefReceived),
  };

  writeMissions([mission, ...missions]);
  return mission;
}

export function updateMission(id: string, patch: Partial<Omit<Mission, "id">>): Mission | null {
  const missions = readMissions();
  const index = missions.findIndex((mission) => mission.id === id);

  if (index === -1) {
    return null;
  }

  const current = missions[index];
  const nextTarget = patch.target?.trim() ?? current.target;
  const nextTemplate = patch.template ?? current.template;
  const nextClient = patch.client?.trim() ?? current.client;
  const nextMission: Mission = {
    ...current,
    ...patch,
    client: nextClient,
    target: nextTarget,
    template: nextTemplate,
    name: patch.name ?? buildMissionName(nextTarget, nextTemplate),
  };

  missions[index] = nextMission;
  writeMissions(missions);
  return nextMission;
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

function createMissionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `mission-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
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
