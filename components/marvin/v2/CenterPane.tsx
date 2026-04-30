"use client";

import React from "react";
import type { WorkspaceTab } from "@/lib/missions/types";
import { humanizeText } from "@/lib/missions/humanize";
import { Mono, Badge, StatusDot, PulsingM } from "./Primitives";

// ─── Prop types ───────────────────────────────────────────────────────────────

export interface CenterFinding {
  id: string;
  kind?: "finding" | "milestone" | "deliverable";
  agent?: string;
  text?: string;
  ts?: string;
  confidence?: string | null;
  impact?: "load_bearing" | "supporting" | "color" | null;
  hypothesis_label?: string | null;
  source?: string | null;
  onOpen?: () => void;
}

export interface CenterActivityItem {
  id: string;
  kind?: string;
  agent?: string;
  text?: string;
  ts?: string;
}

export interface CenterTab {
  id: WorkspaceTab;
  label: string;
  status?: "pending" | "now" | "in_progress" | "completed";
}

export interface CenterCheckpoint {
  id: string;
  label: string;
  status: string;
}

export interface CenterWaitState {
  isWorking: boolean;
  showInOutputs: boolean;
  isStalled: boolean;
  elapsedLabel: string;
  message: string;
  headline: string;
}

export interface CenterPaneProps {
  findingsMap: Record<WorkspaceTab, CenterFinding[]>;
  activityMap: Record<WorkspaceTab, CenterActivityItem[]>;
  tabs: CenterTab[];
  checkpoints: CenterCheckpoint[];
  waitState?: CenterWaitState | null;
  missionClient: string;
  missionStatusLabel: string;
  selectedTab: WorkspaceTab;
  onSelectTab: (tab: WorkspaceTab) => void;
}

// ─── FindingRow ───────────────────────────────────────────────────────────────

