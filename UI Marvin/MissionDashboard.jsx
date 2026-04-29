import React, { useState, useEffect } from "react";

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=Newsreader:ital,opsz,wght@1,6..72,300&family=Geist+Mono:wght@400;500;600&family=Geist:wght@300;400;500;600&display=swap');

*,*::before,*::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --paper: #F4F0EA; --bone: #EEE9DD; --bone2: #E4DDCC;
  --ink: #1A1814; --ink2: #3A362F; --ink3: #5C564C; --muted: #78716A;
  --rule: rgba(26,24,20,.10); --ruleh: rgba(26,24,20,.22);
  --green: #2D6E4E; --amber: #8B6200;
  --d: 'Bricolage Grotesque', sans-serif;
  --s: 'Newsreader', serif;
  --g: 'Geist', sans-serif;
  --m: 'Geist Mono', monospace;
}
html, body, #root { height: 100%; background: var(--paper); }
* { -webkit-font-smoothing: antialiased; }
::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-thumb { background: var(--ruleh); }

.row {
  display: grid;
  grid-template-columns: 1fr 180px 130px 80px;
  align-items: center;
  gap: 0 24px;
  padding: 14px 28px;
  border-bottom: 1px solid var(--rule);
  cursor: pointer;
  transition: background .1s;
}
.row:hover { background: rgba(26,24,20,.025); }
.row:last-child { border-bottom: none; }

.new-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 18px;
  background: var(--ink); color: var(--paper);
  border: none; cursor: pointer;
  font-family: var(--m); font-size: 10px; font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase;
  transition: opacity .1s;
}
.new-btn:hover { opacity: .85; }

.k { font-family: var(--m); font-size: 10px; font-weight: 500; letter-spacing: .16em; text-transform: uppercase; color: var(--muted); }

