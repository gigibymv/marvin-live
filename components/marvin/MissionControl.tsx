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
  findings: Array<{ id: string; agent_id?: string | null; claim_text?: string; confidence?: string | null; ag?: string; text?: string; ts?: string; workstream_id?: string }>;
  deliverables: { id: string; label: string; status: string; href?: string }[];
  activeAgent: string | null;
  workstreamContent?: {
    id: string;
    label: string;
    findings: Array<{ id: string; claim_text: string; confidence: string | null; agent_id: string | null }>;
    milestones: Array<{ id: string; label: string; status: string }>;
  }[];
  pendingGateBanner?: { onResume: () => void } | null;
}

const MissionControlView = RawMissionControlView as unknown as ComponentType<MissionControlViewProps>;

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
  const [progress, setProgress] = useState<{
    gates: any[];
    milestones: any[];
    findings: any[];
    hypotheses: any[];
    deliverables: any[];
    workstreams: any[];
  } | null>(null);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, "idle" | "active" | "done">>({});
  const [liveFindings, setLiveFindings] = useState<Array<{ id: string; claim_text: string; confidence?: string }>>([]);
  const [liveDeliverables, setLiveDeliverables] = useState<Array<{ id: string; label: string }>>([]);
  const [milestoneStatusOverrides, setMilestoneStatusOverrides] = useState<Record<string, string>>({});

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
      setProgress(data as any);
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
            setMessages((current) =>
              current.concat({
                id: makeMessageId(missionId, "tool"),
                from: "m",
                text: humanizeToolCall(event.agent, event.text),
              }),
            );
            break;
          case "tool_result":
            setMessages((current) =>
              current.concat({
                id: makeMessageId(missionId, "result"),
                from: "m",
                text: humanizeToolResult(event.text),
              }),
            );
            break;
          case "gate_pending": {
            // Chat-first gate UX. The modal no longer auto-opens; instead the
            // gate is announced in chat and signalled in the live feed. The
            // persistent banner (derived from progress.gates) is the entry
            // point that opens the detailed review surface on user action.
            // Source of truth for gate state remains the backend gate row.
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
            void refreshProgress();
            break;
          }
          case "agent_active":
            setActiveAgent(event.agent ?? null);
            setAgentStatuses((current) => ({
              ...current,
              [event.agent ?? "unknown"]: "active",
            }));
            break;
          case "agent_done":
            // Agent status tracking for text events
            setMessages((current) =>
              current.concat({
                id: makeMessageId(missionId, "done"),
                from: "m",
                text: `— ${event.label ?? "Agent"} finished —`,
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
            void refreshProgress();
            break;
          case "deliverable_ready":
            if (event.deliverableId) {
              setLiveDeliverables((current) =>
                current.some((d) => d.id === event.deliverableId)
                  ? current
                  : current.concat({
                      id: event.deliverableId as string,
                      label: event.label ?? "deliverable",
                    }),
              );
            }
            void refreshProgress();
            break;
          case "run_end":
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
          await eventStream.sendMessage(value, false);
        } catch (error) {
          console.error("Failed to send message:", error);
          setRunState(mission.id, { isStreaming: false });
          setStreamError(error instanceof Error ? error.message : "Failed to send message");
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
        }
      } catch (error) {
        console.error("Failed to validate gate:", error);
        setStreamError(error instanceof Error ? error.message : "Failed to validate gate");
      }
    },
    [mission, repository.kind, eventStream]
  );

  // Handle gate rejection
  const handleGateReject = useCallback(
    async (gateId: string, notes: string = "") => {
      if (!mission) return;

      setGateModal(null);

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
          await apiValidateGate(mission.id, gateId, "REJECTED", notes);

          // Agent status tracking for text events
          setMessages((current) =>
            current.concat({
              id: makeMessageId(mission.id, "stopped"),
              from: "m",
              text: `Gate rejected. Awaiting further instructions.`,
            }),
          );
        }
      } catch (error) {
        console.error("Failed to validate gate:", error);
        setStreamError(error instanceof Error ? error.message : "Failed to validate gate");
      }
    },
    [mission, repository.kind]
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
  }, [gateModal, mission]);

  // Re-open a deferred gate from the checkpoint surface.
  const reopenGateFromCheckpoint = useCallback(() => {
    if (!progress) return;
    const pending = (progress.gates ?? []).find((g) => g.status === "pending");
    if (!pending) return;
    setGateModal((current) =>
      current ?? {
        gateId: pending.id,
        gateType: pending.gate_type,
        title: pending.gate_type?.replace(/_/g, " ") ?? "Validation required",
        summary:
          "A gate is waiting for human review. Approve, reject, or close to decide later — the mission state is preserved.",
      },
    );
  }, [progress]);

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
    return {
      id: ws.assigned_agent?.toLowerCase() ?? ws.id,
      name: ws.assigned_agent ?? ws.id,
      role: ws.label,
      status: agentStatuses[ws.assigned_agent?.toLowerCase() ?? ""] ?? (activeAgent === ws.assigned_agent?.toLowerCase() ? "active" : "idle"),
      milestonesTotal: wsMilestones.length,
      milestonesDelivered: delivered,
    };
  });

  // Compute checkpoints from gates
  const checkpoints = (progress?.gates ?? []).map(g => ({
    id: g.id,
    label: g.gate_type,
    status: g.status === "completed" ? "done" : g.status === "pending" ? "pending" : "pending",
  }));

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
  const allFindings = [
    ...(progress?.findings ?? []).map(normalizeFinding),
    ...liveFindings.map(normalizeFinding),
  ];
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
    status: d.file_path ? "ready" : "pending",
    href: d.file_path ? getDeliverableDownloadUrl(d.file_path) : undefined,
  }));
  const seedIds = new Set(seedDeliverables.map((d) => d.id));
  const liveOnlyDeliverables = liveDeliverables
    .filter((d) => !seedIds.has(d.id))
    .map((d) => ({ id: d.id, label: d.label, status: "ready", href: undefined as string | undefined }));
  const deliverables = [...seedDeliverables, ...liveOnlyDeliverables];

  // Build per-workstream content for the center tabs from real findings.
  const workstreamContent = (progress?.workstreams ?? []).map((ws) => ({
    id: ws.id,
    label: ws.label,
    findings: (progress?.findings ?? []).filter((f: any) => f.workstream_id === ws.id),
    milestones: (progress?.milestones ?? []).filter((m: any) => m.workstream_id === ws.id),
  }));

  const hasPendingGate = (progress?.gates ?? []).some((g) => g.status === "pending");
  const showDeferredBanner = hasPendingGate && !gateModal;


  // Render with gate modal that includes approve/reject buttons
  return (
    <>
      <MissionControlView
        mission={mission}
        messages={messages}
        initialMessages={messages}
        chatDraft={chatDraft}
        onChatDraftChange={(value: string) => setChatDraft(mission.id, value)}
        onSendMessage={handleSendMessage}
        selectedTab={selectedTab}
        onSelectTab={(tab: WorkspaceTab) => setWorkspaceTab(mission.id, tab)}
        isTyping={runState.isStreaming}
        defaultTab={DEFAULT_WORKSPACE_TAB}
        gateModal={null} // We handle gate modal separately
        onGateClose={handleGateClose}
        backendState={backendState}
        agents={agents}
        checkpoints={checkpoints}
        hypotheses={hypotheses}
        findings={findings}
        deliverables={deliverables}
        activeAgent={activeAgent}
        workstreamContent={workstreamContent}
        pendingGateBanner={showDeferredBanner ? { onResume: reopenGateFromCheckpoint } : null}
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