function formatRowTime(raw: string | undefined): string {
  if (!raw) return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const date = new Date(trimmed);
  if (isNaN(date.getTime())) return trimmed.slice(0, 5);
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function FindingRow({ f }: { f: CenterFinding }): React.ReactElement {
  const [open, setOpen] = React.useState(false);
  const cleanText = humanizeText(f.text ?? "");
  const cleanSource = humanizeText(f.source ?? "");
  const hasSource = !!cleanSource;
  const isKey = f.impact === "load_bearing";

  return (
    <div
      onClick={() => setOpen(o => !o)}
      style={{
        padding: "14px 24px",
        cursor: "pointer",
        background: "white",
        borderBottom: "1px solid var(--rule)",
        transition: "background .15s cubic-bezier(0.16,1,0.3,1)",
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = "rgba(26,24,20,.018)"; }}
      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = "white"; }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
        <Mono size={9} weight={700} color="var(--ink3)" spacing=".06em" style={{ minWidth: 52, flexShrink: 0, paddingTop: 1 }}>
          {f.agent}
        </Mono>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 13, lineHeight: 1.6, color: "var(--ink)", fontWeight: isKey ? 600 : 400 }}>{cleanText}</span>
        </div>
        <Mono size={9} color="var(--muted)" style={{ flexShrink: 0 }}>{formatRowTime(f.ts)}</Mono>
      </div>

      {open && (
        <div style={{ marginTop: 10, marginLeft: 66, display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            {f.confidence && (
              <Badge color={f.confidence === "sourced" ? "var(--green)" : f.confidence === "inferred" ? "var(--amber)" : "var(--muted)"}>
                {f.confidence}
              </Badge>
            )}
            {isKey && <Badge color="var(--ink)">Key finding</Badge>}
            {f.hypothesis_label && <Badge color="var(--ink3)">{f.hypothesis_label}</Badge>}
          </div>
          {hasSource && (
            <div style={{ padding: "8px 12px", background: "var(--bone)", borderRadius: 4 }}>
              <Mono size={9} weight={600} color="var(--ink3)" style={{ marginBottom: 3, display: "block" }}>Source</Mono>
              <div style={{ fontFamily: "var(--m)", fontSize: 10.5, color: "var(--ink2)", lineHeight: 1.6 }}>{cleanSource}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── MilestoneRow ─────────────────────────────────────────────────────────────

function MilestoneRow({ f }: { f: CenterFinding }): React.ReactElement {
  return (
    <div style={{
      padding: "14px 24px",
      background: "var(--ink)",
      color: "var(--paper)",
      borderBottom: "1px solid rgba(244,240,234,.06)",
      display: "flex",
      alignItems: "baseline",
      gap: 14,
    }}>
      <Mono size={9} weight={700} color="rgba(244,240,234,.45)" spacing=".06em" style={{ minWidth: 52 }}>
        {f.agent ?? "MARVIN"}
      </Mono>
      <span style={{ flex: 1, fontSize: 13, fontWeight: 600, lineHeight: 1.6 }}>{humanizeText(f.text ?? "")}</span>
      <Mono size={9} color="rgba(244,240,234,.45)" style={{ fontStyle: "italic" }}>Report generating…</Mono>
      <Mono size={9} color="rgba(244,240,234,.3)">{formatRowTime(f.ts)}</Mono>
    </div>
  );
}

// ─── DeliverableRow ───────────────────────────────────────────────────────────
// Dark theme — same visual weight as a milestone completion event because a
// deliverable IS the artifact that proves the milestone is done. The two
// used to render side by side; now milestones are deduped against
// deliverables in the wrapper so only the deliverable row survives.

function DeliverableRow({ f }: { f: CenterFinding }): React.ReactElement {
  const cleanText = humanizeText(f.text ?? "");
  const cleanBody = humanizeText(f.source ?? "");
  const body = cleanBody.trim() ? cleanBody.trim() : null;
  return (
    <div style={{
      padding: "14px 24px",
      background: "var(--ink)",
      color: "var(--paper)",
      borderBottom: "1px solid rgba(244,240,234,.06)",
      display: "flex",
      flexDirection: "column",
      gap: 10,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <Mono size={9} weight={700} color="rgba(244,240,234,.45)" spacing=".06em" style={{ minWidth: 52 }}>
          {f.agent ?? "MARVIN"}
        </Mono>
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "var(--paper)", lineHeight: 1.6 }}>
          {cleanText}
        </span>
        {f.onOpen && (
          <button
            style={{
              fontFamily: "var(--m)", fontSize: 9, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase",
              color: "var(--paper)", background: "transparent", border: "1px solid rgba(244,240,234,.30)",
              padding: "5px 14px", cursor: "pointer", borderRadius: 4,
              transition: "background .15s cubic-bezier(0.16,1,0.3,1)",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(244,240,234,.08)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
            onClick={f.onOpen}
          >
            Open →
          </button>
        )}
      </div>
      {body && (
        <div style={{
          marginLeft: 66,
          marginRight: 24,
          fontSize: 13,
          lineHeight: 1.6,
          color: "rgba(244,240,234,.78)",
          whiteSpace: "pre-wrap",
        }}>
          {body}
        </div>
      )}
    </div>
  );
}

// ─── OutputRow ────────────────────────────────────────────────────────────────

function OutputRow({ item }: { item: CenterFinding }): React.ReactElement {
  if (item.kind === "milestone") return <MilestoneRow f={item} />;
  if (item.kind === "deliverable") return <DeliverableRow f={item} />;
  return <FindingRow f={item} />;
}

// ─── ActivityItem ─────────────────────────────────────────────────────────────
// Tracks ids we've already animated so re-renders don't re-trigger the
// typewriter effect. Module-scoped because the activity feed re-mounts
// frequently as the parent state churns.
const ANIMATED_ACTIVITY_IDS = new Set<string>();

function useTypewriter(id: string, fullText: string, speedMs = 6): string {
  const alreadyAnimated = ANIMATED_ACTIVITY_IDS.has(id);
  // Skip animation for short rows — the staggered reveal only adds value on
  // multi-sentence prose. Short rows ("Dora finished", "Deliverable ready · X")
  // would be empty for an instant then snap, which reads as a glitch.
  const skipAnimation = !fullText || fullText.length <= 60;
  const initial = alreadyAnimated || skipAnimation ? fullText : "";
  const [shown, setShown] = React.useState<string>(initial);

  React.useEffect(() => {
    if (skipAnimation || alreadyAnimated) {
      ANIMATED_ACTIVITY_IDS.add(id);
      setShown(fullText);
      return;
    }
    let i = 0;
    let cancelled = false;
    const tick = (): void => {
      if (cancelled) return;
      i = Math.min(fullText.length, i + Math.max(1, Math.floor(fullText.length / 80)));
      setShown(fullText.slice(0, i));
      if (i >= fullText.length) {
        ANIMATED_ACTIVITY_IDS.add(id);
        return;
      }
      window.setTimeout(tick, speedMs);
    };
    tick();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, fullText]);

  return shown;
}

function ActivityItem({ e, isLast }: { e: CenterActivityItem; isLast: boolean }): React.ReactElement {
  const itemKey = `${e.kind ?? "a"}:${e.id ?? ""}`;
  const fullText = humanizeText(e.text ?? "");
  const animatedText = useTypewriter(itemKey, fullText);

  if (e.kind === "phase") {
    return (
      <div style={{ padding: "6px 0", margin: "2px 0", borderTop: "1px dashed var(--rule)", borderBottom: "1px dashed var(--rule)" }}>
        <Mono size={9} weight={700} spacing=".14em" color="var(--ink3)">Phase</Mono>
        <Mono size={9} weight={500} color="var(--ink2)" upper={false} spacing=".02em" style={{ marginLeft: 10 }}>{animatedText}</Mono>
      </div>
    );
  }

  const isTool = e.kind === "tool_call" || e.kind === "tool_result";
  return (
    <div style={{
      display: "flex", alignItems: "baseline", gap: 10,
      paddingBottom: isLast ? 0 : 5,
      marginBottom: isLast ? 0 : 5,
      borderBottom: isLast ? "none" : "1px solid rgba(26,24,20,.04)",
      opacity: isTool ? 0.55 : 0.85,
    }}>
      <Mono size={9} weight={700} color="var(--ink3)" spacing=".06em" style={{ minWidth: 48, flexShrink: 0 }}>
        {e.agent ?? ""}
      </Mono>
      <span style={{
        fontFamily: "var(--m)",
        fontSize: 9,
        letterSpacing: ".02em",
        lineHeight: 1.6,
        // Typewriter cursor while still animating
        ...(animatedText.length < fullText.length
          ? { borderRight: "1px solid var(--ink3)", paddingRight: 1 }
          : {}),
        color: "var(--ink3)",
        fontWeight: 400,
        flex: 1,
        minWidth: 0,
      }}>
        {animatedText}
      </span>
    </div>
  );
}

// ─── Spinner ──────────────────────────────────────────────────────────────────

function Spinner(): React.ReactElement {
  return (
    <span
      aria-label="working"
      style={{
        display: "inline-block",
        width: 8, height: 8,
        marginRight: 6,
        verticalAlign: "middle",
        border: "1.5px solid var(--ruleh)",
        borderTopColor: "var(--ink)",
        borderRadius: "50%",
        animation: "marvin-spin 0.9s linear infinite",
      }}
    />
  );
}

// ─── CenterPane ───────────────────────────────────────────────────────────────

export function CenterPane({
  findingsMap,
  activityMap,
  tabs,
  checkpoints,
  waitState,
  missionClient,
  missionStatusLabel,
  selectedTab,
  onSelectTab,
}: CenterPaneProps): React.ReactElement {
  const findings = findingsMap[selectedTab] ?? [];
  const activity = activityMap[selectedTab] ?? [];
  const isWorking = waitState?.isWorking ?? false;


  return (
    <main style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--paper)" }}>

      {/* Header */}
      <div style={{ padding: "14px 24px 0", borderBottom: "1px solid var(--ruleh)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <Mono size={10.5} color="var(--muted)" upper={false}>{missionClient}</Mono>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <PulsingM color="var(--green)" size={10} />
            <Mono size={9} weight={600} color="var(--green)">{missionStatusLabel}</Mono>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ position: "relative" }}>
          <div style={{ display: "flex", gap: 0, overflowX: "auto", scrollbarWidth: "none" } as React.CSSProperties}>
            {tabs.map(t => {
              const isDone = t.status === "completed";
              const isLive = t.status === "in_progress" || t.status === "now";
              const isOn = selectedTab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => onSelectTab(t.id)}
                  style={{
                    fontFamily: "var(--m)", fontSize: 9, letterSpacing: ".05em", textTransform: "uppercase",
                    padding: "9px 16px", background: "transparent", border: "none",
                    borderBottom: isOn ? "2px solid var(--ink)" : "2px solid transparent",
                    color: isOn ? "var(--ink)" : isDone ? "var(--ink3)" : isLive ? "var(--ink2)" : "var(--muted)",
                    fontWeight: isOn ? 700 : 500,
                    cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0,
                    transition: "color .15s cubic-bezier(0.16,1,0.3,1), border-color .15s cubic-bezier(0.16,1,0.3,1)",
                  }}
                >
                  {isDone ? <span style={{ color: "var(--green)" }}>✓ </span> : isLive ? <Spinner /> : null}{t.label}
                </button>
              );
            })}
          </div>
          <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: 36, background: "linear-gradient(to right, transparent, var(--paper))", pointerEvents: "none" }} />
        </div>
      </div>

      {/* Next-gate strip removed: the tab strip's active-step indicator
          already conveys the same information without redundancy. */}

      {/* Split pane: outputs (top) vs activity (bottom) — static 50/50 */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>

        {/* Outputs pane — bg matches FindingRow white so the empty space below
            the last row doesn't read as a separate "beige gap" between
            outputs and activity. */}
        <section
          aria-label="Outputs"
          style={{ flex: "1 1 50%", overflowY: "auto", minHeight: 0, background: "white" }}
        >
          <div style={{ padding: "10px 24px 6px", display: "flex", alignItems: "baseline", gap: 8 }}>
            <Mono size={9} weight={700} spacing=".14em" color="var(--ink)">Outputs</Mono>
            <Mono size={9} color="var(--muted)">{findings.length}</Mono>
          </div>
          {findings.length === 0 ? (
            <div style={{
              padding: "20px 24px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 8,
              maxWidth: 460,
              margin: "0 auto",
              textAlign: "center",
            }}>
              {isWorking ? (
                <>
                  <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 12, color: "var(--ink3)", lineHeight: 1.6 }}>
                      Agents are working
                    </span>
                    <span style={{ display: "inline-flex", gap: 3 }}>
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          style={{
                            width: 4,
                            height: 4,
                            borderRadius: 1,
                            background: "var(--ink3)",
                            animation: `blink 1.1s ${i * 0.25}s ease-in-out infinite`,
                          }}
                        />
                      ))}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.6 }}>
                    New findings will appear here as they are validated.
                  </div>
                </>
              ) : (
                <Mono size={9} color="var(--muted)">No outputs for this section yet.</Mono>
              )}
            </div>
          ) : (
            findings.map(item => <OutputRow key={`${item.kind ?? "f"}:${item.id}`} item={item} />)
          )}
        </section>

        <div style={{ height: 1, flexShrink: 0, background: "var(--ruleh)" }} />

        {/* Activity pane — visually distinct: bone bg, mono compact rows */}
        <section
          aria-label="Activity"
          style={{
            flex: "1 1 50%",
            overflowY: "auto",
            minHeight: 0,
            background: "var(--bone)",
          }}
        >
          <div style={{ padding: "10px 24px 6px", display: "flex", alignItems: "baseline", gap: 8, position: "sticky", top: 0, background: "var(--bone)", zIndex: 1 }}>
            <Mono size={9} weight={700} spacing=".14em" color="var(--ink3)">Activity</Mono>
            <Mono size={9} color="var(--muted)">{activity.length}</Mono>
          </div>
          <div style={{ padding: "4px 24px 14px" }}>
            {activity.length === 0 ? (
              <Mono size={9} color="var(--muted)">No activity yet.</Mono>
            ) : (
              activity.map((e, i) => (
                <ActivityItem key={`${e.kind ?? "a"}:${e.id ?? i}`} e={e} isLast={i === activity.length - 1} />
              ))
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
