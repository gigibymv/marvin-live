// Shell — browser chrome + left nav + view switcher

const CHROME_BG = '#E8E4DC';
const CHROME_INK = '#1A1814';

function TrafficLights() {
  return (
    <div style={{ display:'flex', gap:8, padding:'0 14px' }}>
      <div style={{ width:12, height:12, borderRadius:'50%', background:'#FF5F57' }}/>
      <div style={{ width:12, height:12, borderRadius:'50%', background:'#FEBC2E' }}/>
      <div style={{ width:12, height:12, borderRadius:'50%', background:'#28C840' }}/>
    </div>
  );
}

function BrowserChrome({ children, url, tabs, activeTab, onTab }) {
  return (
    <div style={{
      width:1440, height:900, borderRadius:12, overflow:'hidden',
      boxShadow:'0 40px 120px rgba(0,0,0,0.55), 0 0 0 1px rgba(0,0,0,0.25)',
      display:'flex', flexDirection:'column', background: CHROME_BG,
      fontFamily:'var(--sans)'
    }}>
      {/* tab bar */}
      <div style={{ height:42, background: CHROME_BG, display:'flex', alignItems:'flex-end', paddingRight:10 }}>
        <div style={{ display:'flex', alignItems:'center', height:'100%' }}><TrafficLights/></div>
        <div style={{ display:'flex', alignItems:'flex-end', height:'100%', flex:1, gap:2, paddingLeft:4 }}>
          {tabs.map((t,i)=>(
            <div key={i} onClick={()=>onTab && onTab(i)} style={{
              position:'relative', height:32, padding:'0 14px',
              background: i===activeTab ? '#F4F0EA' : 'transparent',
              color: i===activeTab ? CHROME_INK : '#78716A',
              borderRadius:'8px 8px 0 0', display:'flex', alignItems:'center', gap:10,
              fontSize:12, fontFamily:'var(--mono)', letterSpacing:'0.04em',
              cursor:'pointer', minWidth:160, maxWidth:260,
            }}>
              <div style={{ width:6, height:6, borderRadius:'50%', background: t.live?'#8CB369':'#9A9487' }}/>
              <span style={{ flex:1, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{t.title}</span>
              {i===activeTab && <span style={{ fontSize:11, color:'#9A9487' }}>×</span>}
            </div>
          ))}
          <div style={{ padding:'0 10px', color:'#78716A', fontSize:18, lineHeight:'32px' }}>+</div>
        </div>
      </div>
      {/* toolbar */}
      <div style={{ height:40, background:'#F4F0EA', display:'flex', alignItems:'center', gap:10, padding:'0 14px', borderBottom:'1px solid #1A18141A' }}>
        <div style={{ display:'flex', gap:6, color:'#78716A', fontFamily:'var(--mono)', fontSize:14 }}>
          <span>‹</span><span>›</span><span style={{ fontSize:13 }}>↻</span>
        </div>
        <div style={{
          flex:1, height:26, borderRadius:13, background:'#EEE9DD',
          display:'flex', alignItems:'center', padding:'0 14px', gap:10,
          fontFamily:'var(--mono)', fontSize:12, letterSpacing:'0.04em', color:'#3A362F'
        }}>
          <svg width="11" height="11" viewBox="0 0 11 11"><path d="M3.5 5V3.5a2 2 0 014 0V5M2.5 5h6v5h-6z" fill="none" stroke="currentColor" strokeWidth="1"/></svg>
          <span style={{ color:'#78716A' }}>twin.h-ai.co</span>
          <span>/meridian/</span>
          <span style={{ color:'#1A1814' }}>{url}</span>
          <span style={{ marginLeft:'auto', color:'#78716A' }}>⌘K</span>
        </div>
        <div style={{ display:'flex', gap:8, alignItems:'center', fontFamily:'var(--mono)', fontSize:11, color:'#78716A' }}>
          <div style={{ width:22, height:22, borderRadius:'50%', background:'#C6BFAE', display:'grid', placeItems:'center', color:'#1A1814', fontSize:10, fontWeight:600 }}>CS</div>
        </div>
      </div>
      {/* page */}
      <div style={{ flex:1, background:'#F4F0EA', overflow:'hidden', display:'flex' }}>
        {children}
      </div>
    </div>
  );
}

function NavItem({ icon, label, sub, active, onClick, danger }) {
  return (
    <div onClick={onClick} style={{
      display:'grid', gridTemplateColumns:'32px 1fr', gap:10, alignItems:'center',
      padding:'11px 16px', cursor:'pointer',
      background: active ? '#F4F0EA' : 'transparent',
      borderLeft: active ? '2px solid var(--ink)' : '2px solid transparent',
      marginLeft: active ? 0 : 2,
    }}>
      <div style={{
        width:28, height:28, border:'1px solid var(--ink)', display:'grid', placeItems:'center',
        fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14, color:'var(--ink)',
        background: active ? '#F4F0EA' : 'transparent'
      }}>{icon}</div>
      <div>
        <div style={{ fontFamily:'var(--sans)', fontSize:14, fontWeight:500, color:'var(--ink)', letterSpacing:'-0.005em', display:'flex', alignItems:'center', gap:8 }}>
          {label}
          {danger && <span style={{ fontFamily:'var(--mono)', fontSize:9, letterSpacing:'0.1em', padding:'2px 5px', background:'var(--against)', color:'#F4F0EA' }}>2</span>}
        </div>
        {sub && <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.1em', color:'#78716A', marginTop:2, textTransform:'uppercase' }}>{sub}</div>}
      </div>
    </div>
  );
}

function LeftNav({ view, setView }) {
  return (
    <aside style={{ width:260, background:'#EDE7DC', borderRight:'1px solid var(--rule)', display:'flex', flexDirection:'column' }}>
      <div style={{ padding:'18px 16px 14px', borderBottom:'1px solid var(--rule)' }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{ width:26, height:26, border:'1px solid var(--ink)', display:'grid', placeItems:'center', fontFamily:'var(--serif)', fontStyle:'italic', fontSize:14 }}>H</div>
          <div>
            <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.16em', color:'#78716A', textTransform:'uppercase' }}>H<em style={{ fontFamily:'var(--serif)', fontStyle:'italic' }}>&amp;ai</em> · Twin</div>
            <div style={{ fontFamily:'var(--display)', fontSize:18, fontWeight:400, letterSpacing:'-0.015em' }}>Meridian <em className="it">Capital</em></div>
          </div>
        </div>
      </div>

      <div style={{ padding:'14px 0 6px' }}>
        <div style={{ padding:'0 18px 8px', fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.14em', color:'#78716A', textTransform:'uppercase' }}>The Twin</div>
        <NavItem icon="i"   label="River"         sub="Reasoning · live"  active={view==='dashboard'}    onClick={()=>setView('dashboard')} danger />
        <NavItem icon="ii"  label="Mission 0412"  sub="Day 7 of 10"       active={view==='mission'}      onClick={()=>setView('mission')} />
        <NavItem icon="iii" label="Divergence"    sub="Fork · D7 · 07:02" active={view==='disagreement'} onClick={()=>setView('disagreement')} />
        <NavItem icon="iv"  label="Agent trace"   sub="Osmund · modeling" active={view==='agent'}        onClick={()=>setView('agent')} />
      </div>

      <div style={{ padding:'14px 0 6px', borderTop:'1px solid var(--rule)' }}>
        <div style={{ padding:'0 18px 8px', fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.14em', color:'#78716A', textTransform:'uppercase' }}>Memory</div>
        <NavItem icon="v"   label="Corpus"        sub="47 resolved"       active={view==='corpus'}       onClick={()=>setView('corpus')} />
        <NavItem icon="vi"  label="Install Twin"  sub="New client"        active={view==='onboarding'}   onClick={()=>setView('onboarding')} />
      </div>

      <div style={{ marginTop:'auto', padding:'16px', borderTop:'1px solid var(--rule)', display:'flex', alignItems:'center', gap:10 }}>
        <div style={{ width:28, height:28, borderRadius:'50%', background:'#C6BFAE', display:'grid', placeItems:'center', fontSize:11, fontWeight:600, color:'#1A1814' }}>CS</div>
        <div>
          <div style={{ fontSize:13, fontWeight:500 }}>Chen Sifeng</div>
          <div style={{ fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.1em', color:'#78716A', textTransform:'uppercase' }}>CFO · Meridian</div>
        </div>
      </div>
    </aside>
  );
}

Object.assign(window, { BrowserChrome, LeftNav, TrafficLights });
