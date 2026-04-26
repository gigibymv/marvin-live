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

const CHECKPOINTS = [
  { id: "c1", label: "Hypothesis confirmation", status: "pending" },
  { id: "c2", label: "Review claims", status: "pending" },
  { id: "c3", label: "Defend storyline", status: "pending" },
  { id: "c4", label: "Red-team review", status: "pending" },
  { id: "c5", label: "Final delivery", status: "pending" },
];

const HYP = [];

const AGENTS = [
  { id: "marvin", name: "MARVIN", role: "Orchestration", state: "idle" },
  { id: "dora", name: "Dora", role: "Market research", state: "idle" },
  { id: "calculus", name: "Calculus", role: "Financials", state: "idle" },
  { id: "adversus", name: "Adversus", role: "Red-team", state: "idle" },
  { id: "merlin", name: "Merlin", role: "Synthesis", state: "idle" },
  { id: "papyrus", name: "Papyrus", role: "Deliverables", state: "idle" },
];

const WS = [
  { id: "ws1", label: "Competitive" },
  { id: "ws2", label: "Market" },
  { id: "ws3", label: "Financial" },
  { id: "ws4", label: "Risk" },
  { id: "ws5", label: "Memo" },
];

const LIVE = [];

const DONE = [];

const DELIVERABLES = [
  { id: "dv1", label: "Engagement brief", status: "ready" },
  { id: "dv2", label: "Competitive analysis", status: "ready" },
  { id: "dv3", label: "Market analysis", status: "pending" },
  { id: "dv4", label: "Financial analysis", status: "pending" },
  { id: "dv5", label: "Risk / Red-team", status: "pending" },
  { id: "dv6", label: "Investment memo", status: "pending" },
];

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

function StateTag({ state }) {
  var color = state === "running" ? "var(--green)" : state === "waiting" ? "var(--amber)" : "var(--muted)";
  var weight = state === "running" ? 600 : 400;
  return React.createElement("span", {
    style: { fontFamily: "var(--m)", fontSize: "9px", letterSpacing: ".1em", textTransform: "uppercase", color: color, fontWeight: weight }
  },
    state === "running" ? React.createElement("span", { style: { animation: "pulse 1.4s ease-in-out infinite", display: "inline-block", marginRight: "2px" } }, "\u25cf") : null,
    state
  );
}

