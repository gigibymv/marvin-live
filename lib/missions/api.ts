/**
 * API client for Marvin backend.
 * 
 * Provides typed functions for all backend endpoints.
 * Base URL configurable via NEXT_PUBLIC_API_BASE_URL env var.
 */

import type { MissionGateVerdict } from "@/lib/missions/types";

export type GateReviewPayload = Record<string, unknown>;

// Allow runtime configuration via env var or window global
const getApiBase = (): string => {
  if (typeof window !== "undefined" && (window as any).__MARVIN_API_BASE__) {
    return (window as any).__MARVIN_API_BASE__;
  }
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  return "/api/v1";
};

export const API_BASE = getApiBase();

export class BackendOfflineError extends Error {
  constructor(message = "Backend offline") {
    super(message);
    this.name = "BackendOfflineError";
  }
}

export function isBackendOfflineError(error: unknown): error is BackendOfflineError {
  return error instanceof BackendOfflineError;
}

/**
 * Create a new mission via POST /api/v1/missions
 */
export async function createMission(input: {
  client: string;
  target: string;
  ic_question: string;
  mission_type?: string;
}): Promise<{
  mission_id: string;
  status: string;
  client: string;
  target: string;
}> {
  const response = await fetch(`${API_BASE}/missions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    throw new Error(`Failed to create mission: ${response.status}`);
  }

  return response.json();
}

/**
 * List all missions via GET /api/v1/missions
 */
export async function listMissions(): Promise<{
  missions: Array<{
    id: string;
    client: string;
    target: string;
    mission_type: string;
    status: string;
    progress: number;
    next_checkpoint: string | null;
    created_at: string;
  }>;
}> {
  const response = await fetch(`${API_BASE}/missions`);

  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    throw new Error(`Failed to list missions: ${response.status}`);
  }

  return response.json();
}

/**
 * Get a single mission via GET /api/v1/missions/{id}
 */
export async function getMission(missionId: string): Promise<{
  id: string;
  client: string;
  target: string;
  mission_type: string;
  ic_question: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}> {
  const response = await fetch(`${API_BASE}/missions/${missionId}`);

  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    if (response.status === 404) {
      throw new Error(`Mission not found: ${missionId}`);
    }
    throw new Error(`Failed to get mission: ${response.status}`);
  }

  return response.json();
}

/**
 * Get mission progress via GET /api/v1/missions/{id}/progress
 */
export async function getMissionProgress(missionId: string): Promise<{
  mission: {
    id: string;
    client: string;
    target: string;
    ic_question?: string | null;
    created_at: string;
    status: string;
  };
  framing?: {
    mission_id: string;
    raw_brief: string;
    ic_question: string;
    mission_angle: string;
    brief_summary: string;
    workstream_plan_json: string;
    created_at: string | null;
    updated_at: string | null;
  } | null;
  gates: Array<{
    id: string;
    gate_type: string;
    scheduled_day: number | null;
    status: string;
    lifecycle_status: string;
    is_open: boolean;
    missing_material: string[];
    review_payload: GateReviewPayload;
    format: string | null;
  }>;
  milestones: Array<{
    id: string;
    workstream_id: string;
    label: string;
    status: string;
  }>;
  findings: Array<{
    id: string;
    workstream_id?: string | null;
    hypothesis_id?: string | null;
    source_id: string | null;
    confidence: string | null;
    claim_text: string;
    agent_id: string | null;
  }>;
  hypotheses?: Array<{
    id: string;
    label?: string | null;
    text: string;
    status: string;
    computed?: {
      status: "NOT_STARTED" | "TESTING" | "SUPPORTED" | "WEAKENED";
      total: number;
      known: number;
      reasoned: number;
      low_confidence: number;
      contradicting: number;
      supporting: number;
    };
  }>;
  deliverables?: Array<{
    id: string;
    deliverable_type: string;
    status?: string;
    file_path: string | null;
    created_at: string | null;
  }>;
  workstreams?: Array<{
    id: string;
    label: string;
    assigned_agent: string | null;
    status: string;
  }>;
}> {
  const response = await fetch(`${API_BASE}/missions/${missionId}/progress`);

  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    throw new Error(`Failed to get mission progress: ${response.status}`);
  }

  return response.json();
}

/**
 * Persisted event log for refresh-survival of the live rail.
 * Reconstructed server-side from store (findings/milestones/deliverables/gates).
 */
export interface PersistedRailEvent {
  type: "finding_added" | "milestone_done" | "deliverable_ready" | "gate_resolved";
  ts?: string;
  findingId?: string;
  milestoneId?: string;
  deliverableId?: string;
  gateId?: string;
  text?: string;
  label?: string;
  confidence?: string;
  agent?: string | null;
  workstreamId?: string | null;
  hypothesisId?: string | null;
  sourceId?: string | null;
  deliverableType?: string;
  filePath?: string | null;
  fileSizeBytes?: number | null;
  status?: string;
  resultSummary?: string | null;
  gateType?: string;
  completionNotes?: string | null;
}

export async function getMissionEvents(missionId: string): Promise<{
  mission_id: string;
  events: PersistedRailEvent[];
}> {
  const response = await fetch(`${API_BASE}/missions/${missionId}/events`);
  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    throw new Error(`Failed to get mission events: ${response.status}`);
  }
  return response.json();
}

/**
 * Base SSE event type
 */
interface SSEEventBase {
  type: string;
}

/**
 * SSE event types from backend
 */
export type SSEEvent = SSEEventBase & Record<string, unknown>;

/**
 * Send chat message and receive SSE stream via POST.
 * Returns an async generator that yields SSE events.
 */
export async function* sendChatMessage(
  missionId: string,
  text: string,
  reset = false,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  const url = `${API_BASE}/missions/${missionId}/chat?reset=${reset}`;
  
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });

  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    throw new Error(`Chat request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("No response body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      
      // Process complete SSE events from buffer
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || ""; // Keep incomplete event in buffer
      
      for (const line of lines) {
        if (!line.trim() || line.startsWith(":")) continue; // Skip heartbeats and empty lines
        
        const event = parseSSEEvent(line);
        if (event) {
          yield event;
        }
      }
    }
    
    // Process any remaining buffer
    if (buffer.trim() && !buffer.startsWith(":")) {
      const event = parseSSEEvent(buffer);
      if (event) {
        yield event;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Parse a single SSE event
 */
function parseSSEEvent(raw: string): SSEEvent | null {
  const lines = raw.split("\n");
  let eventType = "message";
  let data = "";

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data = line.slice(5).trim();
    }
  }

  if (!data) return null;

  try {
    const parsed = JSON.parse(data);
    return { type: eventType, ...parsed };
  } catch {
    // If not JSON, treat as plain text message
    return { type: eventType, text: data };
  }
}

/**
 * Validate a gate via POST /api/v1/missions/{mission_id}/gates/{gate_id}/validate
 */
export async function validateGate(
  missionId: string,
  gateId: string,
  verdict: MissionGateVerdict,
  notes = ""
): Promise<{
  status: string;
  mission_id: string;
  gate_id: string;
  resume_id: string;
  idempotent?: boolean;
  conflict?: boolean;
  message?: string;
}> {
  const response = await fetch(
    `${API_BASE}/missions/${missionId}/gates/${gateId}/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict, notes }),
    }
  );

  // Bug 4 (chantier 2.6): backend returns 200 with {idempotent|conflict}
  // for double-clicks and verdict swaps. Surface those as a normal
  // payload — the UI shows a toast instead of throwing.
  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    throw new Error(`Failed to validate gate: ${response.status}`);
  }

  return response.json();
}

/**
 * CP2 (chantier 2.6.1): data_decision gates ship a `decision` value
 * (skip_calculus / proceed_low_confidence / request_data_room) instead
 * of an APPROVED/REJECTED verdict.
 */
export async function validateGateDecision(
  missionId: string,
  gateId: string,
  decision: "skip_calculus" | "proceed_low_confidence" | "request_data_room",
  notes = "",
): Promise<{
  status: string;
  mission_id: string;
  gate_id: string;
  resume_id: string;
  idempotent?: boolean;
  conflict?: boolean;
  message?: string;
}> {
  const response = await fetch(
    `${API_BASE}/missions/${missionId}/gates/${gateId}/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, notes }),
    },
  );

  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    throw new Error(`Failed to validate gate: ${response.status}`);
  }

  return response.json();
}

