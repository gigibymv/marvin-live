// Dashboard v2 — The River of Reasoning.
// A vertical temporal flow from founding brief → today.
// Every signal, finding, drift, human action flows down the river.

const RIVER_EVENTS = [
  { id:'r0',  day:1,  t:'08:42', type:'found',   agent:'',       human:'Amara Okafor',   title:'Brief signed.',                              body:'One sentence. One question. No SOW. "Should Meridian acquire Kepler Systems at $820M?"',  significance: 5 },
  { id:'r1',  day:1,  t:'09:15', type:'agent',   agent:'livia',  human:'',               title:'Livia begins ingestion.',                    body:'4,108 sector sources queued. Analyst reports, patents, earnings calls. Reading starts.',  significance: 2 },
  { id:'r2',  day:2,  t:'06:03', type:'agent',   agent:'marginalia', human:'',           title:'Data room: 11,204 pages normalized.',        body:'96% of claims indexed to source. 14 claims unverifiable — quarantined immediately.',  significance: 3 },
  { id:'r3',  day:3,  t:'11:28', type:'agent',   agent:'praxis', human:'',               title:'47 competitors mapped.',                     body:'6 flagged as material. Stratus AI identified as closest comparable.',  significance: 3 },
  { id:'r4',  day:3,  t:'14:55', type:'human',   agent:'',       human:'Amara Okafor',   title:'Partner rejects Osmund DCF v1–v7.',          body:'"The WACC assumption is 2025 thinking on a 2026 risk curve. Re-run."',  significance: 4 },
  { id:'r5',  day:5,  t:'09:11', type:'agent',   agent:'osmund', human:'',               title:'DCF v9 accepted. Central = $790M.',          body:'3 scenarios: bull $861M, central $790M, bear $691M. All above $760M conditional floor.',  significance: 4 },
  { id:'r6',  day:6,  t:'22:14', type:'drift',   agent:'sentinel', human:'',             title:'FTC draft rule updated overnight.',          body:"Algorithmic-pricing guidance tightened. Kepler's revenue-share model directly affected. Re-reading §4.2.",  significance: 5 },
  { id:'r7',  day:7,  t:'07:02', type:'drift',   agent:'praxis', human:'',               title:'Stratus AI Series D: $3.1B pre-money.',      body:'Closest comparable re-rated. Kepler multiple now overstated ~18%. Osmund re-running scenarios.',  significance: 5 },
  { id:'r8',  day:7,  t:'09:08', type:'agent',   agent:'osmund', human:'',               title:'Central case falls to $728M.',               body:'Below $760M conditional floor. Case-for weakens. Partner review flagged.',  significance: 5 },
  { id:'r9',  day:7,  t:'09:14', type:'fork',    agent:'',       human:'',               title:'THE DISAGREEMENT OPENS.',                    body:'Scrivener begins two opposing memos. Amara argues for. Marchetti argues against. Agents split.',  significance: 5 },
  { id:'r10', day:7,  t:'18:30', type:'human',   agent:'',       human:'I. Marchetti',  title:'"Walk. The moat is funded, not structural."', body:'Marchetti submits case-against v3. Cites Stratus access dependency.',  significance: 4 },
  { id:'r11', day:7,  t:'22:01', type:'human',   agent:'',       human:'Amara Okafor',  title:'"Acquire at $760M with conditions."',         body:'Okafor submits case-for v4. Accepts price discount. Argues FTC path is clear.',  significance: 4 },
  { id:'r12', day:8,  t:'09:00', type:'next',    agent:'',       human:'',               title:'Red team · tomorrow.',                       body:'Partner challenges both sides. Then board arbitrates Monday.',  significance: 3 },
];

const TYPE_META = {
  found:  { color:'var(--ink)',     label:'Founded',   bg:'var(--ink)',     text:'var(--paper)' },
  agent:  { color:'var(--muted)',   label:'Agent',     bg:'var(--paper-2)', text:'var(--ink)' },
  human:  { color:'var(--ink)',     label:'Human',     bg:'#EDE7DC',        text:'var(--ink)' },
  drift:  { color:'oklch(0.50 0.12 25)', label:'Drift', bg:'oklch(0.50 0.12 25)', text:'#F4F0EA' },
  fork:   { color:'var(--ink)',     label:'Fork',      bg:'var(--ink)',     text:'var(--paper)' },
  next:   { color:'var(--muted)',   label:'Queued',    bg:'transparent',   text:'var(--muted)' },
};