/* Modal overlay */
.overlay {
  position: fixed; inset: 0;
  background: rgba(26,24,20,.55);
  backdrop-filter: blur(5px);
  display: flex; align-items: center; justify-content: center;
  z-index: 100; padding: 24px;
  animation: fadeIn .15s ease;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
`;

function ProgressBar({ value }) {
  return (
    <div style={{ position:"relative", height:"3px", background:"var(--ruleh)", borderRadius:"0" }}>
      <div style={{ position:"absolute", left:0, top:0, height:"100%", width:(value*100)+"%", background:"var(--ink)", transition:"width .3s" }}/>
    </div>
  );
}

function ActiveRow({ m, onOpen }) {
  return (
    <div className="row" onClick={() => onOpen(m.id)}>
      <div>
        <div style={{ fontFamily:"var(--d)", fontSize:"16px", fontWeight:600, letterSpacing:"-.02em", color:"var(--ink)", marginBottom:"2px" }}>
          {m.name}
        </div>
        <div style={{ fontFamily:"var(--m)", fontSize:"9.5px", color:"var(--muted)" }}>{m.client}</div>
      </div>
      <div style={{ fontFamily:"var(--m)", fontSize:"9.5px", color:"var(--ink3)" }}>{m.type}</div>
      <div>
        <div style={{ fontFamily:"var(--m)", fontSize:"9px", color:"var(--muted)", marginBottom:"5px" }}>
          {m.checkpoint}
        </div>
        <ProgressBar value={m.progress}/>
      </div>
      <div style={{ display:"flex", alignItems:"center", gap:"5px", justifyContent:"flex-end" }}>
        <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:600, letterSpacing:".1em", textTransform:"uppercase", color:"var(--green)" }}>
          Active
        </span>
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" style={{ color:"var(--muted)" }}>
          <path d="M2.5 6.5h8M7.5 3.5l3 3-3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
    </div>
  );
}

function PastRow({ m }) {
  const outcomeColor = m.outcome === "Invest" ? "var(--green)" : m.outcome === "Pass" ? "var(--muted)" : "var(--amber)";
  return (
    <div className="row" style={{ opacity:.7 }}>
      <div>
        <div style={{ fontFamily:"var(--d)", fontSize:"15px", fontWeight:500, letterSpacing:"-.01em", color:"var(--ink2)", marginBottom:"2px" }}>
          {m.name}
        </div>
        <div style={{ fontFamily:"var(--m)", fontSize:"9.5px", color:"var(--muted)" }}>{m.client}</div>
      </div>
      <div style={{ fontFamily:"var(--m)", fontSize:"9.5px", color:"var(--ink3)" }}>{m.type}</div>
      <div style={{ fontFamily:"var(--m)", fontSize:"9px", color:"var(--muted)" }}>{m.date}</div>
      <div style={{ textAlign:"right" }}>
        <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:600, letterSpacing:".1em", textTransform:"uppercase", color:outcomeColor }}>
          {m.outcome}
        </span>
      </div>
    </div>
  );
}

// ── Inline onboarding modal (simplified from MissionOnboarding.jsx) ──────────

const TEMPLATES = [
  { id:"cdd",     name:"Commercial Due Diligence", desc:"From teaser to IC memo.", active:true  },
  { id:"redteam", name:"Red-team Review",          desc:"Stress-test a thesis.",   active:false },
  { id:"strategy",name:"Strategy",                 desc:"Positioning & options.",   active:false },
  { id:"board",   name:"Board Preparation",        desc:"IC-grade board pack.",     active:false },
];

function NewMissionModal({ onClose, onCreateMission }) {
  const [step, setStep] = useState(0);
  const [tpl, setTpl] = useState("cdd");
  const [client, setClient] = useState("");
  const [target, setTarget] = useState("");
  const [file, setFile] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const canNext = step === 0 ? !!tpl : client && target;

  const inp = {
    width:"100%", padding:"10px 12px",
    border:"1px solid rgba(26,24,20,.12)", borderRadius:"6px",
    background:"var(--bone)", fontFamily:"var(--g)", fontSize:"14px",
    color:"var(--ink)", outline:"none",
  };

  const handleSubmit = async () => {
    if (!canNext) return;
    setIsSubmitting(true);
    setError("");
    try {
      await onCreateMission({
        client,
        target,
        template: tpl,
        fileAttached: Boolean(file),
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend offline");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background:"var(--paper)", border:"1px solid var(--ruleh)",
        borderRadius:"14px", width:"100%", maxWidth:"620px",
        maxHeight:"96vh", overflowY:"auto",
        boxShadow:"0 32px 80px rgba(26,24,20,.22)",
        fontFamily:"var(--g)", color:"var(--ink)",
      }}>
        {/* Header */}
        <div style={{ padding:"18px 24px 14px", borderBottom:"1px solid var(--rule)", display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div style={{ display:"flex", alignItems:"center", gap:"12px" }}>
            <span style={{ fontFamily:"var(--d)", fontSize:"16px", fontWeight:700, letterSpacing:"-.02em" }}>New mission</span>
            <div style={{ display:"flex", gap:"5px" }}>
              {[0,1].map(i => (
                <div key={i} style={{ height:"6px", borderRadius:"3px", transition:"all .2s",
                  width: i===step ? "20px" : "6px",
                  background: i===step ? "var(--ink)" : i<step ? "var(--ink3)" : "var(--rule)" }}/>
              ))}
            </div>
          </div>
          <button onClick={onClose} style={{ background:"none", border:"none", cursor:"pointer", color:"var(--muted)", display:"flex" }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Body */}
        <div style={{ padding:"22px 24px 20px" }}>
          {step === 0 ? (
            <>
              <div style={{ marginBottom:"16px" }}>
                <div style={{ fontFamily:"var(--m)", fontSize:"9.5px", fontWeight:600, letterSpacing:".12em", textTransform:"uppercase", color:"var(--muted)", marginBottom:"5px" }}>
                  Step 1 of 2
                </div>
                <h2 style={{ fontFamily:"var(--d)", fontSize:"21px", fontWeight:700, letterSpacing:"-.025em", marginBottom:"4px" }}>
                  What kind of mission?
                </h2>
                <p style={{ fontSize:"13.5px", color:"var(--ink3)", lineHeight:1.5 }}>
                  Each type activates the right set of agents and checkpoints.
                </p>
              </div>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"8px" }}>
                {TEMPLATES.map(t => {
                  const sel = tpl === t.id;
                  return (
                    <div key={t.id}
                      onClick={() => t.active && setTpl(t.id)}
                      style={{
                        padding:"14px", borderRadius:"10px",
                        border:"1.5px solid " + (sel ? "var(--ink)" : "var(--rule)"),
                        background: sel ? "var(--ink)" : "var(--bone)",
                        cursor: t.active ? "pointer" : "default",
                        opacity: !t.active ? 0.4 : 1,
                        transition:"all .15s", position:"relative",
                      }}>
                      {!t.active && (
                        <div style={{ position:"absolute", top:"10px", right:"10px", fontFamily:"var(--m)", fontSize:"8px", fontWeight:600, letterSpacing:".08em", textTransform:"uppercase", color:"var(--muted)", background:"var(--bone2)", padding:"2px 6px", borderRadius:"4px", border:"1px solid var(--rule)" }}>
                          In development
                        </div>
                      )}
                      <div style={{ fontFamily:"var(--d)", fontSize:"14px", fontWeight:700, letterSpacing:"-.01em", color: sel ? "var(--paper)" : "var(--ink)", marginBottom:"4px" }}>{t.name}</div>
                      <div style={{ fontSize:"12px", lineHeight:1.45, color: sel ? "rgba(244,240,234,.6)" : "var(--ink3)" }}>{t.desc}</div>
                    </div>
                  );
                })}
                {/* Suggest tile */}
                <div style={{ padding:"14px", borderRadius:"10px", border:"1.5px dashed var(--rule)", opacity:0.55, display:"flex", flexDirection:"column", justifyContent:"center" }}>
                  <div style={{ fontFamily:"var(--d)", fontSize:"13px", fontWeight:600, color:"var(--ink3)", marginBottom:"6px" }}>More types to come</div>
                  <a href="mailto:hello@h-ai.co" style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:600, letterSpacing:".08em", textTransform:"uppercase", color:"var(--ink3)", textDecoration:"none" }}>Suggest a type →</a>
                </div>
              </div>
            </>
          ) : (
            <>
              <div style={{ marginBottom:"24px" }}>
                <div style={{ fontFamily:"var(--m)", fontSize:"9.5px", fontWeight:600, letterSpacing:".12em", textTransform:"uppercase", color:"var(--muted)", marginBottom:"5px" }}>
                  Step 2 of 2
                </div>
                <h2 style={{ fontFamily:"var(--d)", fontSize:"21px", fontWeight:700, letterSpacing:"-.025em", marginBottom:"4px" }}>
                  Name the mission
                </h2>
                <p style={{ fontSize:"13.5px", color:"var(--ink3)", lineHeight:1.55 }}>
                  That's all MARVIN needs. Once you're in, it will ask for the brief.
                </p>
              </div>
              <div style={{ display:"flex", flexDirection:"column", gap:"16px" }}>
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"12px" }}>
                  <div>
                    <label style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:600, letterSpacing:".1em", textTransform:"uppercase", color:"var(--ink3)", display:"block", marginBottom:"6px" }}>Client</label>
                    <input style={inp} placeholder="e.g. Meridian Capital" value={client} onChange={e => setClient(e.target.value)} autoFocus/>
                  </div>
                  <div>
                    <label style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:600, letterSpacing:".1em", textTransform:"uppercase", color:"var(--ink3)", display:"block", marginBottom:"6px" }}>Target / company</label>
                    <input style={inp} placeholder="e.g. NovaSec" value={target} onChange={e => setTarget(e.target.value)}/>
                  </div>
                </div>

                {/* Upload */}
                <div>
                  <label style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:600, letterSpacing:".1em", textTransform:"uppercase", color:"var(--ink3)", display:"flex", alignItems:"center", gap:"6px", marginBottom:"6px" }}>
                    Starting material
                    <span style={{ fontFamily:"var(--m)", fontSize:"8.5px", fontWeight:400, color:"var(--muted)", textTransform:"none", letterSpacing:".04em" }}>— optional</span>
                  </label>
                  <label style={{ display:"flex", alignItems:"center", gap:"12px", padding:"12px 14px", border:"1.5px dashed " + (file ? "var(--ruleh)" : "var(--rule)"), borderRadius:"8px", background: file ? "var(--bone)" : "transparent", cursor:"pointer" }}>
                    <input type="file" accept=".pdf,.docx,.pptx,.xlsx" style={{ display:"none" }} onChange={e => setFile(e.target.files[0] || null)}/>
                    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" style={{ flexShrink:0, color:"var(--ink3)" }}>
                      <path d="M4 12.5h8M8 2.5v7M5.5 5L8 2.5 10.5 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span style={{ fontSize:"13px", color: file ? "var(--ink)" : "var(--ink3)", fontWeight: file ? 500 : 400 }}>
                      {file ? file.name : "Teaser, CIM, data room index, or notes"}
                    </span>
                    {file && (
                      <button onClick={e => { e.preventDefault(); setFile(null); }} style={{ marginLeft:"auto", background:"none", border:"none", cursor:"pointer", color:"var(--muted)", display:"flex", flexShrink:0 }}>
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1.5 1.5l9 9M10.5 1.5l-9 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
                      </button>
                    )}
                  </label>
                </div>

                {/* Mission preview */}
                {client && target && (
                  <div style={{ padding:"12px 14px", background:"var(--ink)", borderRadius:"8px", display:"flex", alignItems:"center", justifyContent:"space-between" }}>
                    <div>
                      <div style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:600, letterSpacing:".1em", textTransform:"uppercase", color:"rgba(244,240,234,.4)", marginBottom:"3px" }}>
                        {TEMPLATES.find(t => t.id === tpl)?.name}
                      </div>
                      <div style={{ fontFamily:"var(--d)", fontSize:"15px", fontWeight:600, color:"var(--paper)", letterSpacing:"-.01em" }}>
                        {target} — {client}
                      </div>
                    </div>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ color:"rgba(244,240,234,.3)", flexShrink:0 }}>
                      <path d="M2.5 8h11M9.5 3.5l5 4.5-5 4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding:"12px 24px", borderTop:"1px solid var(--rule)", display:"flex", alignItems:"center", justifyContent:"space-between", background:"var(--bone)", borderRadius:"0 0 14px 14px" }}>
          <div>
            {step > 0 && (
              <button onClick={() => setStep(0)} style={{ display:"inline-flex", alignItems:"center", gap:"7px", padding:"10px 18px", background:"transparent", color:"var(--ink2)", border:"1px solid var(--ruleh)", borderRadius:"8px", fontFamily:"var(--g)", fontSize:"13.5px", fontWeight:500, cursor:"pointer" }}>
                ← Back
              </button>
            )}
            {error && (
              <div style={{ marginTop:"8px", fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".06em", color:"var(--amber)" }}>
                {error}
              </div>
            )}
          </div>
          <button
            onClick={() => canNext && (step === 0 ? setStep(1) : handleSubmit())}
            disabled={isSubmitting}
            style={{ display:"inline-flex", alignItems:"center", gap:"7px", padding:"10px 20px", background:"var(--ink)", color:"var(--paper)", border:"none", borderRadius:"8px", fontFamily:"var(--g)", fontSize:"13.5px", fontWeight:600, cursor: canNext && !isSubmitting ? "pointer" : "default", opacity: canNext ? 1 : 0.38, transition:"opacity .15s" }}>
            {step === 0 ? "Continue →" : isSubmitting ? "Opening..." : "Open mission →"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main dashboard ────────────────────────────────────────────────────────────
export default function MissionDashboard({
  activeMissions = [],
  completedMissions = [],
  onOpenMission = () => {},
  onCreateMission = () => {},
  backendNotice,
}) {
  const [showNew, setShowNew] = useState(false);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("new") === "1") {
      setShowNew(true);
    }
  }, []);
  const today = new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });

  return (
    <>
      <style>{CSS}</style>
      <div style={{ minHeight:"100vh", background:"var(--paper)", fontFamily:"var(--g)", color:"var(--ink)" }}>

        {/* Top nav */}
        <div style={{ height:"52px", borderBottom:"1px solid var(--ruleh)", display:"flex", alignItems:"center", justifyContent:"space-between", padding:"0 28px" }}>
          <a href="/" style={{ display:"flex", flexDirection:"column", gap:"1px", textDecoration:"none", color:"inherit" }}>
              <span style={{ fontFamily:"var(--d)", fontSize:"16px", fontWeight:700, letterSpacing:"-.02em", lineHeight:1 }}>MARVIN</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:500, letterSpacing:".12em", textTransform:"uppercase", color:"var(--muted)" }}>
                by H<em style={{ fontFamily:"var(--s)", fontStyle:"italic", fontWeight:300, textTransform:"none", letterSpacing:"-.01em" }}>&amp;ai</em>
              </span>
            </a>
          <div style={{ display:"flex", alignItems:"center", gap:"20px" }}>
            <span style={{ fontFamily:"var(--m)", fontSize:"9.5px", color:"var(--muted)" }}>{today}</span>
            <div style={{ width:"28px", height:"28px", borderRadius:"50%", background:"var(--ink)", display:"grid", placeItems:"center" }}>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:700, color:"var(--paper)" }}>K</span>
            </div>
          </div>
        </div>

        {/* Page content */}
        <div style={{ maxWidth:"900px", margin:"0 auto", padding:"48px 28px 80px" }}>

          {/* Page header */}
          <div style={{ display:"flex", alignItems:"flex-end", justifyContent:"space-between", marginBottom:"48px" }}>
            <div>
              <div style={{ fontFamily:"var(--m)", fontSize:"10px", fontWeight:500, letterSpacing:".16em", textTransform:"uppercase", color:"var(--muted)", marginBottom:"8px" }}>
                Missions
              </div>
              <h1 style={{ fontFamily:"var(--d)", fontSize:"32px", fontWeight:700, letterSpacing:"-.035em", lineHeight:1, color:"var(--ink)" }}>
                Good morning, Karim.
              </h1>
            </div>
            <button className="new-btn" onClick={() => setShowNew(true)}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
              New mission
            </button>
          </div>

          {backendNotice && (
            <div style={{ marginBottom:"24px", padding:"12px 14px", border:"1px solid var(--ruleh)", background:"var(--bone)", fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".08em", textTransform:"uppercase", color:"var(--ink3)" }}>
              {backendNotice}
            </div>
          )}

          {/* Active missions */}
          <div style={{ marginBottom:"48px" }}>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 180px 130px 80px", gap:"0 24px", padding:"0 28px 10px", borderBottom:"1px solid var(--ink)" }}>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:700, letterSpacing:".18em", textTransform:"uppercase", color:"var(--ink)" }}>Active</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)" }}>Type</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)" }}>Next checkpoint</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)", textAlign:"right" }}>Status</span>
            </div>
            <div style={{ background:"var(--paper)", border:"1px solid var(--rule)", borderTop:"none" }}>
              {activeMissions.length > 0 ? activeMissions.map(m => <ActiveRow key={m.id} m={m} onOpen={onOpenMission}/>) : (
                <div style={{ padding:"18px 28px", fontFamily:"var(--g)", fontSize:"13px", color:"var(--ink3)" }}>
                  No active missions yet.
                </div>
              )}
            </div>
          </div>

          {/* Past missions */}
          <div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 180px 130px 80px", gap:"0 24px", padding:"0 28px 10px", borderBottom:"1px solid var(--ink)" }}>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:700, letterSpacing:".18em", textTransform:"uppercase", color:"var(--ink)" }}>Completed</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)" }}>Type</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)" }}>Date</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)", textAlign:"right" }}>Outcome</span>
            </div>
            <div style={{ background:"var(--paper)", border:"1px solid var(--rule)", borderTop:"none" }}>
              {completedMissions.length > 0 ? completedMissions.map(m => <PastRow key={m.id} m={m}/>) : (
                <div style={{ padding:"18px 28px", fontFamily:"var(--g)", fontSize:"13px", color:"var(--ink3)" }}>
                  No completed missions yet.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* New mission modal */}
        {showNew && <NewMissionModal onClose={() => setShowNew(false)} onCreateMission={onCreateMission}/>}
      </div>
    </>
  );
}
