"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import type { ComponentType } from "react";
import Link from "next/link";
import { MissionControlV2View as RawMissionControlView } from "./v2/MissionControlV2View";
import {
  buildInitialMessages,
  DEFAULT_WORKSPACE_TAB,
  formatDeliverableDisplayName,
  formatDeliverableReadyChatMessage,
  formatGatePendingChatMessage,
  formatGatePendingFeedSignal,
  formatNarrationChatMessage,
  routeDeliverableToSectionId,
} from "@/lib/missions/adapters";
import {
  type MissionEventStream,
  fetchMissionEventStream,
  localMissionEventStream,
} from "@/lib/missions/events";
import {
  type MissionRepository,
  isBackendOfflineError,
  httpMissionRepository,
  localMissionRepository,
} from "@/lib/missions/repository";
import { useMissionUiStore } from "@/lib/missions/store";
import {
  selectChatDraft,
  selectRunState,
  selectWorkspaceTab,
} from "@/lib/missions/selectors";
import type {
  BackendConnectionState,
  Mission,
  MissionChatMessage,
  MissionGateModalState,
  WorkspaceTab,
} from "@/lib/missions/types";
import {
  validateGate as apiValidateGate,
  validateGateDecision as apiValidateGateDecision,
  submitClarificationAnswers as apiSubmitClarificationAnswers,
  getMissionProgress,
  getMissionEvents,
  getDeliverableDownloadUrl,
  rerunAgent as apiRerunAgent,
} from "@/lib/missions/api";
import { mapGateReviewPayloadToModal } from "@/lib/missions/gate-review";
import { shouldAttachResumeStream } from "@/lib/missions/gate-resume";
import { normalizeAgentName } from "@/lib/missions/agent-display";
import { DeliverablePreview } from "./DeliverablePreview";

let _msgCounter = 0;
function makeMessageId(missionId: string, suffix: string): string {
  _msgCounter += 1;
  const rand = Math.random().toString(36).slice(2, 8);
  return `${missionId}-${Date.now()}-${_msgCounter}-${rand}-${suffix}`;
}

// Tool calls whose business outcome is already surfaced as a richer event
// (finding_added, milestone_done, deliverable_ready, gate_pending) — keeping
// them in the live tool-tape would just be noise.
const NOISY_TOOL_NAMES = new Set([
  "add_finding_to_mission",
  "add_source_to_finding",
  "mark_milestone_delivered",
  "mark_milestone_blocked",
  "set_merlin_verdict",
  "generate_engagement_brief",
  "generate_workstream_report",
  "generate_exec_summary",
  // tavily_search, search_sec_filings, fetch_filing_section, query_data_room,
  // query_transcripts intentionally NOT here — they show real work in the feed.
]);

function isNoisyTool(raw: unknown): boolean {
  const name = String(raw ?? "").trim().toLowerCase();
  if (!name) return false;
  if (NOISY_TOOL_NAMES.has(name)) return true;
  // Anything _persisted is a side-effect echo, not a user-meaningful call.
  if (name.endsWith("_persisted")) return true;
  return false;
}

const TOOL_FRIENDLY_NAMES: Record<string, string> = {
  fetch_filing_section: "reading SEC filing",
  search_sec_filings: "searching SEC filings",
  resolve_cik: "resolving company CIK",
  list_filings: "listing SEC filings",
  tavily_search: "web search",
  query_data_room: "querying data room",
  query_transcripts: "scanning transcripts",
  get_findings: "reading findings",
  get_hypotheses: "reading hypotheses",
  check_internal_consistency: "checking internal consistency",
  recompute_mission_corroboration: "recomputing source corroboration",
};

function humanizeToolName(raw: unknown): string {
  const name = String(raw ?? "tool").trim();
  if (!name) return "tool";
  const friendly = TOOL_FRIENDLY_NAMES[name.toLowerCase()];
  if (friendly) return friendly;
  return name.replace(/_/g, " ");
}

// Cap the live event feed so a long mission doesn't accumulate thousands of
// rows in memory or scroll the rail forever.
const MAX_LIVE_TAPE_ENTRIES = 60;

// Verdict labelling and prose sanitisation moved to lib/missions/humanize.ts
// (single source of truth used by every rendering boundary).
import { humanizeText, humanizeVerdict } from "@/lib/missions/humanize";

// Local alias for clarity at call sites that strip internal scaffolding.
const stripVerdictScaffolding = humanizeText;

function humanizeToolResultText(raw: unknown): string {
  const text = String(raw ?? "").trim();
  if (!text) return "step complete";
  if (text.startsWith("{") || text.startsWith("[")) return "step complete";
  return text.length > 200 ? text.slice(0, 200).trimEnd() + "…" : text;
}

function shortenAgentMessage(raw: unknown): string {
  const text = String(raw ?? "").trim();
  if (!text) return "(empty)";
  return text.length > 220 ? text.slice(0, 220).trimEnd() + "…" : text;
}

// Extended view props that include gate validation handlers
interface MissionControlViewProps {
  mission: Mission;
  messages: MissionChatMessage[];
  initialMessages: MissionChatMessage[];
  chatDraft: string;
  onChatDraftChange: (value: string) => void;
  onSendMessage: (value: string) => void;
  selectedTab: WorkspaceTab;
  onSelectTab: (tab: WorkspaceTab) => void;
  isTyping: boolean;
  defaultTab: WorkspaceTab;
  gateModal?: MissionGateModalState | null;
  onGateClose: () => void;
  onGateApprove?: (gateId: string, notes: string) => void;
  onGateReject?: (gateId: string, notes: string) => void;
  backendState?: BackendConnectionState;
  agents: { id: string; name: string; role: string; status: string; milestonesTotal?: number; milestonesDelivered?: number }[];
  checkpoints: { id: string; label: string; status: string }[];
  hypotheses: {
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
  }[];
  activity?: Array<{ id: string; ag?: string; text?: string; ts?: string; claim_text?: string; confidence?: string }>;
  findings: Array<{
    id: string;
    kind?: "finding" | "milestone" | "deliverable";
    agent_id?: string | null;
    claim_text?: string;
    confidence?: string | null;
    ag?: string;
    text?: string;
    ts?: string;
    workstream_id?: string | null;
    hypothesis_id?: string | null;
    hypothesis_label?: string | null;
    source_id?: string | null;
    source_type?: string | null;
    impact?: "load_bearing" | "supporting" | "color" | null;
    href?: string;
    onOpen?: () => void;
    output_label?: string;
    section_id?: string | null;
  }>;
  deliverables: { id: string; label: string; status: string; href?: string; onOpen?: () => void }[];
  activeAgent: string | null;
  currentNarration?: string | null;
  sectionTabs?: {
    id: WorkspaceTab;
    label: string;
    status?: "pending" | "now" | "in_progress" | "completed";
  }[];
  workstreamContent?: {
    id: string;
    label: string;
    status?: "pending" | "now" | "in_progress" | "completed";
    findings: Array<{ id: string; claim_text: string; confidence: string | null; agent_id: string | null }>;
    milestones: Array<{ id: string; label: string; status: string }>;
  }[];
  pendingGateBanner?: {
    onResume: () => void;
    onApprove?: () => void;
    onReject?: () => void;
    actionInFlight?: "approve" | "reject" | null;
    title?: string;
    summary?: string;
    gateId?: string;
  } | null;
  briefStatus?: "pending" | "now" | "completed";
  nextCheckpointLabel?: string | null;
  completedTitle?: string;
  completedEmptyText?: string;
  waitState?: {
    isWorking: boolean;
    showInOutputs: boolean;
    isStalled: boolean;
    elapsedLabel: string;
    message: string;
    headline: string;
  };
  onOpenDeliverable?: (deliverableId: string) => void;
}

const MissionControlView = RawMissionControlView as unknown as ComponentType<MissionControlViewProps>;
type MissionProgressSnapshot = Awaited<ReturnType<typeof getMissionProgress>>;
type WorkstreamViewStatus = "pending" | "now" | "in_progress" | "completed";
type LiveFindingEvent = {
  id: string;
  kind:
    | "finding"
    | "milestone"
    | "deliverable"
    | "gate"
    | "phase"
    | "agent"
    | "agent_message"
    | "tool_call"
    | "tool_result"
    | "narration";
  claim_text: string;
  confidence?: string;
  agent?: string;
  workstreamId?: string;
  hypothesisId?: string;
  ts?: string;
  href?: string;
};

function liveEventKey(event: Pick<LiveFindingEvent, "kind" | "id">): string {
  return `${event.kind}:${event.id}`;
}

function upsertLiveEvent(current: LiveFindingEvent[], event: LiveFindingEvent): LiveFindingEvent[] {
  const key = liveEventKey(event);
  const existingIndex = current.findIndex((item) => liveEventKey(item) === key);
  if (existingIndex === -1) return current.concat(event);
  const next = current.slice();
  next[existingIndex] = { ...next[existingIndex], ...event };
  return next;
}

function dedupeByKey<T>(items: T[], getKey: (item: T) => string): T[] {
  const byKey = new Map<string, T>();
  for (const item of items) byKey.set(getKey(item), item);
  return Array.from(byKey.values());
}

