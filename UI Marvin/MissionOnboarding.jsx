import React, { useState } from "react";

// Shared application tokens keep onboarding aligned with the workspace.
const T = {
  paper: "var(--paper)", bone: "var(--bone)", bone2: "var(--bone2)",
  ink: "var(--ink)", ink2: "var(--ink2)", ink3: "var(--ink3)", muted: "var(--muted)",
  rule: "var(--rule)", ruleM: "var(--ruleh)",
  display: "var(--d)", mono: "var(--m)", sans: "var(--g)",
};
const CSS = `
.mission-onboarding { color:var(--ink); }
.mission-onboarding *, .mission-onboarding *::before { box-sizing:border-box; }
.mission-onboarding button:focus-visible, .mission-onboarding input:focus-visible, .mission-onboarding a:focus-visible { outline:2px solid var(--ink3); outline-offset:4px; }
.mission-onboarding .onboarding-grid { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:8px; }
.mission-onboarding .onboarding-fields { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:12px; }
.mission-onboarding .template-tile { font-family:var(--g); text-align:left; }
@media(max-width:600px) {
  .mission-onboarding { padding:12px!important; }
  .mission-onboarding .onboarding-modal { max-height:calc(100svh - 24px)!important; }
  .mission-onboarding .onboarding-grid, .mission-onboarding .onboarding-fields { grid-template-columns:minmax(0,1fr); }
}
@media(prefers-reduced-motion:reduce) { .mission-onboarding * { transition:none!important; } }
`;

const TEMPLATES = [
  {
    id: "cdd",
    name: "Commercial Due Diligence",
    desc: "From teaser to IC memo. Market, financials, competitive, expert interviews, red-team.",
    modules: ["Thesis","Dora","Calculus","Lector","Adversus","Merlin","Papyrus"],
    active: true,
  },
  {
    id: "redteam",
    name: "Red-team Review",
    desc: "Stress-test an existing investment thesis. 3 attack vectors, scenario analysis, verdict.",
    modules: ["Thesis","Adversus","Dora","Merlin","Papyrus"],
    active: false,
  },
  {
    id: "strategy",
    name: "Strategy",
    desc: "Market positioning, competitive mapping, growth options, recommendations.",
    modules: ["Thesis","Dora","Lector","Adversus","Merlin","Papyrus"],
    active: false,
  },
  {
    id: "board",
    name: "Board Preparation",
    desc: "IC-grade board pack. KPI synthesis, decision framing, executive summary.",
    modules: ["Thesis","Calculus","Merlin","Papyrus"],
    active: false,
  },
  {
    id: "meta",
    name: "Meta-agent",
    desc: "Conversational mission. 4 channels: Research, Documents, Analyse, War Room. No fixed phases.",
    modules: ["Research","Documents","Analyse","War Room"],
    active: true,
  },
];

const MORE_TILE = {
  id: "more",
  isSuggest: true,
  name: "More mission types to come",
};

const s = {
  overlay: {
    position: "fixed", inset: 0,
    background: "rgba(0,0,0,.7)",
    backdropFilter: "blur(4px)",
    display: "flex", alignItems: "center", justifyContent: "center",
    zIndex: 1000, padding: "24px",
  },
  modal: {
    background: T.bone,
    color: T.ink,
    border: "1px solid " + T.ruleM,
    borderRadius: "14px",
    width: "100%", maxWidth: "640px",
    maxHeight: "calc(100svh - 48px)",
    overflowY: "auto",
    boxShadow: "0 24px 64px rgba(0,0,0,.35)",
    fontFamily: T.sans,
  },
  header: {
    padding: "18px 24px 14px",
    borderBottom: "1px solid " + T.rule,
  },
  body: { padding: "20px 24px 18px" },
  footer: {
    padding: "12px 24px",
    borderTop: "1px solid " + T.rule,
    display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap",
    background: T.bone,
    borderRadius: "0 0 14px 14px",
  },
  label: {
    fontFamily: T.sans, fontSize: "13px", fontWeight: 500,
    color: T.ink3, display: "block", marginBottom: "6px",
  },
  input: {
    width: "100%", padding: "10px 12px",
    border: "1px solid " + T.rule,
    borderRadius: "7px",
    background: T.bone,
    fontFamily: T.sans, fontSize: "16px", color: T.ink,
    outline: "none", boxSizing: "border-box",
  },
  btnPrimary: {
    display: "inline-flex", alignItems: "center", gap: "7px",
    padding: "11px 20px", minHeight: "44px",
    background: T.ink, color: T.paper,
    border: "none", borderRadius: "8px",
    fontFamily: T.sans, fontSize: "13.5px", fontWeight: 600,
    cursor: "pointer",
  },
  btnGhost: {
    display: "inline-flex", alignItems: "center", gap: "7px",
    padding: "11px 20px", minHeight: "44px",
    background: "transparent", color: T.ink2,
    border: "1px solid " + T.ruleM, borderRadius: "8px",
    fontFamily: T.sans, fontSize: "13.5px", fontWeight: 500,
    cursor: "pointer",
  },
};