function RiverNode({ ev, isActive, onClick }) {
  const m = TYPE_META[ev.type];
  const isFork = ev.type === 'fork';
  return (
    <div onClick={onClick} style={{ display:'grid', gridTemplateColumns:'80px 1px 1fr', gap:0, cursor:'pointer', marginBottom:0 }}>
      {/* timeline label */}
      <div style={{ paddingRight:16, paddingTop:16, textAlign:'right' }}>
        <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.12em', color:'var(--muted)', textTransform:'uppercase' }}>D{String(ev.day).padStart(2,'0')}</div>
        <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.1em', color:'var(--muted)', marginTop:2 }}>{ev.t}</div>
      </div>

      {/* spine */}
      <div style={{ display:'flex', flexDirection:'column', alignItems:'center' }}>
        <div style={{ width:1, flex:'0 0 16px', background: 'var(--rule-hard)' }}/>
        <div style={{
          width: isFork ? 18 : 10,
          height: isFork ? 18 : 10,
          borderRadius: isFork ? 0 : '50%',
          background: m.color,
          flexShrink:0,
          border: ev.type==='next' ? '1px dashed var(--muted)' : 'none',
          transform: isFork ? 'rotate(45deg)' : 'none',
        }}/>
        <div style={{ width:1, flex:1, background: 'var(--rule-hard)', minHeight:8 }}/>
      </div>

      {/* content */}
      <div style={{
        marginLeft:18, marginBottom: isFork ? 2 : 0, padding:'12px 18px 16px',
        background: isActive ? m.bg : (isFork ? m.bg : 'transparent'),
        border: isFork ? '1px solid var(--ink)' : isActive ? '1px solid var(--ink)' : '1px solid transparent',
        color: isActive || isFork ? m.text : 'var(--ink)',
        transition:'background .15s',
        marginTop: isFork ? -4 : 0,
      }}>
        <div style={{
          fontFamily:'var(--sans)', fontSize: isFork ? 17 : 14, fontWeight: isFork ? 700 : 500,
          letterSpacing: isFork ? '0.06em' : '-0.005em', textTransform: isFork ? 'uppercase' : 'none',
          color: isActive || isFork ? m.text : 'var(--ink)',
        }}>{ev.title}</div>
        {(isActive || isFork) && (
          <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, lineHeight:1.45, marginTop:6, color: isActive || isFork ? m.text : 'var(--ink-2)', opacity: isActive || isFork ? 1 : 0.85 }}>
            {ev.body}
          </div>
        )}
        {(ev.human || ev.agent) && (
          <div style={{ fontFamily:'var(--mono)', fontSize:9.5, letterSpacing:'0.12em', textTransform:'uppercase', marginTop:8, color: isActive||isFork ? (isFork||m.text==='var(--paper)'?'rgba(255,255,255,0.55)':'var(--muted)') : 'var(--muted)' }}>
            {ev.human || (AGENTS.find(a=>a.id===ev.agent)||{}).name || ''}
          </div>
        )}
      </div>
    </div>
  );
}

