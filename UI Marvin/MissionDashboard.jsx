import React, { useState, useEffect } from "react";

const CSS = `
.mission-dashboard { min-height: 100svh; background: var(--paper); color: var(--ink); font-family: var(--g); }
.mission-dashboard *, .mission-dashboard *::before, .mission-dashboard *::after { box-sizing: border-box; }
.mission-dashboard a { color: inherit; text-decoration: none; }
.mission-dashboard button, .mission-dashboard input { font: inherit; }
.mission-dashboard button:focus-visible, .mission-dashboard a:focus-visible,
.mission-dashboard input:focus-visible, .mission-dashboard [tabindex]:focus-visible {
  outline: 2px solid var(--ink3); outline-offset: 4px;
}
.mission-dashboard .row {
  display: grid; grid-template-columns: minmax(0,1fr) 180px 130px 100px;
  align-items: center; gap: 12px 24px; padding: 18px 24px;
  border-bottom: 1px solid var(--rule); cursor: pointer; transition: background .1s;
}
.mission-dashboard .row > div { min-width: 0; overflow-wrap: anywhere; }
.mission-dashboard .row:hover { background: var(--bone); }
.mission-dashboard .row:last-child { border-bottom: none; }
.mission-dashboard .new-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  min-height: 46px; padding: 11px 18px; background: var(--ink); color: var(--paper);
  border: none; border-radius: 5px; cursor: pointer; font-family: var(--g); font-size: 13px; font-weight: 500;
  transition: opacity .1s;
}
.mission-dashboard .new-btn:hover { opacity: .85; }
.mission-dashboard .list-heading { display:grid; grid-template-columns:minmax(0,1fr) 180px 130px 100px; gap:0 24px; padding:0 24px 12px; border-bottom:1px solid var(--ruleh); }
.mission-dashboard .overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.7); backdrop-filter: blur(5px);
  display: flex; align-items: center; justify-content: center; z-index: 100; padding: 24px;
  animation: missionFadeIn .15s ease;
}
.mission-dashboard .mission-modal { width:100%; max-width:620px; max-height:calc(100svh - 48px); overflow-y:auto; }
.mission-dashboard .mission-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.mission-dashboard .mission-fields { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.mission-dashboard .template-tile { text-align:left; color:var(--ink); font-family:var(--g); }
.mission-dashboard .template-tile:disabled { cursor:default; }
.mission-dashboard .modal-footer { gap:12px; flex-wrap:wrap; }
.mission-dashboard .modal-footer > button { min-height:44px; margin-left:auto; }
.mission-dashboard .mission-delete { opacity: .55; min-width:44px; min-height:44px; justify-content:center; align-items:center; }
.mission-dashboard .mission-delete:hover, .mission-dashboard .mission-delete:focus-visible { opacity:1; }
@keyframes missionFadeIn { from { opacity: 0; } to { opacity: 1; } }
@media(max-width:700px) {
  .mission-dashboard .row { grid-template-columns:minmax(0,1fr) auto; padding:18px 16px; gap:12px 18px; }
  .mission-dashboard .row > div:first-child { grid-column:1; }
  .mission-dashboard .row > div:nth-child(2) { grid-column:1; grid-row:2; }
  .mission-dashboard .row > div:nth-child(3) { grid-column:1; grid-row:3; }
  .mission-dashboard .row > div:last-child { grid-column:2; grid-row:1 / 4; }
  .mission-dashboard .row [data-label]::before { content:attr(data-label) ": "; color:var(--muted); font-family:var(--g); font-size:11px; }
  .mission-dashboard .list-heading { display:block; padding:0 16px 12px; }
  .mission-dashboard .list-heading > span:not(:first-child) { display:none; }
  .mission-dashboard .dashboard-content { padding:36px 20px 56px!important; }
  .mission-dashboard .dashboard-nav { padding:0 20px!important; }
  .mission-dashboard .overlay { padding:12px; }
  .mission-dashboard .mission-modal { max-height:calc(100svh - 24px); }
  .mission-dashboard .mission-grid, .mission-dashboard .mission-fields { grid-template-columns:minmax(0,1fr); }
}
@media(prefers-reduced-motion:reduce) { .mission-dashboard *, .mission-dashboard *::before { animation:none!important; transition:none!important; } }
`;

const VIEWER_NAME_KEY = "marvin.viewer-name";

