import type { BackendConnectionState, MissionGateModalState } from "@/lib/missions/types";
import { sendChatMessage, type SSEEvent, isBackendOfflineError } from "@/lib/missions/api";

export type MissionStreamEvent =
  | { type: "text"; text: string }
  | { type: "tool_call"; text: string; agent?: string }
  | { type: "tool_result"; text: string; agent?: string }
  | {
      type: "finding_added";
      text: string;
      badge?: string;
      findingId?: string;
      confidence?: string;
      agent?: string;
      workstreamId?: string;
      hypothesisId?: string;
      sourceId?: string;
      ts?: string;
    }
  | {
      type: "milestone_done";
      milestoneId?: string;
      label?: string;
      workstreamId?: string;
      status?: string;
      resultSummary?: string;
    }
  | {
      type: "gate_pending";
      gateId: string;
      gateType?: string;
      format?: string;
      title: string;
      stage?: string;
      summary?: string;
      unlocksOnApprove?: string;
      unlocksOnReject?: string;
      hypotheses?: Array<{ id: string; text: string; status: string }>;
      researchFindings?: Array<{ claim_text: string; confidence: string | null; agent_id: string | null }>;
      redteamFindings?: Array<{ claim_text: string; confidence: string | null; agent_id: string | null }>;
      arbiterFlags?: string[];
      findingsTotal?: number;
      questions?: string[];
      round?: number;
      maxRounds?: number;
    }
  | {
      type: "deliverable_ready";
      deliverableId?: string;
      label?: string;
      deliverableType?: string;
      filePath?: string;
      fileSizeBytes?: number;
      ts?: string;
    }
  | { type: "agent_done"; agentId?: string; label?: string }
  | { type: "agent_active"; agent: string }
  | { type: "agent_message"; agent: string; text: string }
  | { type: "phase_changed"; phase: string; label?: string }
  | { type: "run_end" };

export interface MissionEventStreamSubscription {
  close(): void;
}

export interface MissionEventStream {
  kind: "local" | "eventsource" | "fetch";
  connect(options: {
    missionId: string;
    onEvent: (event: MissionStreamEvent) => void;
    onStatusChange?: (state: BackendConnectionState) => void;
    onError?: (error: unknown) => void;
  }): MissionEventStreamSubscription;
  /** Send a chat message and stream the response */
  sendMessage?(text: string, reset?: boolean): Promise<void>;
}

export function createLocalMissionEventStream(): MissionEventStream {
  return {
    kind: "local",
    connect({ onStatusChange }) {
      onStatusChange?.("local");
      return { close() {} };
    },
  };
}

export function createEventSourceMissionEventStream(basePath = "/api/v1"): MissionEventStream {
  return {
    kind: "eventsource",
    connect({ missionId, onEvent, onStatusChange, onError }) {
      if (typeof window === "undefined" || typeof EventSource === "undefined") {
        onStatusChange?.("offline");
        return { close() {} };
      }

      onStatusChange?.("connecting");
      const source = new EventSource(`${basePath}/missions/${missionId}/chat`);

      source.onopen = () => onStatusChange?.("ready");
      source.onerror = (error) => {
        onStatusChange?.("offline");
        onError?.(error);
      };

      addListener(source, "text", onEvent, (payload) => ({
        type: "text",
        text: payload.text ?? payload.message ?? payload.content ?? "",
      }));
      addListener(source, "tool_call", onEvent, (payload) => ({
        type: "tool_call",
        text: payload.text ?? payload.name ?? "Tool call",
        agent: payload.agent,
      }));
      addListener(source, "tool_result", onEvent, (payload) => ({
        type: "tool_result",
        text: payload.text ?? payload.result ?? "Tool result",
        agent: payload.agent,
      }));
      addListener(source, "finding_added", onEvent, (payload) => ({
        type: "finding_added",
        text: payload.text ?? payload.finding ?? "Finding added",
        badge: payload.badge,
        findingId: payload.findingId,
        confidence: payload.confidence,
        agent: payload.agent,
        workstreamId: payload.workstreamId,
        hypothesisId: payload.hypothesisId,
        sourceId: payload.sourceId,
        ts: payload.ts,
      }));
      addListener(source, "milestone_done", onEvent, (payload) => ({
        type: "milestone_done",
        milestoneId: payload.milestoneId ?? payload.id,
        label: payload.label,
        workstreamId: payload.workstreamId,
        status: payload.status,
        resultSummary: payload.resultSummary,
      }));
      addListener(source, "phase_changed", onEvent, (payload) => ({
        type: "phase_changed",
        phase: String(payload.phase ?? ""),
        label: payload.label,
      }));
      addListener(source, "agent_message", onEvent, (payload) => ({
        type: "agent_message",
        agent: String(payload.agent ?? ""),
        text: String(payload.text ?? ""),
      }));
      addListener(source, "gate_pending", onEvent, (payload: any) => ({
        type: "gate_pending",
        gateId: payload.gateId ?? payload.id ?? payload.gate_id ?? "gate",
        gateType: payload.gate_type,
        format: payload.format,
        title: payload.title ?? payload.gate_type ?? "Gate review required",
        stage: payload.stage,
        summary: payload.summary,
        unlocksOnApprove: payload.unlocks_on_approve,
        unlocksOnReject: payload.unlocks_on_reject,
        hypotheses: payload.hypotheses,
        researchFindings: payload.research_findings,
        redteamFindings: payload.redteam_findings,
        arbiterFlags: payload.arbiter_flags,
        findingsTotal: payload.findings_total,
        questions: Array.isArray(payload.questions) ? payload.questions.map(String) : undefined,
        round: typeof payload.round === "number" ? payload.round : undefined,
        maxRounds: typeof payload.max_rounds === "number" ? payload.max_rounds : undefined,
      }));
      addListener(source, "deliverable_ready", onEvent, (payload) => ({
        type: "deliverable_ready",
        deliverableId: payload.deliverableId ?? payload.id,
        label: payload.label,
        deliverableType: payload.deliverableType,
        filePath: payload.filePath,
        fileSizeBytes:
          typeof payload.fileSizeBytes === "number"
            ? payload.fileSizeBytes
            : payload.fileSizeBytes
              ? Number(payload.fileSizeBytes)
              : undefined,
        ts: payload.ts,
      }));
      addListener(source, "agent_done", onEvent, (payload) => ({
        type: "agent_done",
        agentId: payload.agentId ?? payload.id,
        label: payload.label,
      }));
      addListener(source, "agent_active", onEvent, (payload) => ({
        type: "agent_active",
        agent: String(payload.agent ?? ""),
      }));
      addListener(source, "run_end", onEvent, () => ({ type: "run_end" }));

      return {
        close() {
          source.close();
        },
      };
    },
  };
}

