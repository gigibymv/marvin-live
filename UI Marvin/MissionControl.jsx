import React, { useState, useRef, useEffect } from "react";

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Newsreader:ital,opsz,wght@1,6..72,300&family=Geist+Mono:wght@400;500;600&family=Geist:wght@400;500;600&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --paper:#F4F0EA;--bone:#EEE9DD;--bone2:#E4DDCC;
  --ink:#1A1814;--ink2:#3A362F;--ink3:#5C564C;--muted:#78716A;
  --rule:rgba(26,24,20,.10);--ruleh:rgba(26,24,20,.22);
  --green:#2D6E4E;--amber:#8B6200;
  --d:'Bricolage Grotesque',sans-serif;
  --s:'Newsreader',serif;
  --g:'Geist',sans-serif;
  --m:'Geist Mono',monospace;
}
html,body,#root{height:100%}
*{-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:3px}
::-webkit-scrollbar-thumb{background:var(--ruleh)}
.k{font-family:var(--m);font-size:10px;font-weight:500;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
.tab{font-family:var(--m);font-size:10px;letter-spacing:.13em;text-transform:uppercase;padding:9px 0;margin-right:24px;background:none;border:none;border-bottom:1.5px solid transparent;color:var(--muted);cursor:pointer;white-space:nowrap;transition:color .12s,border-color .12s;flex-shrink:0}
.tab:hover{color:var(--ink2)}
.tab.on{color:var(--ink);border-bottom-color:var(--ink)}
.tab.done{color:var(--ink3)}
.ag{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--rule)}
.ag:last-child{border-bottom:none}
.dl{display:flex;align-items:baseline;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--rule)}
.dl:last-child{border-bottom:none}
.evc{padding:7px 0;border-bottom:1px solid var(--rule)}
.evc:hover{background:rgba(26,24,20,.025)}
.evc:last-child{border-bottom:none}
.msg-m{background:var(--bone)}
.msg-u{background:var(--ink)}
.send-btn{font-family:var(--m);font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;padding:10px 16px;background:var(--ink);color:var(--paper);border:none;cursor:pointer}
.send-btn:hover{opacity:.8}
textarea{font-family:var(--g);font-size:13px;color:var(--ink);background:transparent;border:none;outline:none;resize:none;line-height:1.6;width:100%}
textarea::placeholder{color:var(--muted)}
.overlay{position:fixed;inset:0;background:rgba(26,24,20,.55);backdrop-filter:blur(5px);display:flex;align-items:center;justify-content:center;z-index:100;padding:24px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes blink{0%,100%{opacity:.15}50%{opacity:1}}
`;

const CHECKPOINTS = [];

const HYP = [];

const AGENTS = [];

const WS = [
  { id: "ws1", label: "Competitive" },
  { id: "ws2", label: "Market" },
  { id: "ws3", label: "Financial" },
  { id: "ws4", label: "Risk" },
  { id: "ws5", label: "Memo" },
];

const LIVE = [];

const DONE = [];

const DELIVERABLES = [];

function Icon({ id, size }) {
  var s = size || 13;
  var paths = {
    marvin: React.createElement("text", { x: "8", y: "11", textAnchor: "middle", fontSize: "7", fill: "currentColor", fontWeight: "700" }, "M"),
    thesis: React.createElement("path", { d: "M8 3v2.5M8 10.5V13M3.8 5.8l1.8 1.8M9.4 9.4l1.8 1.8M2.5 8h2.5M11 8h2.5M3.8 10.2l1.8-1.8M9.4 6.6l1.8-1.8", stroke: "currentColor", strokeWidth: "1.1", strokeLinecap: "round" }),
    dora: React.createElement(React.Fragment, null, React.createElement("circle", { cx: "7", cy: "7", r: "4", stroke: "currentColor", strokeWidth: "1.1", fill: "none" }), React.createElement("path", { d: "M10.2 10.2L13 13", stroke: "currentColor", strokeWidth: "1.1", strokeLinecap: "round" })),
    calculus: React.createElement("path", { d: "M2 11l3-3.5 2.5 2 3-4.5L13 7", stroke: "currentColor", strokeWidth: "1.1", strokeLinecap: "round", strokeLinejoin: "round" }),
    lector: React.createElement(React.Fragment, null, React.createElement("path", { d: "M8 2.5a2.5 2.5 0 012.5 2.5v3.5a2.5 2.5 0 01-5 0V5A2.5 2.5 0 018 2.5z", stroke: "currentColor", strokeWidth: "1", fill: "none" }), React.createElement("path", { d: "M4.5 9a3.5 3.5 0 007 0", stroke: "currentColor", strokeWidth: "1", strokeLinecap: "round", fill: "none" })),
    adversus: React.createElement("path", { d: "M4 4l8 8M12 4L4 12", stroke: "currentColor", strokeWidth: "1.3", strokeLinecap: "round" }),
    merlin: React.createElement(React.Fragment, null, React.createElement("path", { d: "M8 2l6.5 12H1.5L8 2z", stroke: "currentColor", strokeWidth: "1", strokeLinejoin: "round", fill: "none" }), React.createElement("path", { d: "M5.5 10h5", stroke: "currentColor", strokeWidth: "1", strokeLinecap: "round" })),
    papyrus: React.createElement(React.Fragment, null, React.createElement("rect", { x: "3.5", y: "1.5", width: "9", height: "13", rx: "1", stroke: "currentColor", strokeWidth: "1", fill: "none" }), React.createElement("path", { d: "M5.5 5h5M5.5 7.5h5M5.5 10h3", stroke: "currentColor", strokeWidth: ".9", strokeLinecap: "round" })),
  };
  return React.createElement("svg", { width: s, height: s, viewBox: "0 0 16 16", fill: "none" }, paths[id] || null);
}

function Conf({ v }) {
  if (!v) return null;
  var color = v === "inferred" ? "var(--amber)" : v === "sourced" ? "var(--green)" : "var(--muted)";
  return React.createElement("span", {
    style: { fontFamily: "var(--m)", fontSize: "9px", letterSpacing: ".1em", textTransform: "uppercase", padding: "1px 5px", border: "1px solid " + color + "50", color: color }
  }, v);
}

// Visual taxonomy for the live rail. Each entry kind maps to a glyph + colour
// so the user can scan the feed and instantly tell a finding from a tool call
// from a phase change. Colours come from the existing palette to avoid a
// separate stylesheet.
var KIND_VISUALS = {
  finding:       { glyph: "◆", color: "var(--green)", label: "Finding" },
  milestone:     { glyph: "✓", color: "var(--ink)",   label: "Milestone" },
  deliverable:   { glyph: "▤", color: "var(--ink2)",  label: "Deliverable" },
  gate:          { glyph: "◧", color: "var(--amber)", label: "Gate" },
  phase:         { glyph: "—", color: "var(--ink3)",  label: "Phase" },
  agent:         { glyph: "●", color: "var(--ink2)",  label: "Agent" },
  agent_message: { glyph: "“", color: "var(--ink3)",  label: "Reasoning" },
  tool_call:     { glyph: "→", color: "var(--muted)", label: "Tool" },
  tool_result:   { glyph: "←", color: "var(--muted)", label: "Result" },
};

function kindVisual(kind) {
  return KIND_VISUALS[kind] || KIND_VISUALS.finding;
}

function StateTag({ state }) {
  var color = state === "running" || state === "done" ? "var(--green)" : state === "waiting" ? "var(--amber)" : "var(--muted)";
  var weight = state === "running" ? 600 : 400;
  return React.createElement("span", {
    style: { fontFamily: "var(--m)", fontSize: "9px", letterSpacing: ".1em", textTransform: "uppercase", color: color, fontWeight: weight }
  },
    state === "running" ? React.createElement("span", { style: { animation: "pulse 1.4s ease-in-out infinite", display: "inline-block", marginRight: "2px" } }, "\u25cf") : null,
    state
  );
}

// Chantier 4 CP2: rich finding card with confidence badge, hypothesis link,
// agent + timestamp, source citation, and impact-based emphasis.
function FindingCard({ finding, isOpen, onToggle }) {
  var f = finding || {};
  var conf = (f.confidence || "").toUpperCase();
  var confColor = conf === "KNOWN" ? "var(--green)"
    : conf === "REASONED" ? "var(--amber)"
    : "var(--muted)";
  var confLabel = conf === "LOW_CONFIDENCE" ? "LOW" : (conf || "—");
  var hypothesisLabel = f.hypothesis_label || (f.hypothesis_id ? "·" : "");
  var isLoadBearing = f.impact === "load_bearing";
  var hasSource = !!(f.source_id || f.source);
  var clickable = hasSource;

  return React.createElement("div", {
    style: {
      borderBottom: "1px solid var(--rule)",
      borderLeft: isLoadBearing ? "3px solid var(--ink)" : "3px solid transparent",
      paddingLeft: "8px",
      background: isLoadBearing ? "rgba(26,24,20,.03)" : "transparent",
    }
  },
    React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "60px 1fr 36px",
        gap: "0 10px",
        alignItems: "baseline",
        padding: "9px 0",
        cursor: clickable ? "pointer" : "default",
      },
      onClick: clickable ? onToggle : null,
    },
      // Left column: agent + confidence badge stacked
      React.createElement("div", { style: { display: "flex", flexDirection: "column", gap: "3px" } },
        React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink)" } }, f.ag || f.agent_id || "?"),
        React.createElement("span", {
          style: {
            fontFamily: "var(--m)", fontSize: "8px", fontWeight: 700,
            letterSpacing: ".1em", color: confColor,
            border: "1px solid " + confColor, padding: "1px 4px",
            display: "inline-block", width: "fit-content",
          }
        }, confLabel)
      ),
      // Center column: claim text + meta line
      React.createElement("div", { style: { minWidth: 0 } },
        React.createElement("span", { style: { fontFamily: "var(--g)", fontSize: "12.5px", lineHeight: 1.45, color: "var(--ink2)", fontWeight: isLoadBearing ? 600 : 400 } }, f.text || f.claim_text || ""),
        React.createElement("div", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)", marginTop: "3px", display: "flex", gap: "8px" } },
          hypothesisLabel
            ? React.createElement("span", { style: { color: "var(--ink3)", fontWeight: 600 } }, hypothesisLabel)
            : null,
          isLoadBearing
            ? React.createElement("span", { style: { color: "var(--ink)", fontWeight: 700, letterSpacing: ".06em" } }, "LOAD-BEARING")
            : null,
          hasSource
            ? React.createElement("span", null, isOpen ? "\u25be source" : "\u25b8 source")
            : null
        )
      ),
      // Right column: timestamp
      React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)", textAlign: "right" } }, f.ts || "")
    ),
    isOpen && hasSource
      ? React.createElement("div", { style: { paddingBottom: "8px", paddingLeft: "70px" } },
          React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--ink3)", lineHeight: 1.6, fontStyle: "italic" } }, f.source || ("Source: " + f.source_id))
        )
      : null
  );
}

// Chantier 4 CP1: first-class hypothesis panel with computed status,
// finding counts, and click-to-expand. Reads computed{} block from backend.
function HypothesisPanel({ hypotheses, findings }) {
  var _s = useState(null);
  var expandedId = _s[0];
  var setExpandedId = _s[1];

  function statusColor(s) {
    if (s === "SUPPORTED") return "var(--green)";
    if (s === "WEAKENED") return "var(--red, #c43)";
    if (s === "TESTING") return "var(--amber)";
    return "var(--muted)";
  }

  function findingsForHypothesis(hypId) {
    return (findings || []).filter(function (f) {
      return (f.hypothesis_id || f.hypothesisId) === hypId;
    });
  }

  return React.createElement("div", { style: { padding: "13px 20px", borderBottom: "1px solid var(--ruleh)" } },
    React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px", paddingBottom: "8px", borderBottom: "1px solid var(--ink)" } },
      React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink)" } }, "Hypotheses")
    ),
    hypotheses.map(function (h, idx) {
      var label = h.label || ("H" + (idx + 1));
      var isAbandoned = h.status === "abandoned";
      var c = h.computed || { status: "NOT_STARTED", total: 0, known: 0, reasoned: 0, low_confidence: 0, contradicting: 0, supporting: 0 };
      var isOpen = expandedId === h.id;
      var linked = isOpen ? findingsForHypothesis(h.id) : [];

      return React.createElement("div", {
        key: h.id || ("h-" + idx),
        style: {
          padding: "8px 0",
          borderBottom: "1px solid var(--rule)",
          opacity: isAbandoned ? 0.45 : 1,
          cursor: "pointer",
        },
        onClick: function () { setExpandedId(isOpen ? null : h.id); },
      },
        React.createElement("div", { style: { display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "8px", marginBottom: "3px" } },
          React.createElement("div", { style: { display: "flex", alignItems: "baseline", gap: "8px" } },
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "10px", fontWeight: 700, color: "var(--ink)" } }, label),
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", letterSpacing: ".08em", textTransform: "uppercase", color: statusColor(c.status), fontWeight: 600 } }, c.status.replace("_", " "))
          ),
          React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)" } }, isOpen ? "\u25be" : "\u25b8")
        ),
        React.createElement("div", { style: { fontSize: "11px", lineHeight: 1.4, color: "var(--ink2)", marginBottom: "3px" } }, h.text || ""),
        React.createElement("div", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)", display: "flex", gap: "10px" } },
          React.createElement("span", { style: { color: c.known > 0 ? "var(--green)" : "var(--muted)" } }, "K " + c.known),
          React.createElement("span", null, "R " + c.reasoned),
          React.createElement("span", null, "L " + c.low_confidence),
          c.contradicting > 0
            ? React.createElement("span", { style: { color: "var(--red, #c43)" } }, "\u2715 " + c.contradicting)
            : null
        ),
        isOpen && linked.length > 0
          ? React.createElement("div", { style: { marginTop: "6px", paddingLeft: "8px", borderLeft: "1px solid var(--rule)" } },
              linked.map(function (f) {
                return React.createElement("div", {
                  key: f.id,
                  style: { fontSize: "10.5px", color: "var(--ink2)", padding: "3px 0", display: "flex", gap: "6px", alignItems: "baseline" },
                },
                  React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "8px", textTransform: "uppercase", color: "var(--muted)", minWidth: "44px" } }, (f.agent_id || f.ag || "?")),
                  React.createElement("span", null, f.claim_text || f.text || "")
                );
              })
            )
          : null,
        isOpen && linked.length === 0
          ? React.createElement("div", { style: { marginTop: "4px", fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)" } }, "No findings linked yet.")
          : null
      );
    })
  );
}

function Feed({ feedRef, ...props }) {
  var _s = useState(null);
  var expanded = _s[0];
  var setExpanded = _s[1];
  var activity = props.activity || LIVE;
  var completed = props.findings || DONE;

  // Fixed column widths for the completed grid
  var COL_AG = "64px";
  var COL_TS = "36px";

  function ConfDot(v) {
    if (!v) return null;
    var color = v === "inferred" ? "var(--amber)" : "var(--green)";
    return React.createElement("span", {
      title: v,
      style: { display: "inline-block", width: "5px", height: "5px", borderRadius: "50%", background: color, flexShrink: 0, marginBottom: "1px" }
    });
  }

  return React.createElement("div", { ref: feedRef, style: { flex: 1, overflowY: "auto" } },

    // IN PROGRESS
    React.createElement("div", { style: { padding: "12px 24px", background: "rgba(139,98,0,.05)", borderBottom: "1px solid rgba(139,98,0,.2)" } },
      React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "6px", marginBottom: "10px" } },
        React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--amber)" } }, "In progress"),
        React.createElement("span", { style: { color: "var(--amber)", animation: "pulse 1.4s ease-in-out infinite", fontSize: "8px" } }, "\u25cf")
      ),
      activity.map(function (e, i) {
        var visual = kindVisual(e.kind);
        var isPhase = e.kind === "phase";
        // Phase markers render as a full-width separator line with the phase
        // label, distinct from regular rail entries to break the timeline.
        if (isPhase) {
          return React.createElement("div", {
            key: e.id,
            style: {
              display: "flex", alignItems: "center", gap: "8px",
              padding: "10px 0", margin: "4px 0",
              borderTop: "1px dashed " + visual.color + "55",
              borderBottom: "1px dashed " + visual.color + "55",
            }
          },
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: visual.color } }, "Phase"),
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "10px", fontWeight: 600, letterSpacing: ".06em", color: "var(--ink)" } }, e.text)
          );
        }
        return React.createElement("div", {
          key: e.id, style: {
            display: "grid",
            gridTemplateColumns: "14px " + COL_AG + " 1fr",
            gap: "0 10px", alignItems: "baseline",
            paddingBottom: i < activity.length - 1 ? "8px" : "0",
            marginBottom: i < activity.length - 1 ? "8px" : "0",
            borderBottom: i < activity.length - 1 ? "1px solid rgba(139,98,0,.12)" : "none"
          },
          title: visual.label
        },
          React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "11px", color: visual.color, lineHeight: 1.4, alignSelf: "start", paddingTop: "1px", textAlign: "center" } }, visual.glyph),
          React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: visual.color, alignSelf: "start", paddingTop: "2px" } }, e.ag || visual.label),
          e.href
            ? React.createElement("a", { href: e.href, target: "_blank", rel: "noreferrer", style: { fontSize: "13px", lineHeight: 1.5, color: "var(--ink2)", fontWeight: 500, textDecoration: "underline" } }, e.text)
            : React.createElement("span", { style: { fontSize: "13px", lineHeight: 1.5, color: "var(--ink2)", fontWeight: 500 } }, e.text)
        );
      })
    ),

    // NEXT CHECKPOINT
    React.createElement("div", { style: { padding: "8px 24px", borderBottom: "1px solid var(--rule)", display: "flex", alignItems: "center", gap: "10px" } },
      React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", letterSpacing: ".14em", textTransform: "uppercase", color: "var(--muted)" } }, "Next"),
      React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "10px", fontWeight: 600, letterSpacing: ".06em", color: "var(--ink)" } }, props.nextCheckpointLabel || "No open checkpoint")
    ),

    // COMPLETED — strict 3-col grid
    React.createElement("div", { style: { padding: "0 24px" } },
      React.createElement("div", { style: { padding: "9px 0 8px", borderBottom: "1px solid var(--ink)" } },
        React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink)" } }, "Completed")
      ),
      completed.map(function (e) {
        var open = expanded === e.id;
        return React.createElement(FindingCard, {
          key: e.id,
          finding: e,
          isOpen: open,
          onToggle: function () { setExpanded(open ? null : e.id); },
        });
      })
    )
  );
}

export default function MissionControl(props) {
  var mission = props.mission || { name: "Unknown mission", client: "Unknown client", progress: 0 };
  var initialMessages = props.initialMessages || [];
  var messages = props.messages || initialMessages;
  var chatDraft = props.chatDraft || "";
  var onChatDraftChange = props.onChatDraftChange || function () { };
  var onSendMessage = props.onSendMessage || function () { };
  var selectedTab = props.selectedTab || props.defaultTab || "ws1";
  var onSelectTab = props.onSelectTab || function () { };
  var typing = !!props.isTyping;
  var gateModal = props.gateModal || null;
  var onGateClose = props.onGateClose || function () { };
  var backendState = props.backendState || "local";
  var pendingGateBanner = props.pendingGateBanner || null;
  var briefStatus = props.briefStatus || "pending";
  var briefIsComplete = briefStatus === "completed";
  var briefIsActive = briefStatus === "now";
  var workstreamTabs = props.workstreamContent && props.workstreamContent.length
    ? props.workstreamContent.map(function (w) {
      return { id: "ws" + String(w.id || "").replace(/^W/i, ""), label: w.label || w.id };
    })
    : WS;
  var feedRef = useRef(null);
  var chatRef = useRef(null);
  var chatInputRef = useRef(null);

  useEffect(function () { if (chatRef.current) chatRef.current.scrollTop = 99999; }, [messages, typing]);
  useEffect(function () {
    var el = chatInputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 125) + "px";
  }, [chatDraft]);

  function send() {
    if (!chatDraft.trim()) return;
    onSendMessage(chatDraft);
  }

  var pct = mission.progress * 100;

  return React.createElement(React.Fragment, null,
    React.createElement("style", null, CSS),
    React.createElement("div", { style: { display: "grid", gridTemplateColumns: "220px 1fr 288px", height: "100vh", background: "var(--paper)", fontFamily: "var(--g)", color: "var(--ink)", overflow: "hidden" } },

      // LEFT RAIL
      React.createElement("aside", { style: { background: "var(--bone)", borderRight: "1px solid var(--ruleh)", display: "flex", flexDirection: "column", overflowY: "auto", flexShrink: 0 } },

        // Mission
        React.createElement("div", { style: { padding: "13px 20px 14px", borderBottom: "1px solid var(--ruleh)" } },
          React.createElement("div", { className: "k", style: { marginBottom: "5px" } }, "Mission"),
          React.createElement("div", { style: { fontFamily: "var(--d)", fontSize: "15px", fontWeight: 600, letterSpacing: "-.02em", lineHeight: 1.2, marginBottom: "3px" } }, mission.name),
          React.createElement("div", { style: { fontFamily: "var(--m)", fontSize: "9.5px", color: "var(--muted)", marginBottom: "12px" } }, mission.client),
          // Progress bar
          React.createElement("div", { style: { position: "relative", height: "3px", background: "var(--ruleh)" } },
            React.createElement("div", { style: { position: "absolute", left: 0, top: 0, height: "100%", width: pct + "%", background: "var(--ink)" } }),
            (props.checkpoints || CHECKPOINTS).map(function (cp, i) {
              var left = ((i + 1) / (props.checkpoints || CHECKPOINTS).length * 100) + "%";
              var bg = cp.status === "completed" ? "var(--muted)" : cp.status === "now" ? "var(--ink)" : "var(--ruleh)";
              return React.createElement("div", { key: cp.id, style: { position: "absolute", top: "-3.5px", left: left, transform: "translateX(-50%)", width: "1px", height: "10px", background: bg } });
            })
          )
        ),

        // Checkpoints
        React.createElement("div", { style: { padding: "13px 20px", borderBottom: "1px solid var(--ruleh)" } },
          React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px", paddingBottom: "8px", borderBottom: "1px solid var(--ink)" } },
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink)" } }, "Checkpoints")
          ),
          (props.checkpoints || CHECKPOINTS).map(function (cp) {
            var dotBg = (cp.status === "completed" || cp.status === "now") ? (cp.status === "now" ? "var(--ink)" : "var(--muted)") : "transparent";
            var dotBorder = cp.status === "later" ? "var(--ruleh)" : cp.status === "now" ? "var(--ink)" : "var(--muted)";
            var labelColor = cp.status === "now" ? "var(--ink)" : "var(--muted)";
            var labelWeight = cp.status === "now" ? 600 : 400;
            var stateLabel = { completed: "Completed", now: "Now", next: "Next", later: "Later", pending: "Later", done: "Completed" }[cp.status] || cp.status;
            return React.createElement("div", { key: cp.id, style: { display: "flex", alignItems: "center", gap: "8px", padding: "4px 0", borderBottom: cp.id === "c5" ? "none" : "1px solid var(--rule)" } },
              React.createElement("div", { style: { width: "5px", height: "5px", borderRadius: "50%", flexShrink: 0, background: dotBg, border: "1px solid " + dotBorder } }),
              React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9.5px", letterSpacing: ".06em", color: labelColor, fontWeight: labelWeight, flex: 1 } }, cp.label),
              React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)" } }, stateLabel)
            );
          })
        ),

        // Agents
        React.createElement("div", { style: { padding: "13px 20px", borderBottom: "1px solid var(--ruleh)" } },
          React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px", paddingBottom: "8px", borderBottom: "1px solid var(--ink)" } },
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink)" } }, "Agents")
          ),
          (props.agents || AGENTS).map(function (a) {
            var agentState = a.state || (a.status === "active" ? "running" : a.status === "done" ? "done" : "idle");
            return React.createElement("div", { key: a.id, className: "ag", style: { opacity: agentState === "idle" ? 0.35 : 1 } },
              React.createElement("div", { style: { color: agentState === "idle" ? "var(--muted)" : "var(--ink)", flexShrink: 0 } }, React.createElement(Icon, { id: a.id })),
              React.createElement("div", { style: { flex: 1, minWidth: 0 } },
                React.createElement("div", { style: { fontSize: "12px", fontWeight: agentState === "running" ? 500 : 400 } }, a.name),
                React.createElement("div", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, a.role)
              ),
              React.createElement(StateTag, { state: agentState })
            );
          })
        ),

        // HypothesisPanel (Chantier 4 CP1) — first-class panel with computed
        // status, finding counts (KNOWN/REASONED/LOW + contradicting), and
        // click-to-expand showing linked findings. Pre-framing: empty.
        ((props.hypotheses && props.hypotheses.length > 0) ?
          React.createElement(HypothesisPanel, {
            hypotheses: props.hypotheses,
            findings: props.findings || [],
          })
        : null),

        // Deliverables
        React.createElement("div", { style: { padding: "13px 20px 16px" } },
          React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px", paddingBottom: "8px", borderBottom: "1px solid var(--ink)" } },
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink)" } }, "Deliverables")
          ),
          (props.deliverables || DELIVERABLES).map(function (d) {
            var isReady = d.status === "ready";
            var canOpen = isReady && (d.onOpen || d.href);
            // Chantier 4 CP3: prefer onOpen (preview modal) over plain href
            // navigation. Falls back to <a href> if no onOpen handler.
            var asAnchor = canOpen && !d.onOpen && d.href;
            var tag = asAnchor ? "a" : "div";
            var elProps = {
              key: d.id,
              className: "dl",
              style: {
                opacity: isReady ? 1 : 0.4,
                textDecoration: "none",
                color: "inherit",
                cursor: canOpen ? "pointer" : "default",
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                padding: "5px 0",
                borderBottom: "1px solid var(--rule)",
              },
            };
            if (asAnchor) {
              elProps.href = d.href;
              elProps.target = "_blank";
              elProps.rel = "noopener noreferrer";
            } else if (canOpen && d.onOpen) {
              elProps.role = "button";
              elProps.tabIndex = 0;
              elProps.onClick = d.onOpen;
              elProps.onKeyDown = function (ev) {
                if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); d.onOpen(); }
              };
            }
            return React.createElement(tag, elProps,
              React.createElement("span", { style: { fontSize: "11.5px", fontWeight: isReady ? 500 : 400 } }, d.label),
              React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", color: isReady ? "var(--green)" : "var(--muted)" } }, canOpen ? "Open \u2192" : isReady ? "\u2193" : "\u2014")
            );
          })
        )
      ),

      // CENTER
      React.createElement("main", { style: { display: "flex", flexDirection: "column", overflow: "hidden" } },
        // Header
        React.createElement("div", { style: { padding: "16px 24px 0", borderBottom: "1px solid var(--ruleh)", flexShrink: 0 } },
          React.createElement("div", { style: { display: "flex", alignItems: "baseline", gap: "12px", marginBottom: "12px" } },
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "10px", color: "var(--muted)" } }, mission.client),
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 600, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--green)", animation: "pulse 2s ease-in-out infinite", marginLeft: "auto" } }, "\u25cf Active")
          ),
          // Tabs
          React.createElement("div", { style: { display: "flex", overflowX: "auto", scrollbarWidth: "none" } },
            React.createElement("span", {
              className: "tab" + (briefIsComplete ? " done" : briefIsActive ? " on" : ""),
              style: { cursor: "default" }
            }, (briefIsComplete ? "\u2713 " : "") + "Brief"),
            workstreamTabs.map(function (w) {
              return React.createElement("button", { key: w.id, className: "tab" + (selectedTab === w.id ? " on" : ""), onClick: function () { onSelectTab(w.id); } }, w.label);
            })
          )
        ),
        pendingGateBanner ? React.createElement("div", {
          style: {
            padding: "10px 24px",
            background: "rgba(139,98,0,.10)",
            borderBottom: "1px solid rgba(139,98,0,.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            flexShrink: 0,
          }
        },
          React.createElement("span", { style: { fontSize: "12px", color: "var(--ink2)", lineHeight: 1.45 } },
            React.createElement("strong", { style: { fontWeight: 600 } }, pendingGateBanner.title || "Validation required"),
            pendingGateBanner.summary ? " · " + pendingGateBanner.summary : " · Mission is paused until you decide."
          ),
          React.createElement("button", {
            onClick: pendingGateBanner.onResume,
            style: {
              fontFamily: "var(--m)", fontSize: "10px", fontWeight: 600,
              letterSpacing: ".12em", textTransform: "uppercase",
              padding: "6px 12px", background: "var(--ink)", color: "var(--paper)",
              border: "none", cursor: "pointer", borderRadius: "4px",
            }
          }, "Review now")
        ) : null,
        React.createElement(Feed, { feedRef: feedRef, activity: props.activity, findings: props.findings, nextCheckpointLabel: props.nextCheckpointLabel })
      ),

      // RIGHT RAIL
      React.createElement("aside", { style: { borderLeft: "1px solid var(--ruleh)", display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bone2)", flexShrink: 0 } },
        React.createElement("div", { style: { padding: "16px 20px 14px", borderBottom: "1px solid var(--ruleh)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 } },
          React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "11px", fontWeight: 600, letterSpacing: ".14em", textTransform: "uppercase" } }, "MARVIN"),
          React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 600, letterSpacing: ".14em", textTransform: "uppercase", color: backendState === "offline" ? "var(--amber)" : backendState === "ready" ? "var(--green)" : "var(--muted)" } }, backendState === "offline" ? "Backend offline" : backendState === "ready" ? "Ready" : backendState)
        ),
        // Chat
        React.createElement("div", { ref: chatRef, style: { flex: 1, overflow: "auto", padding: "12px 20px", display: "flex", flexDirection: "column", gap: "8px" } },
          messages.map(function (m) {
            return React.createElement("div", { key: m.id, style: { display: "flex", flexDirection: m.from === "u" ? "row-reverse" : "row" } },
              React.createElement("div", { className: m.from === "m" ? "msg-m" : "msg-u", style: { maxWidth: "90%", padding: "9px 12px", fontSize: "12.5px", lineHeight: 1.6, color: m.from === "u" ? "var(--paper)" : "var(--ink2)" } },
                m.from === "m" ? React.createElement("div", { className: "k", style: { marginBottom: "4px" } }, "Marvin") : null,
                m.text
              )
            );
          }),
          typing ? React.createElement("div", null,
            React.createElement("div", { className: "msg-m", style: { display: "inline-block", padding: "9px 13px" } },
              React.createElement("div", { className: "k", style: { marginBottom: "4px" } }, "Marvin"),
              React.createElement("div", { style: { display: "flex", gap: "4px" } },
                [0, 1, 2].map(function (i) {
                  return React.createElement("div", { key: i, style: { width: "4px", height: "4px", background: "var(--muted)", animation: "blink 1.1s " + (i * 0.25) + "s ease-in-out infinite" } });
                })
              )
            )
          ) : null
        ),
        // Input
        React.createElement("div", { style: { borderTop: "1px solid var(--ruleh)", background: "var(--paper)", flexShrink: 0 } },
          React.createElement("div", { style: { padding: "11px 20px 8px" } },
            React.createElement("textarea", { ref: chatInputRef, value: chatDraft, placeholder: "Ask MARVIN or redirect the mission...", style: { minHeight: "62px", maxHeight: "125px", overflowY: "auto", width: "100%", resize: "none" }, onChange: function (e) { onChatDraftChange(e.target.value); }, onKeyDown: function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } } })
          ),
          React.createElement("div", { style: { padding: "7px 20px 11px", display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--rule)" } },
            React.createElement("span", { className: "k" }, "\u2318\u21b5 to send"),
            React.createElement("button", { className: "send-btn", onClick: send }, "Send \u2192")
          )
        )
      )
    ),
    gateModal ? React.createElement("div", { className: "overlay", role: "dialog", "aria-modal": true, onClick: function (e) { if (e.target === e.currentTarget) onGateClose(); } },
      React.createElement("div", { style: { width: "100%", maxWidth: "540px", background: "var(--paper)", border: "1px solid var(--ruleh)", borderRadius: "14px", boxShadow: "0 32px 80px rgba(26,24,20,.22)", padding: "22px 24px" } },
        React.createElement("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "14px" } },
          React.createElement("div", null,
            React.createElement("div", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 600, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--muted)", marginBottom: "5px" } }, "Gate pending"),
            React.createElement("h2", { style: { fontFamily: "var(--d)", fontSize: "22px", fontWeight: 700, letterSpacing: "-.02em" } }, gateModal.title || "Validation required")
          ),
          React.createElement("button", { onClick: onGateClose, style: { background: "none", border: "none", cursor: "pointer", color: "var(--muted)", display: "flex" } },
            React.createElement("svg", { width: "16", height: "16", viewBox: "0 0 16 16", fill: "none" },
              React.createElement("path", { d: "M3 3l10 10M13 3L3 13", stroke: "currentColor", strokeWidth: "1.6", strokeLinecap: "round" })
            )
          )
        ),
        React.createElement("p", { style: { fontSize: "13px", lineHeight: 1.6, color: "var(--ink3)", marginBottom: "16px" } }, gateModal.summary || "A gate is waiting for human review before the mission can proceed."),
        React.createElement("div", { style: { fontFamily: "var(--m)", fontSize: "9px", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink3)" } }, "Gate ID: " + gateModal.gateId)
      )
    ) : null
  );
}
