// View 5 — Corpus. Private library of resolved disagreements.

function CorpusView() {
  const [q, setQ] = React.useState('');
  const filtered = CORPUS.filter(c => !q || (c.question.toLowerCase().includes(q.toLowerCase()) || c.sector.toLowerCase().includes(q.toLowerCase())));

  return (
    <div className="scroll" style={{ flex:1, overflow:'auto', padding:'36px 48px 60px' }}>
      <div style={{ borderBottom:'1px solid var(--rule-hard)', paddingBottom:22, marginBottom:24 }}>
        <div className="kicker">The Corpus · Meridian’s private archive · 47 resolved disagreements</div>
        <h1 className="disp" style={{ fontSize:54, marginTop:10 }}>Every question <em className="it">you’ve ever asked us,</em> still thinking.</h1>
        <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:18, color:'var(--ink-2)', marginTop:12, maxWidth:'64ch' }}>Search is one part. The other part is that every memo here <em>refreshes itself</em> as the world changes. Six months from now, the Kepler verdict will still be current.</div>
      </div>

      <div style={{ display:'flex', gap:16, alignItems:'center', marginBottom:22 }}>
        <div style={{ flex:1, display:'flex', alignItems:'center', gap:12, padding:'12px 18px', background:'#EDE7DC', border:'1px solid var(--rule-hard)' }}>
          <span style={{ fontFamily:'var(--mono)', fontSize:11, color:'var(--muted)', letterSpacing:'0.14em' }}>⌘F</span>
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search 47 memos · 312 agents · 8,204 claims…" style={{ flex:1, background:'transparent', border:'none', outline:'none', fontFamily:'var(--serif)', fontStyle:'italic', fontSize:18, color:'var(--ink)' }}/>
          <span className="kicker">{filtered.length} matches</span>
        </div>
        <div style={{ display:'flex', gap:6 }}>
          {['All','PE','Tech','FS','Health'].map(f=>(
            <button key={f} className="btn ghost" style={{ padding:'10px 14px', fontSize:10 }}>{f}</button>
          ))}
        </div>
      </div>

      <div style={{ border:'1px solid var(--rule-hard)' }}>
        <div style={{ display:'grid', gridTemplateColumns:'70px 200px 1fr 1fr 150px', gap:20, padding:'12px 22px', background:'var(--ink)', color:'var(--paper)', fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.14em', textTransform:'uppercase' }}>
          <span>Year</span><span>Sector</span><span>Question</span><span>Verdict · still current</span><span style={{ textAlign:'right' }}>Artefacts</span>
        </div>
        {filtered.map((c,i)=>(
          <div key={i} style={{ display:'grid', gridTemplateColumns:'70px 200px 1fr 1fr 150px', gap:20, padding:'20px 22px', borderTop: i?'1px solid var(--rule)':'none', alignItems:'start', background:'#EDE7DC', cursor:'pointer' }}>
            <div style={{ fontFamily:'var(--mono)', fontSize:13, color:'var(--muted)', letterSpacing:'0.08em' }}>{c.year}</div>
            <div>
              <div style={{ fontFamily:'var(--mono)', fontSize:11, letterSpacing:'0.1em', color:'var(--ink-2)' }}>{c.sector}</div>
              <div style={{ display:'flex', gap:4, flexWrap:'wrap', marginTop:6 }}>
                {c.tags.map(t=><span key={t} style={{ fontFamily:'var(--mono)', fontSize:9, letterSpacing:'0.08em', padding:'2px 6px', background:'var(--paper)', border:'1px solid var(--rule)', color:'var(--ink-3)' }}>{t}</span>)}
              </div>
            </div>
            <div style={{ fontFamily:'var(--display)', fontSize:19, fontWeight:400, letterSpacing:'-0.01em', lineHeight:1.2, textWrap:'pretty' }}>{c.question}</div>
            <div style={{ fontFamily:'var(--serif)', fontStyle:'italic', fontSize:18, color:'var(--ink-2)', lineHeight:1.3 }}>{c.verdict}</div>
            <div style={{ textAlign:'right' }}>
              <div style={{ fontFamily:'var(--mono)', fontSize:11, color:'var(--muted)', letterSpacing:'0.08em' }}>{c.pages}</div>
              <div style={{ marginTop:6, display:'flex', gap:4, justifyContent:'flex-end' }}>
                <span className="dot-pulse" style={{ background:'var(--signal)', color:'var(--signal)', width:6, height:6 }}/>
                <span style={{ fontFamily:'var(--mono)', fontSize:9, letterSpacing:'0.1em', color:'var(--signal)', textTransform:'uppercase' }}>live</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop:22, fontFamily:'var(--serif)', fontStyle:'italic', fontSize:16, color:'var(--muted)' }}>The corpus is private to Meridian — not shared, not trained on outside your enclave. It is the asset you are really buying.</div>
    </div>
  );
}

window.CorpusView = CorpusView;
