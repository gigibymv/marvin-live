// View 2 — Active mission. Brief, dispatch, agents working in live.

function MissionView({ activeAgent, setActiveAgent }) {
  return (
    <div className="scroll" style={{ flex:1, overflow:'auto', padding:'36px 48px 60px' }}>
      {/* Brief header */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 320px', gap:40, borderBottom:'1px solid var(--rule-hard)', paddingBottom:22, marginBottom:24 }}>
        <div>
          <div className="kicker">Engagement 0412 · Day {MISSION.day} of {MISSION.of} · Pod 07</div>
          <div style={{ fontFamily:'var(--display)', fontSize:46, fontWeight:400, letterSpacing:'-0.03em', lineHeight:1, marginTop:12, textWrap:'balance' }}>{MISSION.question}</div>
        </div>
        <div>
          <div className="kicker" style={{ marginBottom:10 }}>Red lines · Meridian</div>
          <ul style={{ listStyle:'none', display:'flex', flexDirection:'column', gap:10 }}>
            {MISSION.redlines.map((r,i)=>(
              <li key={i} style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, color:'var(--ink-2)', lineHeight:1.35, paddingLeft:14, borderLeft:'2px solid var(--against)' }}>{r}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Sub-questions */}
      <div style={{ marginBottom:32 }}>
        <div className="kicker" style={{ marginBottom:12 }}>Scope tree · 5 sub-questions</div>
        <div style={{ border:'1px solid var(--rule-hard)' }}>
          {MISSION.sub.map((q,i)=>(
            <div key={q.id} style={{ display:'grid', gridTemplateColumns:'60px 1fr auto', gap:20, padding:'14px 20px', borderTop:i?'1px solid var(--rule)':'none', alignItems:'center', background:'#EDE7DC' }}>
              <span style={{ fontFamily:'var(--mono)', fontSize:12, color:'var(--muted)', letterSpacing:'0.1em' }}>Q.{i+1}</span>
              <span style={{ fontFamily:'var(--display)', fontSize:18, fontWeight:400, letterSpacing:'-0.01em' }}>{q.label}</span>
              <span style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.12em', textTransform:'uppercase', padding:'4px 8px',
                background: q.state==='resolved'?'var(--for)': q.state==='contested'?'var(--against)':'var(--ink-3)', color:'var(--paper)' }}>{q.state}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Timeline + agent activity */}
      <div style={{ display:'grid', gridTemplateColumns:'1.2fr 1fr', gap:32 }}>
        <div>
          <div className="kicker" style={{ marginBottom:12 }}>Engagement timeline</div>
          <div style={{ background:'#EDE7DC', border:'1px solid var(--rule-hard)', padding:'6px 0' }}>
            {TIMELINE.map((t,i)=>(
              <div key={i} style={{ display:'grid', gridTemplateColumns:'36px 64px 1fr', gap:14, padding:'12px 20px', alignItems:'start' }}>
                <div style={{ width:20, height:20, borderRadius:'50%', border:'1.5px solid var(--ink)', background: t.done?'var(--ink)':'transparent', display:'grid', placeItems:'center', color:'var(--paper)', fontSize:11 }}>
                  {t.done ? '✓':''}
                </div>
                <div style={{ fontFamily:'var(--mono)', fontSize:11, color:'var(--muted)', letterSpacing:'0.1em' }}>Day {String(t.d).padStart(2,'0')}</div>
                <div>
                  <div style={{ fontFamily:'var(--display)', fontSize:16, fontWeight:400, letterSpacing:'-0.01em', color: t.done?'var(--ink)':'var(--ink-2)' }}>{t.label}</div>
                  <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, color:'var(--ink-3)', marginTop:2 }}>{t.note}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="kicker" style={{ marginBottom:12 }}>Agent activity · live</div>
          <div style={{ background:'#EDE7DC', border:'1px solid var(--rule-hard)' }}>
            {AGENTS.filter(a=>a.active).slice(0,7).map((a,i)=>(
              <div key={a.id} onClick={()=>setActiveAgent(a.id)} style={{ display:'grid', gridTemplateColumns:'32px 1fr auto', gap:14, padding:'14px 18px', borderTop:i?'1px solid var(--rule)':'none', alignItems:'center', cursor:'pointer', background: a.id===activeAgent?'#F4F0EA':'transparent' }}>
                <div style={{ width:28, height:28, background:'var(--ink)', color:'var(--paper)', display:'grid', placeItems:'center', fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14 }}>{a.stack}</div>
                <div>
                  <div style={{ fontFamily:'var(--display)', fontSize:15, fontWeight:400 }}><em className="it">{a.name}</em> · <span style={{ color:'var(--ink-3)' }}>{a.output}</span></div>
                  <div style={{ fontFamily:'var(--mono)', fontSize:10, color:'var(--muted)', letterSpacing:'0.1em', textTransform:'uppercase', marginTop:2 }}>{a.status}</div>
                </div>
                <div className="dot-pulse" style={{ background:a.color, color:a.color }}/>
              </div>
            ))}
          </div>

          <div style={{ marginTop:24, border:'1px solid var(--rule-hard)', background:'var(--ink)', color:'var(--paper)', padding:'20px 22px' }}>
            <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.14em', color:'#9A9487', textTransform:'uppercase', marginBottom:10 }}>Next human step</div>
            <div style={{ fontFamily:'var(--display)', fontSize:22, fontWeight:400, letterSpacing:'-0.015em', lineHeight:1.2 }}>Amara will <em className="it" style={{ color:'#C9C1AF' }}>red-team</em> both memos — tomorrow 08:00 CET.</div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.MissionView = MissionView;