/**
 * Submit clarification answers for a clarification_request gate.
 * Same endpoint as validateGate, but with `answers` instead of `verdict`.
 */
export async function submitClarificationAnswers(
  missionId: string,
  gateId: string,
  answers: string[],
  notes = "",
): Promise<{
  status: string;
  mission_id: string;
  gate_id: string;
  resume_id: string;
}> {
  const response = await fetch(
    `${API_BASE}/missions/${missionId}/gates/${gateId}/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers, notes }),
    },
  );
  if (!response.ok) {
    if (response.status === 0) {
      throw new BackendOfflineError();
    }
    throw new Error(`Failed to submit clarification answers: ${response.status}`);
  }
  return response.json();
}

/**
 * Download a deliverable via GET /api/v1/deliverables/download
 */
export function getDeliverableDownloadUrl(relPath: string): string {
  return `${API_BASE}/deliverables/download?rel_path=${encodeURIComponent(relPath)}`;
}

/**
 * Configure API base URL at runtime (for client-side use)
 */
export function setApiBase(baseUrl: string): void {
  if (typeof window !== "undefined") {
    (window as any).__MARVIN_API_BASE__ = baseUrl;
  }
}

/**
 * Get mission progress including gates, milestones, findings, hypotheses, deliverables.
 */
