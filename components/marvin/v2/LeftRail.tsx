"use client";

import React from "react";
import type { Mission, WorkspaceTab } from "@/lib/missions/types";
import { Icon, StatusDot, Mono, Badge, ProgressBar, StateTag, PulsingM, mapAgentStatus, type AgentState } from "./Primitives";

// ─── Prop types ───────────────────────────────────────────────────────────────

export interface LeftRailAgent {
  id: string;
  name: string;
  role: string;
  status: string;
  milestonesTotal?: number;
  milestonesDelivered?: number;
}

export interface LeftRailHypothesis {
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
}

export interface LeftRailDeliverable {
  id: string;
  label: string;
  status: string;
  href?: string;
  onOpen?: () => void;
}

export interface LeftRailProps {
  mission: Mission;
  agents: LeftRailAgent[];
  hypotheses: LeftRailHypothesis[];
  deliverables: LeftRailDeliverable[];
  selectedHypothesisId?: string | null;
  onSelectHypothesis?: (id: string | null) => void;
}

// ─── Internal data shape ──────────────────────────────────────────────────────

interface MissionCardData {
  name: string;
  client: string;
  statusLabel: string;
  progress: number;
}

interface AgentData {
  id: string;
  name: string;
  state: AgentState;
}

// ─── MissionCard ─────────────────────────────────────────────────────────────

function MissionCard({ mission }: { mission: MissionCardData }): React.ReactElement {
  const isRunning = mission.statusLabel.toLowerCase().includes("running") ||
                    mission.statusLabel.toLowerCase().includes("active");
  // mission.progress is a 0..1 ratio. Display as integer percent — never
  // ship a raw float like "0.16666666...%" to users.
  const ratio = Math.max(0, Math.min(1, mission.progress || 0));
  const pct = Math.round(ratio * 100);

  return (
    <div style={{ padding: "20px 20px 18px", background: "var(--ink)", color: "var(--paper)" }}>
      <a
        href="/missions"
        style={{
          display: "inline-flex", alignItems: "center", gap: 5,
          fontFamily: "var(--m)", fontSize: 9, letterSpacing: ".06em",
          color: "rgba(244,240,234,.4)", textDecoration: "none", marginBottom: 14,
        }}
      >
        <Icon id="back" size={10} color="rgba(244,240,234,.4)" /> Missions
      </a>
      <div style={{ fontFamily: "var(--d)", fontSize: 18, fontWeight: 700, letterSpacing: "-.025em", lineHeight: 1.15, marginBottom: 3 }}>
        {mission.name}
      </div>
      <Mono size={9} color="rgba(244,240,234,.45)" spacing=".06em">{mission.client}</Mono>
      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <PulsingM color={isRunning ? "#4ade80" : "rgba(244,240,234,.3)"} size={10} active={isRunning} />
            <Mono size={9} weight={600} color={isRunning ? "#4ade80" : "rgba(244,240,234,.5)"}>{mission.statusLabel}</Mono>
          </div>
          <span style={{ fontFamily: "var(--d)", fontSize: 20, fontWeight: 700, color: "var(--paper)", letterSpacing: "-.02em" }}>{pct}%</span>
        </div>
        <ProgressBar pct={pct} color="#4ade80" height={3} bg="rgba(244,240,234,.12)" />
      </div>
    </div>
  );
}

// ─── HypothesesRail ───────────────────────────────────────────────────────────

type HypothesisStatus = "SUPPORTED" | "TESTING" | "WEAKENED" | "NOT_STARTED";

function statusStyle(s: HypothesisStatus | string): { c: string; l: string } {
  const map: Record<string, { c: string; l: string }> = {
    SUPPORTED:   { c: "var(--green)", l: "Supported" },
    TESTING:     { c: "var(--amber)", l: "Testing" },
    WEAKENED:    { c: "var(--red)",   l: "Weakened" },
    NOT_STARTED: { c: "var(--muted)", l: "Pending" },
  };
  return map[s] ?? { c: "var(--muted)", l: s || "—" };
}

