// Main app — mounts chrome + nav + active view + tweak panel.

const VIEW_META = {
  dashboard:    { title:'Dashboard',                     url:'dashboard',           live:true },
  mission:      { title:'Mission 0412 · Kepler',         url:'eng-0412',            live:true },
  disagreement: { title:'Disagreement · v4/v3',          url:'eng-0412/disagree',   live:true },
  agent:        { title:'Agent · osmund',                url:'agents/osmund',       live:true },
  corpus:       { title:'Corpus · 47 memos',             url:'corpus',              live:false },
  onboarding:   { title:'Install · Twin',                url:'install',             live:false },
};

const DEFAULT_KEYS = /*EDITMODE-BEGIN*/{
  "activeAgent": "osmund",
  "activeView": "dashboard"
}/*EDITMODE-END*/;

function App() {
  const [view, setView] = React.useState(DEFAULT_KEYS.activeView);
  const [activeAgent, setActiveAgent] = React.useState(DEFAULT_KEYS.activeAgent);
  const [tweakOn, setTweakOn] = React.useState(false);

  const tabs = [
    { title:`twin · ${VIEW_META[view].title}`, live:VIEW_META[view].live },
    { title:'meridian.board.pitch.pptx', live:false },
    { title:'fin.times · kepler', live:false },
  ];

  const content = {
    dashboard:    <DashboardView    activeAgent={activeAgent} setActiveAgent={setActiveAgent}/>,
    mission:      <MissionView      activeAgent={activeAgent} setActiveAgent={a=>{setActiveAgent(a); setView('agent');}}/>,
    disagreement: <DisagreementView/>,
    agent:        <AgentView        activeAgent={activeAgent}/>,
    corpus:       <CorpusView/>,
    onboarding:   <OnboardingView/>,
  }[view];

  // Edit-mode plumbing
  React.useEffect(()=>{
    const onMsg = (e)=>{
      const d = e.data||{};
      if (d.type==='__activate_edit_mode') setTweakOn(true);
      if (d.type==='__deactivate_edit_mode') setTweakOn(false);
    };
    window.addEventListener('message', onMsg);
    try { window.parent.postMessage({ type:'__edit_mode_available' }, '*'); } catch(e){}
    return ()=>window.removeEventListener('message', onMsg);
  },[]);

  const setKey = (patch)=>{
    if (patch.activeAgent) setActiveAgent(patch.activeAgent);
    if (patch.activeView) setView(patch.activeView);
    try { window.parent.postMessage({ type:'__edit_mode_set_keys', edits: patch }, '*'); } catch(e){}
  };

  return (
    <>
      <BrowserChrome url={VIEW_META[view].url} tabs={tabs} activeTab={0} onTab={()=>{}}>
        <LeftNav view={view} setView={setView}/>
        <main style={{ flex:1, minWidth:0, display:'flex', flexDirection:'column', background: view==='agent' ? 'var(--term-bg)' : '#F4F0EA' }}>
          {content}
        </main>
      </BrowserChrome>

      {tweakOn && (
        <div style={{ position:'fixed', right:24, bottom:24, width:320, padding:20, background:'#F4F0EA', color:'#1A1814', border:'1px solid #1A1814', fontFamily:'var(--sans)', fontSize:13, zIndex:9999 }}>
          <div style={{ fontFamily:'var(--display)', fontSize:20, fontWeight:400, letterSpacing:'-0.015em' }}>Tweaks</div>
          <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.12em', textTransform:'uppercase', color:'#78716A', marginBottom:14 }}>Platform knobs</div>

          <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.12em', textTransform:'uppercase', color:'#78716A', marginTop:10, marginBottom:6 }}>View</div>
          <select value={view} onChange={e=>{ setView(e.target.value); setKey({activeView:e.target.value}); }} style={{ width:'100%', padding:'8px 10px', fontFamily:'var(--sans)', fontSize:14, border:'1px solid #1A1814', background:'#F4F0EA' }}>
            {Object.entries(VIEW_META).map(([k,v])=><option key={k} value={k}>{v.title}</option>)}
          </select>

          <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.12em', textTransform:'uppercase', color:'#78716A', marginTop:14, marginBottom:6 }}>Active agent</div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:6 }}>
            {AGENTS.map(a=>(
              <button key={a.id} onClick={()=>{ setActiveAgent(a.id); setKey({activeAgent:a.id}); }} style={{
                padding:'8px 6px', border: activeAgent===a.id?'1.5px solid #1A1814':'1px solid #1A181433',
                background: activeAgent===a.id?'#1A1814':'transparent', color: activeAgent===a.id?'#F4F0EA':'#1A1814',
                fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.08em', cursor:'pointer', textTransform:'uppercase',
              }}>{a.stack} {a.name.toLowerCase()}</button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