/**
 * Fetch-based SSE stream that POSTs messages and consumes SSE response.
 * This is the preferred method for real backend integration.
 */
export function createFetchMissionEventStream(): MissionEventStream & { sendMessage: (text: string, reset?: boolean) => Promise<void> } {
  let abortController: AbortController | null = null;
  let currentMissionId: string | null = null;
  let currentOnEvent: ((event: MissionStreamEvent) => void) | null = null;
  let currentOnStatusChange: ((state: BackendConnectionState) => void) | null = null;
  let currentOnError: ((error: unknown) => void) | null = null;
  let isStreaming = false;

  async function handleStream(text: string, reset = false) {
    if (!currentMissionId || !currentOnEvent) return;

    if (isStreaming && abortController) {
      abortController.abort();
    }

    abortController = new AbortController();
    isStreaming = true;

    try {
      currentOnStatusChange?.("connecting");

      for await (const event of sendChatMessage(currentMissionId, text, reset, abortController.signal)) {
        // Map SSE event to frontend event
        const mappedEvent = mapSSEToStreamEvent(event);
        if (mappedEvent) {
          currentOnEvent(mappedEvent);
        }
      }

      currentOnStatusChange?.("ready");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        // Aborted, don't report as error
        return;
      }
      if (isBackendOfflineError(error)) {
        currentOnStatusChange?.("offline");
        currentOnError?.(error);
      } else {
        currentOnError?.(error);
      }
    } finally {
      isStreaming = false;
      currentOnStatusChange?.("ready");
    }
  }

  return {
    kind: "fetch",
    connect({ missionId, onEvent, onStatusChange, onError }) {
      currentMissionId = missionId;
      currentOnEvent = onEvent;
      currentOnStatusChange = onStatusChange ?? null;
      currentOnError = onError ?? null;
      
      onStatusChange?.("ready");

      return {
        close() {
          if (abortController) {
            abortController.abort();
          }
          currentMissionId = null;
          currentOnEvent = null;
          currentOnStatusChange = null;
          currentOnError = null;
        },
      };
    },
    async sendMessage(text: string, reset = false) {
      await handleStream(text, reset);
    },
  };
}

/**
 * Map SSE events from backend to frontend stream events
 */
