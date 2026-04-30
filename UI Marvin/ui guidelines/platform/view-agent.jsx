// View 4 — Agent room (terminal). Dark, monospaced. Shows Osmund's live trace.

function AgentView({ activeAgent }) {
  const [lines, setLines] = React.useState([
    { t:'08:42:11', tag:'boot',   text:'osmund.agent@twin-meridian · session 0412.osmund.14', c:'term-muted' },
    { t:'08:42:12', tag:'scope',  text:'load brief::eng-0412 · "Acquire Kepler Systems?" · budget: 2.4M tokens', c:'term-muted' },
    { t:'08:42:14', tag:'ingest', text:'marginalia :: 11,204 pages normalized · schema v6 · 96% claims indexed', c:'term-blue' },
    { t:'08:47:03', tag:'build',  text:'dcf.scenario_A → central · WACC 11.5% · g 3.0% · → $790M', c:'term-green' },
    { t:'08:51:22', tag:'build',  text:'dcf.scenario_B → bull · WACC 10.2% · g 3.8% · → $861M', c:'term-green' },
    { t:'08:56:40', tag:'build',  text:'dcf.scenario_C → bear · WACC 12.9% · g 1.8% · → $691M', c:'term-green' },
    { t:'09:03:18', tag:'check',  text:'quorum :: 142/156 claims cross-verified · 14 unverified → frozen', c:'term-amber' },
    { t:'09:07:55', tag:'signal', text:'praxis :: Stratus AI Series D priced @ $3.1B pre · re-rate sector +11%', c:'term-amber' },
    { t:'09:08:02', tag:'replan', text:'re-running scenarios with updated multiple · ETA 3m12s', c:'term-muted' },
    { t:'09:11:14', tag:'build',  text:'dcf.scenario_A′ → central (re-rated) · → $728M · Δ -$62M', c:'term-green' },
    { t:'09:11:45', tag:'flag',   text:'partner-review required :: central falls below $760M conditional floor', c:'term-red' },
    { t:'09:12:01', tag:'notify', text:'→ amara.okafor · "price defense weakens; recommend re-argue the case-for"', c:'term-blue' },
    { t:'09:14:22', tag:'watch',  text:'sentinel :: FTC algorithmic-pricing rule draft updated overnight · re-reading §4.2, §4.7', c:'term-amber' },
    { t:'09:18:40', tag:'idle',   text:'holding for partner · 4m28s · no new signal', c:'term-muted' },
  ]);

  React.useEffect(()=>{
    const id = setInterval(()=>{
      setLines(prev=>{
        const now = new Date();
        const hh = String(now.getHours()).padStart(2,'0'), mm = String(now.getMinutes()).padStart(2,'0'), ss = String(now.getSeconds()).padStart(2,'0');
        const picks = [
          { tag:'watch',  text:'marginalia :: re-scanning clause 4.7 · found 2 new references · citing', c:'term-blue' },
          { tag:'build',  text:'monte-carlo :: 10,000 draws · p05=$672M p50=$728M p95=$812M', c:'term-green' },
          { tag:'signal', text:'praxis :: Anthropic infra partnership rumor · low-confidence · not yet priced', c:'term-amber' },
          { tag:'check',  text:'quorum :: 3 new claims reach threshold · releasing from quarantine', c:'term-amber' },
        ];
        const next = picks[Math.floor(Math.random()*picks.length)];
        return [...prev.slice(-22), { t:`${hh}:${mm}:${ss}`, ...next }];
      });
    }, 3200);
    return ()=>clearInterval(id);
  },[]);

  const agent = AGENTS.find(a=>a.id===activeAgent) || AGENTS.find(a=>a.id==='osmund');

  return (
    <div className="term" style={{ flex:1, display:'grid', gridTemplateColumns:'320px 1fr', background:'var(--term-bg)', color:'var(--term-text)', fontFamily:'var(--mono)' }}>
      {/* Agent info sidebar */}
      <aside style={{ borderRight:'1px solid var(--term-rule-hard)', padding:'28px 22px', display:'flex', flexDirection:'column', gap:20 }}>
        <div>
          <div style={{ fontSize:10, letterSpacing:'0.18em', color:'var(--term-muted)', textTransform:'uppercase' }}>twin/agents/</div>
          <div style={{ display:'flex', alignItems:'center', gap:14, marginTop:14 }}>
            <div style={{ width:54, height:54, background:'var(--term-bg-3)', border:'1px solid var(--term-rule-hard)', display:'grid', placeItems:'center', color: agent.color, fontFamily:'var(--serif)', fontStyle:'italic', fontSize:28 }}>{agent.stack}</div>
            <div>
              <div style={{ fontFamily:'var(--display)', fontSize:26, fontWeight:400, letterSpacing:'-0.015em', color:'var(--term-text)' }}><em style={{ fontFamily:'var(--serif)', fontStyle:'italic', color: agent.color }}>{agent.name.toLowerCase()}</em></div>
              <div style={{ fontSize:11, letterSpacing:'0.12em', color:'var(--term-muted)', textTransform:'uppercase', marginTop:2 }}>pid 0412.{agent.id}.14</div>
            </div>
          </div>
        </div>

        <div>
          <div style={{ fontSize:10, letterSpacing:'0.14em', color:'var(--term-muted)', textTransform:'uppercase', marginBottom:8 }}>role</div>
          <div style={{ fontSize:14, color:'var(--term-text)' }}>{agent.role}</div>
        </div>
        <div>
          <div style={{ fontSize:10, letterSpacing:'0.14em', color:'var(--term-muted)', textTransform:'uppercase', marginBottom:8 }}>scope</div>
          <div style={{ fontSize:13, color:'var(--term-text)' }}>{agent.scope}</div>
        </div>
        <div>
          <div style={{ fontSize:10, letterSpacing:'0.14em', color:'var(--term-muted)', textTransform:'uppercase', marginBottom:8 }}>state</div>
          <div style={{ display:'flex', alignItems:'center', gap:10, fontSize:13 }}>
            <span className="dot-pulse" style={{ background: agent.active?'var(--term-green)':'var(--term-dim)', color: agent.active?'var(--term-green)':'var(--term-dim)' }}/>
            <span>{agent.status}</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize:10, letterSpacing:'0.14em', color:'var(--term-muted)', textTransform:'uppercase', marginBottom:8 }}>latest output</div>
          <div style={{ fontSize:13, color:'var(--term-amber)' }}>{agent.output}</div>
        </div>

        <div style={{ marginTop:'auto', borderTop:'1px solid var(--term-rule)', paddingTop:14 }}>
          <div style={{ fontSize:10, letterSpacing:'0.14em', color:'var(--term-muted)', textTransform:'uppercase', marginBottom:10 }}>controls</div>
          <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
            <button className="btn">pause</button>
            <button className="btn">replay</button>
            <button className="btn">fork</button>
            <button className="btn">export</button>
          </div>
        </div>
      </aside>

      {/* Terminal */}
      <div style={{ display:'flex', flexDirection:'column', minWidth:0 }}>
        <div style={{ padding:'14px 24px', borderBottom:'1px solid var(--term-rule-hard)', display:'flex', alignItems:'center', gap:14, fontSize:11, letterSpacing:'0.14em', color:'var(--term-muted)', textTransform:'uppercase' }}>
          <span style={{ color:'var(--term-green)' }}>● connected</span>
          <span>twin-meridian · eng 0412</span>
          <span style={{ marginLeft:'auto', color:'var(--term-muted)' }}>tokens · 1.84M / 2.40M</span>
          <span>·</span>
          <span>uptime 14h 07m</span>
        </div>

        <div className="scroll" style={{ flex:1, padding:'18px 24px', overflow:'auto', fontSize:12.5, lineHeight:1.65 }}>
          {lines.map((l,i)=>(
            <div key={i} style={{ display:'grid', gridTemplateColumns:'88px 72px 1fr', gap:14, animation:'slide-in .3s ease', padding:'1px 0' }}>
              <span style={{ color:'var(--term-dim)' }}>{l.t}</span>
              <span style={{ color:'var(--term-muted)', textTransform:'uppercase', letterSpacing:'0.08em', fontSize:11 }}>{l.tag}</span>
              <span style={{ color: `var(--${l.c})`, wordBreak:'break-word' }}>{l.text}</span>
            </div>
          ))}
          <div style={{ display:'grid', gridTemplateColumns:'88px 72px 1fr', gap:14, marginTop:6 }}>
            <span style={{ color:'var(--term-dim)' }}>now</span>
            <span style={{ color:'var(--term-muted)' }}>&gt;</span>
            <span style={{ color:'var(--term-text)' }}>osmund<span className="cursor"/></span>
          </div>
        </div>

        {/* Sources strip */}
        <div style={{ borderTop:'1px solid var(--term-rule-hard)', padding:'12px 24px', display:'flex', gap:24, fontSize:11, letterSpacing:'0.1em', color:'var(--term-muted)', textTransform:'uppercase' }}>
          <span>sources touched · <span style={{ color:'var(--term-text)' }}>4,108</span></span>
          <span>claims cited · <span style={{ color:'var(--term-text)' }}>142</span></span>
          <span>quarantined · <span style={{ color:'var(--term-red)' }}>14</span></span>
          <span style={{ marginLeft:'auto' }}>replayable from · 08:42:11</span>
        </div>
      </div>
    </div>
  );
}

window.AgentView = AgentView;
