// mc-v2/left.jsx — Left rail after impeccable audit
// No pulse. Compact hypotheses. No checkpoints. Static indicators.

function MissionCard({ mission }) {
  const isRunning = mission.statusLabel?.includes("running");
  const pct = mission.progress || 0;

  return (
    <div style={{ padding: "20px 20px 18px", background: "var(--ink)", color: "var(--paper)" }}>
      <a href="/missions" style={{ display: "inline-flex", alignItems: "center", gap: 5, fontFamily: "var(--m)", fontSize: 9, letterSpacing: ".06em", color: "rgba(244,240,234,.4)", textDecoration: "none", marginBottom: 14 }}>
        <Icon id="back" size={10} color="rgba(244,240,234,.4)" /> Missions
      </a>
      <div style={{ fontFamily: "var(--d)", fontSize: 18, fontWeight: 700, letterSpacing: "-.025em", lineHeight: 1.15, marginBottom: 3 }}>{mission.name}</div>
      <Mono size={9} color="rgba(244,240,234,.45)" spacing=".06em">{mission.client}</Mono>
      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <StatusDot color={isRunning ? "#4ade80" : "rgba(244,240,234,.3)"} size={6} />
            <Mono size={9} weight={600} color={isRunning ? "#4ade80" : "rgba(244,240,234,.5)"}>{mission.statusLabel}</Mono>
          </div>
          <span style={{ fontFamily: "var(--d)", fontSize: 20, fontWeight: 700, color: "var(--paper)", letterSpacing: "-.02em" }}>{pct}%</span>
        </div>
        <ProgressBar pct={pct} color="#4ade80" height={3} bg="rgba(244,240,234,.12)" />
      </div>
    </div>
  );
}

function HypothesesRail({ hypotheses = [] }) {
  const statusStyle = s => ({
    SUPPORTED:   { c: "var(--green)", l: "Supported" },
    TESTING:     { c: "var(--amber)", l: "Testing" },
    WEAKENED:    { c: "var(--red)",   l: "Weakened" },
    NOT_STARTED: { c: "var(--muted)", l: "Pending" },
  }[s] || { c: "var(--muted)", l: s || "—" });

  return (
    <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--ruleh)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <Mono size={9} weight={700} spacing=".16em" color="var(--ink)">Hypotheses</Mono>
      </div>
      {hypotheses.map((h, i) => {
        const c = h.computed || {};
        const st = statusStyle(c.status);
        return (
          <div key={h.id || i} style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "6px 0", borderBottom: "1px solid var(--rule)" }}>
            <Mono size={10.5} weight={700} color="var(--ink)" style={{ minWidth: 22 }}>{h.label || `H${i+1}`}</Mono>
            <span style={{ fontSize: 12, lineHeight: 1.6, color: "var(--ink2)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.text}</span>
            <Mono size={9} weight={600} color={st.c} spacing=".08em" style={{ flexShrink: 0 }}>{st.l}</Mono>
          </div>
        );
      })}
    </div>
  );
}

function DeliverablesRail({ deliverables = [] }) {
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
          <div key={d.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--rule)", opacity: ok ? 1 : 0.35, cursor: ok ? "pointer" : "default" }}>
            <span style={{ fontSize: 12, fontWeight: ok ? 500 : 400, color: ok ? "var(--ink)" : "var(--ink3)" }}>{d.label}</span>
            {ok && <Mono size={9} weight={600} color="var(--green)">Open →</Mono>}
          </div>
        );
      })}
    </div>
  );
}

function AgentsRail({ agents = [] }) {
  return (
    <div style={{ padding: "14px 16px" }}>
      <Mono size={9} weight={700} spacing=".16em" color="var(--ink)" style={{ marginBottom: 10, display: "block" }}>Agents</Mono>
      {agents.map(a => (
        <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", borderBottom: "1px solid var(--rule)", opacity: a.state === "idle" ? 0.25 : 1 }}>
          <Icon id={a.id} size={12} color={a.state === "running" ? "var(--green)" : a.state === "waiting" ? "var(--amber)" : "var(--muted)"} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontSize: 12, fontWeight: a.state === "running" ? 600 : 400, lineHeight: 1.6 }}>{a.name}</span>
          </div>
          <StateTag state={a.state} />
        </div>
      ))}
    </div>
  );
}

function LeftRail({ data }) {
  return (
    <aside style={{ background: "var(--bone)", borderRight: "1px solid var(--ruleh)", display: "flex", flexDirection: "column", overflowY: "auto", flexShrink: 0 }}>
      <MissionCard mission={data.mission} />
      <HypothesesRail hypotheses={data.hypotheses} />
      <DeliverablesRail deliverables={data.deliverables} />
      <AgentsRail agents={data.agents} />
    </aside>
  );
}

Object.assign(window, { LeftRail });