// Step indicator dots
function StepDots({ current, total }) {
  return (
    <div role="img" aria-label={`Step ${current + 1} of ${total}`} style={{ display: "flex", gap: "6px", alignItems: "center" }}>
      {Array.from({ length: total }, (_, i) => (
        <div key={i} style={{
          width: i === current ? "20px" : "6px",
          height: "6px", borderRadius: "3px",
          background: i === current ? T.ink : i < current ? T.ink3 : T.rule,
          transition: "all .2s",
        }}/>
      ))}
    </div>
  );
}

// STEP 1 — Mission type
function Step1({ value, onChange }) {
  const tiles = [...TEMPLATES, MORE_TILE];
  return (
    <div>
      <div style={{ marginBottom: "16px" }}>
        <h2 style={{ fontFamily: T.display, fontSize: "28px", fontWeight: 400, letterSpacing: "-.025em", color: T.ink, margin: "0 0 4px" }}>
          What kind of mission?
        </h2>
        <p style={{ fontSize: "13.5px", color: T.ink3, margin: 0, lineHeight: 1.5 }}>
          Each type activates the right set of agents and checkpoints.
        </p>
      </div>

      <div className="onboarding-grid">
        {tiles.map((t) => {
          if (t.isSuggest) return (
            <div key={t.id} style={{
              padding: "16px",
              border: "1.5px dashed " + T.rule,
              borderRadius: "10px",
              opacity: 0.6,
              display: "flex", flexDirection: "column", justifyContent: "center",
              minHeight: "60px",
            }}>
              <div style={{ fontFamily: T.display, fontSize: "13px", fontWeight: 600, color: T.ink3, marginBottom: "8px" }}>
                {t.name}
              </div>
              <a href="mailto:hello@h-ai.co" style={{
                fontFamily: T.mono, fontSize: "9.5px", fontWeight: 600,
                letterSpacing: ".08em", textTransform: "uppercase",
                color: T.ink3, textDecoration: "none",
              }}>
                Suggest a type →
              </a>
            </div>
          );

          const selected = value === t.id;
          return (
            <button type="button" className="template-tile" key={t.id} disabled={!t.active} aria-pressed={selected}
              onClick={() => t.active && onChange(t.id)}
              style={{
                padding: "14px",
                border: "1.5px solid " + (selected ? T.ink : T.rule),
                borderRadius: "10px",
                background: selected ? T.bone2 : T.bone,
                cursor: t.active ? "pointer" : "default",
                opacity: 1,
                transition: "all .15s",
                position: "relative",
              }}
            >
              {!t.active && (
                <div style={{
                  display: "inline-block", marginBottom: "10px",
                  fontFamily: T.mono, fontSize: "8px", fontWeight: 600,
                  letterSpacing: ".08em", textTransform: "uppercase",
                  color: T.muted, background: T.bone2,
                  padding: "2px 6px", borderRadius: "4px",
                  border: "1px solid " + T.rule,
                }}>
                  In development
                </div>
              )}
              <div style={{
                fontFamily: T.display, fontSize: "20px", fontWeight: 400,
                color: T.ink,
                marginBottom: "6px", letterSpacing: "-.01em",
              }}>
                {t.name}
              </div>
              <div style={{
                fontSize: "12px", lineHeight: 1.5,
                color: T.ink3,
                marginBottom: "0",
              }}>
                {t.desc}
              </div>

            </button>
          );
        })}
      </div>
    </div>
  );
}