function HypothesesRail({
  hypotheses,
  selectedHypothesisId,
  onSelectHypothesis,
}: {
  hypotheses: LeftRailHypothesis[];
  selectedHypothesisId?: string | null;
  onSelectHypothesis?: (id: string | null) => void;
}): React.ReactElement {
  return (
    <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--ruleh)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <Mono size={9} weight={700} spacing=".16em" color="var(--ink)">Hypotheses</Mono>
      </div>
      {hypotheses.map((h, i) => {
        const c = h.computed;
        const st = statusStyle(c?.status ?? h.status);
        const isSelected = h.id === selectedHypothesisId;
        return (
          <div
            key={h.id}
            onClick={() => onSelectHypothesis?.(h.id)}
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 8,
              padding: "6px 0",
              borderBottom: "1px solid var(--rule)",
              cursor: "pointer",
              background: isSelected ? "rgba(26,24,20,.04)" : "transparent",
              borderLeft: isSelected ? "2px solid var(--ink)" : "2px solid transparent",
              paddingLeft: isSelected ? 6 : 0,
              transition: "background .12s cubic-bezier(0.16,1,0.3,1)",
            }}
          >
            <Mono size={10.5} weight={700} color="var(--ink)" style={{ minWidth: 22 }}>{h.label ?? `H${i + 1}`}</Mono>
            <span style={{ fontSize: 12, lineHeight: 1.6, color: "var(--ink2)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {h.text}
            </span>
            <Mono size={9} weight={600} color={st.c} spacing=".08em" style={{ flexShrink: 0 }}>{st.l}</Mono>
          </div>
        );
      })}
    </div>
  );
}

// ─── DeliverablesRail ─────────────────────────────────────────────────────────

function DeliverablesRail({ deliverables }: { deliverables: LeftRailDeliverable[] }): React.ReactElement {
  const readyCount = deliverables.filter(d => d.status === "ready").length;
  return (
    <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--ruleh)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <Mono size={9} weight={700} spacing=".16em" color="var(--ink)">Deliverables</Mono>
        {readyCount > 0 && <Badge color="var(--green)" filled>{readyCount} ready</Badge>}
      </div>
      {deliverables.map(d => {
        const ok = d.status === "ready";
        return (
          <div
            key={d.id}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "6px 0", borderBottom: "1px solid var(--rule)",
              opacity: ok ? 1 : 0.35,
              cursor: ok ? "pointer" : "default",
            }}
            onClick={ok ? d.onOpen : undefined}
          >
            <span style={{ fontSize: 12, fontWeight: ok ? 500 : 400, color: ok ? "var(--ink)" : "var(--ink3)" }}>{d.label}</span>
            {ok && <Mono size={9} weight={600} color="var(--green)">Open →</Mono>}
          </div>
        );
      })}
    </div>
  );
}

// ─── AgentsRail ───────────────────────────────────────────────────────────────

function AgentsRail({ agents }: { agents: AgentData[] }): React.ReactElement {
  return (
    <div style={{ padding: "14px 16px" }}>
      <Mono size={9} weight={700} spacing=".16em" color="var(--ink)" style={{ marginBottom: 10, display: "block" }}>Agents</Mono>
      {agents.map(a => (
        <div
          key={a.id}
          style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "5px 0", borderBottom: "1px solid var(--rule)",
            opacity: a.state === "idle" ? 0.25 : 1,
          }}
        >
          <Icon
            id={a.id}
            size={12}
            color={a.state === "running" ? "var(--green)" : a.state === "waiting" ? "var(--amber)" : "var(--muted)"}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{
              fontFamily: "var(--m)",
              fontSize: 11,
              fontWeight: a.state === "running" ? 700 : 500,
              lineHeight: 1.6,
              textTransform: "uppercase",
              letterSpacing: ".08em",
            }}>
              {a.name}
            </span>
          </div>
          <StateTag state={a.state} />
        </div>
      ))}
    </div>
  );
}

// ─── LeftRail ─────────────────────────────────────────────────────────────────

export function LeftRail({ mission, agents, hypotheses, deliverables, selectedHypothesisId, onSelectHypothesis }: LeftRailProps): React.ReactElement {
  const missionData: MissionCardData = {
    name: mission.name,
    client: mission.client,
    statusLabel: mission.status === "active" ? "Running" : "Completed",
    progress: mission.progress,
  };

  const agentData: AgentData[] = agents.map(a => ({
    id: a.id,
    name: a.name,
    state: mapAgentStatus(a.status),
  }));

  return (
    <aside style={{
      background: "var(--bone)",
      borderRight: "1px solid var(--ruleh)",
      display: "flex",
      flexDirection: "column",
      overflowY: "auto",
      flexShrink: 0,
    }}>
      <MissionCard mission={missionData} />
      <HypothesesRail hypotheses={hypotheses} selectedHypothesisId={selectedHypothesisId} onSelectHypothesis={onSelectHypothesis} />
      <DeliverablesRail deliverables={deliverables} />
      <AgentsRail agents={agentData} />
    </aside>
  );
}
