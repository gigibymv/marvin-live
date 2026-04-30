// mc-v2/app.jsx — orchestrator + demo data

const DEMO = {
  mission: { name: "Project Omega", client: "Blackridge Capital · CDD", progress: 61, statusLabel: "running · Day 2" },
  agents: [
    { id: "thesis", name: "Thesis", role: "Framework & hypotheses", state: "done" },
    { id: "dora", name: "Dora", role: "Market sizing & comps", state: "running" },
    { id: "calculus", name: "Calculus", role: "Data room & QoE", state: "running" },
    { id: "lector", name: "Lector", role: "Expert interviews", state: "waiting" },
    { id: "adversus", name: "Adversus", role: "Stress testing", state: "idle" },
    { id: "merlin", name: "Merlin", role: "Argument coherence", state: "idle" },
    { id: "papyrus", name: "Papyrus", role: "Output assembly", state: "idle" },
  ],
  checkpoints: [
    { id: "c1", label: "Brief validated", status: "completed" },
    { id: "c2", label: "Hypotheses approved", status: "completed" },
    { id: "c3", label: "Market Gate", status: "now" },
    { id: "c4", label: "Financial Gate", status: "next" },
    { id: "c5", label: "IC Memo delivery", status: "later" },
  ],
  deliverables: [
    { id: "d1", label: "Thesis Memo", status: "ready" },
    { id: "d2", label: "Market Sizing", status: "ready" },
    { id: "d3", label: "QoE Analysis", status: "pending" },
    { id: "d4", label: "Competitive Map", status: "pending" },
    { id: "d5", label: "Red-team Memo", status: "pending" },
    { id: "d6", label: "IC Memo", status: "pending" },
  ],
  hypotheses: [
    { id: "h1", label: "H1", text: "Market growing structurally above management guidance.", computed: { status: "SUPPORTED", known: 7, reasoned: 3, low_confidence: 0, contradicting: 0 } },
    { id: "h2", label: "H2", text: "Reported ARR overstates true recurring revenue by 10–15%.", computed: { status: "TESTING", known: 3, reasoned: 2, low_confidence: 1, contradicting: 0 } },
    { id: "h3", label: "H3", text: "Competitive moat narrower than presented — two direct substitutes.", computed: { status: "WEAKENED", known: 2, reasoned: 1, low_confidence: 0, contradicting: 2 } },
    { id: "h4", label: "H4", text: "Mid-market NRR masked by enterprise cohort performance.", computed: { status: "NOT_STARTED", known: 0, reasoned: 0, low_confidence: 0, contradicting: 0 } },
  ],
  tabs: [
    { id: "brief", label: "Brief", status: "completed" },
    { id: "ws1", label: "Market analysis", status: "in_progress" },
    { id: "ws2", label: "Financial analysis", status: "in_progress" },
    { id: "ws3", label: "Synthesis", status: "pending" },
    { id: "ws4", label: "Stress testing", status: "pending" },
    { id: "final", label: "Final deliverables", status: "pending" },
  ],
  findingsMap: {
    brief: [
      { id: "b1", kind: "milestone", agent: "MARVIN", text: "Brief validated. 4 hypotheses declared — analytical framework confirmed.", ts: "09:14" },
      { id: "b2", kind: "finding", agent: "Thesis", text: "Central question: Is the market large enough and the moat durable enough to justify €280M at 7× revenue?", ts: "09:16", confidence: "sourced", source: "Brief document, p.1", impact: "load_bearing" },
    ],
    ws1: [
      { id: "w1a", kind: "milestone", agent: "Dora", text: "Market sizing complete. Bottom-up TAM: €4.2B global, €890M serviceable EU mid-market.", ts: "11:02" },
      { id: "w1b", kind: "finding", agent: "Dora", text: "34% CAGR confirmed via 3 independent sources. Management guidance conservative by ≥10pp — this is a significant understatement.", ts: "10:44", confidence: "sourced", source: "Gartner SaaS Market Report 2024, p.14; IDC European SaaS Outlook; bottom-up channel survey (n=340).", hypothesis_id: "h1", hypothesis_label: "H1", impact: "load_bearing" },
      { id: "w1c", kind: "finding", agent: "Dora", text: "Three undercounted ICP verticals (healthcare, logistics, public sector) represent €380M additional TAM not in management materials.", ts: "10:58", confidence: "sourced", source: "Cross-reference: Gartner vertical breakdown, IDC vertical TAM, management deck gap analysis.", hypothesis_id: "h1", hypothesis_label: "H1" },
      { id: "w1d", kind: "finding", agent: "Dora", text: "Competitor A launched mid-market tier in Q3 2024 — direct overlap with ~40% of target's ICP. Pricing 30% below target.", ts: "11:15", confidence: "inferred", hypothesis_id: "h3", hypothesis_label: "H3" },
      { id: "w1e", kind: "deliverable", agent: "Papyrus", text: "Market Sizing Report — 22 pages, all claims sourced, ready for download.", ts: "12:00" },
    ],
    ws2: [
      { id: "w2a", kind: "finding", agent: "Calculus", text: "Q3 2024 ARR overstated by €8.2M — expansion revenue misclassified as new ARR in ERP extraction.", ts: "13:07", confidence: "sourced", source: "Data room: contracts_Q3_2024.xlsx, cross-referenced with ERP export and signed contracts.", hypothesis_id: "h2", hypothesis_label: "H2", impact: "load_bearing" },
      { id: "w2b", kind: "finding", agent: "Calculus", text: "Net revenue retention of 108% masks critical SMB cohort at 84% — enterprise cohort at 127% inflates headline number.", ts: "13:22", confidence: "sourced", source: "Cohort analysis derived from data room: customer_cohorts_FY22-24.csv.", hypothesis_id: "h4", hypothesis_label: "H4", impact: "load_bearing" },
      { id: "w2c", kind: "finding", agent: "Calculus", text: "Gross margin 74% — in line with management claims and SaaS sector benchmarks. No anomaly detected.", ts: "13:35", confidence: "sourced", source: "P&L statements FY2022–2024, validated against sector comparables." },
    ],
    ws3: [], ws4: [], final: [],
  },
  activityMap: {
    brief: [],
    ws1: [
      { id: "a1", kind: "phase", text: "Market Analysis · Phase 2 of 4" },
      { id: "a2", kind: "tool_call", agent: "Dora", text: "web_search: 'SaaS B2B mid-market TAM 2024 Europe IDC'" },
      { id: "a3", kind: "tool_result", agent: "Dora", text: "Retrieved: Gartner SaaS Market Report 2024 (47 pages), IDC European SaaS Outlook Q1-2024" },
      { id: "a4", kind: "agent_message", agent: "Dora", text: "Cross-validating IDC estimates against Gartner — minor divergence in healthcare vertical (+€40M). Averaging both sources weighted by methodology quality." },
      { id: "a5", kind: "tool_call", agent: "Dora", text: "web_search: 'Competitor A enterprise launch pricing 2024'" },
      { id: "a6", kind: "tool_result", agent: "Dora", text: "Found: TechCrunch article confirming mid-market tier at $180/seat vs target's $260/seat" },
    ],
    ws2: [
      { id: "b1", kind: "tool_call", agent: "Calculus", text: "parse_file: data_room/contracts_Q3_2024.xlsx (312 contracts)" },
      { id: "b2", kind: "tool_result", agent: "Calculus", text: "Parsed 312 contracts — 8 anomalies flagged for manual review" },
      { id: "b3", kind: "agent_message", agent: "Calculus", text: "Running cohort analysis by segment. Splitting SMB (<€50K ACV) vs mid-market (€50-500K) vs enterprise (>€500K) to isolate NRR dynamics." },
      { id: "b4", kind: "tool_call", agent: "Calculus", text: "parse_file: data_room/customer_cohorts_FY22-24.csv" },
    ],
  },
  messages: [
    { id: "m1", from: "m", text: "Mission started. Brief validated, 4 hypotheses generated. Dora and Calculus are active across market sizing and data room review. First structured outputs expected within 2 hours." },
    { id: "m2", from: "u", text: "Focus on ARR quality — the sponsor flagged concerns about cohort retention. I want to see the SMB/enterprise split." },
    { id: "m3", from: "m", text: "Understood. I've re-weighted Calculus toward cohort-level analysis and ARR bridge reconciliation. Lector's interview guides will probe retention dynamics with the CFO and VP Sales. Early signal: NRR headline number is masking significant SMB deterioration." },
  ],
  waitState: { isWorking: true, headline: "Market Gate preparation", elapsedLabel: "2h 14m", message: "Dora finalising competitive map." },
};

function App() {
  const [selectedTab, setSelectedTab] = useState("ws1");

  return (
    <div style={{ display: "grid", gridTemplateColumns: "256px 1fr 310px", height: "100vh", overflow: "hidden" }}>
      <LeftRail data={DEMO} />
      <CenterPane data={DEMO} selectedTab={selectedTab} onSelectTab={setSelectedTab} />
      <RightRail messages={DEMO.messages} typing={true} narration="Dora is finalising the competitive landscape map — 22 competitors mapped, positioning matrix in progress..." />
    </div>
  );
}

Object.assign(window, { App });
