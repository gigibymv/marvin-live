// mc-v2/utils.jsx — cleaned per impeccable audit
// No pulse animations. Static indicators. Controlled radius vocabulary (0, 4, 8).
// 3 mono sizes (9, 10.5, 12). Body line-height 1.6 everywhere.

const { useState, useEffect, useRef, useCallback } = React;

const ICON_PATHS = {
  thesis:    <path d="M8 3v2.5M8 10.5V13M3.8 5.8l1.8 1.8M9.4 9.4l1.8 1.8M2.5 8h2.5M11 8h2.5M3.8 10.2l1.8-1.8M9.4 6.6l1.8-1.8" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>,
  dora:      <><circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.1" fill="none"/><path d="M10.2 10.2L13 13" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></>,
  calculus:  <path d="M2 11l3-3.5 2.5 2 3-4.5L13 7" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round"/>,
  lector:    <><path d="M8 2.5a2.5 2.5 0 012.5 2.5v3.5a2.5 2.5 0 01-5 0V5A2.5 2.5 0 018 2.5z" stroke="currentColor" strokeWidth="1" fill="none"/><path d="M4.5 9a3.5 3.5 0 007 0" stroke="currentColor" strokeWidth="1" strokeLinecap="round" fill="none"/></>,
  adversus:  <path d="M4 4l8 8M12 4L4 12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>,
  merlin:    <><path d="M8 2l6.5 12H1.5L8 2z" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" fill="none"/><path d="M5.5 10h5" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/></>,
  papyrus:   <><rect x="3.5" y="1.5" width="9" height="13" rx="1" stroke="currentColor" strokeWidth="1" fill="none"/><path d="M5.5 5h5M5.5 7.5h5M5.5 10h3" stroke="currentColor" strokeWidth=".9" strokeLinecap="round"/></>,
  back:      <path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>,
  grip:      <><circle cx="6" cy="5" r=".8" fill="currentColor"/><circle cx="10" cy="5" r=".8" fill="currentColor"/><circle cx="6" cy="8" r=".8" fill="currentColor"/><circle cx="10" cy="8" r=".8" fill="currentColor"/><circle cx="6" cy="11" r=".8" fill="currentColor"/><circle cx="10" cy="11" r=".8" fill="currentColor"/></>,
  chevron_d: <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>,
  chevron_r: <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>,
  doc:       <><rect x="4" y="1.5" width="8" height="13" rx="1.5" stroke="currentColor" strokeWidth="1" fill="none"/><path d="M6.5 5h3M6.5 7.5h3M6.5 10h2" stroke="currentColor" strokeWidth=".8" strokeLinecap="round"/></>,
};

function Icon({ id, size = 14, color = "currentColor", style: extra }) {
  return <svg width={size} height={size} viewBox="0 0 16 16" fill="none" style={{ color, flexShrink: 0, display: "block", ...extra }}>{ICON_PATHS[id] || null}</svg>;
}

/* Static status dot — no animation. Filled = active, hollow = inactive. */
function StatusDot({ color = "var(--green)", size = 6, hollow = false }) {
  return <span style={{
    display: "inline-block", width: size, height: size, borderRadius: "50%", flexShrink: 0,
    background: hollow ? "transparent" : color,
    border: hollow ? `1.5px solid ${color}` : "none",
  }} />;
}

/* Mono label — 3 sizes only: 9 (micro), 10.5 (label), 12 (body mono) */
function Mono({ children, color = "var(--muted)", size = 9, weight = 500, spacing = ".12em", upper = true, style: extra }) {
  return <span style={{ fontFamily: "var(--m)", fontSize: size, fontWeight: weight, letterSpacing: spacing, textTransform: upper ? "uppercase" : "none", color, lineHeight: 1.4, ...extra }}>{children}</span>;
}

/* Badge — radius 4px only */
function Badge({ children, color = "var(--muted)", filled = false }) {
  return (
    <span style={{
      fontFamily: "var(--m)", fontSize: 9, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase",
      color: filled ? "white" : color,
      background: filled ? color : "transparent",
      border: filled ? "none" : `1px solid ${color}55`,
      padding: "2px 7px", borderRadius: 4, display: "inline-block", lineHeight: 1.4,
    }}>
      {children}
    </span>
  );
}

function ProgressBar({ pct = 0, color = "var(--ink)", height = 4, bg = "var(--rule)" }) {
  return (
    <div style={{ height, background: bg, borderRadius: 0, overflow: "hidden", width: "100%" }}>
      <div style={{ height, width: `${Math.min(100, Math.max(0, pct))}%`, background: color, transition: "width .6s cubic-bezier(0.16,1,0.3,1)" }} />
    </div>
  );
}

/* State tag — static dot, no pulse */
function StateTag({ state }) {
  const m = {
    running: { c: "var(--green)", active: true },
    done:    { c: "var(--muted)", active: false },
    waiting: { c: "var(--amber)", active: true },
    idle:    { c: "var(--muted)", active: false },
    error:   { c: "var(--red)",   active: true },
  };
  const cfg = m[state] || m.idle;
  return (
    <span style={{ fontFamily: "var(--m)", fontSize: 9, letterSpacing: ".1em", textTransform: "uppercase", color: cfg.c, fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 4 }}>
      <StatusDot color={cfg.c} size={5} hollow={!cfg.active} />
      {state}
    </span>
  );
}

Object.assign(window, { useState, useEffect, useRef, useCallback, Icon, StatusDot, Mono, Badge, ProgressBar, StateTag });
