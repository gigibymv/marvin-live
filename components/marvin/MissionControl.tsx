"use client";

import React, { useCallback, useEffect, useState } from "react";
import type { ComponentType } from "react";
import Link from "next/link";
import RawMissionControlView from "../../UI Marvin/MissionControl.jsx";
import {
  buildInitialMessages,
  DEFAULT_WORKSPACE_TAB,
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
import { validateGate as apiValidateGate, getMissionProgress } from "@/lib/missions/api";

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
  findings: { id: string; agent_id: string | null; claim_text: string; confidence: string }[];
  deliverables: { id: string; label: string; status: string }[];
  activeAgent: string | null;
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
            console.log("text event:", event);
            // Agent status tracking for text events
            setMessages((current) =>
              current.concat({
                id: `${missionId}-${Date.now()}-stream`,
                from: "m",
                text: event.text,
              }),
            );
            break;
          case "tool_call":
            // Agent status tracking for text events
            setMessages((current) =>
              current.concat({
                id: `${missionId}-${Date.now()}-tool`,
                from: "m",
                text: `🔧 ${event.agent ?? "Agent"}: ${event.text}`,
              }),
            );
            break;
          case "tool_result":
            // Agent status tracking for text events
            setMessages((current) =>
              current.concat({
                id: `${missionId}-${Date.now()}-result`,
                from: "m",
                text: `✓ ${event.text}`,
              }),
            );
            break;
          case "gate_pending":
            setGateModal({
              gateId: event.gateId,
              title: event.title,
              summary: event.summary,
            });
            break;
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
                id: `${missionId}-${Date.now()}-done`,
                from: "m",
                text: `— ${event.label ?? "Agent"} finished —`,
              }),
            );
            break;
          case "finding_added":
            setLiveFindings((current) =>
              current.concat({
                id: `live-finding-${Date.now()}-${current.length}`,
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
  }, [eventStream, missionId, setRunState]);

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
          id: `${mission.id}-${Date.now()}-user`,
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
              id: `${mission.id}-${Date.now()}-marvin`,
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
          id: `${mission.id}-${Date.now()}-approve`,
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
              id: `${mission.id}-${Date.now()}-resumed`,
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
          id: `${mission.id}-${Date.now()}-reject`,
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
              id: `${mission.id}-${Date.now()}-stopped`,
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

  const handleGateClose = useCallback(() => {
    setGateModal(null);
  }, []);

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
  const findings = [...(progress?.findings ?? []), ...liveFindings];

  // Compute deliverables (snapshot + live SSE additions, deduped by id)
  const seedDeliverables = (progress?.deliverables ?? []).map(d => ({
    id: d.id,
    label: d.deliverable_type,
    status: d.file_path ? "ready" : "pending",
  }));
  const seedIds = new Set(seedDeliverables.map(d => d.id));
  const liveOnlyDeliverables = liveDeliverables
    .filter(d => !seedIds.has(d.id))
    .map(d => ({ id: d.id, label: d.label, status: "ready" }));
  const deliverables = [...seedDeliverables, ...liveOnlyDeliverables];


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

            <p
              style={{
                fontSize: "13px",
                lineHeight: 1.6,
                color: "#5a5854",
                marginBottom: "16px",
              }}
            >
              {gateModal.summary || "A gate is waiting for human review before the mission can proceed."}
            </p>

            <div
              style={{
                fontFamily: "system-ui",
                fontSize: "9px",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "#5a5854",
                marginBottom: "16px",
              }}
            >
              Gate ID: {gateModal.gateId}
            </div>

            <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
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
      )}
    </>
  );
}

