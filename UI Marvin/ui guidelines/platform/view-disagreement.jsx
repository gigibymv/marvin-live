// Disagreement v2 — The Divergence Map.
// Two agent timelines start from the same brief and visually bifurcate.
// The moment of divergence is dramatized. Client drills into each node.

const FOR_TRACE = [
  { t:'D3 · 11:28', agent:'praxis',    claim:'47 comps mapped. Kepler moat holds vs. 4 of 6 entrants who abandoned.',        conf:0.81, src:'Comp table · n=47' },
  { t:'D5 · 09:11', agent:'osmund',    claim:'DCF central $790M. All scenarios above $760M conditional floor.',               conf:0.74, src:'Osmund · v9' },
  { t:'D6 · 14:33', agent:'marginalia',claim:'Top-3 customer concentration: 41%. Below Meridian\'s 45% red line.',           conf:0.92, src:'Data room · p. 88' },
  { t:'D7 · 08:00', agent:'sentinel',  claim:'FTC rule carries no retroactive clause. Jun 30 close is safe.',                conf:0.68, src:'Sentinel · §4.7' },
  { t:'D7 · 11:22', agent:'scrivener', claim:'Case-for memo v4. Verdict: acquire at $760M with conditions.',                 conf:null, src:'Scrivener · draft' },
];

const AGAINST_TRACE = [
  { t:'D7 · 07:02', agent:'praxis',    claim:'Stratus D: $3.1B pre. Kepler multiple overstated ~18%. Moat is funded, not structural.', conf:0.77, src:'Praxis · live signal' },
  { t:'D7 · 08:14', agent:'osmund',    claim:'DCF central re-rated to $728M — below $760M floor. Case-for weakens.',         conf:0.79, src:'Osmund · v12' },
  { t:'D7 · 09:14', agent:'chronos',   claim:'ARR bridge in data room understates churn by ~$4.1M. Unresolved.',             conf:0.61, src:'Chronos · §3.2' },
  { t:'D7 · 10:55', agent:'sentinel',  claim:'EU AI Act Art. 6 classification: likely, under appeal, unresolved.',           conf:0.55, src:'Sentinel · EU reg' },
  { t:'D7 · 18:30', agent:'scrivener', claim:'Case-against memo v3. Verdict: walk. Premium is air.',                         conf:null, src:'Scrivener · draft' },
];

const FORK_MOMENT = { t:'D7 · 07:02', claim:'Stratus AI Series D re-rates the sector.', note:'This is where the two paths separated. Before this signal, both traces agreed. After it, Marchetti diverged.', agent:'praxis' };

function TraceNode({ node, side, isActive, onClick }) {
  const dark = side === 'against';
  return (
    <div onClick={onClick} style={{
      display:'flex', gap:10, alignItems:'flex-start', padding:'12px 0', borderTop:'1px solid var(--rule)',
      cursor:'pointer', transition:'background .1s',
    }}>
      <div style={{ width:28, height:28, background: dark?'var(--paper-2)':'var(--ink)', color: dark?'var(--ink)':'var(--paper)', display:'grid', placeItems:'center', fontFamily:'var(--serif)', fontStyle:'italic', fontSize:13, flexShrink:0, border:`1px solid ${dark?'var(--rule-hard)':'var(--ink)'}` }}>
        {(AGENTS.find(a=>a.id===node.agent)||{}).stack||'?'}
      </div>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontFamily:'var(--mono)', fontSize:9, letterSpacing:'0.12em', color:'var(--muted)', textTransform:'uppercase', marginBottom:4 }}>
          {node.t} · {node.src}
          {node.conf && <span style={{ marginLeft:8, color: node.conf>0.75?'var(--for)':node.conf>0.6?'var(--warn)':'var(--against)' }}>{Math.round(node.conf*100)}% conf.</span>}
        </div>
        <div style={{ fontFamily:'var(--sans)', fontSize:13, lineHeight:1.4, color:'var(--ink)' }}>{node.claim}</div>
        {node.conf === null && (
          <div style={{ fontFamily:'var(--mono)', fontSize:9, padding:'3px 8px', marginTop:6, display:'inline-block', background:'var(--ink)', color:'var(--paper)', letterSpacing:'0.12em', textTransform:'uppercase' }}>
            {side==='for' ? 'SIGNED · OKAFOR' : 'SIGNED · MARCHETTI'}
          </div>
        )}
      </div>
    </div>
  );
}

