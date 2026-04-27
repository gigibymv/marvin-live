"use client";

import React, { useCallback, useEffect, useState } from "react";
import type { ComponentType } from "react";
import Link from "next/link";
import RawMissionControlView from "../../UI Marvin/MissionControl.jsx";
import {
  buildInitialMessages,
  DEFAULT_WORKSPACE_TAB,
  formatGatePendingChatMessage,
  formatGatePendingFeedSignal,
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
  getMissionProgress,
  getDeliverableDownloadUrl,
} from "@/lib/missions/api";
import { mapGateReviewPayloadToModal } from "@/lib/missions/gate-review";

let _msgCounter = 0;
function makeMessageId(missionId: string, suffix: string): string {
  _msgCounter += 1;
  const rand = Math.random().toString(36).slice(2, 8);
  return `${missionId}-${Date.now()}-${_msgCounter}-${rand}-${suffix}`;
}

const TOOL_LABELS: Record<string, string> = {
  add_finding_to_mission: "recording finding",
  mark_milestone_delivered: "completing milestone",
  list_hypotheses: "loading hypotheses",
  list_findings: "loading findings",
  generate_market_brief: "drafting market brief",
  generate_competitive_brief: "drafting competitive brief",
  generate_financial_brief: "drafting financial brief",
  generate_risk_brief: "drafting risk brief",
  generate_investment_memo: "drafting investment memo",
  check_internal_consistency: "checking consistency",
  web_search: "searching the web",
};

function humanizeToolCall(agent: unknown, text: unknown): string {
  const agentName = agent ? String(agent) : "Agent";
  const raw = String(text ?? "");
  const label = TOOL_LABELS[raw] ?? raw.replace(/_/g, " ");
  return `${agentName} — ${label}`;
}

const DELIVERABLE_LABELS: Record<string, string> = {
  market_brief: "Market brief",
  competitive_brief: "Competitive analysis",
  financial_brief: "Financial analysis",
  risk_brief: "Risk / Red-team",
  investment_memo: "Investment memo",
  engagement_brief: "Engagement brief",
};

function humanizeDeliverableType(t: unknown): string {
  const raw = String(t ?? "deliverable");
  return DELIVERABLE_LABELS[raw] ?? raw.replace(/_/g, " ");
}

function humanizeToolResult(text: unknown): string {
  const raw = String(text ?? "");
  if (!raw) return "step complete";
  // Strip raw JSON dumps from chat surface
  if (raw.startsWith("{") || raw.startsWith("[")) {
    return "step complete";
  }
  if (raw.length > 240) {
    return raw.slice(0, 240).trim() + "…";
  }
  return raw;
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
  hypotheses: { id: string; text: string; status: string }[];
  activity?: Array<{ id: string; ag?: string; text?: string; ts?: string; claim_text?: string; confidence?: string }>;
  findings: Array<{ id: string; agent_id?: string | null; claim_text?: string; confidence?: string | null; ag?: string; text?: string; ts?: string; workstream_id?: string }>;
  deliverables: { id: string; label: string; status: string; href?: string }[];
  activeAgent: string | null;
  workstreamContent?: {
    id: string;
    label: string;
    findings: Array<{ id: string; claim_text: string; confidence: string | null; agent_id: string | null }>;
    milestones: Array<{ id: string; label: string; status: string }>;
  }[];
  pendingGateBanner?: { onResume: () => void; title?: string; summary?: string } | null;
  briefStatus?: "pending" | "now" | "completed";
  nextCheckpointLabel?: string | null;
}

const MissionControlView = RawMissionControlView as unknown as ComponentType<MissionControlViewProps>;
type MissionProgressSnapshot = Awaited<ReturnType<typeof getMissionProgress>>;