function Feed({ feedRef, ...props }) {
  var _s = useState(null);
  var expanded = _s[0];
  var setExpanded = _s[1];

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
      (props.findings || LIVE).map(function (e, i) {
        return React.createElement("div", {
          key: e.id, style: {
            display: "grid", gridTemplateColumns: COL_AG + " 1fr",
            gap: "0 10px", alignItems: "baseline",
            paddingBottom: i < (props.findings || LIVE).length - 1 ? "8px" : "0",
            marginBottom: i < (props.findings || LIVE).length - 1 ? "8px" : "0",
            borderBottom: i < (props.findings || LIVE).length - 1 ? "1px solid rgba(139,98,0,.12)" : "none"
          }
        },
          React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--amber)", alignSelf: "start", paddingTop: "2px" } }, e.ag),
          React.createElement("span", { style: { fontSize: "13px", lineHeight: 1.5, color: "var(--ink2)", fontWeight: 500 } }, e.text)
        );
      })
    ),

    // NEXT CHECKPOINT
    React.createElement("div", { style: { padding: "8px 24px", borderBottom: "1px solid var(--rule)", display: "flex", alignItems: "center", gap: "10px" } },
      React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", letterSpacing: ".14em", textTransform: "uppercase", color: "var(--muted)" } }, "Next"),
      React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "10px", fontWeight: 600, letterSpacing: ".06em", color: "var(--ink)" } }, "Review claims")
    ),

    // COMPLETED — strict 3-col grid
    React.createElement("div", { style: { padding: "0 24px" } },
      React.createElement("div", { style: { padding: "9px 0 8px", borderBottom: "1px solid var(--ink)" } },
        React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink)" } }, "Completed")
      ),
      (props.findings || DONE).map(function (e) {
        var open = expanded === e.id;
        return React.createElement("div", { key: e.id, style: { borderBottom: "1px solid var(--rule)" } },
          // Main row — strict grid
          React.createElement("div", {
            style: {
              display: "grid",
              gridTemplateColumns: COL_AG + " 1fr " + COL_TS,
              gap: "0 10px",
              alignItems: "baseline",
              padding: "8px 0",
              cursor: e.source ? "pointer" : "default"
            }, onClick: e.source ? function () { setExpanded(open ? null : e.id); } : null
          },
            // Agent
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 500, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--muted)" } }, e.ag),
            // Text + conf dot
            React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "6px", minWidth: 0 } },
              React.createElement("span", { style: { fontFamily: "var(--g)", fontSize: "12.5px", lineHeight: 1.45, color: "var(--ink2)" } }, e.text)
            ),
            // Timestamp
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)", textAlign: "right" } }, e.ts)
          ),
          // Source expansion
          open && e.source ? React.createElement("div", { style: { paddingBottom: "8px", paddingLeft: "74px" } },
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--ink3)", lineHeight: 1.6, fontStyle: "italic" } }, e.source)
          ) : null
        );
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
  var feedRef = useRef(null);
  var chatRef = useRef(null);

  useEffect(function () { if (chatRef.current) chatRef.current.scrollTop = 99999; }, [messages, typing]);

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
            var stateLabel = { completed: "Completed", now: "Now", next: "Next", later: "Later" }[cp.status];
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
            var msTotal = a.milestonesTotal || 0;
            var msDone = a.milestonesDelivered || 0;
            var msColor = msTotal > 0 && msDone === msTotal ? "var(--green)" : "var(--muted)";
            return React.createElement("div", { key: a.id, className: "ag", style: { opacity: a.state === "idle" ? 0.35 : 1 } },
              React.createElement("div", { style: { color: a.state === "idle" ? "var(--muted)" : "var(--ink)", flexShrink: 0 } }, React.createElement(Icon, { id: a.id })),
              React.createElement("div", { style: { flex: 1, minWidth: 0 } },
                React.createElement("div", { style: { fontSize: "12px", fontWeight: a.state === "running" ? 500 : 400 } }, a.name),
                React.createElement("div", { style: { fontFamily: "var(--m)", fontSize: "9px", color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, a.role)
              ),
              msTotal > 0 ? React.createElement("span", {
                "data-testid": "milestone-counter-" + a.id,
                style: { fontFamily: "var(--m)", fontSize: "9px", letterSpacing: ".06em", color: msColor, marginRight: "6px", fontVariantNumeric: "tabular-nums" }
              }, msDone + "/" + msTotal) : null,
              React.createElement(StateTag, { state: a.state })
            );
          })
        ),

        // Deliverables
        React.createElement("div", { style: { padding: "13px 20px 16px" } },
          React.createElement("div", { style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px", paddingBottom: "8px", borderBottom: "1px solid var(--ink)" } },
            React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink)" } }, "Deliverables")
          ),
          (props.deliverables || DELIVERABLES).map(function (d) {
            return React.createElement("div", { key: d.id, className: "dl", style: { opacity: d.status === "pending" ? 0.4 : 1 } },
              React.createElement("span", { style: { fontSize: "11.5px", fontWeight: d.status === "ready" ? 500 : 400 } }, d.label),
              React.createElement("span", { style: { fontFamily: "var(--m)", fontSize: "9px", color: d.status === "ready" ? "var(--green)" : "var(--muted)" } }, d.status === "ready" ? "\u2193" : "\u2014")
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
            React.createElement("span", { className: "tab done", style: { cursor: "default" } }, "\u2713 Brief"),
            WS.map(function (w) {
              return React.createElement("button", { key: w.id, className: "tab" + (selectedTab === w.id ? " on" : ""), onClick: function () { onSelectTab(w.id); } }, w.label);
            })
          )
        ),
        React.createElement(Feed, { feedRef: feedRef, findings: props.findings })
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
            React.createElement("textarea", { rows: 2, value: chatDraft, placeholder: "Ask MARVIN or redirect the mission...", onChange: function (e) { onChatDraftChange(e.target.value); }, onKeyDown: function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } } })
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
