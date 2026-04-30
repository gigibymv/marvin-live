// Shared data for H&ai platform prototype.
// Scenario: Meridian Capital board evaluating acquisition of Kepler Systems ($820M, AI infra).

const AGENTS = [
  { id:'livia',      name:'Livia',      role:'Market Research',    stack:'Li', color:'#C4A56B', scope:'4,108 sources / week',       active:true,  status:'reading',   output:'Sector notes · n=312' },
  { id:'osmund',     name:'Osmund',     role:'Financial Modeler',  stack:'Os', color:'#8CB369', scope:'DCF + MC sensitivity · 3 scn', active:true,  status:'modeling',  output:'Scenario C v12 · Δ $41M' },
  { id:'praxis',     name:'Praxis',     role:'Competitive Intel',  stack:'Pr', color:'#7AA9C4', scope:'47 comps · 9 jurisdictions', active:true,  status:'benchmarking',output:'Comp table · 6 outliers flagged' },
  { id:'marginalia', name:'Marginalia', role:'Document Analysis',  stack:'Ma', color:'#B58863', scope:'11,204 pages ingested',       active:true,  status:'citing',    output:'Claim graph · 96% cited' },
  { id:'chronos',    name:'Chronos',    role:'Timeline & Risk',    stack:'Ch', color:'#D9A441', scope:'Re-baselines hourly',         active:true,  status:'watching',  output:'2 drift alerts · 17 this mo.' },
  { id:'atlas',      name:'Atlas',      role:'Market Sizing',      stack:'At', color:'#A38E6C', scope:'2.4k geos on file',           active:false, status:'idle',      output:'—' },
  { id:'scrivener',  name:'Scrivener',  role:'Draft & Narrative',  stack:'Sc', color:'#C9C1AF', scope:'Memo v8, median',             active:true,  status:'drafting',  output:'Memo v4 · "The case for"' },
  { id:'quorum',     name:'Quorum',     role:'Citation Audit',     stack:'Qu', color:'#9B8F75', scope:'Zero-tolerance reference',    active:true,  status:'auditing',  output:'14 claims unverified · frozen' },
  { id:'sentinel',   name:'Sentinel',   role:'Regulatory Watch',   stack:'Se', color:'#C96D6D', scope:'EU AI Act · current',         active:true,  status:'monitoring',output:'FTC Hart-Scott-Rodino · relevant' },
];

const HUMANS = [
  { id:'amara',  initials:'AO', name:'Amara Okafor',  role:'Partner · Lead',         tint:'#C6BFAE' },
  { id:'ines',   initials:'IM', name:'I. Marchetti',  role:'Principal',              tint:'#B5AD99' },
  { id:'henrik', initials:'HV', name:'H. Vass',       role:'Associate · Conductor',  tint:'#D4CDB8' },
  { id:'kovacs', initials:'KS', name:'Dr. K. Szabo',  role:'Domain · AI Infra',      tint:'#BFB8A3' },
];

const DRIFT_ALERTS = [
  { when:'09:14 CET',  agent:'sentinel',  severity:'high',   title:'FTC guidance on algorithmic pricing — draft rule updated overnight.',  note:'Affects Kepler revenue share model. Re-reading contract clauses 4.2 & 4.7.' },
  { when:'07:02 CET',  agent:'praxis',    severity:'medium', title:'Stratus AI raised $240M Series D at $3.1B pre.',                       note:'Closest comp. Implies +11% on the Kepler multiple. Osmund re-running.' },
  { when:'Yesterday',  agent:'chronos',   severity:'low',    title:'Kepler EMEA ARR figure in data room disagrees with press release.',     note:'Delta of $4.1M. Flagged for Q&A with Kepler CFO.' },
];

const CORPUS = [
  { year:2025, sector:'PE · Industrials', question:'Should the sponsor acquire Heliodyne?',     verdict:'Proceed with carve-out',            pages:'42p · 6 agents',  tags:['carve-out','environmental','DACH'] },
  { year:2025, sector:'Tech · M&A',       question:'Is the Orbit buyout priced fairly?',       verdict:'Walk — 18% overpay at midpoint',    pages:'28p · 5 agents',  tags:['saas','multiples','AI'] },
  { year:2026, sector:'FS · Strategy',    question:'Enter the Vietnamese retail market?',       verdict:'Enter Q4 via partnership',          pages:'61p · 7 agents',  tags:['market-entry','APAC','regulatory'] },
  { year:2026, sector:'Health · Reg.',    question:'Should Calyx restructure its EU trials?',   verdict:'Restructure — 2 regulators aligned',pages:'34p · 4 agents',  tags:['clinical','EMA','operations'] },
  { year:2025, sector:'Tech · AI',        question:'Can Nimbus ship before the moratorium?',    verdict:'No — pivot to federated model',     pages:'52p · 8 agents',  tags:['AI-Act','EU','product'] },
  { year:2024, sector:'PE · Consumer',    question:'Divest the DTC portfolio now or hold?',     verdict:'Hold 18 months, then divest',       pages:'47p · 5 agents',  tags:['consumer','DTC','timing'] },
];

const MISSION = {
  code:'ENG-0412',
  title:'Acquire Kepler Systems?',
  client:'Meridian Capital · Board',
  value:'$820M',
  day: 7, of: 10,
  question:'Should Meridian Capital acquire Kepler Systems at the proposed $820M, and if so, under what conditions?',
  sub:[
    { id:'q1', label:'Is the $820M price defensible against comps and a 5-yr DCF?', state:'contested' },
    { id:'q2', label:'Does Kepler’s AI infra moat survive an 18-month competitive horizon?', state:'open' },
    { id:'q3', label:'What regulatory exposure does the deal carry — FTC, EU AI Act, data residency?', state:'resolved' },
    { id:'q4', label:'Is Kepler’s revenue quality (ARR, churn, concentration) consistent with the data room?', state:'open' },
    { id:'q5', label:'What is the integration risk vs. Meridian’s two prior platform plays?', state:'open' },
  ],
  redlines:[
    'Meridian will not proceed if top-3 customer concentration exceeds 45%.',
    'No deal structure that triggers EU AI Act Article 6 high-risk classification.',
    'Must close before the FTC algorithmic-pricing rule takes effect (Jun 30).',
  ],
};

const TIMELINE = [
  { d: 1, label:'Brief framed',        done:true,  note:'One page. Signed by Okafor + Chen.' },
  { d: 2, label:'Data room ingested',  done:true,  note:'11,204 pages · Marginalia · 38h' },
  { d: 3, label:'Comps built',         done:true,  note:'Praxis · 47 comps · 6 outliers' },
  { d: 5, label:'DCF v1 → v9',         done:true,  note:'Osmund · 9 iterations · partner rejected 7' },
  { d: 7, label:'Disagreement drafted',done:true,  note:'Two memos · Scrivener · currently v4/v3' },
  { d: 8, label:'Red team memo',       done:false, note:'Partner challenges both sides · due tmrw' },
  { d: 9, label:'Client arbitration',  done:false, note:'Meridian board · 45 min · in person' },
  { d:10, label:'Signed verdict',      done:false, note:'Okafor signs · shipped as replayable console' },
];

Object.assign(window, { AGENTS, HUMANS, DRIFT_ALERTS, CORPUS, MISSION, TIMELINE });