function DashboardView({ activeAgent, setActiveAgent }) {
  const [activeNode, setActiveNode] = React.useState('r9');
  const [counter, setCounter] = React.useState(4108);

  React.useEffect(()=>{
    const id = setInterval(()=>setCounter(c=>c+1), 2400);
    return ()=>clearInterval(id);
  },[]);

  return (
    <div style={{ flex:1, display:'grid', gridTemplateColumns:'1fr 320px', overflow:'hidden' }}>
      {/* River */}
      <div className="scroll" style={{ overflow:'auto', padding:'40px 0 60px 48px' }}>
        <div style={{ borderBottom:'1px solid var(--rule-hard)', paddingBottom:18, marginBottom:28 }}>
          <div className="kicker">The Twin · River of Reasoning · Meridian Capital · Eng 0412</div>
          <div style={{ fontFamily:'var(--display)', fontSize:44, marginTop:10, lineHeight:0.96 }}>Every thought,<br/><em style={{ fontFamily:'var(--serif)', fontStyle:'italic' }}>in order.</em></div>
          <div style={{ fontFamily:'var(--sans)', fontSize:13, color:'var(--muted)', marginTop:10 }}>Click any node to open it. The river flows from the founding brief to now.</div>
        </div>

        <div style={{ paddingRight:24 }}>
          {RIVER_EVENTS.map(ev=>(
            <RiverNode key={ev.id} ev={ev} isActive={activeNode===ev.id} onClick={()=>setActiveNode(ev.id===activeNode?null:ev.id)}/>
          ))}
          {/* live tail */}
          <div style={{ display:'grid', gridTemplateColumns:'80px 1px 1fr', gap:0, marginTop:0 }}>
            <div/>
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center' }}>
              <div style={{ width:1, flex:'0 0 16px', background:'var(--rule-hard)'}}/>
              <span className="dot-pulse" style={{ background:'var(--ink)', color:'var(--ink)' }}/>
              <div style={{ width:1, flex:'0 0 32px', background:'transparent'}}/>
            </div>
            <div style={{ marginLeft:18, paddingTop:14, fontFamily:'var(--mono)', fontSize:11, color:'var(--muted)', letterSpacing:'0.1em' }}>
              NOW · {counter.toLocaleString()} sources read
            </div>
          </div>
        </div>
      </div>

      {/* Right panel — live snapshot */}
      <aside style={{ borderLeft:'1px solid var(--rule-hard)', overflow:'auto', padding:'40px 22px 40px', background:'#EDE7DC' }}>
        <div className="kicker" style={{ marginBottom:16 }}>Live · 3 drift alerts</div>
        {DRIFT_ALERTS.map((d,i)=>(
          <div key={i} style={{ paddingBottom:14, marginBottom:14, borderBottom:'1px solid var(--rule)' }}>
            <div style={{ display:'flex', gap:8, alignItems:'center', marginBottom:6 }}>
              <span style={{ fontFamily:'var(--mono)', fontSize:9, letterSpacing:'0.12em', padding:'2px 6px', textTransform:'uppercase',
                background: d.severity==='high'?'var(--against)': d.severity==='medium'?'var(--warn)':'var(--ink-3)', color:'#F4F0EA' }}>{d.severity}</span>
              <span style={{ fontFamily:'var(--mono)', fontSize:10, color:'var(--muted)', letterSpacing:'0.08em' }}>{d.when}</span>
            </div>
            <div style={{ fontFamily:'var(--sans)', fontSize:13, fontWeight:500, lineHeight:1.35 }}>{d.title}</div>
            <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:12, color:'var(--ink-2)', lineHeight:1.35, marginTop:4 }}>{d.note}</div>
          </div>
        ))}

        <div className="kicker" style={{ marginBottom:14, marginTop:8 }}>Agents · now</div>
        {AGENTS.filter(a=>a.active).map(a=>(
          <div key={a.id} onClick={()=>setActiveAgent(a.id)} style={{ display:'flex', gap:10, alignItems:'center', padding:'8px 0', borderTop:'1px solid var(--rule)', cursor:'pointer' }}>
            <div style={{ width:26, height:26, background:'var(--ink)', color:'var(--paper)', display:'grid', placeItems:'center', fontFamily:'var(--serif)', fontStyle:'italic', fontSize:13, flexShrink:0 }}>{a.stack}</div>
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontFamily:'var(--sans)', fontSize:12, fontWeight:500 }}>{a.name}</div>
              <div style={{ fontFamily:'var(--mono)', fontSize:9, letterSpacing:'0.1em', color:'var(--muted)', textTransform:'uppercase', marginTop:1, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{a.status}</div>
            </div>
            <span className="dot-pulse" style={{ background:a.color, color:a.color, flexShrink:0 }}/>
          </div>
        ))}

        <div style={{ marginTop:20, padding:'16px', background:'var(--ink)', color:'var(--paper)' }}>
          <div className="kicker on-ink" style={{ marginBottom:8 }}>Next · Day 8</div>
          <div style={{ fontFamily:'var(--display)', fontSize:20, lineHeight:1.1 }}>Amara red-teams both memos. <em style={{ fontFamily:'var(--serif)', fontStyle:'italic', color:'#C9C1AF' }}>Tomorrow 08:00.</em></div>
        </div>
      </aside>
    </div>
  );
}

window.DashboardView = DashboardView;