// STEP 2 — Mission shell (minimal)
function Step2({ value, onChange, templateId }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value });
  const canCreate = value.client && value.target;
  const tmpl = TEMPLATES.find((t) => t.id === templateId);

  return (
    <div>
      <div style={{ marginBottom: "28px" }}>
        <h2 style={{ fontFamily: T.display, fontSize: "28px", fontWeight: 400, letterSpacing: "-.025em", color: T.ink, margin: "0 0 6px" }}>
          Name the mission
        </h2>
        <p style={{ fontSize: "13.5px", color: T.ink3, margin: 0, lineHeight: 1.55 }}>
          That's all MARVIN needs to open the mission.
          Once you're in, it will ask for the brief.
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "18px" }}>

        {/* Client + Target */}
        <div className="onboarding-fields">
          <div>
            <label htmlFor="onboarding-client" style={s.label}>Client</label>
            <input
              style={s.input}
              id="onboarding-client"
              placeholder="e.g. Meridian Capital"
              value={value.client}
              onChange={set("client")}
              autoFocus
            />
          </div>
          <div>
            <label htmlFor="onboarding-target" style={s.label}>Target / company</label>
            <input
              style={s.input}
              id="onboarding-target"
              placeholder="e.g. NovaSec"
              value={value.target}
              onChange={set("target")}
            />
          </div>
        </div>

        {/* Optional document upload */}
        <div>
          <label style={{ ...s.label, display: "flex", alignItems: "center", gap: "6px" }}>
            Starting material
            <span style={{ fontFamily: T.mono, fontSize: "12px", fontWeight: 400, color: T.muted, letterSpacing: ".06em", textTransform: "none" }}>
              — optional
            </span>
          </label>
          <label style={{
            display: "flex", alignItems: "center", gap: "12px",
            padding: "13px 14px",
            border: "1.5px dashed " + (value.file ? T.ruleM : T.rule),
            borderRadius: "9px",
            background: value.file ? T.bone : "transparent",
            cursor: "pointer", transition: "all .15s",
          }}>
            <input
              type="file"
              accept=".pdf,.docx,.pptx,.xlsx"
              style={{ display: "none" }}
              onChange={(e) => onChange({ ...value, file: e.target.files[0] || null })}
            />
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, color: T.ink3 }}>
              <path d="M4 12.5h8M8 2.5v7M5.5 5L8 2.5 10.5 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <div style={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>
              <div style={{ fontSize: "13px", fontWeight: 500, color: value.file ? T.ink : T.ink3 }}>
                {value.file ? value.file.name : "Teaser, CIM, data room index, or notes"}
              </div>
              {value.file && (
                <div style={{ fontFamily: T.mono, fontSize: "9px", color: T.muted, marginTop: "2px" }}>
                  {(value.file.size / 1024).toFixed(0)} KB
                </div>
              )}
            </div>
            {value.file && (
              <button aria-label="Remove attachment"
                onClick={(e) => { e.preventDefault(); onChange({ ...value, file: null }); }}
                style={{ background: "none", border: "none", cursor: "pointer", color: T.muted, padding: "2px", display: "flex", flexShrink: 0 }}
              >
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                  <path d="M2 2l9 9M11 2L2 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
            )}
          </label>
        </div>

        {/* Mission preview — shows when ready */}
        {canCreate && tmpl && (
          <div style={{
            padding: "12px 14px",
            background: T.bone2,
            gap: "16px", overflowWrap: "anywhere",
            borderRadius: "8px",
            display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <div>
              <div style={{ fontFamily: T.display, fontSize: "19px", fontWeight: 400, color: T.ink, letterSpacing: "-.01em" }}>
                {value.target} — {tmpl.name.replace("Commercial ", "")}
              </div>
              <div style={{ fontFamily: T.mono, fontSize: "10px", color: T.ink3, marginTop: "3px" }}>
                {value.client}
              </div>
            </div>
            <div style={{ fontFamily: T.mono, fontSize: "9px", fontWeight: 600, letterSpacing: ".1em", textTransform: "uppercase", color: T.muted }}>
              {tmpl.modules.length} agents
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ROOT
export default function MissionOnboarding({ onClose, onLaunch }) {
  const [step, setStep] = useState(0);
  const [template, setTemplate] = useState("cdd");
  const [mission, setMission] = useState({ client: "", target: "", file: null });

  const canNext = step === 0 ? !!template : mission.client && mission.target;

  const handleCreate = () => {
    onLaunch && onLaunch({
      client: mission.client,
      target: mission.target,
      template,
      fileAttached: Boolean(mission.file),
    });
    onClose && onClose();
  };

  return (
    <div className="mission-onboarding" style={s.overlay} onClick={(e) => e.target === e.currentTarget && onClose && onClose()}>
      <style>{CSS}</style>
      <div className="onboarding-modal" role="dialog" aria-modal="true" aria-label="New mission" style={s.modal}>

        {/* Header */}
        <div style={s.header}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontFamily: T.display, fontSize: "22px", fontWeight: 400, letterSpacing: "-.02em", color: T.ink }}>
                New mission
              </span>
              <StepDots current={step} total={2}/>
            </div>
            <button aria-label="Close new mission" onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: T.ink3, padding: "4px", minWidth:"44px", minHeight:"44px", justifyContent:"center", display: "flex", alignItems: "center" }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div style={s.body}>
          {step === 0 && <Step1 value={template} onChange={setTemplate}/>}
          {step === 1 && <Step2 value={mission} onChange={setMission} templateId={template}/>}
        </div>

        {/* Footer */}
        <div style={s.footer}>
          <div>
            {step > 0 && (
              <button style={s.btnGhost} onClick={() => setStep(0)}>← Back</button>
            )}
          </div>
          <div>
            {step === 0 ? (
              <button
                style={{ ...s.btnPrimary, opacity: canNext ? 1 : 0.4, cursor: canNext ? "pointer" : "default" }}
                onClick={() => canNext && setStep(1)}
              >
                Continue →
              </button>
            ) : (
              <button
                style={{ ...s.btnPrimary, opacity: canNext ? 1 : 0.4, cursor: canNext ? "pointer" : "default" }}
                onClick={() => canNext && handleCreate()}
              >
                Open mission →
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