function DisagreementView() {
  const [leaning, setLeaning] = React.useState(50);
  const [activeNode, setActiveNode] = React.useState(null);

  const leanLabel = leaning > 55 ? 'Proceed at $760M' : leaning < 45 ? 'Walk' : 'Equipoise';
  const leanColor = leaning > 55 ? 'var(--for)' : leaning < 45 ? 'var(--against)' : 'var(--ink)';

  return (
    <div className="scroll" style={{ flex:1, overflow:'auto', padding:'36px 48px 60px' }}>
      {/* Header */}
      <div style={{ borderBottom:'1px solid var(--rule-hard)', paddingBottom:20, marginBottom:24 }}>
        <div className="kicker">Eng 0412 · The divergence · Two traces · One question</div>
        <div style={{ fontFamily:'var(--display)', fontSize:52, marginTop:10, lineHeight:0.96 }}>
          The moment the<br/><em style={{ fontFamily:'var(--serif)', fontStyle:'italic' }}>paths split.</em>
        </div>
        <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:16, color:'var(--ink-2)', marginTop:12, maxWidth:'72ch', lineHeight:1.45 }}>
          Both traces began from the same brief. They agreed until D7 07:02 — when Praxis flagged the Stratus raise. After that, <em>Amara and Marchetti diverged.</em> Below is where, exactly, and why.
        </div>
      </div>

      {/* Fork moment */}
      <div style={{ background:'var(--ink)', color:'var(--paper)', padding:'20px 24px', marginBottom:24, display:'grid', gridTemplateColumns:'60px 1fr', gap:18, alignItems:'center' }}>
        <div style={{ fontFamily:'var(--sans)', fontSize:11, letterSpacing:'0.14em', textTransform:'uppercase', color:'#9A9487', textAlign:'center', lineHeight:1.3 }}>Fork<br/>point</div>
        <div>
          <div style={{ fontFamily:'var(--sans)', fontSize:16, fontWeight:600, letterSpacing:'0.06em', textTransform:'uppercase' }}>{FORK_MOMENT.t} · {FORK_MOMENT.claim}</div>
          <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, color:'#C9C1AF', marginTop:6, lineHeight:1.4 }}>{FORK_MOMENT.note}</div>
        </div>
      </div>

      {/* Two columns — diverging traces */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:0, marginBottom:28 }}>
        {/* Case for */}
        <div style={{ padding:'0 32px 0 0', borderRight:'1px solid var(--rule-hard)' }}>
          <div style={{ fontFamily:'var(--sans)', fontSize:11, letterSpacing:'0.14em', textTransform:'uppercase', marginBottom:4 }}>The case for — Amara Okafor</div>
          <div style={{ fontFamily:'var(--display)', fontSize:34, lineHeight:1, marginBottom:4 }}>Acquire at <em style={{ fontFamily:'var(--serif)', fontStyle:'italic' }}>$760M</em></div>
          <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, color:'var(--ink-2)', marginBottom:16, lineHeight:1.35 }}>Discount for concentration risk. FTC path is clear. Close before Jun 30.</div>
          {FOR_TRACE.map((n,i)=><TraceNode key={i} node={n} side="for" isActive={activeNode===`f${i}`} onClick={()=>setActiveNode(activeNode===`f${i}`?null:`f${i}`)}/>)}
          <div style={{ marginTop:16, padding:'14px 16px', background:'var(--for)', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <div style={{ fontFamily:'var(--sans)', fontSize:13, fontWeight:600, color:'#F4F0EA', letterSpacing:'-0.01em' }}>Strength of case</div>
            <div style={{ fontFamily:'var(--display)', fontSize:32, color:'#F4F0EA' }}>8.2<span style={{ fontSize:16, opacity:0.7 }}>/10</span></div>
          </div>
        </div>

        {/* Case against */}
        <div style={{ padding:'0 0 0 32px' }}>
          <div style={{ fontFamily:'var(--sans)', fontSize:11, letterSpacing:'0.14em', textTransform:'uppercase', marginBottom:4 }}>The case against — I. Marchetti</div>
          <div style={{ fontFamily:'var(--display)', fontSize:34, lineHeight:1, marginBottom:4 }}>Walk. <em style={{ fontFamily:'var(--serif)', fontStyle:'italic' }}>The moat is air.</em></div>
          <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, color:'var(--ink-2)', marginBottom:16, lineHeight:1.35 }}>Moat is funded by Nvidia access, now commoditised. $728M DCF below floor.</div>
          {AGAINST_TRACE.map((n,i)=><TraceNode key={i} node={n} side="against" isActive={activeNode===`a${i}`} onClick={()=>setActiveNode(activeNode===`a${i}`?null:`a${i}`)}/>)}
          <div style={{ marginTop:16, padding:'14px 16px', background:'var(--against)', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <div style={{ fontFamily:'var(--sans)', fontSize:13, fontWeight:600, color:'#F4F0EA', letterSpacing:'-0.01em' }}>Strength of case</div>
            <div style={{ fontFamily:'var(--display)', fontSize:32, color:'#F4F0EA' }}>7.4<span style={{ fontSize:16, opacity:0.7 }}>/10</span></div>
          </div>
        </div>
      </div>

      {/* Arbitration */}
      <div style={{ border:'1px solid var(--rule-hard)', padding:'24px 28px', background:'#EDE7DC' }}>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:40, alignItems:'center' }}>
          <div>
            <div className="kicker" style={{ marginBottom:10 }}>Your arbitration</div>
            <div style={{ fontFamily:'var(--display)', fontSize:40, lineHeight:0.95 }}>
              <em style={{ fontFamily:'var(--serif)', fontStyle:'italic', color:leanColor }}>{leanLabel}</em>
            </div>
            <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, color:'var(--ink-2)', marginTop:10, lineHeight:1.4, maxWidth:'36ch' }}>
              {leaning > 55 ? 'You accept Okafor\'s case. Agents will formalize the $760M conditional offer.' :
               leaning < 45 ? 'You accept Marchetti\'s case. Agents will draft a walk memo for the board.' :
               'You\'re balanced. Take both memos to the board as posed. Let them arbitrate.'}
            </div>
          </div>
          <div>
            <div style={{ display:'flex', justifyContent:'space-between', fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.12em', textTransform:'uppercase', color:'var(--muted)', marginBottom:10 }}>
              <span style={{ color:'var(--against)' }}>Walk</span>
              <span>Equipoise</span>
              <span style={{ color:'var(--for)' }}>Proceed</span>
            </div>
            <input type="range" min="0" max="100" value={leaning} onChange={e=>setLeaning(+e.target.value)} style={{ width:'100%', accentColor:'var(--ink)', height:4 }}/>
            <div style={{ marginTop:20, display:'flex', gap:10, justifyContent:'flex-end' }}>
              <button className="btn ghost">Request red-team</button>
              <button className="btn primary">Lock verdict →</button>
            </div>
          </div>
        </div>
      </div>

      {/* Replay note */}
      <div style={{ marginTop:16, fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, color:'var(--muted)', textAlign:'center' }}>
        This divergence is replayable — every node traces back to source data, timestamp, and agent reasoning. You can replay it in 6 months on new market data.
      </div>
    </div>
  );
}

window.DisagreementView = DisagreementView;