function assertGateLifecycleContract(data: MissionProgressSnapshot): void {
  for (const gate of data.gates ?? []) {
    if (typeof gate.lifecycle_status !== "string" || typeof gate.is_open !== "boolean") {
      throw new Error("Backend /progress gate payload is missing lifecycle_status/is_open");
    }
  }
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

  // Progress state for real-time data from backend
  const [progress, setProgress] = useState<MissionProgressSnapshot | null>(null);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, "idle" | "active" | "done">>({});
  const [liveFindings, setLiveFindings] = useState<Array<{ id: string; claim_text: string; confidence?: string }>>([]);
  const [milestoneStatusOverrides, setMilestoneStatusOverrides] = useState<Record<string, string>>({});
  const [gatePayloads, setGatePayloads] = useState<Record<string, MissionGateModalState>>({});
  const [pausedForGate, setPausedForGate] = useState(false);

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
        setMessages(nextMission ? buildInitialMessages(nextMission) : []);
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
            setLiveFindings((current) =>
              current.concat({
                id: makeMessageId(missionId, "tool"),
                claim_text: humanizeToolCall(event.agent, event.text),
                confidence: "step",
              }),
            );
            break;
          case "tool_result":
            setLiveFindings((current) =>
              current.concat({
                id: makeMessageId(missionId, "result"),
                claim_text: humanizeToolResult(event.text),
                confidence: "done",
              }),
            );
            break;
          case "gate_pending": {
            // Chat-first gate UX. The modal no longer auto-opens; instead the
            // gate is announced in chat and signalled in the live feed. The
            // persistent banner (derived from progress.gates) is the entry
            // point that opens the detailed review surface on user action.
            // Source of truth for gate state remains the backend gate row.
            const modalPayload = mapGateReviewPayloadToModal(event);
            setGatePayloads((current) => ({
              ...current,
              [modalPayload.gateId]: modalPayload,
            }));
            setMessages((current) =>
              current.concat({
                id: makeMessageId(missionId, "gate-pending"),
                from: "m",
                text: formatGatePendingChatMessage(event),
              }),
            );
            setLiveFindings((current) =>
              current.concat({
                id: makeMessageId(missionId, "gate-signal"),
                claim_text: formatGatePendingFeedSignal(event),
                confidence: "gate",
              }),
            );
            setPausedForGate(true);
            setRunState(missionId, { isStreaming: false });
            void refreshProgress();
            break;
          }
          case "agent_active":
            setActiveAgent(event.agent ?? null);
            setAgentStatuses((current) => ({
              ...current,
              [(event.agent ?? "unknown").toLowerCase()]: "active",
            }));
            setLiveFindings((current) =>
              current.concat({
                id: makeMessageId(missionId, "agent-active"),
                claim_text: `${event.agent ?? "Agent"} started`,
                confidence: "active",
              }),
            );
            break;
          case "agent_done":
            setLiveFindings((current) =>
              current.concat({
                id: makeMessageId(missionId, "done"),
                claim_text: `${event.label ?? "Agent"} finished`,
                confidence: "done",
              }),
            );
            break;
          case "finding_added":
            setLiveFindings((current) =>
              current.concat({
                id: makeMessageId(missionId, "finding"),
                claim_text: event.text,
                confidence: event.badge,
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
              current.concat({
                id: makeMessageId(missionId, "milestone"),
                claim_text: event.label
                  ? `Milestone complete · ${event.label}`
                  : `Milestone complete · ${event.milestoneId ?? "mission step"}`,
                confidence: "done",
              }),
            );
            void refreshProgress();
            break;
          case "deliverable_ready":
            setLiveFindings((current) =>
              current.concat({
                id: makeMessageId(missionId, "deliverable"),
                claim_text: event.label
                  ? `Deliverable ready · ${event.label}`
                  : "Deliverable ready",
                confidence: "ready",
              }),
            );
            void refreshProgress();
            break;
          case "run_end":
            setPausedForGate(false);
            setRunState(missionId, { isStreaming: false });
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
  }, [eventStream, missionId, setRunState, refreshProgress]);

  useEffect(() => {
    setRunState(missionId, { isStreaming: false });
  }, [missionId, setRunState]);

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

  // Handle gate approval
  const handleGateApprove = useCallback(
    async (gateId: string, notes: string = "") => {
      if (!mission) return;

      setGateModal(null);
      setPausedForGate(false);
      setRunState(mission.id, { isStreaming: true });

      // Add user action message
      // Agent status tracking for text events
      setMessages((current) =>
        current.concat({
          id: makeMessageId(mission.id, "approve"),
          from: "u",
          text: `✓ Gate approved: ${gateId}`,
        }),
      );

      try {
        // For HTTP repository, call the API
        if (repository.kind === "http") {
          const result = await apiValidateGate(mission.id, gateId, "APPROVED", notes);

          // Agent status tracking for text events
          setMessages((current) =>
            current.concat({
              id: makeMessageId(mission.id, "resumed"),
              from: "m",
              text: `Gate validated. Resuming execution... (${result.resume_id})`,
            }),
          );

          // If there's an active stream, send a system message to continue
          if (eventStream.kind === "fetch" && eventStream.sendMessage) {
            // The graph should resume automatically, but we can also send a message
            // to continue the conversation
          }
          if (result.status !== "resumed" && result.status !== "resume_pending") {
            setRunState(mission.id, { isStreaming: false });
          }
        }
      } catch (error) {
        console.error("Failed to validate gate:", error);
        setRunState(mission.id, { isStreaming: false });
        setStreamError(error instanceof Error ? error.message : "Failed to validate gate");
      }
    },
    [mission, repository.kind, eventStream, setRunState]
  );

  // Handle gate rejection
  const handleGateReject = useCallback(
    async (gateId: string, notes: string = "") => {
      if (!mission) return;

      setGateModal(null);
      setPausedForGate(false);
      setRunState(mission.id, { isStreaming: true });

      // Add user action message
      // Agent status tracking for text events
      setMessages((current) =>
        current.concat({
          id: makeMessageId(mission.id, "reject"),
          from: "u",
          text: `✗ Gate rejected: ${gateId}`,
        }),
      );

      try {
        // For HTTP repository, call the API
        if (repository.kind === "http") {
          const result = await apiValidateGate(mission.id, gateId, "REJECTED", notes);

          // Agent status tracking for text events
          setMessages((current) =>
            current.concat({
              id: makeMessageId(mission.id, "stopped"),
              from: "m",
              text: `Gate rejected. Awaiting further instructions.`,
            }),
          );
          if (result.status !== "resumed" && result.status !== "resume_pending") {
            setRunState(mission.id, { isStreaming: false });
          }
        }
      } catch (error) {
        console.error("Failed to validate gate:", error);
        setRunState(mission.id, { isStreaming: false });
        setStreamError(error instanceof Error ? error.message : "Failed to validate gate");
      }
    },
    [mission, repository.kind, setRunState]
  );

  // Deferring closes the modal but does NOT call the validate API.
  // The pending gate state is preserved server-side in the LangGraph checkpoint
  // and will re-interrupt on the next chat turn or page reload.
  const handleGateClose = useCallback(() => {
    if (gateModal && mission) {
      setMessages((current) =>
        current.concat({
          id: makeMessageId(mission.id, "deferred"),
          from: "m",
          text: `Gate "${gateModal.title}" deferred. The mission is paused and your decision is preserved — reopen anytime to approve or reject.`,
        }),
      );
    }
    setGateModal(null);
    setRunState(missionId, { isStreaming: false });
  }, [gateModal, mission, missionId, setRunState]);

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
    if (g.status === "completed") return "completed";
    if (g.lifecycle_status === "open" || g.is_open) return "now";
    return "later";
  };
  const checkpoints = (progress?.gates ?? []).map(g => ({
    id: g.id,
    label: String(g.gate_type ?? "").replace(/_/g, " "),
    status: gateStatusToCheckpoint(g),
  }));
  const nextCheckpointLabel =
    checkpoints.find((cp) => cp.status === "now")?.label ?? null;
  const deliveredMilestones = allMilestones.filter((m) => {
    const liveStatus = milestoneStatusOverrides[m.id];
    return (liveStatus ?? m.status) === "delivered";
  }).length;
  const progressRatio = allMilestones.length > 0 ? deliveredMilestones / allMilestones.length : 0;
  const missionForView = {
    ...mission,
    progress: progressRatio,
    checkpoint: nextCheckpointLabel ?? "No open checkpoint",
  };

  // Compute hypotheses
  const hypotheses = progress?.hypotheses ?? [];

  // Compute findings (snapshot from /progress + live SSE additions)
  // When a workstream tab is selected, scope findings to that workstream so
  // the center pane reflects per-stream content instead of a global feed.
  // Normalize findings to the shape the presentational Feed expects
  // ({ id, ag, text, ts }), so progress + SSE rows render correctly.
  const normalizeFinding = (f: any) => ({
    id: f.id,
    ag: (f.agent_id ?? f.ag ?? "agent").toString().toUpperCase(),
    text: f.claim_text ?? f.text ?? "",
    ts: f.ts ?? "",
    confidence: f.confidence,
    workstream_id: f.workstream_id,
    agent_id: f.agent_id,
    claim_text: f.claim_text,
  });
  const allFindings = (progress?.findings ?? []).map(normalizeFinding);
  const activity = liveFindings.map(normalizeFinding);
  // Tab id "ws1" maps to backend workstream id "W1", etc.
  // Strict filter: only show findings tagged to the selected workstream.
  // Untagged findings are intentionally excluded so per-tab content stays
  // distinct rather than every untagged finding bleeding into all tabs.
  const tabToWorkstream = (tab: string) => tab.replace(/^ws/i, "W");
  const selectedWs = selectedTab ? tabToWorkstream(selectedTab) : null;
  const findings = selectedWs
    ? allFindings.filter((f) => f.workstream_id === selectedWs)
    : allFindings;

  // Compute deliverables (snapshot + live SSE additions, deduped by id)
  const seedDeliverables = (progress?.deliverables ?? []).map((d) => ({
    id: d.id,
    label: humanizeDeliverableType(d.deliverable_type),
    status: d.status === "ready" && d.file_path ? "ready" : "pending",
    href: d.status === "ready" && d.file_path ? getDeliverableDownloadUrl(d.file_path) : undefined,
  }));
  const deliverables = seedDeliverables;

  // Build per-workstream content for the center tabs from real findings.
  const workstreamContent = (progress?.workstreams ?? []).map((ws) => ({
    id: ws.id,
    label: ws.label,
    findings: (progress?.findings ?? []).filter((f: any) => f.workstream_id === ws.id),
    milestones: (progress?.milestones ?? []).filter((m: any) => m.workstream_id === ws.id),
  }));

  const hasPendingGate = (progress?.gates ?? []).some((g) => g.lifecycle_status === "open" || g.is_open);
  const showDeferredBanner = hasPendingGate && !gateModal;
  const pendingGate = (progress?.gates ?? []).find((g) => g.lifecycle_status === "open" || g.is_open);
  const pendingGateModal =
    pendingGate
      ? gatePayloads[pendingGate.id] ??
        mapGateReviewPayloadToModal(pendingGate.review_payload, {
          id: pendingGate.id,
          gate_type: pendingGate.gate_type,
        })
      : null;
  const briefStatus: "pending" | "now" | "completed" = progress?.framing ? "completed" : "now";
  const showTyping = runState.isStreaming && !pausedForGate;


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
        selectedTab={selectedTab}
        onSelectTab={(tab: WorkspaceTab) => setWorkspaceTab(mission.id, tab)}
        isTyping={showTyping}
        defaultTab={DEFAULT_WORKSPACE_TAB}
        gateModal={null} // We handle gate modal separately
        onGateClose={handleGateClose}
        backendState={backendState}
        agents={agents}
        checkpoints={checkpoints}
        hypotheses={hypotheses}
        activity={activity}
        findings={findings}
        deliverables={deliverables}
        activeAgent={activeAgent}
        workstreamContent={workstreamContent}
        pendingGateBanner={
          showDeferredBanner
            ? {
                onResume: reopenGateFromCheckpoint,
                title: pendingGateModal?.title,
                summary: pendingGateModal?.summary,
              }
            : null
        }
        briefStatus={briefStatus}
        nextCheckpointLabel={nextCheckpointLabel}
      />

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
              padding: "22px 24px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "14px",
              }}
            >
              <div>
                <div
                  style={{
                    fontFamily: "system-ui",
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
                    fontFamily: "Georgia, serif",
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

            {gateModal.stage && (
              <div
                style={{
                  fontFamily: "system-ui",
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
                <div style={{ fontFamily: "system-ui", fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#5a5854", marginBottom: "6px" }}>
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
                <div style={{ fontFamily: "system-ui", fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#5a5854", marginBottom: "6px" }}>
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
                <div style={{ fontFamily: "system-ui", fontSize: "9px", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#2D6E4E", marginBottom: "6px" }}>
                  Merlin verdict · {gateModal.merlinVerdict.verdict}
                </div>
                {gateModal.merlinVerdict.notes && (
                  <div style={{ fontSize: "12px", lineHeight: 1.5, color: "#3a362f" }}>
                    {gateModal.merlinVerdict.notes}
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
              <div style={{ marginBottom: "14px", maxHeight: "180px", overflowY: "auto" }}>
                <div
                  style={{
                    fontFamily: "system-ui",
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
              <div style={{ marginBottom: "14px", maxHeight: "180px", overflowY: "auto" }}>
                <div
                  style={{
                    fontFamily: "system-ui",
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
                    fontFamily: "system-ui",
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
                fontFamily: "system-ui",
                fontSize: "9px",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "#8a8784",
                marginBottom: "16px",
              }}
            >
              Gate ID: {gateModal.gateId}
            </div>

            <div style={{ display: "flex", gap: "10px", justifyContent: "space-between", alignItems: "center" }}>
              <button
                onClick={handleGateClose}
                style={{
                  padding: "10px 16px",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  fontFamily: "system-ui",
                  fontSize: "12px",
                  color: "#78716A",
                  textDecoration: "underline",
                }}
                title="Close without losing the pending gate. State is preserved — you can decide later."
              >
                Decide later
              </button>
              <div style={{ display: "flex", gap: "12px" }}>
                <button
                  onClick={() => handleGateReject(gateModal.gateId, "")}
                  style={{
                    padding: "10px 20px",
                    background: "#fff",
                    border: "1px solid #d5d2ce",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontFamily: "system-ui",
                    fontSize: "13px",
                    fontWeight: 500,
                    color: "#5a5854",
                  }}
                >
                  Reject
                </button>
                <button
                  onClick={() => handleGateApprove(gateModal.gateId, "")}
                  style={{
                    padding: "10px 20px",
                    background: "#1a1814",
                    border: "none",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontFamily: "system-ui",
                    fontSize: "13px",
                    fontWeight: 500,
                    color: "#fff",
                  }}
                >
                  Approve
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