function mapSSEToStreamEvent(event: SSEEvent): MissionStreamEvent | null {
  const eventType = event.type as string;
  
  switch (eventType) {
    case "text":
      return { type: "text", text: String(event.text ?? "") };
    case "tool_call":
      return { type: "tool_call", text: String(event.tool ?? ""), agent: event.agent ? String(event.agent) : undefined };
    case "tool_result":
      return { type: "tool_result", text: String(event.text ?? ""), agent: event.agent ? String(event.agent) : undefined };
    case "gate_pending": {
      const arbiterFlags = Array.isArray(event.arbiter_flags)
        ? (event.arbiter_flags as unknown[]).map(String)
        : undefined;
      const hypotheses = Array.isArray(event.hypotheses)
        ? (event.hypotheses as Array<Record<string, unknown>>).map((h) => ({
            id: String(h.id ?? ""),
            text: String(h.text ?? ""),
            status: String(h.status ?? ""),
          }))
        : undefined;
      const mapFindings = (raw: unknown) =>
        Array.isArray(raw)
          ? (raw as Array<Record<string, unknown>>).map((f) => ({
              claim_text: String(f.claim_text ?? ""),
              confidence: f.confidence == null ? null : String(f.confidence),
              agent_id: f.agent_id == null ? null : String(f.agent_id),
            }))
          : undefined;
      const questions = Array.isArray(event.questions)
        ? (event.questions as unknown[]).map(String)
        : undefined;
      return {
        type: "gate_pending",
        gateId: String(event.gate_id ?? event.gateId ?? "gate"),
        gateType: event.gate_type ? String(event.gate_type) : undefined,
        format: event.format ? String(event.format) : undefined,
        title: String(event.title ?? event.gate_type ?? "Gate review required"),
        stage: event.stage ? String(event.stage) : undefined,
        summary: event.summary ? String(event.summary) : undefined,
        unlocksOnApprove: event.unlocks_on_approve
          ? String(event.unlocks_on_approve)
          : undefined,
        unlocksOnReject: event.unlocks_on_reject
          ? String(event.unlocks_on_reject)
          : undefined,
        hypotheses,
        researchFindings: mapFindings(event.research_findings),
        redteamFindings: mapFindings(event.redteam_findings),
        arbiterFlags,
        findingsTotal:
          typeof event.findings_total === "number"
            ? (event.findings_total as number)
            : undefined,
        questions,
        round: typeof event.round === "number" ? (event.round as number) : undefined,
        maxRounds:
          typeof event.max_rounds === "number" ? (event.max_rounds as number) : undefined,
      };
    }
    case "finding_added":
      return {
        type: "finding_added",
        text: String(event.text ?? ""),
        badge: event.badge ? String(event.badge) : undefined,
        findingId: event.findingId ? String(event.findingId) : undefined,
        confidence: event.confidence ? String(event.confidence) : undefined,
        agent: event.agent ? String(event.agent) : undefined,
        workstreamId: event.workstreamId ? String(event.workstreamId) : undefined,
        hypothesisId: event.hypothesisId ? String(event.hypothesisId) : undefined,
        sourceId: event.sourceId ? String(event.sourceId) : undefined,
        ts: event.ts ? String(event.ts) : undefined,
      };
    case "milestone_done":
      return {
        type: "milestone_done",
        milestoneId: event.milestoneId ? String(event.milestoneId) : undefined,
        label: event.label ? String(event.label) : undefined,
        workstreamId: event.workstreamId ? String(event.workstreamId) : undefined,
        status: event.status ? String(event.status) : undefined,
        resultSummary: event.resultSummary ? String(event.resultSummary) : undefined,
      };
    case "deliverable_ready":
      return {
        type: "deliverable_ready",
        deliverableId: event.deliverableId ? String(event.deliverableId) : undefined,
        label: event.label ? String(event.label) : undefined,
        deliverableType: event.deliverableType ? String(event.deliverableType) : undefined,
        filePath: event.filePath ? String(event.filePath) : undefined,
        fileSizeBytes:
          typeof event.fileSizeBytes === "number"
            ? (event.fileSizeBytes as number)
            : event.fileSizeBytes
              ? Number(event.fileSizeBytes)
              : undefined,
        ts: event.ts ? String(event.ts) : undefined,
      };
    case "agent_done":
      return { type: "agent_done", label: event.agent ? String(event.agent) : undefined };
    case "agent_active":
      return { type: "agent_active", agent: String(event.agent ?? "") };
    case "phase_changed":
      return {
        type: "phase_changed",
        phase: String(event.phase ?? ""),
        label: event.label ? String(event.label) : undefined,
      };
    case "agent_message":
      return {
        type: "agent_message",
        agent: String(event.agent ?? ""),
        text: String(event.text ?? ""),
      };
    case "run_end":
      return { type: "run_end" };
    case "run_start":
    case "error":
      // These are handled internally
      return null;
    default:
      return null;
  }
}

export const localMissionEventStream = createLocalMissionEventStream();
export const fetchMissionEventStream = createFetchMissionEventStream();

function addListener(
  source: EventSource,
  eventName: string,
  onEvent: (event: MissionStreamEvent) => void,
  mapPayload: (payload: Record<string, string>) => MissionStreamEvent,
) {
  source.addEventListener(eventName, (event) => {
    const payload = parsePayload((event as MessageEvent<string>).data);
    onEvent(mapPayload(payload));
  });
}

function parsePayload(data: string): Record<string, string> {
  try {
    return JSON.parse(data) as Record<string, string>;
  } catch {
    return { text: data };
  }
}

export function createGateModalState(payload: MissionGateModalState): MissionGateModalState {
  return payload;
}