function formatElapsed(seconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = String(safeSeconds % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function assertGateLifecycleContract(data: MissionProgressSnapshot): void {
  for (const gate of data.gates ?? []) {
    if (typeof gate.lifecycle_status !== "string" || typeof gate.is_open !== "boolean") {
      throw new Error("Backend /progress gate payload is missing lifecycle_status/is_open");
    }
  }
}

// C-RESUME-RECOVERY: render a fixed banner when any gate is in
// status="failed" with a structured failure_reason. Offers a "Rerun {agent}"
// button that re-enters only the failed node (research is not replayed).
function TransientFailureBanner({
  gates,
  missionId,
  onRerunStarted,
}: {
  gates: Array<{
    id: string;
    status: string;
    failure_reason: {
      agent: string;
      error: string;
      cause: string;
      retries_exhausted: number;
    } | null;
  }>;
  missionId: string;
  onRerunStarted: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const failed = gates.find(
    (g) => g.status === "failed" && g.failure_reason && g.failure_reason.agent,
  );
  if (!failed || !failed.failure_reason) return null;

  const agent = failed.failure_reason.agent as "adversus" | "merlin";
  const cause = failed.failure_reason.cause;
  const attempts = failed.failure_reason.retries_exhausted;
  const agentLabel = agent.charAt(0).toUpperCase() + agent.slice(1);

  const handleRerun = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await apiRerunAgent(missionId, agent);
      onRerunStarted();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Rerun failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      role="alert"
      aria-label={`${agentLabel} failed`}
      style={{
        position: "fixed",
        top: "16px",
        right: "16px",
        width: "min(420px, calc(100vw - 32px))",
        background: "#fff5f5",
        border: "1px solid #f5b5b5",
        borderRadius: "10px",
        boxShadow: "0 12px 32px rgba(120, 30, 30, .18)",
        padding: "14px 16px",
        zIndex: 950,
      }}
    >
      <div style={{ fontWeight: 600, color: "#8a1d1d", marginBottom: "4px" }}>
        {agentLabel} failed — upstream LLM unavailable
      </div>
      <div style={{ fontSize: "13px", color: "#5a2222", marginBottom: "10px" }}>
        {cause} · {attempts} attempts. Click Rerun {agentLabel} to retry from
        this node only — research is not replayed.
      </div>
      {error ? (
        <div style={{ fontSize: "12px", color: "#7a1d1d", marginBottom: "8px" }}>
          {error}
        </div>
      ) : null}
      <button
        type="button"
        onClick={handleRerun}
        disabled={submitting}
        style={{
          background: submitting ? "#d49797" : "#b03434",
          color: "#fff",
          border: 0,
          borderRadius: "6px",
          padding: "8px 14px",
          fontSize: "13px",
          fontWeight: 600,
          cursor: submitting ? "default" : "pointer",
        }}
      >
        {submitting ? "Restarting…" : `Rerun ${agentLabel}`}
      </button>
    </div>
  );
}

export default function MissionControl({
  missionId,
  repository = httpMissionRepository,
  eventStream = fetchMissionEventStream,
}: {
  missionId: string;
  repository?: MissionRepository;
  eventStream?: MissionEventStream;
}) {
  const [mission, setMission] = useState<Mission | null>(null);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [messages, setMessages] = useState<MissionChatMessage[]>([]);
  const [gateModal, setGateModal] = useState<MissionGateModalState | null>(null);
  const [backendState, setBackendState] = useState<BackendConnectionState>(
    repository.kind === "local" ? "local" : "connecting",
  );
  const [isOffline, setIsOffline] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [isStalled, setIsStalled] = useState(false);
  const [streamStartedAt, setStreamStartedAt] = useState<number | null>(null);
  const [streamElapsedSeconds, setStreamElapsedSeconds] = useState(0);
  const [gateActionInFlight, setGateActionInFlight] = useState<{
    gateId: string;
    action: "approve" | "reject" | "decision" | "clarification";
  } | null>(null);
  const [resolvingGateIds, setResolvingGateIds] = useState<Set<string>>(new Set());
  const lastEventAtRef = useRef<number>(Date.now());

  // Progress state for real-time data from backend
  const [progress, setProgress] = useState<MissionProgressSnapshot | null>(null);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [activeAgentSince, setActiveAgentSince] = useState<number | null>(null);
  const [activeAgentElapsed, setActiveAgentElapsed] = useState(0);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, "idle" | "active" | "done">>({});
  const [latestNarration, setLatestNarration] = useState<string | null>(null);
  // Bug #6a: track which agent owns the current narration so we can clear it
  // when that agent emits `agent_done` (otherwise stale "Calculus — still
  // working" lingers in chat after the sidebar already shows DONE).
  const narrationAgentRef = useRef<string | null>(null);
  // Bug #6b: tab follows phase until the user manually picks one. Reset on
  // phase changes so subsequent transitions auto-advance again.
  const userPickedTabRef = useRef<boolean>(false);
  const [liveFindings, setLiveFindings] = useState<LiveFindingEvent[]>([]);
  const [milestoneStatusOverrides, setMilestoneStatusOverrides] = useState<Record<string, string>>({});
  const [gatePayloads, setGatePayloads] = useState<Record<string, MissionGateModalState>>({});
  const [pausedForGate, setPausedForGate] = useState(false);
  const [clarificationGate, setClarificationGate] = useState<MissionGateModalState | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<string[]>([]);
  // Chantier 4 CP3: deliverable inline preview modal state.
  const [previewDeliverableId, setPreviewDeliverableId] = useState<string | null>(null);
  const [clarificationSubmitting, setClarificationSubmitting] = useState(false);
  const resumeTimerRef = useRef<number | null>(null);
  const announcedDeliverablesRef = useRef<Set<string>>(new Set());

  const markGateResolving = useCallback((gateId: string) => {
    setResolvingGateIds((current) => {
      const next = new Set(current);
      next.add(gateId);
      return next;
    });
  }, []);

  const clearGateResolving = useCallback((gateId: string) => {
    setResolvingGateIds((current) => {
      if (!current.has(gateId)) return current;
      const next = new Set(current);
      next.delete(gateId);
      return next;
    });
  }, []);

  const chatDraft = useMissionUiStore((state) => selectChatDraft(state, missionId));
  const selectedTab = useMissionUiStore((state) => selectWorkspaceTab(state, missionId));
  const runState = useMissionUiStore((state) => selectRunState(state, missionId));
  const setChatDraft = useMissionUiStore((state) => state.setChatDraft);
  const setWorkspaceTab = useMissionUiStore((state) => state.setWorkspaceTab);
  const setRunState = useMissionUiStore((state) => state.setRunState);

  // Fetch /progress for center/deliverables/agents/checkpoints. Refreshed
  // on mount and again on key persistence events (milestone_done,
  // deliverable_ready, finding_added) so the UI reflects backend truth.
  const refreshProgress = useCallback(async () => {
    if (repository.kind !== "http") return;
    try {
      const data = await getMissionProgress(missionId);
      assertGateLifecycleContract(data);
      setProgress(data);
    } catch (error) {
      console.error("Failed to load mission progress:", error);
    }
  }, [missionId, repository.kind]);

  useEffect(() => {
    void refreshProgress();
  }, [refreshProgress]);

  // Tick elapsed seconds while an agent is active so the wait headline shows
  // how long the agent has been running.
  useEffect(() => {
    if (activeAgentSince === null) {
      setActiveAgentElapsed(0);
      return;
    }
    const interval = window.setInterval(() => {
      setActiveAgentElapsed(Math.floor((Date.now() - activeAgentSince) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [activeAgentSince]);

  const announceDeliverableReady = useCallback(
    (
      deliverableId: string | undefined,
      deliverable: { deliverableType?: unknown; label?: unknown; filePath?: unknown },
      { announce = true } = {},
    ) => {
      const key = deliverableId || String(deliverable.deliverableType ?? deliverable.label ?? "deliverable");
      if (announcedDeliverablesRef.current.has(key)) return;
      announcedDeliverablesRef.current.add(key);
      if (!announce) return;
      const label = formatDeliverableDisplayName({
        deliverable_type: deliverable.deliverableType ?? deliverable.label,
        file_path: deliverable.filePath,
      });
      setMessages((current) =>
        current.concat({
          id: makeMessageId(missionId, "deliverable-chat"),
          from: "m",
          text: formatDeliverableReadyChatMessage(label),
          deliverableId: deliverableId,
          deliverableLabel: label,
        }),
      );
    },
    [missionId],
  );

  const refreshMissionEvents = useCallback(async ({ replace = false } = {}) => {
    if (repository.kind !== "http") return;
    try {
      const { events } = await getMissionEvents(missionId);
      for (const evt of events) {
        if (evt.type === "deliverable_ready") {
          announceDeliverableReady(
            evt.deliverableId,
            {
              deliverableType: evt.deliverableType ?? evt.label,
              label: evt.label,
              filePath: evt.filePath,
            },
            { announce: !replace },
          );
        }
      }
      const hydrated = events.map((evt) => {
        if (evt.type === "finding_added") {
          return {
            id: evt.findingId ?? `${missionId}-${evt.ts ?? ""}-finding`,
            kind: "finding" as const,
            claim_text: evt.text ?? "",
            confidence: evt.confidence ?? undefined,
            agent: evt.agent ?? undefined,
            workstreamId: evt.workstreamId ?? undefined,
            hypothesisId: evt.hypothesisId ?? undefined,
            ts: evt.ts,
          };
        }
        if (evt.type === "milestone_done") {
          return {
            id: evt.milestoneId ?? `${missionId}-${evt.ts ?? ""}-milestone`,
            kind: "milestone" as const,
            claim_text: evt.label
              ? `Milestone complete · ${evt.label}`
              : `Milestone complete · ${evt.milestoneId ?? "step"}`,
            confidence: "done",
            workstreamId: evt.workstreamId ?? undefined,
            ts: evt.ts,
          };
        }
        if (evt.type === "deliverable_ready") {
          return {
            id: evt.deliverableId ?? `${missionId}-${evt.ts ?? ""}-deliverable`,
            kind: "deliverable" as const,
            claim_text: `Deliverable ready · ${formatDeliverableDisplayName({
              deliverable_type: evt.deliverableType ?? evt.label,
              file_path: evt.filePath,
            })}`,
            confidence: "ready",
            ts: evt.ts,
            href: evt.filePath
              ? getDeliverableDownloadUrl(evt.filePath)
              : undefined,
          };
        }
        // gate_resolved
        return {
          id: evt.gateId ?? `${missionId}-${evt.ts ?? ""}-gate`,
          kind: "gate" as const,
          claim_text: `Gate ${evt.status ?? "resolved"} · ${evt.gateType ?? evt.gateId ?? ""}`,
          confidence: evt.status ?? "gate",
          ts: evt.ts,
        };
      });

      if (replace) {
        // Replace rather than append: this is the source-of-truth snapshot.
        setLiveFindings(dedupeByKey(hydrated, liveEventKey));
        return;
      }

      setLiveFindings((current) => {
        const byId = new Map(current.map((event) => [liveEventKey(event), event]));
        for (const event of hydrated) {
          byId.set(liveEventKey(event), event);
        }
        return Array.from(byId.values());
      });
    } catch (error) {
      console.error("Failed to hydrate mission events:", error);
    }
  }, [announceDeliverableReady, missionId, repository.kind]);

  // Hydrate the live rail from persisted events so a refresh restores the
  // chronology instead of starting empty (CLAUDE.md invariant: UI reflects
  // backend truth — the rail is a view onto persisted state, not session-only).
  useEffect(() => {
    void refreshMissionEvents({ replace: true });
  }, [refreshMissionEvents]);

  // Load mission on mount
  useEffect(() => {
    let cancelled = false;

    async function loadMission() {
      try {
        const nextMission = await repository.getMission(missionId);

        if (cancelled) {
          return;
        }

        setMission(nextMission);
        setMessages((current) =>
          current.length > 0 ? current : nextMission ? buildInitialMessages(nextMission) : [],
        );
        setBackendState(repository.kind === "local" ? "local" : "ready");
        setIsOffline(false);
      } catch (error) {
        if (cancelled) {
          return;
        }

        if (isBackendOfflineError(error)) {
          setIsOffline(true);
          setBackendState("offline");
          setMission(null);
          setMessages([]);
        } else {
          throw error;
        }
      } finally {
        if (!cancelled) {
          setHasLoaded(true);
        }
      }
    }

    void loadMission();

    return () => {
      cancelled = true;
    };
  }, [missionId, repository]);

  // Set up SSE event stream connection
  useEffect(() => {
    // Only set up connection for fetch-based streams (real backend)
    if (eventStream.kind !== "fetch") {
      // For local/eventsource streams, just set status
      if (eventStream.kind === "local") {
        setBackendState("local");
      }
      return;
    }

    const subscription = eventStream.connect({
      missionId,
      onStatusChange: (state) => {
        setBackendState(state);
        if (state === "ready") {
          setIsOffline(false);
        }
      },
      onEvent: (event) => {
        lastEventAtRef.current = Date.now();
        setIsStalled(false);
        switch (event.type) {
          case "text":
            setMessages((current) =>
              current.concat({
                id: makeMessageId(missionId, "stream"),
                from: "m",
                text: event.text,
              }),
            );
            break;
          case "tool_call":
            // Tool plumbing belongs in the rail (transparency on agent
            // activity), never in chat. Chat is reserved for Marvin's voice.
            // Drop noisy persistence echoes — those have richer events of
            // their own (finding_added, milestone_done, …).
            if (isNoisyTool(event.text)) break;
            {
              const friendly = humanizeToolName(event.text);
              if (event.agent && friendly) {
                const agentDisplay = normalizeAgentName(event.agent);
                setLatestNarration(`${agentDisplay} — ${friendly}…`);
                narrationAgentRef.current = String(event.agent).toLowerCase();
              }
            }
            setLiveFindings((current) => {
              const next = upsertLiveEvent(current, {
                id: makeMessageId(missionId, "tool"),
                kind: "tool_call",
                claim_text: `${event.agent ?? "Agent"} → ${humanizeToolName(event.text)}`,
                agent: event.agent,
              });
              return next.length > MAX_LIVE_TAPE_ENTRIES
                ? next.slice(next.length - MAX_LIVE_TAPE_ENTRIES)
                : next;
            });
            break;
          case "tool_result":
            if (isNoisyTool(event.text)) break;
            setLiveFindings((current) => {
              const next = upsertLiveEvent(current, {
                id: makeMessageId(missionId, "result"),
                kind: "tool_result",
                claim_text: humanizeToolResultText(event.text),
                agent: event.agent,
              });
              return next.length > MAX_LIVE_TAPE_ENTRIES
                ? next.slice(next.length - MAX_LIVE_TAPE_ENTRIES)
                : next;
            });
            break;
          case "agent_message":
            // Sub-agent prose (Dora/Calculus/Adversus/Merlin reasoning) goes
            // to the rail, not chat — keeps chat focused on Marvin's voice
            // while still showing what working agents are thinking.
            setLiveFindings((current) =>
              upsertLiveEvent(current, {
                id: makeMessageId(missionId, "agent-msg"),
                kind: "agent_message",
                claim_text: shortenAgentMessage(event.text),
                agent: event.agent,
              }),
            );
            break;
          case "narration": {
            if (!event.intent.trim()) {
              break;
            }
            const narrationText = formatNarrationChatMessage({
              agent: normalizeAgentName(event.agent),
              intent: event.intent,
            });
            setLatestNarration(narrationText);
            narrationAgentRef.current = event.agent ? String(event.agent).toLowerCase() : null;
            setMessages((current) => {
              const last = current[current.length - 1];
              if (last?.from === "m" && last.text === narrationText) {
                return current;
              }
              return current.concat({
                id: makeMessageId(missionId, "narration-chat"),
                from: "m",
                text: narrationText,
              });
            });
            // Replace any existing narration entry from the same agent so only
            // the latest intent is visible in the in-progress block.
            setLiveFindings((current) => {
              const filtered = current.filter(
                (e) => !(e.kind === "narration" && e.agent === event.agent),
              );
              return filtered.concat({
                id: makeMessageId(missionId, "narration"),
                kind: "narration",
                claim_text: event.intent,
                agent: event.agent,
                ts: event.ts,
              });
            });
            break;
          }
          case "gate_pending": {
            // Chat-first gate UX. The modal no longer auto-opens; instead the
            // gate is announced in chat and signalled in the live feed. The
            // persistent banner (derived from progress.gates) is the entry
            // point that opens the detailed review surface on user action.
            // Source of truth for gate state remains the backend gate row.
            const modalPayload = mapGateReviewPayloadToModal(event);

            if (modalPayload.format === "clarification_questions") {
              // Inline clarification flow — render a panel above the chat
              // composer instead of routing through the gate modal pathway.
              const questions = modalPayload.questions ?? [];
              setClarificationGate(modalPayload);
              setClarificationAnswers(questions.map(() => ""));
              setClarificationSubmitting(false);
              setLiveFindings((current) =>
                upsertLiveEvent(current, {
                  id: makeMessageId(missionId, "clarif-signal"),
                  kind: "gate",
                  claim_text: `Clarification round ${modalPayload.round ?? 1} of ${
                    modalPayload.maxRounds ?? 3
                  } — ${questions.length} question${questions.length === 1 ? "" : "s"}`,
                  confidence: "gate",
                }),
              );
              setPausedForGate(true);
              setLatestNarration(null);
              setRunState(missionId, { isStreaming: false });
              void refreshProgress();
              break;
            }

            setGatePayloads((current) => ({
              ...current,
              [modalPayload.gateId]: modalPayload,
            }));
            const gateMsgId = `${modalPayload.gateId}-gate-pending`;
            const gateFeedId = `${modalPayload.gateId}-gate-signal`;
            setMessages((current) => {
              if (current.some((m) => m.id === gateMsgId)) return current;
              return current.concat({
                id: gateMsgId,
                from: "m",
                text: formatGatePendingChatMessage(event),
                gateId: modalPayload.gateId,
                gateAction: "pending",
              });
            });
            setLiveFindings((current) => {
              if (current.some((f) => f.id === gateFeedId)) return current;
              return upsertLiveEvent(current, {
                id: gateFeedId,
                kind: "gate",
                claim_text: formatGatePendingFeedSignal(event),
                confidence: "gate",
              });
            });
            setPausedForGate(true);
            setLatestNarration(null);
            setRunState(missionId, { isStreaming: false });
            void refreshProgress();
            break;
          }
          case "agent_active": {
            const display = normalizeAgentName(event.agent);
            setActiveAgent(display);
            setActiveAgentSince(Date.now());
            setAgentStatuses((current) => ({
              ...current,
              [(event.agent ?? "unknown").toLowerCase()]: "active",
            }));
            setLiveFindings((current) =>
              upsertLiveEvent(current, {
                id: makeMessageId(missionId, "agent-active"),
                kind: "agent",
                claim_text: `${display} started`,
                confidence: "active",
                agent: display,
              }),
            );
            break;
          }
          case "agent_done": {
            setActiveAgent(null);
            setActiveAgentSince(null);
            setActiveAgentElapsed(0);
            const display = normalizeAgentName(event.label);
            if (event.label) {
              const lower = event.label.toLowerCase();
              setAgentStatuses((current) => ({
                ...current,
                [lower]: "done",
              }));
              // Bug #6a: replace stale narration with a positive "done"
              // signal so the user sees the transition explicitly. The
              // narration is cleared on the next narration / phase change.
              if (narrationAgentRef.current === lower) {
                setLatestNarration(`${display} — step complete.`);
                narrationAgentRef.current = null;
              }
            }
            setLiveFindings((current) =>
              upsertLiveEvent(current, {
                id: makeMessageId(missionId, "agent-done"),
                kind: "agent",
                claim_text: `${display} finished`,
                confidence: "done",
                agent: display,
              }),
            );
            break;
          }
          case "phase_changed":
            if (event.phase && event.phase !== "awaiting_confirmation") {
              setResolvingGateIds(new Set());
            }
            // Bug #6b: a phase boundary re-arms tab auto-follow so the
            // highlighted tab tracks the new active step until the user
            // manually picks one again.
            userPickedTabRef.current = false;
            setLiveFindings((current) =>
              upsertLiveEvent(current, {
                id: makeMessageId(missionId, "phase"),
                kind: "phase",
                claim_text: `Phase · ${event.label ?? event.phase}`,
                confidence: "phase",
              }),
            );
            // A phase transition flips the active gate, the agent activation
            // map, and milestone scheduling. The detached-resume path emits
            // phase_changed but does not push a fresh /progress payload —
            // re-fetch so the center pane reflects backend truth.
            void refreshProgress();
            void refreshMissionEvents();
            break;
          case "finding_added":
            // A finding implies the producing agent is alive even if no
            // explicit `agent_active` SSE wrapped this work. Without this,
            // the left-rail agents stay IDLE while the activity feed shows
            // them streaming claims (observed live with adversus).
            if (event.agent) {
              const agentLower = String(event.agent).toLowerCase();
              setAgentStatuses((current) => {
                if (current[agentLower] === "done") return current;
                if (current[agentLower] === "active") return current;
                return { ...current, [agentLower]: "active" };
              });
            }
            setLiveFindings((current) =>
              upsertLiveEvent(current, {
                id: event.findingId ?? makeMessageId(missionId, "finding"),
                kind: "finding",
                claim_text: event.text,
                confidence: event.confidence ?? event.badge,
                agent: event.agent,
                workstreamId: event.workstreamId,
                hypothesisId: event.hypothesisId,
                ts: event.ts,
              }),
            );
            break;
          case "milestone_done":
            if (event.milestoneId) {
              setMilestoneStatusOverrides((current) => ({
                ...current,
                [event.milestoneId as string]: "delivered",
              }));
            }
            setLiveFindings((current) =>
              upsertLiveEvent(current, {
                id: event.milestoneId ?? makeMessageId(missionId, "milestone"),
                kind: "milestone",
                claim_text: event.label
                  ? `Milestone complete · ${event.label}`
                  : `Milestone complete · ${event.milestoneId ?? "mission step"}`,
                confidence: "done",
                workstreamId: event.workstreamId,
              }),
            );
            void refreshProgress();
            break;
          case "deliverable_ready":
            announceDeliverableReady(
              event.deliverableId,
              {
                deliverableType: event.deliverableType ?? event.label,
                label: event.label,
                filePath: event.filePath,
              },
            );
            setLiveFindings((current) =>
              upsertLiveEvent(current, {
                id: event.deliverableId ?? makeMessageId(missionId, "deliverable"),
                kind: "deliverable",
                claim_text: event.label
                  ? `Deliverable ready · ${formatDeliverableDisplayName({
                      deliverable_type: event.deliverableType ?? event.label,
                      file_path: event.filePath,
                    })}`
                  : "Deliverable ready",
                confidence: "ready",
                ts: event.ts,
                href: event.filePath
                  ? getDeliverableDownloadUrl(event.filePath)
                  : undefined,
              }),
            );
            void refreshProgress();
            break;
          case "run_end":
            setPausedForGate(false);
            setLatestNarration(null);
            setRunState(missionId, { isStreaming: false });
            setGateActionInFlight(null);
            // Multi-stage refresh: a detached driver may emit deliverables
            // (notably the final IC memo from papyrus_delivery) AFTER
            // run_end fires on the user's stream. announceDeliverableReady
            // dedupes via Ref, so polling at 0.5s/3s/10s catches stragglers
            // without spamming chat.
            for (const delay of [500, 3000, 10000]) {
              window.setTimeout(() => {
                void refreshProgress();
                void refreshMissionEvents();
              }, delay);
            }
            break;
          default:
            break;
        }
      },
      onError: (error) => {
        console.error("SSE error:", error);
        setIsOffline(eventStream.kind === "fetch");
        setBackendState(eventStream.kind === "fetch" ? "offline" : "local");
        setStreamError(error instanceof Error ? error.message : "Connection error");
      },
    });

    return () => {
      subscription.close();
    };
  }, [eventStream, missionId, setRunState, refreshProgress, refreshMissionEvents, announceDeliverableReady]);

  // Chantier 2.7 FIX 2 — re-attach to checkpointed mission on mount.
  // Recovers tab close, network blip, and uvicorn restart. Backend emits
  // run_end when there's no checkpoint, so this is safe for fresh missions.
  useEffect(() => {
    if (!hasLoaded) return;
    if (eventStream.kind !== "fetch") return;
    const stream = eventStream as MissionEventStream & { resume?: () => Promise<void> };
    if (typeof stream.resume !== "function") return;
    if (!mission || mission.status !== "active") return;
    void stream.resume();
  }, [eventStream, hasLoaded, mission, missionId]);

  useEffect(() => {
    setRunState(missionId, { isStreaming: false });
  }, [missionId, setRunState]);

  useEffect(() => {
    return () => {
      if (resumeTimerRef.current !== null) {
        window.clearTimeout(resumeTimerRef.current);
        resumeTimerRef.current = null;
      }
    };
  }, []);

  // Handle sending a message
  const handleSendMessage = useCallback(
    async (text: string) => {
      const value = text.trim();

      if (!value || !mission) {
        return;
      }

      // Clear draft
      setChatDraft(mission.id, "");

      // Add user message immediately
      // Agent status tracking for text events
      setMessages((current) =>
        current.concat({
          id: makeMessageId(mission.id, "user"),
          from: "u",
          text: value,
        }),
      );

      // Set streaming state
      setRunState(mission.id, { isStreaming: true });
      setLiveFindings((current) =>
        upsertLiveEvent(current, {
          id: "startup",
          kind: "phase",
          agent: "Workflow",
          claim_text: "Mission starting…",
          ts: String(Date.now()),
        })
      );
      setLatestNarration("MARVIN — Starting the mission run.");
      setStreamError(null);

      // For local repository, use mock response
      if (repository.kind === "local" || eventStream.kind === "local") {
        window.setTimeout(() => {
          setRunState(mission.id, { isStreaming: false });
          // Agent status tracking for text events
          setMessages((current) =>
            current.concat({
              id: makeMessageId(mission.id, "marvin"),
              from: "m",
              text: "Understood. I'll use that to shape the initial hypotheses and orient the team before the first checkpoint.",
            }),
          );
        }, 1600);
        return;
      }

      // For fetch-based stream, call sendMessage
      if (eventStream.kind === "fetch" && eventStream.sendMessage) {
        try {
          setPausedForGate(false);
          await eventStream.sendMessage(value, false);
        } catch (error) {
          console.error("Failed to send message:", error);
          setStreamError(error instanceof Error ? error.message : "Failed to send message");
        } finally {
          setRunState(mission.id, { isStreaming: false });
        }
      }
    },
    [mission, repository.kind, eventStream, setChatDraft, setRunState]
  );

  // Per-gate, per-event-type dedup with a 2s window. Live missions surfaced
  // triple-emission of "✓ Gate approved" and double "Gate deferred" when the
  // same handler fired twice in quick succession (fast double-click, race
  // between SSE replay and user click). Keying on (gateId, eventType) lets a
  // legitimate later re-action through after the window expires.
  const recentGateEventsRef = useRef<Map<string, number>>(new Map());
  const GATE_DEDUP_WINDOW_MS = 2000;
  const appendGateMessage = useCallback(
    (gateId: string, eventType: string, message: MissionChatMessage) => {
      const key = `${gateId}:${eventType}`;
      const now = Date.now();
      const last = recentGateEventsRef.current.get(key) ?? 0;
      if (now - last < GATE_DEDUP_WINDOW_MS) return;
      recentGateEventsRef.current.set(key, now);
      setMessages((current) => current.concat(message));
    },
    [],
  );

  const scheduleResumeStream = useCallback(() => {
    if (eventStream.kind !== "fetch" || typeof eventStream.resume !== "function") {
      return false;
    }
    const resumeStream = eventStream.resume;
    if (resumeTimerRef.current !== null) {
      window.clearTimeout(resumeTimerRef.current);
    }
    // Gate validation may spawn a detached driver that holds the mission lock.
    // Re-attach shortly after the API response so _stream_resume_passive can
    // relay graph + persistence events into the live rail.
    resumeTimerRef.current = window.setTimeout(() => {
      resumeTimerRef.current = null;
      void resumeStream().finally(() => {
        void refreshProgress();
        setRunState(missionId, { isStreaming: false });
        setGateActionInFlight(null);
        window.setTimeout(() => {
          setResolvingGateIds(new Set());
        }, 1_500);
      });
    }, 300);
    return true;
  }, [eventStream, missionId, refreshProgress, setRunState]);

  // Handle gate approval
  const handleGateApprove = useCallback(
    async (gateId: string, notes: string = "") => {
      if (!mission) return;
      if (gateActionInFlight?.gateId === gateId) return;

      setGateActionInFlight({ gateId, action: "approve" });
      markGateResolving(gateId);
      setGateModal(null);
      setPausedForGate(false);
      setRunState(mission.id, { isStreaming: true });
      // Pick narration based on which gate just unlocked. G1=research,
      // G2=synthesis, G3=final delivery — using a single hard-coded line
      // confused users at G3 by claiming research was restarting.
      const gateMeta = (progress?.gates ?? []).find((g) => g.id === gateId);
      const gatePayload = gatePayloads[gateId];
      const unlocks = gatePayload?.unlocksOnApprove?.trim();
      const approveNarration = unlocks
        ? `Workflow — Gate approved. ${unlocks}`
        : (() => {
            switch (gateMeta?.gate_type) {
              case "hypothesis_confirmation":
                return "Workflow — Gate approved. Starting the research workstreams.";
              case "manager_review":
                return "Workflow — Gate approved. Synthesising the verdict.";
              case "final_review":
                return "Workflow — Gate approved. Generating the final IC memo.";
              default:
                return "Workflow — Gate approved. Continuing the mission.";
            }
          })();
      setLatestNarration(approveNarration);

      try {
        // For HTTP repository, call the API
        if (repository.kind === "http") {
          const result = await apiValidateGate(mission.id, gateId, "APPROVED", notes);

          // Bug 4 (chantier 2.6): idempotent / conflict responses are 200,
          // not errors. Surface a quiet status message — and skip the
          // "✓ Gate approved" bubble, since this click did NOT cause a
          // state transition. Without this, repeated clicks (or a banner
          // click racing the chat-driven approve path) printed multiple
          // "✓ Gate approved" lines that confused the user.
          if (result.idempotent) {
            appendGateMessage(gateId, "approve-idem", {
              id: makeMessageId(mission.id, "idem"),
              from: "m",
              text: result.message ?? "Gate already validated.",
            });
            setRunState(mission.id, { isStreaming: false });
            setGateActionInFlight(null);
            clearGateResolving(gateId);
            return;
          }
          if (result.conflict) {
            appendGateMessage(gateId, "approve-conflict", {
              id: makeMessageId(mission.id, "conflict"),
              from: "m",
              text: result.message ?? "Gate already completed; cannot change.",
            });
            setRunState(mission.id, { isStreaming: false });
            setGateActionInFlight(null);
            clearGateResolving(gateId);
            return;
          }

          // Backend confirmed a real state transition. Prune the rail so
          // stale "gate pending" / "human review" lines disappear instead
          // of accumulating in the In progress history.
          setLiveFindings((current) =>
            current.filter(
              (event) => !(event.kind === "gate" && event.id.includes(gateId))
            )
          );
          // Clear the Approve/Reject buttons from the gate's chat bubble.
          setMessages((current) =>
            current.map((msg) =>
              msg.gateId === gateId ? { ...msg, gateAction: undefined } : msg
            )
          );

          // Now — and only now — emit the user's "✓ Gate approved" bubble
          // and the system follow-up, so the chat log reflects backend
          // truth instead of optimistic UI state. Use the API response's
          // gate_id (authoritative) over the local `gateId` to avoid the
          // stale-state duplicate where the previous gate's id leaked into
          // the next approval bubble.
          const confirmedGateId = result.gate_id ?? gateId;
          appendGateMessage(gateId, "approve", {
            id: makeMessageId(mission.id, "approve"),
            from: "u",
            text: `✓ Gate approved: ${confirmedGateId}`,
          });
          appendGateMessage(gateId, "approve-resumed", {
            id: makeMessageId(mission.id, "resumed"),
            from: "m",
            text: `Approved. Launching the next phase.`,
          });

          const shouldResume = shouldAttachResumeStream(result);
          if (!shouldResume || !scheduleResumeStream()) {
            setRunState(mission.id, { isStreaming: false });
            setGateActionInFlight(null);
          }
        }
      } catch (error) {
        console.error("Failed to validate gate:", error);
        setRunState(mission.id, { isStreaming: false });
        setGateActionInFlight(null);
        clearGateResolving(gateId);
        setStreamError(error instanceof Error ? error.message : "Failed to validate gate");
      }
    },
    [clearGateResolving, gateActionInFlight, markGateResolving, mission, repository.kind, setRunState, appendGateMessage, scheduleResumeStream]
  );

  // Handle gate rejection
  const handleGateReject = useCallback(
    async (gateId: string, notes: string = "") => {
      if (!mission) return;
      if (gateActionInFlight?.gateId === gateId) return;

      setGateActionInFlight({ gateId, action: "reject" });
      markGateResolving(gateId);
      setGateModal(null);
      setPausedForGate(false);
      setRunState(mission.id, { isStreaming: true });
      setLatestNarration("Workflow — Reworking the mission from your feedback.");

      try {
        // For HTTP repository, call the API
        if (repository.kind === "http") {
          const result = await apiValidateGate(mission.id, gateId, "REJECTED", notes);

          if (result.idempotent) {
            appendGateMessage(gateId, "reject-idem", {
              id: makeMessageId(mission.id, "idem"),
              from: "m",
              text: result.message ?? "Gate already rejected.",
            });
            setRunState(mission.id, { isStreaming: false });
            setGateActionInFlight(null);
            clearGateResolving(gateId);
            return;
          }
          if (result.conflict) {
            appendGateMessage(gateId, "reject-conflict", {
              id: makeMessageId(mission.id, "conflict"),
              from: "m",
              text: result.message ?? "Gate already completed; cannot change.",
            });
            setRunState(mission.id, { isStreaming: false });
            setGateActionInFlight(null);
            clearGateResolving(gateId);
            return;
          }

          // Prune stale gate signals from the rail before emitting the
          // user-visible "rejected" line so the In progress block reflects
          // backend truth.
          setLiveFindings((current) =>
            current.filter(
              (event) => !(event.kind === "gate" && event.id.includes(gateId))
            )
          );
          // Clear the Approve/Reject buttons from the gate's chat bubble.
          setMessages((current) =>
            current.map((msg) =>
              msg.gateId === gateId ? { ...msg, gateAction: undefined } : msg
            )
          );

          // No local "Awaiting further instructions" message: the backend
          // now emits a specific AIMessage (per gate_type) describing what
          // re-runs next. Adding a generic placeholder here would race the
          // real message and confuse the user.
          appendGateMessage(gateId, "reject", {
            id: makeMessageId(mission.id, "reject"),
            from: "u",
            text: `Gate rejected: ${gateId}`,
          });

          const shouldResume = shouldAttachResumeStream(result);
          if (!shouldResume || !scheduleResumeStream()) {
            setRunState(mission.id, { isStreaming: false });
            setGateActionInFlight(null);
          }
        }
      } catch (error) {
        console.error("Failed to validate gate:", error);
        setRunState(mission.id, { isStreaming: false });
        setGateActionInFlight(null);
        clearGateResolving(gateId);
        setStreamError(error instanceof Error ? error.message : "Failed to validate gate");
      }
    },
    [clearGateResolving, gateActionInFlight, markGateResolving, mission, repository.kind, setRunState, appendGateMessage, scheduleResumeStream]
  );

  // CP2 (chantier 2.6.1): data_decision gate handler. Posts a `decision`
  // value (skip_calculus / proceed_low_confidence / request_data_room)
  // instead of an APPROVED/REJECTED verdict.
  const handleGateDecision = useCallback(
    async (
      gateId: string,
      decision: "skip_calculus" | "proceed_low_confidence" | "request_data_room",
      label: string,
    ) => {
      if (!mission) return;
      setGateModal(null);
      setPausedForGate(false);
      setRunState(mission.id, { isStreaming: true });
      setLatestNarration("Workflow — Applying your gate decision.");
      setMessages((current) =>
        current.concat({
          id: makeMessageId(mission.id, "decision"),
          from: "u",
          text: `→ ${label}`,
        }),
      );
      try {
        if (repository.kind === "http") {
          const result = await apiValidateGateDecision(mission.id, gateId, decision, "");
          if (result.idempotent) {
            setMessages((current) =>
              current.concat({
                id: makeMessageId(mission.id, "idem"),
                from: "m",
                text: result.message ?? "Decision already recorded.",
              }),
            );
            setRunState(mission.id, { isStreaming: false });
            return;
          }
          if (result.conflict) {
            setMessages((current) =>
              current.concat({
                id: makeMessageId(mission.id, "conflict"),
                from: "m",
                text: result.message ?? "Decision already recorded; cannot change.",
              }),
            );
            setRunState(mission.id, { isStreaming: false });
            return;
          }
          const shouldResume = shouldAttachResumeStream(result);
          if (!shouldResume || !scheduleResumeStream()) {
            setRunState(mission.id, { isStreaming: false });
          }
        }
      } catch (error) {
        console.error("Failed to record decision:", error);
        setRunState(mission.id, { isStreaming: false });
        setStreamError(error instanceof Error ? error.message : "Failed to record decision");
      }
    },
    [mission, repository.kind, setRunState, scheduleResumeStream],
  );

  // Submit clarification answers for a clarification_request gate.
  // Validates that every question has at least an empty string slot, sends
  // the answers via the standard validate endpoint, and clears local state
  // so the next gate_pending event (or framing memo) can take over.
  const handleClarificationSubmit = useCallback(async () => {
    if (!mission || !clarificationGate) return;
    const questions = clarificationGate.questions ?? [];
    const answers = questions.map((_, idx) => (clarificationAnswers[idx] ?? "").trim());
    setClarificationSubmitting(true);
    setRunState(mission.id, { isStreaming: true });
    setLatestNarration("Workflow — Applying your clarification.");
    try {
      const result = await apiSubmitClarificationAnswers(
        mission.id,
        clarificationGate.gateId,
        answers,
      );
      setMessages((current) =>
        current.concat({
          id: makeMessageId(mission.id, "clarif-answer"),
          from: "u",
          text: answers.filter((a) => a.length > 0).join(" · ") || "(skipped)",
        }),
      );
      setClarificationGate(null);
      setClarificationAnswers([]);
      setPausedForGate(false);
      const shouldResume = shouldAttachResumeStream(result);
      if (!shouldResume || !scheduleResumeStream()) {
        setRunState(mission.id, { isStreaming: false });
      }
    } catch (error) {
      setStreamError(
        error instanceof Error ? error.message : "Failed to submit clarification answers",
      );
      setRunState(mission.id, { isStreaming: false });
    } finally {
      setClarificationSubmitting(false);
    }
  }, [mission, clarificationGate, clarificationAnswers, setRunState, scheduleResumeStream]);

  // Deferring closes the modal but does NOT call the validate API.
  // The pending gate state is preserved server-side in the LangGraph checkpoint
  // and will re-interrupt on the next chat turn or page reload.
  const handleGateClose = useCallback(() => {
    if (gateModal && mission) {
      appendGateMessage(gateModal.gateId, "deferred", {
        id: `${gateModal.gateId}-deferred-${Date.now()}`,
        from: "m",
        text: `Gate "${gateModal.title}" deferred. The mission is paused and your decision is preserved — reopen anytime to approve or reject.`,
      });
    }
    setGateModal(null);
    setRunState(missionId, { isStreaming: false });
    setLatestNarration(null);
  }, [gateModal, mission, missionId, setRunState, appendGateMessage]);

  // Re-open a deferred gate from the checkpoint surface.
  const reopenGateFromCheckpoint = useCallback(() => {
    if (!progress) return;
    const pending = (progress.gates ?? []).find((g) => g.lifecycle_status === "open" || g.is_open);
    if (!pending) return;
    const modalPayload =
      gatePayloads[pending.id] ??
      mapGateReviewPayloadToModal(pending.review_payload, {
        id: pending.id,
        gate_type: pending.gate_type,
      });
    setGateModal((current) =>
      current ?? modalPayload,
    );
  }, [gatePayloads, progress]);

  useEffect(() => {
    if (!runState.isStreaming && gateActionInFlight) {
      setGateActionInFlight(null);
    }
  }, [gateActionInFlight, runState.isStreaming]);

  useEffect(() => {
    if (!runState.isStreaming || pausedForGate) {
      setStreamStartedAt(null);
      setStreamElapsedSeconds(0);
      return;
    }

    const startedAt = streamStartedAt ?? Date.now();
    if (streamStartedAt === null) {
      setStreamStartedAt(startedAt);
      lastEventAtRef.current = startedAt;
    }

    setStreamElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    const handle = window.setInterval(() => {
      setStreamElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1_000);
    return () => window.clearInterval(handle);
  }, [pausedForGate, runState.isStreaming, streamStartedAt]);

  useEffect(() => {
    if (!runState.isStreaming || pausedForGate) {
      if (isStalled) setIsStalled(false);
      return;
    }
    const handle = window.setInterval(() => {
      setIsStalled(Date.now() - lastEventAtRef.current > 30_000);
    }, 5_000);
    return () => window.clearInterval(handle);
  }, [runState.isStreaming, pausedForGate, isStalled]);

  if (!hasLoaded) {
    return null;
  }

  if (isOffline) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          background: "#f4f0ea",
          padding: "24px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <div style={{ maxWidth: "420px", textAlign: "center" }}>
          <h1 style={{ margin: "0 0 12px", fontSize: "28px" }}>Backend offline</h1>
          <p style={{ margin: "0 0 16px", lineHeight: 1.6 }}>
            The backend server is not reachable. Please ensure the backend is running on port 8091.
          </p>
          <Link href="/missions">Return to missions</Link>
        </div>
      </div>
    );
  }

  if (!mission) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          background: "#f4f0ea",
          padding: "24px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <div style={{ maxWidth: "420px", textAlign: "center" }}>
          <h1 style={{ margin: "0 0 12px", fontSize: "28px" }}>Mission not found</h1>
          <p style={{ margin: "0 0 16px", lineHeight: 1.6 }}>
            The URL mission id is valid route authority, but no matching mission record exists.
          </p>
          <Link href="/missions">Return to missions</Link>
        </div>
      </div>
    );
  }


  // Compute agent statuses from workstreams and current active agent
  // milestonesDelivered counts milestones whose status (from /progress) is
  // "delivered", OR whose id has been flipped to "delivered" by a live
  // milestone_done SSE event captured in milestoneStatusOverrides.
  const allMilestones = progress?.milestones ?? [];
  const agents = (progress?.workstreams ?? []).map(ws => {
    const wsMilestones = allMilestones.filter(m => m.workstream_id === ws.id);
    const delivered = wsMilestones.filter(m => {
      const liveStatus = milestoneStatusOverrides[m.id];
      return (liveStatus ?? m.status) === "delivered";
    }).length;
    const agentKey = ws.assigned_agent?.toLowerCase() ?? ws.id;
    const liveStatus = agentStatuses[agentKey] ?? (activeAgent?.toLowerCase() === agentKey ? "active" : "idle");
    return {
      id: agentKey,
      name: ws.assigned_agent ?? ws.id,
      role: ws.label,
      status: liveStatus,
      state: liveStatus === "active" ? "running" : liveStatus === "done" ? "done" : "idle",
      milestonesTotal: wsMilestones.length,
      milestonesDelivered: delivered,
    };
  });

  // Compute checkpoints from gates
  const gateStatusToCheckpoint = (g: any) => {
    if (resolvingGateIds.has(g.id)) return "completed";
    if (g.status === "completed") return "completed";
    if (g.lifecycle_status === "open" || g.is_open) return "now";
    return "later";
  };
  const checkpoints = (progress?.gates ?? []).map(g => ({
    id: g.id,
    label: String(g.gate_type ?? "").replace(/_/g, " "),
    status: gateStatusToCheckpoint(g),
  }));
  const visiblePendingGates = (progress?.gates ?? []).filter(
    (g) => (g.lifecycle_status === "open" || g.is_open) && !resolvingGateIds.has(g.id),
  );
  const hasPendingGate = visiblePendingGates.length > 0;
  const pendingGate = visiblePendingGates[0];
  const nextCheckpointLabel =
    visiblePendingGates[0]?.gate_type?.replace(/_/g, " ") ??
    checkpoints.find((cp) => cp.status === "now")?.label ??
    null;
  const deliveredMilestones = allMilestones.filter((m) => {
    const liveStatus = milestoneStatusOverrides[m.id];
    return (liveStatus ?? m.status) === "delivered";
  }).length;
  // Phase-based progress so the % reflects the workflow stage (brief → W1 →
  // W2 → W3 → W4 → final) rather than raw milestone delivery counts. Raw
  // milestone counts under-report progress dramatically when the mission
  // has done significant analytical work but only one or two milestones
  // have crossed the "delivered" boundary.
  // Phase-based progress. Backend `ws.status` is a free-form string and does
  // NOT reliably equal "completed" when the workstream is finished — that's
  // why the % was stuck at 33% on a fully-completed mission. Mirror the
  // same UI signals used by `workstreamContent` (terminal milestones, ready
  // deliverable, or merlin verdict for W3).
  const phaseStageCount = (() => {
    const allMs = progress?.milestones ?? [];
    const allDels = progress?.deliverables ?? [];
    const merlinDone = Boolean((progress as any)?.merlin_verdict?.verdict);
    const wsHasReadyDeliverable = (wsId: string): boolean =>
      allDels.some((d) => {
        if (d.status !== "ready" || !d.file_path) return false;
        return routeDeliverableToSectionId({
          deliverable_type: d.deliverable_type,
          file_path: d.file_path,
        }) === wsId;
      });
    const wsAllMilestonesTerminal = (wsId: string): boolean => {
      const ms = allMs.filter((m: any) => m.workstream_id === wsId);
      if (ms.length === 0) return false;
      return ms.every((m: any) => {
        const live = milestoneStatusOverrides[m.id];
        return ["delivered", "skipped", "blocked"].includes(live ?? m.status);
      });
    };
    const wsAnyDelivered = (wsId: string): boolean => {
      const ms = allMs.filter((m: any) => m.workstream_id === wsId);
      return ms.some((m: any) => {
        const live = milestoneStatusOverrides[m.id];
        return (live ?? m.status) === "delivered";
      });
    };
    const wsDone = (id: string): number => {
      if (wsAllMilestonesTerminal(id)) return 1;
      if (wsHasReadyDeliverable(id)) return 1;
      if (id === "W3" && merlinDone) return 1;
      return 0;
    };
    const wsActive = (id: string): number => {
      if (wsDone(id)) return 0;
      const agentKey = (progress?.workstreams ?? []).find((w) => w.id === id)?.assigned_agent?.toLowerCase();
      if (agentKey && (agentStatuses[agentKey] === "active" || activeAgent?.toLowerCase() === agentKey)) return 0.5;
      if (wsAnyDelivered(id)) return 0.5;
      return 0;
    };
    const briefDone = progress?.framing ? 1 : 0;
    const finalDone = allDels.some(
      (d) => /^(final|ic_memo|exec_summary|final_deliverable|investment_memo|data_book)/i.test(d.deliverable_type ?? ""),
    ) ? 1 : 0;
    return (
      briefDone +
      wsDone("W1") + wsActive("W1") +
      wsDone("W2") + wsActive("W2") +
      wsDone("W3") + wsActive("W3") +
      wsDone("W4") + wsActive("W4") +
      finalDone
    );
  })();
  const progressRatio = Math.min(1, phaseStageCount / 6);
  const missionStatusLabel = resolvingGateIds.size > 0
    ? "Mission running"
    : hasPendingGate
    ? `Gate pending · ${nextCheckpointLabel ?? "Review"}`
    : progressRatio >= 1 && allMilestones.length > 0
      ? "Complete"
      : activeAgent
        ? `${activeAgent} running`
        : runState.isStreaming
          ? "Mission running"
          : nextCheckpointLabel
            ? `Next gate · ${nextCheckpointLabel}`
            : "Ready";
  const missionForView = {
    ...mission,
    progress: progressRatio,
    checkpoint: nextCheckpointLabel ?? "No open checkpoint",
    statusLabel: missionStatusLabel,
  };

  // Compute hypotheses
  const hypotheses = progress?.hypotheses ?? [];

  // Compute section outputs (findings + milestones + deliverables). The center
  // pane is scoped to an explicit section, so Brief, Synthesis, Stress testing,
  // and Final deliverables are distinct instead of sharing a misleading global
  // list.
  const tabToSectionId = (tab: string): string => {
    if (tab === "brief" || tab === "final") return tab;
    if (tab === "ws5") return "final";
    return tab.replace(/^ws/i, "W");
  };
  const selectedSectionId = selectedTab ? tabToSectionId(selectedTab) : "brief";
  const sectionLabelById: Record<string, string> = {
    brief: "Brief",
    W1: "Market analysis",
    W2: "Financial analysis",
    W3: "Synthesis",
    W4: "Stress testing",
    final: "Final deliverables",
  };
  const workstreamLabel = sectionLabelById[selectedSectionId] ?? "section";
  // Lifted so both `normalizeFinding` (output filter) and
  // `workstreamContent.findings` (per-tab content) agree on which agent
  // owns which workstream. Without this, merlin/adversus findings with a
  // null workstream_id never reach the Synthesis / Stress testing tabs.
  const AGENT_TO_WS: Record<string, string> = {
    dora: "W1", calculus: "W2", merlin: "W3", adversus: "W4",
  };
  const normalizeFinding = (f: any) => {
    const agentRaw = String(f.agent ?? f.agent_id ?? f.ag ?? "").toLowerCase();
    const explicitWs = f.workstream_id ?? f.workstreamId ?? null;
    return {
      id: f.id,
      kind: f.kind ?? "finding",
      ag: normalizeAgentName(f.agent ?? f.agent_id ?? f.ag),
      text: f.claim_text ?? f.text ?? "",
      ts: f.ts ?? f.created_at ?? "",
      confidence: f.confidence,
      section_id: f.section_id ?? f.sectionId ?? null,
      workstream_id: explicitWs ?? AGENT_TO_WS[agentRaw] ?? null,
      agent_id: f.agent ?? f.agent_id,
      claim_text: f.claim_text,
      href: f.href,
      // Chantier 4 CP2: enrich for FindingCard.
      hypothesis_id: f.hypothesis_id ?? f.hypothesisId ?? null,
      hypothesis_label: f.hypothesis_label ?? null,
      source_id: f.source_id ?? null,
      source_type: f.source_type ?? f.sourceType ?? null,
      impact: f.impact ?? null,
    };
  };
  const allFindings = (progress?.findings ?? []).map(normalizeFinding);
  // Newest-on-top: the rail is a live feed; users want the most recent event
  // visible without scrolling. liveFindings is appended in arrival order;
  // reverse for display.
  const activity = liveFindings.slice().reverse().map(normalizeFinding);
  // Tab id "ws1" maps to backend workstream id "W1", etc.
  // Strict filter: only show outputs tagged/routed to the selected workstream.
  // Untagged findings are intentionally excluded so per-tab content stays
  // distinct rather than every untagged finding bleeding into all tabs.

  // Compute deliverables (snapshot + live SSE additions, deduped by id)
  const seedDeliverables = (progress?.deliverables ?? []).map((d) => ({
    id: d.id,
    label: formatDeliverableDisplayName(d),
    deliverable_type: d.deliverable_type,
    file_path: d.file_path,
    milestone_id: (d as any).milestone_id ?? null,
    status: d.status === "ready" && d.file_path ? "ready" : "pending",
    href: d.status === "ready" && d.file_path ? getDeliverableDownloadUrl(d.file_path) : undefined,
    // Chantier 4 CP3: ready deliverables open the preview modal instead of
    // forcing a download. The download link is still available inside.
    onOpen:
      d.status === "ready" && d.file_path
        ? () => setPreviewDeliverableId(d.id)
        : undefined,
  }));
  const deliverables = seedDeliverables;
  const deliverableOutputs = seedDeliverables
    .filter((d) => d.status === "ready")
    .map((d) => ({
      id: d.id,
      kind: "deliverable" as const,
      ag: "MARVIN",
      text: `Deliverable ready · ${d.label}`,
      claim_text: `Deliverable ready · ${d.label}`,
      confidence: "READY",
      section_id: routeDeliverableToSectionId(d),
      workstream_id: null,
      ts: "",
      href: d.href,
      onOpen: d.onOpen,
      output_label: d.label,
    }));
  // C-PER-MILESTONE: pair each delivered milestone row with its
  // milestone_report deliverable so the row exposes Open/Download.
  // Fall back to the parent workstream report when no per-milestone
  // artifact exists yet (older missions, or milestones with too few
  // findings to render a per-milestone report).
  const milestoneOutputs = allMilestones
    .filter((m) => {
      const liveStatus = milestoneStatusOverrides[m.id];
      return (liveStatus ?? m.status) === "delivered";
    })
    .map((m) => {
      const tied = seedDeliverables.find(
        (d) => d.status === "ready" && d.milestone_id === m.id,
      );
      const wsFallback = !tied
        ? seedDeliverables.find(
            (d) =>
              d.status === "ready" &&
              routeDeliverableToSectionId({
                deliverable_type: d.deliverable_type,
                file_path: d.file_path,
              }) === m.workstream_id,
          )
        : undefined;
      const linked = tied ?? wsFallback;
      return {
        id: m.id,
        kind: "milestone" as const,
        ag: "MARVIN",
        text: `Milestone complete · ${m.label}`,
        claim_text: `Milestone complete · ${m.label}`,
        confidence: "DONE",
        section_id: null,
        workstream_id: m.workstream_id,
        ts: "",
        href: linked?.href,
        onOpen: linked?.onOpen,
        output_label: linked?.label,
      };
    });
  // Synthesis (W3) is verdict-driven, not finding-driven: merlin doesn't
  // call add_finding_to_mission, so without surfacing the verdict the
  // tab would be permanently empty. Build a synthetic output card from
  // /progress.merlin_verdict so the user sees what merlin concluded.
  const synthesisOutputs: any[] = (() => {
    const v = (progress as any)?.merlin_verdict;
    if (!v?.verdict) return [];
    // Safety net: strip any leading "Verdict: <ENUM>" line and
    // hyp-UUID artifacts the model may still echo despite the
    // prompt ban. The verdict enum is rendered as a badge via
    // `confidence`; the prose lives in `text`.
    const sanitizeVerdictNotes = (raw: string): string => {
      let out = String(raw ?? "").trim();
      out = out.replace(/^\s*Verdict:\s*[A-Z_]+\s*\n?/i, "").trim();
      out = out.replace(/\bhyp-[0-9a-f]{6,}\b/gi, "").trim();
      out = out.replace(/[ \t]{2,}/g, " ");
      out = out.replace(/\n{3,}/g, "\n\n");
      return stripVerdictScaffolding(out);
    };
    const prose = sanitizeVerdictNotes(v.notes ?? "");
    const verdictLabel = humanizeVerdict(v.verdict);
    // Single dark deliverable row carrying the verdict label as title and
    // the prose as a multi-line body. Stuffed into `source_id` because
    // CenterFinding already exposes it as a body block on expand; doubles
    // as the inline body for the synthesis row (which is always expanded
    // visually since it has no file to "Open").
    const baseRow = {
      kind: "deliverable" as const,
      ag: "Merlin",
      text: `Synthesis · ${verdictLabel || "Verdict"}`,
      claim_text: `Synthesis · ${verdictLabel || "Verdict"}`,
      confidence: verdictLabel,
      agent_id: "merlin",
      ts: v.created_at ?? "",
      source_id: prose || null,
    };
    // Surface the verdict on BOTH Synthesis (W3) and Final deliverables (final)
    // so the final tab isn't just a bare file list — the user sees the
    // verdict + prose at the top of the IC handoff view.
    return [
      { ...baseRow, id: `synthesis-verdict-w3-${v.created_at ?? "current"}`, section_id: null, workstream_id: "W3" },
      { ...baseRow, id: `synthesis-verdict-final-${v.created_at ?? "current"}`, section_id: "final", workstream_id: null },
    ];
  })();
  // Live findings (SSE-driven, not yet persisted to /progress.findings) are
  // merged in alongside DB findings so the user sees adversus/calculus
  // outputs the moment they are emitted instead of waiting for the
  // backend persistence round-trip. Deduped by `kind:id` — when the
  // backend later persists the same row, the DB version wins (later
  // entries override earlier ones in dedupeByKey ordering).
  const liveFindingOutputs = activity.filter((a: any) => a.kind === "finding");
  const allSectionOutputs = dedupeByKey([
    ...liveFindingOutputs,
    ...allFindings,
    ...synthesisOutputs,
    ...deliverableOutputs,
    ...milestoneOutputs,
  ], (output) => `${output.kind}:${output.id}`);
  const findings = allSectionOutputs.filter((output) => {
    const sectionId = output.section_id ?? output.workstream_id;
    return sectionId === selectedSectionId;
  });
  const completedTitle = `${workstreamLabel} outputs`;
  const completedEmptyText = `No outputs for ${workstreamLabel} yet.`;

  // Build per-workstream content for the center tabs from real findings.
  // Bug 6 (chantier 2.6): tabs are content-driven (DB findings), not the
  // SSE meta-event stream. Fall back to the agent → workstream map so a
  // finding with workstream_id=null still surfaces in the right tab.
  // W3 (Synthesis) is verdict-driven, not milestone-driven — once Merlin
  // has issued a verdict the tab is complete regardless of milestone count.
  const merlinVerdictPresent = Boolean((progress as any)?.merlin_verdict?.verdict);
  const workstreamContent = (progress?.workstreams ?? []).map((ws) => {
    const wsMilestones = (progress?.milestones ?? []).filter((m: any) => m.workstream_id === ws.id);
    // Count any terminal status — delivered, skipped, or blocked — as "done".
    // A legitimately blocked milestone (e.g. LOW_CONFIDENCE finding that
    // research_join could not progress) used to pin the tab on `●` forever.
    const wsTerminal = wsMilestones.filter((m: any) => {
      const liveStatus = milestoneStatusOverrides[m.id];
      return ["delivered", "skipped", "blocked"].includes(liveStatus ?? m.status);
    }).length;
    const wsDelivered = wsMilestones.filter((m: any) => {
      const liveStatus = milestoneStatusOverrides[m.id];
      return (liveStatus ?? m.status) === "delivered";
    }).length;
    const agentKey = ws.assigned_agent?.toLowerCase() ?? ws.id.toLowerCase();
    const liveStatus = agentStatuses[agentKey] ?? (activeAgent?.toLowerCase() === agentKey ? "active" : "idle");
    const wsHasReadyDeliverable = seedDeliverables.some((d) => {
      if (d.status !== "ready") return false;
      return routeDeliverableToSectionId({
        deliverable_type: d.deliverable_type,
        file_path: d.file_path,
      }) === ws.id;
    });
    const allMilestonesDone = wsMilestones.length > 0 && wsTerminal === wsMilestones.length;
    const synthesisDone = ws.id === "W3" && merlinVerdictPresent;
    // Only mark a tab "completed" when ALL milestones are terminal (or for W3,
    // when Merlin's verdict exists). A single ready deliverable used to flip
    // the tab to ✓ done while the agent was still working on later
    // milestones — visible mismatch with the agent status pill.
    const status: WorkstreamViewStatus =
      allMilestonesDone || synthesisDone
        ? "completed"
        : liveStatus === "active"
          ? "now"
          : wsDelivered > 0 || wsHasReadyDeliverable
            ? "in_progress"
            : "pending";
    return {
      id: ws.id,
      label: ws.label,
      status,
      findings: (progress?.findings ?? []).filter((f: any) => {
        if (f.workstream_id === ws.id) return true;
        const mapped = AGENT_TO_WS[(f.agent_id || "").toLowerCase()];
        return mapped === ws.id;
      }),
      milestones: wsMilestones,
    };
  });

  const showDeferredBanner = hasPendingGate && !gateModal;
  const pendingGateModal =
    pendingGate
      ? gatePayloads[pendingGate.id] ??
        mapGateReviewPayloadToModal(pendingGate.review_payload, {
          id: pendingGate.id,
          gate_type: pendingGate.gate_type,
        })
      : null;
  const briefStatus: "pending" | "now" | "completed" = progress?.framing ? "completed" : "now";
  const workstreamStatus = (workstreamId: string): WorkstreamViewStatus =>
    workstreamContent.find((ws) => ws.id === workstreamId)?.status ?? "pending";
  const hasFinalDeliverables = deliverableOutputs.some((d) => d.section_id === "final");
  const missionIsWorking = (runState.isStreaming || resolvingGateIds.size > 0) && !pausedForGate;
  const baseSectionTabs: MissionControlViewProps["sectionTabs"] = [
    { id: "brief", label: "Brief", status: briefStatus },
    { id: "ws1", label: "Market analysis", status: workstreamStatus("W1") },
    { id: "ws2", label: "Financial analysis", status: workstreamStatus("W2") },
    { id: "ws3", label: "Synthesis", status: workstreamStatus("W3") },
    { id: "ws4", label: "Stress testing", status: workstreamStatus("W4") },
    { id: "final", label: "Final deliverables", status: hasFinalDeliverables ? "completed" : "pending" },
  ];
  const hasLiveStep = baseSectionTabs.some((tab) => tab.status === "now" || tab.status === "in_progress");
  const nextPendingStepIndex = baseSectionTabs.findIndex((tab) => tab.status === "pending");
  const sectionTabs = missionIsWorking && !hasPendingGate && !hasLiveStep && nextPendingStepIndex >= 0
    ? baseSectionTabs.map((tab, index) =>
        index === nextPendingStepIndex ? { ...tab, status: "now" as const } : tab,
      )
    : baseSectionTabs;
  const showTyping = missionIsWorking;
  const activeStep = sectionTabs.find((tab) => tab.status === "now") ?? sectionTabs.find((tab) => tab.status === "in_progress");
  // Bug #6b: when the user hasn't manually picked a tab, surface the active
  // step's tab as the displayed selection. We don't write back into the
  // store — that would clobber a real user pick mid-render and also can't
  // run as an effect here (early returns above). Pure derivation only.
  const effectiveSelectedTab: WorkspaceTab =
    userPickedTabRef.current || !activeStep ? selectedTab : activeStep.id;
  const selectedTabId = selectedSectionId === "brief" || selectedSectionId === "final"
    ? selectedSectionId
    : (`ws${selectedSectionId.replace(/^W/i, "")}` as WorkspaceTab);
  const showWaitInSelectedOutputs = showTyping && activeStep?.id === selectedTabId;
  const waitHeadline = activeAgent
    ? `${activeAgent} is working${activeAgentSince ? ` · ${activeAgentElapsed}s` : ""}`
    : "MARVIN is working";
  const waitBaseMessage =
    latestNarration ??
    (activeAgent
      ? `${activeAgent} is working on the next mission step.`
      : "Workflow — Starting the research workstreams.");
  const waitMessage = isStalled
    ? "Still working. No action needed — MARVIN will update this panel as soon as the next event arrives."
    : streamElapsedSeconds >= 8
      ? `${waitBaseMessage} This can take a minute while agents search, reason, and write findings.`
      : waitBaseMessage;
  const waitState: MissionControlViewProps["waitState"] = {
    isWorking: showTyping,
    showInOutputs: showWaitInSelectedOutputs,
    isStalled,
    elapsedLabel: formatElapsed(streamElapsedSeconds),
    message: waitMessage,
    headline: waitHeadline,
  };


  // Render with gate modal that includes approve/reject buttons
  return (
    <>
      <MissionControlView
        mission={missionForView}
        messages={messages}
        initialMessages={messages}
        chatDraft={chatDraft}
        onChatDraftChange={(value: string) => setChatDraft(mission.id, value)}
        onSendMessage={handleSendMessage}
        selectedTab={effectiveSelectedTab}
        onSelectTab={(tab: WorkspaceTab) => {
          userPickedTabRef.current = true;
          setWorkspaceTab(mission.id, tab);
        }}
        isTyping={showTyping}
        defaultTab={DEFAULT_WORKSPACE_TAB}
        gateModal={null} // We handle gate modal separately
        onGateClose={handleGateClose}
        onGateApprove={handleGateApprove}
        onGateReject={handleGateReject}
        backendState={backendState}
        agents={agents}
        checkpoints={checkpoints}
        hypotheses={hypotheses}
        activity={activity}
        findings={findings}
        deliverables={deliverables}
        activeAgent={activeAgent}
        currentNarration={waitState.message}
        sectionTabs={sectionTabs}
        workstreamContent={workstreamContent}
        waitState={waitState}
        pendingGateBanner={
          showDeferredBanner && pendingGate
            ? {
                onResume: reopenGateFromCheckpoint,
                onApprove: () => handleGateApprove(pendingGate.id, ""),
                onReject: () => handleGateReject(pendingGate.id, ""),
                actionInFlight:
                  gateActionInFlight?.gateId === pendingGate.id &&
                  (gateActionInFlight.action === "approve" || gateActionInFlight.action === "reject")
                    ? gateActionInFlight.action
                    : null,
                gateId: pendingGate.id,
                title: pendingGateModal?.title,
                summary: pendingGateModal?.summary,
              }
            : null
        }
        briefStatus={briefStatus}
        nextCheckpointLabel={nextCheckpointLabel}
        completedTitle={completedTitle}
        completedEmptyText={completedEmptyText}
        onOpenDeliverable={(id: string) => setPreviewDeliverableId(id)}
      />

      {/* Chantier 4 CP3: deliverable preview modal. */}
      <DeliverablePreview
        deliverableId={previewDeliverableId}
        onClose={() => setPreviewDeliverableId(null)}
      />

      {/* C-RESUME-RECOVERY: transient LLM failure banner. Surfaces a Rerun
          button targeting the failed agent (adversus|merlin). The server's
          /agents/{agent}/rerun endpoint clears the failed gate and resumes
          the graph from that node — research is NOT replayed. */}
      <TransientFailureBanner
        gates={progress?.gates ?? []}
        missionId={mission.id}
        onRerunStarted={() => {
          // Best-effort progress refresh so the banner clears once the
          // server has cleared the gate. The detached driver re-emits
          // SSE events that update progress on the way through.
          void getMissionProgress(mission.id).then((next) => {
            if (next) setProgress(next);
          });
        }}
      />

      {/* Inline clarification panel (does not block other UI like the modal does). */}
      {clarificationGate && (
        <div
          role="dialog"
          aria-modal="false"
          aria-label="Clarification needed"
          style={{
            position: "fixed",
            left: "50%",
            transform: "translateX(-50%)",
            bottom: "24px",
            width: "min(640px, calc(100vw - 32px))",
            background: "#fffaf2",
            border: "1px solid #e5dccd",
            borderRadius: "12px",
            boxShadow: "0 18px 48px rgba(26,24,20,.18)",
            padding: "18px 20px",
            zIndex: 900,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: "10px",
            }}
          >
            <div
              style={{
                fontFamily: "system-ui",
                fontSize: "11px",
                fontWeight: 600,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "#8a8784",
              }}
            >
              MARVIN needs context · Round {clarificationGate.round ?? 1} of{" "}
              {clarificationGate.maxRounds ?? 3}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {(clarificationGate.questions ?? []).map((q, idx) => (
              <div key={`${clarificationGate.gateId}-q-${idx}`}>
                <label
                  style={{
                    display: "block",
                    fontFamily: "Georgia, serif",
                    fontSize: "14px",
                    color: "#3a362f",
                    marginBottom: "6px",
                  }}
                >
                  {q}
                </label>
                <textarea
                  value={clarificationAnswers[idx] ?? ""}
                  onChange={(e) => {
                    const next = [...clarificationAnswers];
                    next[idx] = e.target.value;
                    setClarificationAnswers(next);
                  }}
                  rows={2}
                  placeholder="Your answer..."
                  style={{
                    width: "100%",
                    boxSizing: "border-box",
                    padding: "8px 10px",
                    fontFamily: "system-ui",
                    fontSize: "13px",
                    border: "1px solid #ddd2bd",
                    borderRadius: "8px",
                    resize: "vertical",
                    background: "#fffefb",
                  }}
                />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "14px" }}>
            <button
              type="button"
              onClick={handleClarificationSubmit}
              disabled={clarificationSubmitting}
              style={{
                background: "#1f3b2c",
                color: "#fffefb",
                border: "none",
                borderRadius: "8px",
                padding: "9px 16px",
                fontFamily: "system-ui",
                fontSize: "13px",
                cursor: clarificationSubmitting ? "wait" : "pointer",
                opacity: clarificationSubmitting ? 0.7 : 1,
              }}
            >
              {clarificationSubmitting ? "Submitting…" : "Submit answers"}
            </button>
          </div>
        </div>
      )}

      {/* Custom gate modal with approve/reject buttons */}
      {gateModal && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            display: "grid",
            placeItems: "center",
            zIndex: 1000,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) handleGateClose();
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: "540px",
              background: "#f9f7f4",
              border: "1px solid #e5e2de",
              borderRadius: "14px",
              boxShadow: "0 32px 80px rgba(26,24,20,.22)",
              display: "flex",
              flexDirection: "column",
              maxHeight: "80vh",
              padding: 0,
              fontFamily: '"Geist", sans-serif',
            }}
          >
            {/* Header */}
            <div
              style={{
                flexShrink: 0,
                padding: "22px 24px 14px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div
                    style={{
                      fontFamily: '"Geist Mono", monospace',
                      fontSize: "9px",
                      fontWeight: 600,
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: "#8a8784",
                      marginBottom: "5px",
                    }}
                  >
                    Gate pending
                  </div>
                  <h2
                    style={{
                      fontFamily: '"Newsreader", "Georgia", serif',
                      fontSize: "22px",
                      fontWeight: 700,
                      letterSpacing: "-0.02em",
                      margin: 0,
                    }}
                  >
                    {gateModal.title || "Validation required"}
                  </h2>
                </div>
                <button
                  onClick={handleGateClose}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "#8a8784",
                    display: "flex",
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M3 3l10 10M13 3L3 13"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>
            </div>

            {/* Body — scrollable */}
            <div
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "0 24px",
              }}
            >
              {gateModal.stage && (
                <div
                  style={{
                    fontFamily: '"Geist Mono", monospace',
                    fontSize: "9px",
                    letterSpacing: "0.14em",
                    textTransform: "uppercase",
                    color: "#8a8784",
                    marginBottom: "10px",
                  }}
                >
                  Stage · {gateModal.stage}
                </div>
              )}

              <p
                style={{
                  fontSize: "13px",
                  lineHeight: 1.6,
                  color: "#3a362f",
                  marginBottom: "14px",
                }}
              >
                {gateModal.summary || "A gate is waiting for human review before the mission can proceed."}
              </p>

              {gateModal.framing && (
                <div style={{ marginBottom: "14px", border: "1px solid #e5e2de", borderRadius: "8px", padding: "10px 12px", background: "#fff" }}>
                  <div style={{ fontFamily: '"Geist Mono", monospace', fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#5a5854", marginBottom: "6px" }}>
                    Framing summary
                  </div>
                  {gateModal.framing.briefSummary && (
                    <div style={{ fontSize: "12px", lineHeight: 1.5, color: "#3a362f", marginBottom: "6px" }}>
                      {gateModal.framing.briefSummary}
                    </div>
                  )}
                  {gateModal.framing.missionAngle && (
                    <div style={{ fontSize: "11px", lineHeight: 1.5, color: "#78716A" }}>
                      Angle: {gateModal.framing.missionAngle}
                    </div>
                  )}
                </div>
              )}

              {gateModal.coverage && (
                <div style={{ marginBottom: "14px", border: "1px solid #e5e2de", borderRadius: "8px", padding: "10px 12px", background: "#fff" }}>
                  <div style={{ fontFamily: '"Geist Mono", monospace', fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#5a5854", marginBottom: "6px" }}>
                    Research coverage
                  </div>
                  <div style={{ fontSize: "12px", lineHeight: 1.5, color: "#3a362f", marginBottom: "8px" }}>
                    {gateModal.coverage.findings_total} findings across {gateModal.coverage.workstreams_with_material}/{gateModal.coverage.workstreams_total} workstreams · {gateModal.coverage.milestones_delivered}/{gateModal.coverage.milestones_total} milestones delivered
                  </div>
                  <div style={{ display: "grid", gap: "4px" }}>
                    {gateModal.coverage.workstreams.map((w) => (
                      <div key={w.id} style={{ display: "flex", justifyContent: "space-between", gap: "10px", fontSize: "11px", color: "#5a5854" }}>
                        <span>{w.id} · {w.label}</span>
                        <span>{w.findings_total} findings · {w.milestones_delivered}/{w.milestones_total}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {gateModal.merlinVerdict && (
                <div style={{ marginBottom: "14px", border: "1px solid #d5e2d8", borderRadius: "8px", padding: "10px 12px", background: "rgba(45,110,78,.06)" }}>
                  <div style={{ fontFamily: '"Geist Mono", monospace', fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#2D6E4E", marginBottom: "6px" }}>
                    Merlin verdict · {humanizeVerdict(gateModal.merlinVerdict.verdict)}
                  </div>
                  {gateModal.merlinVerdict.notes && (
                    <div style={{ fontSize: "12px", lineHeight: 1.5, color: "#3a362f" }}>
                      {stripVerdictScaffolding(gateModal.merlinVerdict.notes)}
                    </div>
                  )}
                </div>
              )}

              {(gateModal.unlocksOnApprove || gateModal.unlocksOnReject) && (
                <div
                  style={{
                    border: "1px solid #e5e2de",
                    borderRadius: "8px",
                    padding: "10px 12px",
                    marginBottom: "14px",
                    background: "#fff",
                  }}
                >
                  {gateModal.unlocksOnApprove && (
                    <div style={{ fontSize: "12px", color: "#3a362f", marginBottom: gateModal.unlocksOnReject ? "6px" : 0 }}>
                      <strong style={{ color: "#2D6E4E" }}>Approve →</strong> {gateModal.unlocksOnApprove}
                    </div>
                  )}
                  {gateModal.unlocksOnReject && (
                    <div style={{ fontSize: "12px", color: "#3a362f" }}>
                      <strong style={{ color: "#8B6200" }}>Reject →</strong> {gateModal.unlocksOnReject}
                    </div>
                  )}
                </div>
              )}

              {gateModal.hypotheses && gateModal.hypotheses.length > 0 && (
                <div style={{ marginBottom: "14px" }}>
                  <div
                    style={{
                      fontFamily: '"Geist Mono", monospace',
                      fontSize: "9px",
                      fontWeight: 700,
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: "#5a5854",
                      marginBottom: "6px",
                    }}
                  >
                    Hypotheses ({gateModal.hypotheses.length})
                  </div>
                  <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", lineHeight: 1.5, color: "#3a362f" }}>
                    {gateModal.hypotheses.map((h) => (
                      <li key={h.id} style={{ marginBottom: "4px" }}>
                        {h.text}
                        {h.status && h.status !== "open" && (
                          <span style={{ color: "#78716A", marginLeft: "6px", fontSize: "10px" }}>· {h.status}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {gateModal.researchFindings && gateModal.researchFindings.length > 0 && (
                <div style={{ marginBottom: "14px" }}>
                  <div
                    style={{
                      fontFamily: '"Geist Mono", monospace',
                      fontSize: "9px",
                      fontWeight: 700,
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: "#5a5854",
                      marginBottom: "6px",
                    }}
                  >
                    Recent claims{typeof gateModal.findingsTotal === "number" ? ` (showing ${gateModal.researchFindings.length} of ${gateModal.findingsTotal})` : ""}
                  </div>
                  <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", lineHeight: 1.5, color: "#3a362f" }}>
                    {gateModal.researchFindings.map((f, i) => (
                      <li key={`${f.agent_id ?? "x"}-${i}`} style={{ marginBottom: "4px" }}>
                        {f.claim_text}
                        <span style={{ color: "#78716A", marginLeft: "6px", fontSize: "10px" }}>
                          {f.agent_id ?? "agent"}{f.confidence ? ` · ${f.confidence}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {gateModal.redteamFindings && gateModal.redteamFindings.length > 0 && (
                <div style={{ marginBottom: "14px", border: "1px solid rgba(139,98,0,0.3)", borderRadius: "8px", padding: "10px 12px", background: "rgba(139,98,0,.05)" }}>
                  <div
                    style={{
                      fontFamily: '"Geist Mono", monospace',
                      fontSize: "9px",
                      fontWeight: 700,
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: "#8B6200",
                      marginBottom: "6px",
                    }}
                  >
                    Red-team challenges
                  </div>
                  <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "12px", lineHeight: 1.5, color: "#3a362f" }}>
                    {gateModal.redteamFindings.map((f, i) => (
                      <li key={`rt-${i}`}>{f.claim_text}</li>
                    ))}
                  </ul>
                </div>
              )}

              {gateModal.openRisks && gateModal.openRisks.length > 0 && (
                <div style={{ marginBottom: "14px", color: "#8B6200", fontSize: "12px", lineHeight: 1.5 }}>
                  <strong>Open risks:</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: "16px" }}>
                    {gateModal.openRisks.map((risk, i) => (
                      <li key={`risk-${i}`}>{risk}</li>
                    ))}
                  </ul>
                </div>
              )}

              {gateModal.arbiterFlags && gateModal.arbiterFlags.length > 0 && (
                <div style={{ marginBottom: "14px", color: "#8B6200", fontSize: "12px", lineHeight: 1.5 }}>
                  <strong>Arbiter flagged:</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: "16px" }}>
                    {gateModal.arbiterFlags.map((flag, i) => (
                      <li key={`af-${i}`}>{flag}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div
                style={{
                  fontFamily: '"Geist Mono", monospace',
                  fontSize: "9px",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: "#8a8784",
                  marginBottom: "16px",
                }}
              >
                Gate ID: {gateModal.gateId}
              </div>
            </div>

            {/* Footer */}
            <div
              style={{
                flexShrink: 0,
                padding: "14px 24px 22px",
                borderTop: "1px solid #e5e2de",
                background: "#f9f7f4",
              }}
            >
              {gateModal.format === "data_decision" && gateModal.options && gateModal.options.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "8px" }}>
                  {gateModal.options.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => handleGateDecision(
                        gateModal.gateId,
                        opt.value as "skip_calculus" | "proceed_low_confidence" | "request_data_room",
                        opt.label,
                      )}
                      style={{
                        textAlign: "left",
                        padding: "12px 14px",
                        background: "#fff",
                        border: "1px solid #d5d2ce",
                        borderRadius: "8px",
                        cursor: "pointer",
                        fontFamily: '"Geist Mono", monospace',
                      }}
                    >
                      <div style={{ fontSize: "13px", fontWeight: 600, color: "#1a1814", marginBottom: "4px" }}>
                        {opt.label}
                      </div>
                      {opt.consequence && (
                        <div style={{ fontSize: "12px", color: "#5a5854", lineHeight: 1.4 }}>
                          {opt.consequence}
                        </div>
                      )}
                    </button>
                  ))}
                  <button
                    onClick={handleGateClose}
                    style={{
                      alignSelf: "flex-start",
                      marginTop: "4px",
                      padding: "8px 0",
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      fontFamily: '"Geist Mono", monospace',
                      fontSize: "12px",
                      color: "#78716A",
                      textDecoration: "underline",
                    }}
                  >
                    Decide later
                  </button>
                </div>
              ) : (
              <div style={{ display: "flex", justifyContent: "flex-start" }}>
                <button
                  onClick={handleGateClose}
                  style={{
                    padding: "10px 16px",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    fontFamily: '"Geist Mono", monospace',
                    fontSize: "12px",
                    color: "#78716A",
                    textDecoration: "underline",
                  }}
                  title="Close without losing the pending gate. Use the banner Approve/Reject to decide."
                >
                  Decide later
                </button>
              </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

