"use client";

import React, { useMemo } from "react";
import type {
  BackendConnectionState,
  Mission,
  MissionChatMessage,
  MissionGateModalState,
  WorkspaceTab,
} from "@/lib/missions/types";
import "./Tokens.css";
import { LeftRail } from "./LeftRail";
import { CenterPane, type CenterFinding, type CenterActivityItem } from "./CenterPane";
import { RightRail } from "./RightRail";

// Match the prop contract of the legacy `MissionControlView` (UI Marvin/MissionControl.jsx).
export interface MissionControlV2ViewProps {
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
  activity?: Array<{ id: string; ag?: string; text?: string; ts?: string; claim_text?: string; confidence?: string; kind?: string }>;
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

const TAB_IDS: WorkspaceTab[] = ["brief", "ws1", "ws2", "ws3", "ws4", "final"];

function emptyTabMap<T>(): Record<WorkspaceTab, T[]> {
  return TAB_IDS.reduce((acc, id) => {
    acc[id] = [];
    return acc;
  }, {} as Record<WorkspaceTab, T[]>);
}

// Map a finding/output's section_id|workstream_id to a tab id.
function routeToTab(sectionId: string | null | undefined, workstreamId: string | null | undefined): WorkspaceTab | null {
  const raw = (sectionId ?? workstreamId ?? "").trim();
  if (!raw) return null;
  const lower = raw.toLowerCase();
  if (lower === "brief") return "brief";
  if (lower === "final") return "final";
  // W1 / W2 / W3 / W4 → ws1..ws4
  const match = lower.match(/^w(\d)$/);
  if (match) {
    const n = match[1];
    if (n === "1" || n === "2" || n === "3" || n === "4") return (`ws${n}` as WorkspaceTab);
  }
  if (lower === "ws1" || lower === "ws2" || lower === "ws3" || lower === "ws4") return lower as WorkspaceTab;
  return null;
}

// Bug #3 (frontend hide): suppress the framing memo deliverable label without
// touching the backend. Full removal lives in Phase C.
const HIDDEN_DELIVERABLE_LABELS = new Set(["framing memo", "framing_memo"]);

function isFramingMemo(label: string): boolean {
  return HIDDEN_DELIVERABLE_LABELS.has(label.trim().toLowerCase());
}

export function MissionControlV2View(props: MissionControlV2ViewProps): React.ReactElement {
  const {
    mission,
    messages,
    chatDraft,
    onChatDraftChange,
    onSendMessage,
    selectedTab,
    onSelectTab,
    isTyping,
    agents,
    checkpoints,
    hypotheses,
    activity,
    findings,
    deliverables,
    sectionTabs,
    pendingGateBanner,
    waitState,
    currentNarration,
    onOpenDeliverable,
    onGateApprove,
    onGateReject,
  } = props;

  const visibleDeliverables = useMemo(
    () => deliverables.filter(d => !isFramingMemo(d.label)),
    [deliverables],
  );

  // Build findingsMap from flat findings[]; unrouted entries land in `brief`
  // so they remain visible somewhere. Sort each tab so deliverables sit at
  // the top of the thread (most "shippable" outputs first), then milestones,
  // then findings. Within a kind we keep insertion order.
  // Bug 2: tab ✓ flips to completed before lingering milestone rows have
  // a paired deliverable, so users saw "REPORT GENERATING…" rows on a
  // tab that was already checked. Use sectionTabs to know which tabs the
  // backend considers completed and mark milestones on those tabs as
  // terminal so MilestoneRow suppresses the spinner copy (or hides the
  // row entirely when no deliverable will ever be paired to it).
  const completedTabIds = useMemo<Set<WorkspaceTab>>(() => {
    const set = new Set<WorkspaceTab>();
    if (!sectionTabs) return set;
    for (const t of sectionTabs) {
      if (t.status === "completed") set.add(t.id);
    }
    return set;
  }, [sectionTabs]);

  const findingsMap = useMemo<Record<WorkspaceTab, CenterFinding[]>>(() => {
    const map = emptyTabMap<CenterFinding>();
    for (const f of findings) {
      const tab = routeToTab(f.section_id ?? null, f.workstream_id ?? null) ?? "brief";
      const text = f.claim_text ?? f.text ?? "";
      map[tab].push({
        id: f.id,
        kind: f.kind,
        agent: f.ag ?? f.agent_id ?? undefined,
        text,
        ts: f.ts ?? "",
        confidence: f.confidence ?? null,
        impact: f.impact ?? null,
        hypothesis_label: f.hypothesis_label ?? null,
        source: f.source_id ?? null,
        onOpen: f.onOpen,
      });
    }
    const kindRank = (k: CenterFinding["kind"]): number => {
      if (k === "deliverable") return 0;
      if (k === "milestone") return 1;
      return 2;
    };
    // Strip a leading "Deliverable ready · " / "Milestone complete · " prefix
    // and lowercase so we can match the artifact text across kinds.
    const normalizeMatchText = (raw: string): string =>
      raw
        .replace(/^\s*(deliverable\s+ready|milestone\s+complete)\s*[·\-:]\s*/i, "")
        .trim()
        .toLowerCase();
    for (const tab of TAB_IDS) {
      const deliverableLabels = new Set(
        map[tab].filter((m) => m.kind === "deliverable").map((d) => normalizeMatchText(d.text ?? "")),
      );
      // Drop a milestone only when a paired deliverable already exists on
      // the same tab. Otherwise the milestone is the sole signal that the
      // step is done (e.g., Dora completed Market size before papyrus has
      // generated the per-milestone deliverable file). Without this fallback
      // the Market Analysis tab read as empty even though work was visibly
      // happening in the activity feed.
      map[tab] = map[tab].filter((item) => {
        if (item.kind !== "milestone") return true;
        const key = normalizeMatchText(item.text ?? "");
        return key.length > 0 && !deliverableLabels.has(key);
      });
      const tabCompleted = completedTabIds.has(tab);
      if (tabCompleted) {
        map[tab] = map[tab].map((item) =>
          item.kind === "milestone" ? { ...item, isTerminal: true } : item,
        );
      }
      map[tab] = map[tab]
        .map((item, index) => ({ item, index }))
        .sort((a, b) => {
          const r = kindRank(a.item.kind) - kindRank(b.item.kind);
          return r !== 0 ? r : a.index - b.index;
        })
        .map((entry) => entry.item);
    }
    return map;
  }, [findings, completedTabIds]);

  // Activity is a single live tape today — assign to whichever tab the user
  // is on so it remains visible. (When backend gains per-tab activity, this
  // is the place to route it properly.) Drop `deliverable` and `milestone`
  // echoes from the activity tape — they already render as full rows in
  // Outputs, and the duplicate compact mono row was confusing (count went
  // up but visually nothing new appeared because the eye expects the
  // larger top-of-pane row).
  const activityMap = useMemo<Record<WorkspaceTab, CenterActivityItem[]>>(() => {
    const map = emptyTabMap<CenterActivityItem>();
    if (!activity) return map;
    // Bug 5: server returns activity in chronological order, so a 97-item
    // feed pushed the latest entries below the viewport and the user only
    // saw stale items. Surface newest first so the most recent step is
    // always visible at the top of the activity pane.
    const items: CenterActivityItem[] = activity
      .map((a, idx) => ({
        id: a.id,
        kind: a.kind,
        agent: a.ag,
        text: a.claim_text ?? a.text ?? "",
        ts: a.ts ?? "",
        _idx: idx,
      }))
      .sort((a, b) => {
        if (a.ts && b.ts && a.ts !== b.ts) return a.ts < b.ts ? 1 : -1;
        return b._idx - a._idx;
      })
      .map(({ _idx, ...rest }) => rest);
    map[selectedTab] = items;
    return map;
  }, [activity, selectedTab]);

  const tabs = useMemo(() => {
    if (sectionTabs && sectionTabs.length > 0) return sectionTabs;
    // Fallback: derive minimal tab set.
    return TAB_IDS.map(id => ({ id, label: id.toUpperCase(), status: "pending" as const }));
  }, [sectionTabs]);

  const banner = pendingGateBanner && !pendingGateBanner.actionInFlight ? pendingGateBanner : null;

  const missionStatusLabel = mission.status === "active" ? "Running" : "Completed";

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "256px 1fr 310px",
        height: "100vh",
        width: "100%",
        overflow: "hidden",
        background: "var(--paper)",
      }}
    >
      <LeftRail
        mission={mission}
        agents={agents}
        hypotheses={hypotheses}
        deliverables={visibleDeliverables}
      />

      <div style={{ position: "relative", display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        {banner && (
          <div
            role="region"
            aria-label="Gate review pending"
            style={{
              padding: "10px 24px",
              background: "rgba(139,98,0,.10)",
              borderBottom: "1px solid rgba(139,98,0,.30)",
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexShrink: 0,
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: "var(--m)", fontSize: 9, fontWeight: 700, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--amber)", marginBottom: 4 }}>
                Gate pending {banner.title ? `· ${banner.title}` : ""}
              </div>
              {banner.summary && (
                <div style={{ fontSize: 12, lineHeight: 1.6, color: "var(--ink2)" }}>{banner.summary}</div>
              )}
            </div>
            <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
              {banner.onApprove && (
                <button
                  type="button"
                  onClick={banner.onApprove}
                  style={{
                    fontFamily: "var(--m)", fontSize: 9, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase",
                    padding: "6px 14px", background: "var(--ink)", color: "var(--paper)",
                    border: "none", borderRadius: 4, cursor: "pointer",
                  }}
                >
                  Approve
                </button>
              )}
              {banner.onReject && (
                <button
                  type="button"
                  onClick={banner.onReject}
                  style={{
                    fontFamily: "var(--m)", fontSize: 9, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase",
                    padding: "6px 14px", background: "transparent", color: "var(--ink)",
                    border: "1px solid var(--ruleh)", borderRadius: 4, cursor: "pointer",
                  }}
                >
                  Reject
                </button>
              )}
              <button
                type="button"
                onClick={banner.onResume}
                style={{
                  fontFamily: "var(--m)", fontSize: 9, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase",
                  padding: "6px 14px", background: "transparent", color: "var(--ink)",
                  border: "1px solid var(--ruleh)", borderRadius: 4, cursor: "pointer",
                }}
              >
                Review
              </button>
            </div>
          </div>
        )}

        <CenterPane
          findingsMap={findingsMap}
          activityMap={activityMap}
          tabs={tabs}
          checkpoints={checkpoints}
          waitState={waitState ?? null}
          missionClient={mission.client}
          missionStatusLabel={missionStatusLabel}
          selectedTab={selectedTab}
          onSelectTab={onSelectTab}
        />
      </div>

      <RightRail
        messages={messages}
        isTyping={isTyping}
        currentNarration={currentNarration ?? null}
        chatDraft={chatDraft}
        onChatDraftChange={onChatDraftChange}
        onSendMessage={onSendMessage}
        onOpenDeliverable={onOpenDeliverable}
        onGateApprove={onGateApprove ? (gateId) => onGateApprove(gateId, "") : undefined}
        onGateReject={onGateReject ? (gateId) => onGateReject(gateId, "") : undefined}
        onGateReview={pendingGateBanner?.onResume ? () => pendingGateBanner.onResume() : undefined}
      />
    </div>
  );
}

export default MissionControlV2View;