function ProgressBar({ value }) {
  return (
    <div style={{ position:"relative", height:"3px", background:"var(--ruleh)", borderRadius:"0" }}>
      <div style={{ position:"absolute", left:0, top:0, height:"100%", width:(value*100)+"%", background:"var(--ink)", transition:"width .3s" }}/>
    </div>
  );
}

function ActiveRow({ m, onOpen, onDelete }) {
  return (
    <div
      className="row"
      onClick={() => onOpen(m.id)}
    >
      <div>
        <div style={{ fontFamily:"var(--d)", fontSize:"20px", fontWeight:400, letterSpacing:"-.02em", color:"var(--ink)", marginBottom:"2px" }}>
          {m.name}
        </div>
        <div style={{ fontFamily:"var(--m)", fontSize:"9.5px", color:"var(--muted)" }}>{m.client}</div>
      </div>
      <div data-label="Type" style={{ fontFamily:"var(--m)", fontSize:"11px", color:"var(--ink3)" }}>{m.type}</div>
      <div>
        <div data-label="Next checkpoint" style={{ fontFamily:"var(--m)", fontSize:"11px", color:"var(--muted)", marginBottom:"5px" }}>
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
        {onDelete && (
          <button className="mission-delete" aria-label={"Delete " + m.name}
            onClick={e => { e.stopPropagation(); onDelete(m.id); }}
            style={{
              background:"none", border:"none", cursor:"pointer",
              color:"var(--muted)", display:"flex", padding:"2px", marginLeft:4,
              transition:"opacity .1s",
            }}
            title="Delete mission"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M1.5 1.5l9 9M10.5 1.5l-9 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

function PastRow({ m, onDelete }) {
  const outcomeColor = m.outcome === "Invest" ? "var(--green)" : m.outcome === "Pass" ? "var(--muted)" : "var(--amber)";
  return (
    <div
      className="row"
      style={{ opacity:.7 }}
    >
      <div>
        <div style={{ fontFamily:"var(--d)", fontSize:"20px", fontWeight:400, letterSpacing:"-.01em", color:"var(--ink2)", marginBottom:"2px" }}>
          {m.name}
        </div>
        <div style={{ fontFamily:"var(--m)", fontSize:"9.5px", color:"var(--muted)" }}>{m.client}</div>
      </div>
      <div data-label="Type" style={{ fontFamily:"var(--m)", fontSize:"11px", color:"var(--ink3)" }}>{m.type}</div>
      <div data-label="Date" style={{ fontFamily:"var(--m)", fontSize:"11px", color:"var(--muted)" }}>{m.date}</div>
      <div style={{ textAlign:"right", display:"flex", alignItems:"center", justifyContent:"flex-end", gap:"6px" }}>
        <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:600, letterSpacing:".1em", textTransform:"uppercase", color:outcomeColor }}>
          {m.outcome}
        </span>
        {onDelete && (
          <button className="mission-delete" aria-label={"Delete " + m.name}
            onClick={e => { e.stopPropagation(); onDelete(m.id); }}
            style={{
              background:"none", border:"none", cursor:"pointer",
              color:"var(--muted)", display:"flex", padding:"2px",
              transition:"opacity .1s",
            }}
            title="Delete mission"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M1.5 1.5l9 9M10.5 1.5l-9 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
          </button>
        )}
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
    border:"1px solid var(--ruleh)", borderRadius:"6px",
    background:"var(--bone)", fontFamily:"var(--g)", fontSize:"16px",
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
      <div className="mission-modal" role="dialog" aria-modal="true" aria-label="New mission" style={{
        background:"var(--bone)", border:"1px solid var(--ruleh)",
        borderRadius:"14px", width:"100%", maxWidth:"620px",
        boxShadow:"0 32px 80px rgba(0,0,0,.35)",
        fontFamily:"var(--g)", color:"var(--ink)",
      }}>
        {/* Header */}
        <div style={{ padding:"18px 24px 14px", borderBottom:"1px solid var(--rule)", display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div style={{ display:"flex", alignItems:"center", gap:"12px" }}>
            <span style={{ fontFamily:"var(--d)", fontSize:"22px", fontWeight:400, letterSpacing:"-.02em" }}>New mission</span>
            <div role="img" aria-label={`Step ${step + 1} of 2`} style={{ display:"flex", gap:"5px" }}>
              {[0,1].map(i => (
                <div key={i} style={{ height:"6px", borderRadius:"3px", transition:"all .2s",
                  width: i===step ? "20px" : "6px",
                  background: i===step ? "var(--ink)" : i<step ? "var(--ink3)" : "var(--rule)" }}/>
              ))}
            </div>
          </div>
          <button aria-label="Close new mission" onClick={onClose} style={{ background:"none", border:"none", cursor:"pointer", color:"var(--muted)", display:"flex", alignItems:"center", justifyContent:"center", minWidth:"44px", minHeight:"44px" }}>
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
                <h2 style={{ fontFamily:"var(--d)", fontSize:"28px", fontWeight:400, letterSpacing:"-.025em", marginBottom:"4px" }}>
                  What kind of mission?
                </h2>
                <p style={{ fontSize:"13.5px", color:"var(--ink3)", lineHeight:1.5 }}>
                  Each type activates the right set of agents and checkpoints.
                </p>
              </div>
              <div className="mission-grid">
                {TEMPLATES.map(t => {
                  const sel = tpl === t.id;
                  return (
                    <button type="button" className="template-tile" key={t.id} disabled={!t.active} aria-pressed={sel}
                      onClick={() => t.active && setTpl(t.id)}
                      style={{
                        padding:"14px", borderRadius:"10px",
                        border:"1.5px solid " + (sel ? "var(--ink)" : "var(--rule)"),
                        background: sel ? "var(--bone2)" : "var(--bone)",
                        cursor: t.active ? "pointer" : "default",
                        opacity: 1,
                        transition:"all .15s", position:"relative",
                      }}>
                      {!t.active && (
                        <div style={{ display:"inline-block", marginBottom:"10px", fontFamily:"var(--m)", fontSize:"8px", fontWeight:600, letterSpacing:".08em", textTransform:"uppercase", color:"var(--muted)", background:"var(--bone2)", padding:"2px 6px", borderRadius:"4px", border:"1px solid var(--rule)" }}>
                          In development
                        </div>
                      )}
                      <div style={{ fontFamily:"var(--d)", fontSize:"20px", fontWeight:400, letterSpacing:"-.01em", color:"var(--ink)", marginBottom:"4px" }}>{t.name}</div>
                      <div style={{ fontSize:"12px", lineHeight:1.45, color:"var(--ink3)" }}>{t.desc}</div>
                    </button>
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
                <h2 style={{ fontFamily:"var(--d)", fontSize:"28px", fontWeight:400, letterSpacing:"-.025em", marginBottom:"4px" }}>
                  Name the mission
                </h2>
                <p style={{ fontSize:"13.5px", color:"var(--ink3)", lineHeight:1.55 }}>
                  That's all MARVIN needs. Once you're in, it will ask for the brief.
                </p>
              </div>
              <div style={{ display:"flex", flexDirection:"column", gap:"16px" }}>
                <div className="mission-fields">
                  <div>
                    <label htmlFor="mission-client" style={{ fontFamily:"var(--g)", fontSize:"13px", fontWeight:500, color:"var(--ink2)", display:"block", marginBottom:"8px" }}>Client</label>
                    <input id="mission-client" style={inp} placeholder="e.g. Meridian Capital" value={client} onChange={e => setClient(e.target.value)} autoFocus/>
                  </div>
                  <div>
                    <label htmlFor="mission-target" style={{ fontFamily:"var(--g)", fontSize:"13px", fontWeight:500, color:"var(--ink2)", display:"block", marginBottom:"8px" }}>Target / company</label>
                    <input id="mission-target" style={inp} placeholder="e.g. NovaSec" value={target} onChange={e => setTarget(e.target.value)}/>
                  </div>
                </div>

                {/* Upload */}
                <div>
                  <label style={{ fontFamily:"var(--g)", fontSize:"13px", fontWeight:500, color:"var(--ink2)", display:"flex", alignItems:"center", gap:"6px", marginBottom:"8px" }}>
                    Starting material
                    <span style={{ fontFamily:"var(--m)", fontSize:"12px", fontWeight:400, color:"var(--muted)", textTransform:"none", letterSpacing:".04em" }}>— optional</span>
                  </label>
                  <label style={{ display:"flex", alignItems:"center", gap:"12px", padding:"12px 14px", border:"1.5px dashed " + (file ? "var(--ruleh)" : "var(--rule)"), borderRadius:"8px", background: file ? "var(--bone)" : "transparent", cursor:"pointer" }}>
                    <input type="file" accept=".pdf,.docx,.pptx,.xlsx" style={{ display:"none" }} onChange={e => setFile(e.target.files[0] || null)}/>
                    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" style={{ flexShrink:0, color:"var(--ink3)" }}>
                      <path d="M4 12.5h8M8 2.5v7M5.5 5L8 2.5 10.5 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span style={{ minWidth:0, overflowWrap:"anywhere", fontSize:"13px", color: file ? "var(--ink)" : "var(--ink3)", fontWeight: file ? 500 : 400 }}>
                      {file ? file.name : "Teaser, CIM, data room index, or notes"}
                    </span>
                    {file && (
                      <button aria-label="Remove attachment" onClick={e => { e.preventDefault(); setFile(null); }} style={{ marginLeft:"auto", background:"none", border:"none", cursor:"pointer", color:"var(--muted)", display:"flex", flexShrink:0 }}>
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1.5 1.5l9 9M10.5 1.5l-9 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
                      </button>
                    )}
                  </label>
                </div>

                {/* Mission preview */}
                {client && target && (
                  <div style={{ padding:"12px 14px", background:"var(--bone2)", borderRadius:"8px", display:"flex", alignItems:"center", justifyContent:"space-between", gap:"16px", overflowWrap:"anywhere" }}>
                    <div>
                      <div style={{ fontFamily:"var(--d)", fontSize:"19px", fontWeight:400, color:"var(--ink)", letterSpacing:"-.01em" }}>
                        {target} — {client}
                      </div>
                      <div style={{ fontFamily:"var(--g)", fontSize:"12px", color:"var(--muted)", marginTop:"5px" }}>
                        {TEMPLATES.find(t => t.id === tpl)?.name}
                      </div>
                    </div>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ color:"var(--muted)", flexShrink:0 }}>
                      <path d="M2.5 8h11M9.5 3.5l5 4.5-5 4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="modal-footer" style={{ padding:"12px 24px", borderTop:"1px solid var(--rule)", display:"flex", alignItems:"center", justifyContent:"space-between", background:"var(--bone)", borderRadius:"0 0 14px 14px" }}>
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
  onDeleteMission = () => {},
  backendNotice,
}) {
  const [showNew, setShowNew] = useState(false);
  const [viewerName, setViewerName] = useState("");
  const [nameDraft, setNameDraft] = useState("");
  const [profileReady, setProfileReady] = useState(false);
  useEffect(() => {
    try {
      setViewerName((localStorage.getItem(VIEWER_NAME_KEY) || "").trim().slice(0, 80));
    } catch {
      // The name still works for this visit when browser storage is unavailable.
    }
    setProfileReady(true);
  }, []);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("new") === "1") {
      setShowNew(true);
    }
  }, []);
  const today = new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });

  function saveName(event) {
    event.preventDefault();
    const name = nameDraft.trim().replace(/\s+/g, " ").slice(0, 80);
    if (!name) return;
    try {
      localStorage.setItem(VIEWER_NAME_KEY, name);
    } catch {
      // Do not block access when browser storage is unavailable.
    }
    setViewerName(name);
  }

  function changeName() {
    try {
      localStorage.removeItem(VIEWER_NAME_KEY);
    } catch {
      // Editing remains available when browser storage is unavailable.
    }
    setNameDraft(viewerName);
    setViewerName("");
  }

  if (!profileReady || !viewerName) {
    return (
      <>
        <style>{CSS}</style>
        <div className="mission-dashboard">
          <nav className="dashboard-nav" style={{ height:"72px", borderBottom:"1px solid var(--ruleh)", display:"flex", alignItems:"center", padding:"0 28px" }}>
            <a href="/" style={{ fontFamily:"var(--d)", fontSize:"22px", fontWeight:400, letterSpacing:"-.02em" }}>MARVIN <span style={{ fontFamily:"var(--g)", fontSize:"12px", fontWeight:400 }}>by H&amp;ai</span></a>
          </nav>
          {profileReady && (
            <main style={{ maxWidth:"480px", margin:"0 auto", padding:"clamp(48px, 14vh, 140px) 28px 48px" }}>
              <h1 style={{ fontFamily:"var(--d)", fontSize:"clamp(36px, 7vw, 48px)", fontWeight:400, letterSpacing:"-.035em", lineHeight:1.1 }}>What should we call you?</h1>
              <p style={{ marginTop:"16px", color:"var(--ink3)", fontSize:"15px", lineHeight:1.6 }}>Enter your name to personalise your workspace.</p>
              <form onSubmit={saveName} style={{ marginTop:"32px" }}>
                <label htmlFor="viewer-name" style={{ display:"block", fontSize:"14px", fontWeight:500, marginBottom:"10px" }}>Your name</label>
                <input id="viewer-name" name="given-name" autoComplete="given-name" autoFocus required maxLength={80} value={nameDraft} onChange={event => setNameDraft(event.target.value)} style={{ display:"block", width:"100%", minHeight:"48px", padding:"12px 14px", border:"1px solid var(--ruleh)", background:"var(--bone)", color:"var(--ink)", fontFamily:"var(--g)", fontSize:"16px" }}/>
                <button type="submit" className="new-btn" disabled={!nameDraft.trim()} style={{ minHeight:"44px", marginTop:"20px", opacity:nameDraft.trim() ? 1 : .4 }}>Continue →</button>
              </form>
            </main>
          )}
        </div>
      </>
    );
  }

  return (
    <>
      <style>{CSS}</style>
      <div className="mission-dashboard">

        {/* Top nav */}
        <div className="dashboard-nav" style={{ height:"72px", borderBottom:"1px solid var(--ruleh)", display:"flex", alignItems:"center", justifyContent:"space-between", padding:"0 28px" }}>
          <a href="/" style={{ display:"flex", flexDirection:"column", gap:"1px", textDecoration:"none", color:"inherit" }}>
              <span style={{ fontFamily:"var(--d)", fontSize:"22px", fontWeight:400, letterSpacing:"-.02em", lineHeight:1 }}>MARVIN</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:500, letterSpacing:".12em", textTransform:"uppercase", color:"var(--muted)" }}>
                by H<em style={{ fontFamily:"var(--s)", fontStyle:"italic", fontWeight:300, textTransform:"none", letterSpacing:"-.01em" }}>&amp;ai</em>
              </span>
            </a>
          <div style={{ display:"flex", alignItems:"center", gap:"20px" }}>
            <span style={{ fontFamily:"var(--m)", fontSize:"11px", color:"var(--muted)" }}>{today}</span>
            <button type="button" aria-label="Change name" onClick={changeName} style={{ width:"44px", height:"44px", border:0, cursor:"pointer", background:"transparent", display:"grid", placeItems:"center" }}>
              <span style={{ width:"28px", height:"28px", borderRadius:"50%", background:"var(--ink)", display:"grid", placeItems:"center", fontFamily:"var(--m)", fontSize:"10px", fontWeight:700, color:"var(--paper)" }}>{Array.from(viewerName)[0].toLocaleUpperCase()}</span>
            </button>
          </div>
        </div>

        {/* Page content */}
        <div className="dashboard-content" style={{ maxWidth:"1000px", margin:"0 auto", padding:"64px 28px 80px" }}>

          {/* Page header */}
          <div style={{ display:"flex", flexWrap:"wrap", gap:"24px", alignItems:"flex-end", justifyContent:"space-between", marginBottom:"48px" }}>
            <div style={{ flex:"1 1 250px", minWidth:0 }}>
              <h1 style={{ fontFamily:"var(--d)", fontSize:"clamp(36px, 6vw, 48px)", fontWeight:400, letterSpacing:"-.035em", lineHeight:1.1, overflowWrap:"anywhere", color:"var(--ink)" }}>
                Good morning, {viewerName}
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
            <div className="list-heading">
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:700, letterSpacing:".18em", textTransform:"uppercase", color:"var(--ink)" }}>Active</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)" }}>Type</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)" }}>Next checkpoint</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)", textAlign:"right" }}>Status</span>
            </div>
            <div style={{ background:"var(--paper)", border:"1px solid var(--rule)", borderTop:"none" }}>
              {activeMissions.length > 0 ? activeMissions.map(m => <ActiveRow key={m.id} m={m} onOpen={onOpenMission} onDelete={onDeleteMission}/>) : (
                <div style={{ padding:"18px 28px", fontFamily:"var(--g)", fontSize:"13px", color:"var(--ink3)" }}>
                  No active missions yet.
                </div>
              )}
            </div>
          </div>

          {/* Past missions */}
          <div>
            <div className="list-heading">
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", fontWeight:700, letterSpacing:".18em", textTransform:"uppercase", color:"var(--ink)" }}>Completed</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)" }}>Type</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)" }}>Date</span>
              <span style={{ fontFamily:"var(--m)", fontSize:"9px", letterSpacing:".14em", textTransform:"uppercase", color:"var(--muted)", textAlign:"right" }}>Outcome</span>
            </div>
            <div style={{ background:"var(--paper)", border:"1px solid var(--rule)", borderTop:"none" }}>
              {completedMissions.length > 0 ? completedMissions.map(m => <PastRow key={m.id} m={m} onDelete={onDeleteMission}/>) : (
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
