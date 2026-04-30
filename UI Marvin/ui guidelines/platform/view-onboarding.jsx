// View 6 — Onboarding. Install Twin at a new client.

function OnboardingView() {
  const steps = [
    { n:'01', label:'Sign the one-page charter', state:'done',    who:'Partner · CEO',        t:'12 min',  detail:'Two signatures. Scope sentence. First question. No SOW, no SLA.' },
    { n:'02', label:'Provision the enclave',     state:'done',    who:'Client IT · Vass',      t:'2 hours', detail:'Private VPC. SSO. Your data never leaves. We can audit, not read.' },
    { n:'03', label:'Ingest the starting corpus',state:'active',  who:'Marginalia',            t:'38 hrs',  detail:'Filings, contracts, internal memos, board decks. 11,204 pages of you.' },
    { n:'04', label:'Interview the 4 humans',    state:'queued',  who:'Pod 07',                t:'60 min ea',detail:'We learn the house vocabulary. Your red lines. Your taste for risk.' },
    { n:'05', label:'Calibrate the 9 agents',    state:'queued',  who:'Vass · Conductor',      t:'1 day',   detail:'Each agent is tuned to your sector, your history, your idioms.' },
    { n:'06', label:'First drift alert · live',  state:'queued',  who:'Twin',                  t:'within 48h', detail:'A signal about your world you didn\'t know you needed. Proof of life.' },
    { n:'07', label:'First question · framed',   state:'queued',  who:'Partner · CEO',         t:'30 min',  detail:'One sentence. The pod mobilizes. The disagreement drafts.' },
    { n:'08', label:'Twin is yours',             state:'final',   who:'—',                     t:'forever', detail:'Standing counsel begins. Monthly retainer. Agents never sleep.' },
  ];
  return (
    <div className="scroll" style={{ flex:1, overflow:'auto', padding:'40px 48px 60px', background:'#F4F0EA' }}>
      <div style={{ borderBottom:'1px solid var(--rule-hard)', paddingBottom:24, marginBottom:28 }}>
        <div className="kicker">Install a Twin · for a new client</div>
        <h1 className="disp" style={{ fontSize:62, marginTop:12 }}>Eight steps.<br/> <em className="it">Six days</em> from charter to signal.</h1>
        <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:20, color:'var(--ink-2)', marginTop:14, maxWidth:'54ch' }}>You do not buy a deck from us. You install an <em>organ</em>. We remain its surgeons.</div>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:0, border:'1px solid var(--rule-hard)' }}>
        {steps.map((s,i)=>{
          const col = i%2, row = Math.floor(i/2);
          return (
            <div key={i} style={{
              padding:'26px 30px 28px', background: s.state==='final'?'var(--ink)':s.state==='active'?'#EDE7DC':'#F4F0EA',
              color: s.state==='final'?'var(--paper)':'var(--ink)',
              borderRight: col===0?'1px solid var(--rule)':'none',
              borderTop: row>0?'1px solid var(--rule)':'none',
              position:'relative',
            }}>
              <div style={{ display:'flex', alignItems:'baseline', gap:14, marginBottom:8 }}>
                <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:38, color: s.state==='final'?'#9A9487':'var(--muted)', lineHeight:1 }}>{s.n}</div>
                <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.14em', color: s.state==='final'?'#9A9487':'var(--muted)', textTransform:'uppercase', padding:'3px 7px', border:`1px solid ${s.state==='done'?'var(--for)':s.state==='active'?'var(--warn)':s.state==='final'?'var(--paper)':'var(--rule-hard)'}`, color:s.state==='done'?'var(--for)':s.state==='active'?'var(--warn)':s.state==='final'?'var(--paper)':'var(--muted)' }}>
                  {s.state==='done'?'complete':s.state==='active'?'in progress':s.state==='final'?'ongoing':'queued'}
                </div>
              </div>
              <div style={{ fontFamily:'var(--display)', fontSize:26, fontWeight:400, letterSpacing:'-0.02em', lineHeight:1.1, textWrap:'balance' }}>{s.label.split(' · ')[0]} <em className="it" style={{ color: s.state==='final'?'#C9C1AF':'var(--ink-2)' }}>{s.label.split(' · ')[1]||''}</em></div>
              <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:15, color: s.state==='final'?'#C9C1AF':'var(--ink-2)', lineHeight:1.4, marginTop:10 }}>{s.detail}</div>
              <div style={{ marginTop:14, paddingTop:12, borderTop:`1px solid ${s.state==='final'?'#FFFFFF1F':'var(--rule)'}`, display:'flex', justifyContent:'space-between', fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.12em', color: s.state==='final'?'#9A9487':'var(--muted)', textTransform:'uppercase' }}>
                <span>Owner · <b style={{ color: s.state==='final'?'var(--paper)':'var(--ink)', fontWeight:500 }}>{s.who}</b></span>
                <span>{s.t}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop:28, padding:'22px 28px', background:'var(--ink)', color:'var(--paper)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div>
          <div className="kicker on-ink">Ready to charter</div>
          <div style={{ fontFamily:'var(--display)', fontSize:30, fontWeight:400, letterSpacing:'-0.02em', marginTop:6 }}>One question. <em className="it" style={{ color:'#C9C1AF' }}>Ten days.</em> A partner signs.</div>
        </div>
        <button className="btn primary">Charter a Twin →</button>
      </div>
    </div>
  );
}

window.OnboardingView = OnboardingView;
