// mc-v2/center.jsx — After impeccable audit
// Merged feed (no split pane). No glyphs. No border stripes.
// "Key finding" not "LOAD-BEARING". Metadata on expand only.
// line-height 1.6 everywhere. Radius: 0, 4, 8 only.

/* ─── Finding row — clean, metadata on expand ─────────────────────────── */
function FindingRow({ f }) {
  const [open, setOpen] = useState(false);
  const hasSource = !!(f.source);
  const isKey = f.impact === "load_bearing";

  return (
    <div
      onClick={() => setOpen(o => !o)}
      style={{
        padding: "14px 24px", cursor: "pointer",
        background: "white", borderBottom: "1px solid var(--rule)",
        transition: "background .15s cubic-bezier(0.16,1,0.3,1)",
      }}
      onMouseEnter={e => e.currentTarget.style.background = "rgba(26,24,20,.018)"}
      onMouseLeave={e => e.currentTarget.style.background = "white"}
    >
      {/* Main row: agent — text — time */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
        <Mono size={9} weight={700} color="var(--ink3)" spacing=".06em" style={{ minWidth: 52, flexShrink: 0, paddingTop: 1 }}>{f.agent}</Mono>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 13, lineHeight: 1.6, color: "var(--ink)", fontWeight: isKey ? 600 : 400 }}>{f.text}</span>
        </div>
        <Mono size={9} color="var(--muted)" style={{ flexShrink: 0 }}>{f.ts}</Mono>
      </div>

      {/* Expanded metadata — only shown on click */}
      {open && (
        <div style={{ marginTop: 10, marginLeft: 66, display: "flex", flexDirection: "column", gap: 6 }}>
          {/* Tags row */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            {f.confidence && <Badge color={f.confidence === "sourced" ? "var(--green)" : f.confidence === "inferred" ? "var(--amber)" : "var(--muted)"}>{f.confidence}</Badge>}
            {isKey && <Badge color="var(--ink)">Key finding</Badge>}
            {f.hypothesis_label && <Badge color="var(--ink3)">{f.hypothesis_label}</Badge>}
          </div>
          {/* Source */}
          {hasSource && (
            <div style={{ padding: "8px 12px", background: "var(--bone)", borderRadius: 4 }}>
              <Mono size={9} weight={600} color="var(--ink3)" style={{ marginBottom: 3, display: "block" }}>Source</Mono>
              <div style={{ fontFamily: "var(--m)", fontSize: 10.5, color: "var(--ink2)", lineHeight: 1.6 }}>{f.source}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── Milestone — dark row, no border tricks ──────────────────────────── */
function MilestoneRow({ f }) {
  return (
    <div style={{ padding: "14px 24px", background: "var(--ink)", color: "var(--paper)", borderBottom: "1px solid rgba(244,240,234,.06)", display: "flex", alignItems: "baseline", gap: 14 }}>
      <Mono size={9} weight={700} color="rgba(244,240,234,.45)" spacing=".06em" style={{ minWidth: 52 }}>{f.agent || "MARVIN"}</Mono>
      <span style={{ flex: 1, fontSize: 13, fontWeight: 600, lineHeight: 1.6 }}>{f.text}</span>
      <Mono size={9} color="rgba(244,240,234,.3)">{f.ts}</Mono>
    </div>
  );
}

/* ─── Deliverable — subtle distinction ────────────────────────────────── */
function DeliverableRow({ f }) {
  return (
    <div style={{ padding: "14px 24px", background: "rgba(45,110,78,.04)", borderBottom: "1px solid var(--rule)", display: "flex", alignItems: "baseline", gap: 14 }}>
      <Mono size={9} weight={700} color="var(--green)" spacing=".06em" style={{ minWidth: 52 }}>{f.agent || "Papyrus"}</Mono>
      <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "var(--ink)", lineHeight: 1.6 }}>{f.text}</span>
      <button style={{ fontFamily: "var(--m)", fontSize: 9, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--green)", background: "transparent", border: "1px solid rgba(45,110,78,.25)", padding: "5px 14px", cursor: "pointer", borderRadius: 4, transition: "background .15s cubic-bezier(0.16,1,0.3,1)" }}
        onMouseEnter={e => e.currentTarget.style.background = "rgba(45,110,78,.08)"}
        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
      >Open →</button>
    </div>
  );
}

function OutputRow({ item }) {
  if (item.kind === "milestone") return <MilestoneRow f={item} />;
  if (item.kind === "deliverable") return <DeliverableRow f={item} />;
  return <FindingRow f={item} />;
}

/* ─── Activity item — no glyphs, just agent name + mono for tools ─────── */
function ActivityItem({ e, isLast }) {
  if (e.kind === "phase") {
    return (
      <div style={{ padding: "8px 0", margin: "4px 0", borderTop: "1px solid var(--rule)", borderBottom: "1px solid var(--rule)" }}>
        <Mono size={9} weight={700} spacing=".14em" color="var(--ink3)">Phase</Mono>
        <span style={{ fontSize: 12, fontWeight: 500, color: "var(--ink)", marginLeft: 10 }}>{e.text}</span>
      </div>
    );
  }

  const isTool = e.kind === "tool_call" || e.kind === "tool_result";
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 10, paddingBottom: isLast ? 0 : 7, marginBottom: isLast ? 0 : 7, borderBottom: isLast ? "none" : "1px solid rgba(26,24,20,.05)", opacity: isTool ? 0.45 : 1 }}>
      <Mono size={9} weight={700} color="var(--ink3)" spacing=".06em" style={{ minWidth: 52, flexShrink: 0 }}>{e.agent || ""}</Mono>
      <span style={{ fontSize: isTool ? 12 : 13, lineHeight: 1.6, color: "var(--ink2)", fontWeight: isTool ? 400 : 500, fontFamily: isTool ? "var(--m)" : "var(--g)" }}>{e.text}</span>
    </div>
  );
}

/* ─── Center pane — single merged feed, collapsible activity at bottom ── */
function CenterPane({ data, selectedTab, onSelectTab }) {
  const [activityOpen, setActivityOpen] = useState(true);

  const findings = data.findingsMap[selectedTab] || [];
  const activity = data.activityMap[selectedTab] || [];
  const nextCP = data.checkpoints.find(c => c.status === "now" || c.status === "next");
  const isWorking = data.waitState?.isWorking;

  return (
    <main style={{ display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--paper)" }}>

      {/* Header */}
      <div style={{ padding: "14px 24px 0", borderBottom: "1px solid var(--ruleh)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <Mono size={10.5} color="var(--muted)" upper={false}>{data.mission.client}</Mono>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <StatusDot color="var(--green)" size={5} />
            <Mono size={9} weight={600} color="var(--green)">{data.mission.statusLabel}</Mono>
          </div>
        </div>

        {/* Tabs — simple underline */}
        <div style={{ position: "relative" }}>
          <div style={{ display: "flex", gap: 0, overflowX: "auto", scrollbarWidth: "none" }}>
            {data.tabs.map(t => {
              const isDone = t.status === "completed";
              const isLive = t.status === "in_progress" || t.status === "now";
              const isOn = selectedTab === t.id;
              return (
                <button key={t.id} onClick={() => onSelectTab(t.id)} style={{
                  fontFamily: "var(--m)", fontSize: 9, letterSpacing: ".05em", textTransform: "uppercase",
                  padding: "9px 16px", background: "transparent", border: "none",
                  borderBottom: isOn ? "2px solid var(--ink)" : "2px solid transparent",
                  color: isOn ? "var(--ink)" : isDone ? "var(--ink3)" : isLive ? "var(--ink2)" : "var(--muted)",
                  fontWeight: isOn ? 700 : 500,
                  cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0,
                  transition: "color .15s cubic-bezier(0.16,1,0.3,1), border-color .15s cubic-bezier(0.16,1,0.3,1)",
                }}>
                  {isDone ? "✓ " : isLive ? "● " : ""}{t.label}
                </button>
              );
            })}
          </div>
          <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: 36, background: "linear-gradient(to right, transparent, var(--paper))", pointerEvents: "none" }} />
        </div>
      </div>

      {/* Single scrollable feed */}
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>

        {/* Next gate strip */}
        <div style={{ padding: "8px 24px", borderBottom: "1px solid var(--rule)", display: "flex", alignItems: "center", gap: 8 }}>
          <Mono size={9} color="var(--muted)" spacing=".1em">Next gate</Mono>
          <Mono size={10.5} weight={600} color="var(--ink)" spacing=".04em">{nextCP?.label || "—"}</Mono>
        </div>

        {/* Findings */}
        {findings.length === 0 ? (
          <div style={{ padding: "48px 24px", textAlign: "center" }}>
            {isWorking
              ? <><StatusDot color="var(--amber)" size={7} /><div style={{ fontSize: 13, color: "var(--ink3)", marginTop: 12, lineHeight: 1.6 }}>Agents are working — outputs will appear here as they are validated.</div></>
              : <Mono size={9} color="var(--muted)">No outputs for this section yet.</Mono>}
          </div>
        ) : findings.map(item => <OutputRow key={`${item.kind}:${item.id}`} item={item} />)}

        {/* Activity log — collapsible, same scroll context */}
        {activity.length > 0 && (
          <div style={{ borderTop: "1px solid var(--ruleh)", marginTop: findings.length ? 0 : 0 }}>
            <button
              onClick={() => setActivityOpen(v => !v)}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 24px", width: "100%", background: "var(--bone)", border: "none", borderBottom: activityOpen ? "1px solid var(--rule)" : "none", cursor: "pointer", textAlign: "left" }}
            >
              <Mono size={9} weight={700} spacing=".14em" color="var(--ink3)">Activity log</Mono>
              <Mono size={9} color="var(--muted)">{activity.length}</Mono>
              <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)" }}>{activityOpen ? "▾" : "▸"}</span>
            </button>
            {activityOpen && (
              <div style={{ padding: "12px 24px 20px", background: "var(--bone)" }}>
                {activity.map((e, i) => <ActivityItem key={`${e.kind}:${e.id || i}`} e={e} isLast={i === activity.length - 1} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

Object.assign(window, { CenterPane });
