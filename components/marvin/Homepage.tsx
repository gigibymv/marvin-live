"use client";

import React, { useEffect, useRef, useState } from "react";

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=Newsreader:ital,opsz,wght@1,6..72,400;1,6..72,500;1,6..72,600&family=EB+Garamond:ital,wght@1,400;1,500&family=Geist:wght@300;400;500;600&family=Geist+Mono:wght@400;500;600&display=swap');

:root {
  --paper:#F4F0EA; --bone:#EEE9DD; --bone2:#E8E1D1; --olive:#EFEDE3;
  --ink:#1A1814; --ink2:#3A362F; --ink3:#5C564C; --muted:#78716A;
  --rule:rgba(26,24,20,.09); --rule-m:rgba(26,24,20,.14); --rule-s:rgba(26,24,20,.22);
  --ok:#2D7A4E; --warn:#D97706; --alert:#B43A2E;
  --display:'Bricolage Grotesque',system-ui,sans-serif;
  --serif:'EB Garamond','Newsreader',Georgia,serif;
  --sans:'Geist',-apple-system,sans-serif;
  --mono:'Geist Mono',ui-monospace,monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--paper);font-family:var(--sans);color:var(--ink);-webkit-font-smoothing:antialiased;line-height:1.5;overflow-x:hidden;max-width:100%}
button,input,textarea,select{font-family:inherit;font-size:inherit;color:inherit}
button{cursor:pointer;border:none;background:none}
a{color:inherit;text-decoration:none}
*:focus-visible{outline:2px solid var(--ink);outline-offset:3px;border-radius:3px}
img,svg{display:block;max-width:100%}

.wrap{max-width:1200px;margin:0 auto;padding:0 32px}
.eyebrow{font-family:var(--mono);font-size:9.5px;font-weight:600;color:var(--ink3);letter-spacing:.1em;text-transform:uppercase;margin-bottom:20px}
.eyebrow::before,.eyebrow::after{display:none}
.btn{display:inline-flex;align-items:center;gap:10px;padding:14px 26px;border-radius:8px;font-weight:600;font-size:14.5px;letter-spacing:-.01em;transition:all .2s;font-family:var(--sans)}
.btn svg{transition:transform .2s}
.btn:hover svg{transform:translateX(3px)}
.btn.primary{background:var(--ink);color:var(--paper)}
.btn.primary:hover{background:var(--ink2);transform:translateY(-1px)}
.btn.ghost{color:var(--ink);border:1px solid var(--rule-m)}
.btn.ghost:hover{background:var(--bone);border-color:var(--rule-s)}

section{padding:100px 0;position:relative}
section.tight{padding:72px 0}

.reveal{transition:opacity .5s ease,transform .5s ease}
.js-anim .reveal{opacity:0;transform:translateY(10px)}
.js-anim .reveal.in{opacity:1;transform:translateY(0)}
@media (prefers-reduced-motion: reduce){
  .js-anim .reveal{opacity:1;transform:none}
  .reveal{transition:none}
}
.reveal-delay-1{transition-delay:.08s}
.reveal-delay-2{transition-delay:.16s}
.reveal-delay-3{transition-delay:.24s}
.reveal-delay-4{transition-delay:.32s}
.reveal-delay-5{transition-delay:.4s}

.nav{position:fixed;top:0;left:0;right:0;z-index:100;padding:18px 0;background:rgba(244,240,234,.82);backdrop-filter:blur(14px) saturate(1.2);border-bottom:1px solid transparent;transition:border-color .3s}
.nav.scrolled{border-bottom-color:var(--rule)}
.nav-inner{max-width:1200px;margin:0 auto;padding:0 32px;display:flex;align-items:center;justify-content:space-between}
.brand{font-family:var(--display);font-size:22px;font-weight:700;letter-spacing:-.02em}
.brand-badge{font-family:var(--mono);font-size:10px;font-weight:600;color:var(--muted);letter-spacing:.08em;border:1px solid var(--rule-m);padding:3px 7px;border-radius:4px;margin-left:10px}
.nav-links{display:flex;gap:28px;align-items:center}
.nav-links a{font-size:13px;color:var(--ink3);font-weight:500;transition:color .15s}
.nav-links a:hover{color:var(--ink)}
.nav-cta{font-size:13px;padding:9px 16px;border-radius:6px;background:var(--ink);color:var(--paper);font-weight:600;transition:all .15s}
.nav-cta:hover{background:var(--ink2);transform:translateY(-1px)}

.hero{padding:0;display:block;min-height:0}
.ticker-wrap{border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);overflow:hidden;background:var(--bone);padding:0}
.ticker-track{display:flex;width:max-content;animation:ticker 28s linear infinite}
.ticker-track:hover{animation-play-state:paused}
.ticker-item{display:flex;align-items:center;gap:10px;padding:14px 36px;border-right:1px solid var(--rule);white-space:nowrap;flex-shrink:0}
.ticker-v{font-family:var(--display);font-size:22px;font-weight:700;letter-spacing:-.03em;color:var(--ink)}
.ticker-k{font-family:var(--mono);font-size:9px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}
@keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}

.s-quote{padding:60px 0;background:var(--bone)}
.s-quote blockquote{font-family:var(--display);font-size:clamp(22px,2.8vw,36px);line-height:1.3;letter-spacing:-.02em;text-align:center;max-width:860px;margin:0 auto;color:var(--ink);font-weight:500}

.s-changes h2{font-family:var(--display);font-size:clamp(32px,4vw,52px);line-height:1.08;letter-spacing:-.03em;font-weight:600;margin-bottom:64px}
.s-changes h2 em{font-family:var(--serif);font-style:italic;font-weight:500;color:var(--ink2)}
.benefits{display:grid;grid-template-columns:repeat(2,1fr);gap:2px;background:var(--rule);border:1px solid var(--rule);border-radius:14px;overflow:hidden}
.benefit{background:var(--paper);padding:36px 32px;transition:background .2s}
.benefit:hover{background:var(--bone)}
.benefit-name{font-family:var(--display);font-size:28px;font-weight:600;letter-spacing:-.025em;margin-bottom:14px}
.benefit-body{font-size:14.5px;line-height:1.6;color:var(--ink2)}

.s-workflow{background:var(--bone)}
.s-workflow h2{font-family:var(--display);font-size:clamp(34px,4.5vw,52px);line-height:1.08;letter-spacing:-.03em;font-weight:600;margin-bottom:64px}
.wf-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:var(--rule);border:1px solid var(--rule);border-radius:14px;overflow:hidden}
.wf{background:var(--paper);padding:40px 36px;transition:background .3s}
.wf-top{display:flex;align-items:baseline;gap:14px;margin-bottom:22px;padding-bottom:22px;border-bottom:1px solid var(--rule)}
.wf-n{font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.1em;color:var(--muted)}
.wf-name{font-family:var(--display);font-size:22px;font-weight:600;letter-spacing:-.02em;color:var(--ink)}
.wf-body{font-size:15px;line-height:1.6;color:var(--ink2)}

.s-missions h2{font-family:var(--display);font-size:clamp(32px,4vw,44px);line-height:1.1;letter-spacing:-.025em;font-weight:600;margin-bottom:16px}
.s-missions .intro{font-size:17px;color:var(--ink2);max-width:680px;line-height:1.55;margin-bottom:56px}
.mcat{border:1px solid var(--rule);border-radius:12px;background:var(--paper);margin-bottom:14px;overflow:hidden}
.mcat-hd{padding:22px 28px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.mcat-left{display:flex;align-items:center;gap:16px;flex:1;min-width:0}
.mcat-name{font-family:var(--display);font-size:22px;font-weight:600;letter-spacing:-.02em}
.mcat-status{font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;padding:4px 9px;border-radius:4px}
.mcat-status.active{background:rgba(45,122,78,.12);color:var(--ok);border:1px solid rgba(45,122,78,.25)}
.mcat-status.soon{background:var(--bone);color:var(--ink3);border:1px solid var(--rule-m)}

.s-team{background:var(--bone)}
.s-team h2{font-family:var(--display);font-size:clamp(30px,3.8vw,42px);line-height:1.12;letter-spacing:-.025em;font-weight:600;margin-bottom:16px;max-width:900px}
.s-team .sub{font-size:16.5px;color:var(--ink2);max-width:640px;line-height:1.6;margin-bottom:64px}
.team-gate{max-width:800px;margin:0 auto;padding:28px 36px;border:1px solid var(--rule-m);border-radius:12px;background:var(--paper);text-align:center}
.team-gate-copy{font-size:15px;line-height:1.6;color:var(--ink2);margin-bottom:20px}

.s-deliver h2{font-family:var(--display);font-size:clamp(32px,4vw,46px);line-height:1.1;letter-spacing:-.025em;font-weight:600;margin-bottom:20px}
.s-deliver .body{font-size:17px;color:var(--ink2);max-width:720px;line-height:1.6;margin-bottom:44px}
.showcase{position:relative;overflow:hidden;margin-bottom:48px}
.showcase-track{display:flex;gap:16px;overflow-x:auto;scroll-behavior:smooth;padding:8px 0 24px 0;scrollbar-width:thin}
.showcase-card{flex:0 0 min(320px,85vw);border:1px solid var(--rule);border-radius:12px;background:var(--paper);overflow:hidden;box-shadow:0 2px 0 rgba(26,24,20,.03),0 12px 28px rgba(26,24,20,.06)}
.showcase-card-hd{padding:16px 20px;border-bottom:1px solid var(--rule);background:var(--bone);display:flex;justify-content:space-between;align-items:center}
.showcase-card-name{font-family:var(--display);font-size:16px;font-weight:600;letter-spacing:-.015em}
.showcase-card-meta{font-family:var(--mono);font-size:9.5px;color:var(--muted);letter-spacing:.04em}
.showcase-card-thumb{height:240px;background:linear-gradient(135deg,var(--bone) 0%,var(--bone2) 100%);display:grid;place-items:center;color:var(--muted);font-family:var(--mono);font-size:11px}
.showcase-card-ft{padding:14px 20px;font-size:12.5px;color:var(--ink3);border-top:1px solid var(--rule)}

.footer{background:var(--ink);color:var(--paper);padding:96px 0 40px}
.footer h2{font-family:var(--display);font-size:clamp(36px,4.6vw,56px);line-height:1.08;letter-spacing:-.03em;font-weight:600;margin-bottom:36px}
.footer-ctas{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:80px}
.footer .btn.primary{background:var(--paper);color:var(--ink)}
.footer .btn.primary:hover{background:#fff}
.footer .btn.ghost{color:var(--paper);border-color:rgba(244,240,234,.2)}
.footer .btn.ghost:hover{background:rgba(244,240,234,.06);border-color:rgba(244,240,234,.35)}
.footer-note{padding-top:36px;border-top:1px solid rgba(244,240,234,.12);font-family:var(--mono);font-size:11px;color:rgba(244,240,234,.5);letter-spacing:.06em;display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px}
.footer-note em{font-family:var(--serif);font-style:italic;letter-spacing:0;font-size:15px;color:rgba(244,240,234,.75)}

@media (max-width: 1000px){
  .wf-grid{grid-template-columns:1fr}
  .benefits{grid-template-columns:1fr}
}
@media (max-width: 768px){
  .nav-links a:not(.nav-cta){display:none}
}
`;

export default function Homepage() {
  const navRef = useRef<HTMLElement>(null);
  const [tellOpen, setTellOpen] = useState(false);
  const [tellText, setTellText] = useState("");
  const [tellSent, setTellSent] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [emailCopied, setEmailCopied] = useState(false);

  useEffect(() => {
    document.documentElement.classList.add("js-anim");

    setTimeout(() => {
      document.querySelectorAll(".reveal:not(.in)").forEach((el) =>
        el.classList.add("in")
      );
    }, 0);

    const nav = navRef.current;
    if (!nav) return;
    let lastY = 0;
    const onScroll = () => {
      const y = window.scrollY;
      if (y > 60 && y > lastY) nav.classList.add("scrolled");
      else if (y < 30) nav.classList.remove("scrolled");
      lastY = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            observer.unobserve(e.target);
          }
        });
      },
      { threshold: 0, rootMargin: "0px 0px 100px 0px" }
    );
    document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));

    return () => {
      window.removeEventListener("scroll", onScroll);
      observer.disconnect();
      document.documentElement.classList.remove("js-anim");
    };
  }, []);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />

      {/* Nav */}
      <nav className="nav" ref={navRef}>
        <div className="nav-inner">
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: 1 }}>
            <div className="brand">MARVIN</div>
            <span style={{ fontFamily: "var(--mono)", fontSize: "9px", fontWeight: 500, color: "var(--muted)", letterSpacing: ".06em", marginTop: "2px" }}>
              by H&amp;ai
            </span>
          </div>
          <div className="nav-links">
            <a href="#workflow">How it works</a>
            <a href="#missions">Missions</a>
            <a href="#team">The team</a>
            <button onClick={() => setContactOpen(true)} style={{ fontFamily: "inherit", fontSize: "13px", color: "var(--ink3)", fontWeight: 500, background: "none", border: "none", cursor: "pointer", transition: "color .15s", padding: 0 }}>Contact</button>
            <a href="/missions" className="nav-cta" style={{ color: "#F4F0EA" }}>Start a mission →</a>
          </div>
        </div>
      </nav>

      {/* 1. Hero */}
      <section className="hero" style={{ background: "var(--paper)", padding: 0, display: "block", minHeight: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", minHeight: "auto", alignItems: "center", width: "100%", maxWidth: "100%", overflow: "hidden" }}>
          {/* Left: text */}
          <div style={{ padding: "120px 5% 80px calc(max(32px, (100vw - 1200px) / 2 + 32px))" }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: "9.5px", fontWeight: 600, color: "var(--muted)", letterSpacing: ".12em", textTransform: "uppercase", marginBottom: "24px" }}>
              AI-AUGMENTED CONSULTING OPERATIONS
            </div>
            <h1 style={{ fontFamily: "'Bricolage Grotesque',var(--display)", fontSize: "clamp(44px,4vw,72px)", fontWeight: 700, lineHeight: 1.01, letterSpacing: "-.04em", color: "var(--ink)", margin: "0 0 18px 0", whiteSpace: "nowrap" }}>
              Do more for more clients.
            </h1>
            <p style={{ fontFamily: "'Bricolage Grotesque',var(--display)", fontSize: "clamp(20px,2vw,26px)", fontWeight: 700, letterSpacing: "-.02em", color: "var(--ink2)", margin: "0 0 40px 0", lineHeight: 1.2 }}>
              Focus on judgment during your consulting missions.
            </p>
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <a href="/missions" className="btn primary" style={{ fontSize: "14px", padding: "12px 20px", whiteSpace: "nowrap", color: "#F4F0EA" }}>
                Start a mission{" "}
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </a>
              <a href="#workflow" className="btn ghost" style={{ fontSize: "14px", padding: "12px 20px", whiteSpace: "nowrap" }}>
                See how it works
              </a>
            </div>
          </div>

          {/* Right: hero image */}
          <div style={{ alignSelf: "stretch", display: "flex", alignItems: "center", overflow: "visible", minWidth: 0 }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img style={{ width: "100%", height: "auto", display: "block", maxWidth: "100%" }} src="/homepage-hero.png" alt="MARVIN platform preview" />
          </div>
        </div>

        {/* Ticker */}
        <div className="ticker-wrap">
          <div className="ticker-track">
            {[
              { v: "5 days", k: "Full CDD delivered" },
              { v: "5×", k: "Mission capacity" },
              { v: "5×", k: "More interviews with experts found more easily" },
              { v: "0", k: "Slides built by seniors" },
              { v: "100%", k: "Claims traced to source" },
              { v: "10 days", k: "From teaser to IC memo" },
              { v: "5 days", k: "Full CDD delivered" },
              { v: "5×", k: "Mission capacity" },
              { v: "5×", k: "More interviews with experts found more easily" },
              { v: "0", k: "Slides built by seniors" },
              { v: "100%", k: "Claims traced to source" },
              { v: "10 days", k: "From teaser to IC memo" },
            ].map((item, i) => (
              <div key={i} className="ticker-item">
                <span className="ticker-v">{item.v}</span>
                <span className="ticker-k">{item.k}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 3. What Changes + Core Value */}
      <section className="s-changes">
        <div className="wrap">
          <div className="eyebrow reveal">WHAT CHANGES</div>
          <h2 className="reveal reveal-delay-1" style={{ marginBottom: "20px" }}>
            When MARVIN runs the mechanical work,
            <br />your team can do more of what matters.
          </h2>
          <p className="reveal reveal-delay-2" style={{ fontSize: "17px", color: "var(--ink2)", maxWidth: "760px", lineHeight: 1.6, marginBottom: "64px" }}>
            MARVIN runs the numbers, does the desk research, writes the documents, so your consultants can focus on the thinking, gather more insights from experts and build stronger connections with clients.
          </p>

          <div className="benefits">
            {[
              {
                name: "Speed",
                body: "MARVIN delivers a first structured output within hours and a full engagement in days, not weeks, so your team stays available for what matters most.",
                from: ["Research taking days", "Deals turned down due to limited capacity"],
                to: ["First structured output in one day", "Accepting mandates that previously had no available team"],
              },
              {
                name: "Depth",
                body: "Every engagement goes further because agents source more data, challenge more sources, and conduct more expert interviews than your team could manage under time pressure.",
                from: ["Limited data found due to time constraints", "Limited expert interviews due to time spent on production"],
                to: ["More reliable data and triangulated faster", "More expert interviews, more depth per engagement"],
              },
              {
                name: "Focus",
                body: "Your seniors spend their time in client conversations, on-site visits, and expert interviews — not reconciling models or formatting outputs.",
                from: ["Seniors formatting outputs and reconciling models", "Office-bound analysis work"],
                to: ["Seniors in client conversations and expert interviews", "More on-site visits, more client interactions"],
              },
              {
                name: "Scale",
                body: "The same team handles more mandates and deeper workstreams because the capacity ceiling was always the mechanical work, not the thinking.",
                from: ["Assumptions buried in models", "Hypotheses abandoned without documentation"],
                to: ["Every claim traced to a source, every inference labeled", "Every abandoned hypothesis documented with its reason"],
              },
            ].map((b, i) => (
              <div key={b.name} className={`benefit reveal${i > 0 ? ` reveal-delay-${i}` : ""}`}>
                <div className="benefit-name">{b.name}</div>
                <div className="benefit-body" style={{ marginBottom: "20px" }}>{b.body}</div>
                <div style={{ border: "1px solid var(--rule)", borderRadius: "8px", overflow: "hidden", fontSize: "13px" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", background: "var(--rule)" }}>
                    <div style={{ padding: "6px 12px", background: "var(--bone)", fontFamily: "var(--mono)", fontSize: "9px", fontWeight: 600, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--muted)" }}>From</div>
                    <div style={{ padding: "6px 12px", background: "var(--bone)", fontFamily: "var(--mono)", fontSize: "9px", fontWeight: 600, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink)" }}>To</div>
                  </div>
                  {b.from.map((f, j) => (
                    <div key={j} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1px", background: "var(--rule)" }}>
                      <div style={{ padding: "11px 12px", background: "var(--paper)", lineHeight: 1.5, color: "var(--ink2)" }}>{f}</div>
                      <div style={{ padding: "11px 12px", background: "var(--bone)", lineHeight: 1.5, color: "var(--ink)", fontWeight: 500 }}>{b.to[j]}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 4. Workflow */}
      <section id="workflow" className="s-workflow">
        <div className="wrap">
          <div className="eyebrow reveal">THE WORKFLOW</div>
          <h2 className="reveal reveal-delay-1">
            You define the mission.
            <br />MARVIN runs the work.
            <br />You make the decisions.
          </h2>
          <div className="wf-grid">
            {[
              { n: "STEP 1", name: "Brief", body: "Define the target, the client, the central investment question. Ten minutes. The specialist AI agents configure automatically from there.", delay: "" },
              { n: "STEP 2", name: "Execute", body: "Specialist AI agents work across every workstream. You are free to focus on what only you can do.", delay: " reveal-delay-2" },
              { n: "STEP 3", name: "Decide", body: "At structured gates, your judgment applies. Validate findings. Challenge the storyline. Name the weak link. You intervene only where your level is required.", delay: " reveal-delay-4" },
            ].map((step) => (
              <div key={step.n} className={`wf reveal${step.delay}`}>
                <div className="wf-top">
                  <div className="wf-n">{step.n}</div>
                  <div className="wf-name">{step.name}</div>
                </div>
                <div className="wf-body">{step.body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 5. Mission types */}
      <section id="missions" className="s-missions" style={{ paddingBottom: "48px" }}>
        <div className="wrap">
          <div className="eyebrow reveal">MISSION TYPES</div>
          <h2 className="reveal reveal-delay-1">
            Built for specific types of consulting work — the engagements where analytical rigor and speed matter most.
          </h2>

          <div className="mcat reveal reveal-delay-2" style={{ border: "1.5px solid rgba(45,122,78,.3)", background: "rgba(45,122,78,.04)" }}>
            <div className="mcat-hd" style={{ paddingBottom: "20px" }}>
              <div className="mcat-left" style={{ flexDirection: "column", alignItems: "flex-start", gap: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <div className="mcat-name">Commercial Due Diligence</div>
                  <div className="mcat-status active">Active</div>
                </div>
                <div style={{ fontSize: "14px", color: "var(--ink2)", lineHeight: 1.6, maxWidth: "700px", fontWeight: 400 }}>
                  Full-stack CDD in days, not weeks. Market sizing, competitive landscape, hypothesis validation, red-team analysis, and IC memo — all structured, all sourced, all defensible.
                </div>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "4px" }}>
                  {["Market sizing", "Competitive landscape", "Red-team", "IC memo", "Expert interviews"].map((tag) => (
                    <span key={tag} style={{ fontFamily: "var(--mono)", fontSize: "10px", fontWeight: 600, letterSpacing: ".06em", padding: "4px 10px", borderRadius: "5px", background: "rgba(45,122,78,.1)", color: "rgba(45,122,78,.85)", border: "1px solid rgba(45,122,78,.2)" }}>{tag}</span>
                  ))}
                </div>
              </div>
              <a href="/missions" style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: "6px", padding: "10px 18px", borderRadius: "8px", background: "var(--ink)", color: "#F4F0EA", fontFamily: "var(--sans)", fontSize: "13px", fontWeight: 600, textDecoration: "none", alignSelf: "flex-start" }}>
                Start
                <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </a>
            </div>
          </div>

          <div className="mcat reveal reveal-delay-3">
            <div className="mcat-hd">
              <div className="mcat-left">
                <div className="mcat-name">Strategy</div>
                <div className="mcat-status soon">In development</div>
              </div>
            </div>
          </div>

          <div className="mcat reveal reveal-delay-4">
            <div className="mcat-hd">
              <div className="mcat-left">
                <div className="mcat-name">AI Implementation Roadmap</div>
                <div className="mcat-status soon">In development</div>
              </div>
            </div>
          </div>

          <div className="mcat reveal reveal-delay-5" style={{ borderStyle: "dashed", opacity: 0.75 }}>
            <div className="mcat-hd" style={{ flexDirection: "column", alignItems: "flex-start", gap: "10px" }}>
              <div className="mcat-left" style={{ flexDirection: "column", alignItems: "flex-start", gap: "8px" }}>
                <div className="mcat-name">More engagement types in development</div>
                <div style={{ fontSize: "14px", color: "var(--ink2)", lineHeight: 1.55, fontWeight: 400, maxWidth: "600px" }}>
                  Board preparation, competitive intelligence, growth diagnostics, AI implementation roadmaps, M&amp;A target screening.
                </div>
                {!tellOpen && !tellSent && (
                  <button className="btn ghost" onClick={() => setTellOpen(true)} style={{ fontSize: "12.5px", padding: "8px 16px", marginTop: "4px" }}>
                    Tell us what you need →
                  </button>
                )}
                {tellOpen && !tellSent && (
                  <div style={{ display: "flex", gap: "8px", marginTop: "4px", width: "100%", maxWidth: "500px" }}>
                    <input
                      autoFocus
                      type="text"
                      value={tellText}
                      onChange={(e) => setTellText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && tellText.trim()) {
                          setTellSent(true);
                          setTellOpen(false);
                        }
                        if (e.key === "Escape") { setTellOpen(false); setTellText(""); }
                      }}
                      placeholder="What type of engagement do you need?"
                      style={{ flex: 1, padding: "8px 12px", borderRadius: "6px", border: "1px solid var(--rule-s)", background: "var(--paper)", fontSize: "13px", fontFamily: "var(--sans)", outline: "none" }}
                    />
                    <button
                      onClick={() => {
                        if (tellText.trim()) {
                          setTellSent(true);
                          setTellOpen(false);
                        }
                      }}
                      style={{ padding: "8px 14px", borderRadius: "6px", background: "var(--ink)", color: "var(--paper)", fontSize: "12.5px", fontWeight: 600, fontFamily: "var(--sans)", border: "none", cursor: "pointer" }}
                    >
                      Send →
                    </button>
                  </div>
                )}
                {tellSent && (
                  <div style={{ marginTop: "4px", fontFamily: "var(--mono)", fontSize: "11px", color: "var(--ok)", letterSpacing: ".04em" }}>
                    Thanks — we&apos;ll be in touch.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 7. What you deliver */}
      <section className="s-deliver" style={{ padding: "48px 0 80px" }}>
        <div className="wrap">
          <div className="eyebrow reveal">CLIENT-READY OUTPUT</div>
          <h2 className="reveal reveal-delay-1">Client-ready output. Every claim defended.</h2>
          <p className="body reveal reveal-delay-2">
            MARVIN doesn&apos;t produce summaries. It produces structured findings — each labeled by confidence level, traced to its source, reasoning chain explicit. Your name goes on the report. You defend every line.
          </p>
        </div>

        <div className="showcase reveal reveal-delay-4" style={{ maxWidth: "1200px", margin: "0 auto", padding: "0 32px" }}>
          <div className="showcase-track" style={{ paddingBottom: "32px" }}>

            {/* IC Memo */}
            <div className="showcase-card">
              <div className="showcase-card-hd">
                <div className="showcase-card-name">IC Memo</div>
                <div className="showcase-card-meta">Commercial Due Diligence</div>
              </div>
              <div className="showcase-card-thumb" style={{ padding: 0, overflow: "hidden" }}>
                <svg viewBox="0 0 340 200" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
                  <rect width="340" height="200" fill="#E4DDCC"/>
                  <rect x="36" y="16" width="268" height="168" rx="2" fill="#F4F0EA" stroke="rgba(26,24,20,.18)" strokeWidth="1"/>
                  <rect x="36" y="16" width="268" height="26" fill="rgba(26,24,20,.08)"/>
                  <text x="50" y="33" fontFamily="'Geist Mono',monospace" fontSize="7.5" fontWeight="600" fill="rgba(26,24,20,.75)" letterSpacing=".8">INVESTMENT COMMITTEE MEMO</text>
                  <text x="50" y="56" fontFamily="'Geist Mono',monospace" fontSize="5" fontWeight="600" fill="rgba(26,24,20,.5)" letterSpacing=".4">HYPOTHESES</text>
                  <line x1="50" y1="59" x2="290" y2="59" stroke="rgba(26,24,20,.12)" strokeWidth=".6"/>
                  {[
                    { y: 68, label: "H1  Large and growing market", verdict: "✓", vc: "rgba(45,110,78,.8)", vx: 272, partial: false },
                    { y: 80, label: "H2  Strong value proposition", verdict: "✓", vc: "rgba(45,110,78,.8)", vx: 272, partial: false },
                    { y: 92, label: "H3  Scalable business model", verdict: "✓", vc: "rgba(45,110,78,.8)", vx: 272, partial: false },
                    { y: 104, label: "H4  Defensible moat", verdict: "Partial", vc: "rgba(139,98,0,.7)", vx: 256, partial: true },
                    { y: 116, label: "H5  Attractive unit economics", verdict: "✓", vc: "rgba(45,110,78,.8)", vx: 272, partial: false },
                    { y: 128, label: "H6  Experienced management", verdict: "✓", vc: "rgba(45,110,78,.8)", vx: 272, partial: false },
                  ].map((row) => (
                    <g key={row.y}>
                      <text x="54" y={row.y} fontFamily="'Geist Mono',monospace" fontSize="4.5" fill="rgba(26,24,20,.6)">{row.label}</text>
                      <text x={row.vx} y={row.y} fontFamily="'Geist Mono',monospace" fontSize={row.partial ? "4.5" : "6"} fill={row.vc} textAnchor="end">{row.verdict}</text>
                      <line x1="50" y1={row.y + 3} x2="290" y2={row.y + 3} stroke="rgba(26,24,20,.06)" strokeWidth=".5"/>
                    </g>
                  ))}
                  <rect x="50" y="140" width="240" height="32" rx="2" fill="rgba(26,24,20,.05)" stroke="rgba(26,24,20,.22)" strokeWidth="1"/>
                  <text x="62" y="153" fontFamily="'Geist Mono',monospace" fontSize="5" fontWeight="600" fill="rgba(26,24,20,.55)" letterSpacing=".4">RECOMMENDATION</text>
                  <text x="175" y="157" fontFamily="'Geist Mono',monospace" fontSize="13" fontWeight="700" fill="rgba(26,24,20,.85)" textAnchor="middle">INVEST</text>
                  <rect x="262" y="143" width="16" height="16" rx="1.5" fill="none" stroke="rgba(26,24,20,.55)" strokeWidth="1.2"/>
                  <path d="M264.5 151l3.5 3.5 7-7" stroke="rgba(26,24,20,.7)" strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                  <text x="62" y="166" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.4)">High conviction · pp. 55-58 scenario analysis</text>
                </svg>
              </div>
              <div className="showcase-card-ft">65 pages · 142 claims sourced · 6 hypotheses tested</div>
            </div>

            {/* Market Sizing */}
            <div className="showcase-card">
              <div className="showcase-card-hd">
                <div className="showcase-card-name">Market Sizing</div>
                <div className="showcase-card-meta">Commercial Due Diligence</div>
              </div>
              <div className="showcase-card-thumb" style={{ padding: 0, overflow: "hidden" }}>
                <svg viewBox="0 0 340 200" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
                  <rect width="340" height="200" fill="#E4DDCC"/>
                  <rect x="20" y="12" width="300" height="176" rx="2" fill="#F4F0EA" stroke="rgba(26,24,20,.1)" strokeWidth=".8"/>
                  <text x="30" y="28" fontFamily="'Geist Mono',monospace" fontSize="7" fontWeight="600" fill="rgba(26,24,20,.7)" letterSpacing=".5">MARKET SIZING ANALYSIS</text>
                  <line x1="30" y1="32" x2="310" y2="32" stroke="rgba(26,24,20,.15)" strokeWidth=".8"/>
                  <text x="30" y="46" fontFamily="'Geist Mono',monospace" fontSize="5" fill="rgba(26,24,20,.5)">MARKET GROWTH (TAM) · $B</text>
                  <line x1="42" y1="52" x2="42" y2="125" stroke="rgba(26,24,20,.2)" strokeWidth=".8"/>
                  <line x1="42" y1="125" x2="155" y2="125" stroke="rgba(26,24,20,.2)" strokeWidth=".8"/>
                  <line x1="42" y1="85" x2="155" y2="85" stroke="rgba(26,24,20,.07)" strokeWidth=".5" strokeDasharray="2,2"/>
                  <line x1="42" y1="105" x2="155" y2="105" stroke="rgba(26,24,20,.07)" strokeWidth=".5" strokeDasharray="2,2"/>
                  <rect x="49" y="104" width="14" height="21" fill="rgba(26,24,20,.18)"/>
                  <rect x="67" y="97" width="14" height="28" fill="rgba(26,24,20,.22)"/>
                  <rect x="85" y="87" width="14" height="38" fill="rgba(26,24,20,.28)"/>
                  <rect x="103" y="78" width="14" height="47" fill="rgba(26,24,20,.22)"/>
                  <rect x="121" y="68" width="14" height="57" fill="rgba(26,24,20,.35)"/>
                  {[["2022",53,102,128],["2023",71,95,142],["2024E",89,85,156],["2025E",107,76,171],["2026E",125,66,186]].map(([yr,cx,ty,val]) => (
                    <g key={yr as string}>
                      <text x={cx as number} y="133" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.45)" textAnchor="middle">{yr}</text>
                      <text x={cx as number} y={ty as number} fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.5)" textAnchor="middle">{val}</text>
                    </g>
                  ))}
                  <text x="175" y="46" fontFamily="'Geist Mono',monospace" fontSize="5" fill="rgba(26,24,20,.5)">MARKET SIZE (USD)</text>
                  <rect x="170" y="52" width="125" height="76" rx="3" fill="rgba(26,24,20,.06)" stroke="rgba(26,24,20,.18)" strokeWidth="1"/>
                  <text x="183" y="65" fontFamily="'Geist Mono',monospace" fontSize="5" fill="rgba(26,24,20,.5)">TAM</text>
                  <text x="248" y="65" fontFamily="'Geist Mono',monospace" fontSize="6.5" fontWeight="600" fill="rgba(26,24,20,.75)" textAnchor="middle">$186B</text>
                  <rect x="180" y="70" width="105" height="34" rx="2" fill="rgba(26,24,20,.06)" stroke="rgba(26,24,20,.15)" strokeWidth=".8"/>
                  <text x="191" y="82" fontFamily="'Geist Mono',monospace" fontSize="5" fill="rgba(26,24,20,.5)">SAM</text>
                  <text x="248" y="82" fontFamily="'Geist Mono',monospace" fontSize="6" fontWeight="600" fill="rgba(26,24,20,.7)" textAnchor="middle">$42B</text>
                  <rect x="192" y="87" width="80" height="14" rx="2" fill="rgba(26,24,20,.08)" stroke="rgba(26,24,20,.2)" strokeWidth=".8"/>
                  <text x="202" y="96" fontFamily="'Geist Mono',monospace" fontSize="4.5" fill="rgba(26,24,20,.5)">SOM</text>
                  <text x="248" y="96" fontFamily="'Geist Mono',monospace" fontSize="5" fontWeight="600" fill="rgba(26,24,20,.7)" textAnchor="middle">$6.3B</text>
                  <text x="30" y="185" fontFamily="'Geist Mono',monospace" fontSize="3.5" fill="rgba(26,24,20,.35)">SOURCES: IDC Worldwide Security Spend Guide 2024 · Gartner Market Databook 2024</text>
                </svg>
              </div>
              <div className="showcase-card-ft">22 pages · Bottom-up TAM · Penetration analysis</div>
            </div>

            {/* Red-team Memo */}
            <div className="showcase-card">
              <div className="showcase-card-hd">
                <div className="showcase-card-name">Red-team Memo</div>
                <div className="showcase-card-meta">Red-team</div>
              </div>
              <div className="showcase-card-thumb" style={{ padding: 0, overflow: "hidden" }}>
                <svg viewBox="0 0 340 200" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
                  <rect width="340" height="200" fill="#E4DDCC"/>
                  <rect x="20" y="12" width="300" height="176" rx="2" fill="#F4F0EA" stroke="rgba(26,24,20,.1)" strokeWidth=".8"/>
                  <text x="30" y="28" fontFamily="'Geist Mono',monospace" fontSize="7" fontWeight="600" fill="rgba(26,24,20,.7)" letterSpacing=".5">RED-TEAM ANALYSIS</text>
                  <line x1="30" y1="32" x2="310" y2="32" stroke="rgba(180,58,46,.25)" strokeWidth="1"/>
                  <text x="30" y="42" fontFamily="'Geist Mono',monospace" fontSize="4.5" fontWeight="600" fill="rgba(26,24,20,.5)" letterSpacing=".3">RISK REGISTER</text>
                  <rect x="30" y="46" width="3" height="28" rx="1" fill="rgba(180,58,46,.7)"/>
                  <text x="38" y="55" fontFamily="'Geist Mono',monospace" fontSize="4" fontWeight="600" fill="rgba(180,58,46,.8)">HIGH · Customer concentration</text>
                  <text x="38" y="62" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.55)">Top 12 accounts = 23% ARR. Two contracts</text>
                  <text x="38" y="69" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.55)">with 90-day exit clauses, renewal imminent.</text>
                  <line x1="30" y1="78" x2="310" y2="78" stroke="rgba(26,24,20,.08)" strokeWidth=".5"/>
                  <rect x="30" y="81" width="3" height="28" rx="1" fill="rgba(139,98,0,.6)"/>
                  <text x="38" y="90" fontFamily="'Geist Mono',monospace" fontSize="4" fontWeight="600" fill="rgba(139,98,0,.8)">MEDIUM · Competitive window</text>
                  <text x="38" y="97" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.55)">CrowdStrike mid-market program launch</text>
                  <text x="38" y="104" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.55)">estimated 35% probability within 24 months.</text>
                  <line x1="30" y1="113" x2="310" y2="113" stroke="rgba(26,24,20,.08)" strokeWidth=".5"/>
                  <rect x="30" y="116" width="3" height="28" rx="1" fill="rgba(139,98,0,.5)"/>
                  <text x="38" y="125" fontFamily="'Geist Mono',monospace" fontSize="4" fontWeight="600" fill="rgba(139,98,0,.75)">MEDIUM · Key-man dependency</text>
                  <text x="38" y="132" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.55)">CTO authored 68% of detection logic.</text>
                  <text x="38" y="139" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.55)">CTO/CPO tension flagged in 3 interviews.</text>
                  <line x1="30" y1="148" x2="310" y2="148" stroke="rgba(26,24,20,.08)" strokeWidth=".5"/>
                  <rect x="30" y="151" width="3" height="18" rx="1" fill="rgba(26,24,20,.3)"/>
                  <text x="38" y="160" fontFamily="'Geist Mono',monospace" fontSize="4" fontWeight="600" fill="rgba(26,24,20,.55)">LOW · FedRAMP certification gap</text>
                  <text x="38" y="167" fontFamily="'Geist Mono',monospace" fontSize="4" fill="rgba(26,24,20,.45)">Blocks federal market. 18-month roadmap.</text>
                </svg>
              </div>
              <div className="showcase-card-ft">12 pages · 3 attack vectors · Thesis stress-tested</div>
            </div>

          </div>
        </div>
      </section>

      {/* 6. Team */}
      <section id="team" className="s-team">
        <div className="wrap">
          <div className="eyebrow reveal">THE TEAM</div>
          <h2 className="reveal reveal-delay-1" style={{ maxWidth: "820px" }}>
            Every mission deploys a dedicated team of specialist AI agents, configured for the mission type.
          </h2>
          <p className="sub reveal reveal-delay-2">
            You don&apos;t brief them. They activate when the mission starts. At every gate, your judgment applies.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "10px", marginBottom: "40px", maxWidth: "960px" }} className="reveal reveal-delay-3">
            {[
              { name: "Thesis", desc: "Generates testable hypotheses, selects frameworks, declares the analytical structure before any work begins.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="#1A1814" strokeWidth="1.5" strokeLinecap="round"/></svg> },
              { name: "Dora", desc: "Builds bottom-up TAM, challenges management figures, maps competitive landscape and assesses moat and competitive window.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="#1A1814" strokeWidth="1.5"/><path d="M16.5 16.5L21 21" stroke="#1A1814" strokeWidth="1.5" strokeLinecap="round"/></svg> },
              { name: "Calculus", desc: "Parses data room, detects anomalies between management claims and actual numbers, runs Quality of Earnings and cohort analysis.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M3 17L8 12l4 4 5-7 4 3" stroke="#1A1814" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg> },
              { name: "Lector", desc: "Generates interview guides tailored by profile, structures transcripts, detects patterns across interviews.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 2a4 4 0 014 4v6a4 4 0 01-8 0V6a4 4 0 014-4z" stroke="#1A1814" strokeWidth="1.5"/><path d="M8 14a4 4 0 008 0" stroke="#1A1814" strokeWidth="1.5" strokeLinecap="round"/><path d="M12 18v3" stroke="#1A1814" strokeWidth="1.5" strokeLinecap="round"/></svg> },
            ].map((agent, idx) => (
              idx === 3
                ? (
                  <React.Fragment key={agent.name}>
                    <div style={{ background: "var(--paper)", border: "1px solid var(--rule)", borderRadius: "10px", padding: "18px 20px", display: "flex", gap: "12px" }}>
                      <div style={{ width: "36px", height: "36px", borderRadius: "8px", background: "var(--bone)", border: "1px solid var(--rule-m)", display: "grid", placeItems: "center", flexShrink: 0 }}>{agent.icon}</div>
                      <div>
                        <div style={{ fontFamily: "var(--mono)", fontSize: "12px", fontWeight: 600, color: "var(--ink)", marginBottom: "3px" }}>{agent.name}</div>
                        <div style={{ fontSize: "12px", color: "var(--ink2)", lineHeight: 1.45 }}>{agent.desc}</div>
                      </div>
                    </div>
                    {/* MARVIN center */}
                    <div style={{ background: "var(--ink)", border: "1px solid var(--ink)", borderRadius: "10px", padding: "18px 20px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", minHeight: "110px" }}>
                      <div style={{ fontFamily: "'Bricolage Grotesque',sans-serif", fontSize: "20px", fontWeight: 700, color: "var(--paper)", letterSpacing: ".04em", marginBottom: "4px" }}>MARVIN</div>
                      <div style={{ fontFamily: "var(--mono)", fontSize: "9px", color: "rgba(244,240,234,.5)", letterSpacing: ".08em", textTransform: "uppercase" }}>orchestration</div>
                      <div style={{ fontSize: "11px", color: "rgba(244,240,234,.45)", lineHeight: 1.5, marginTop: "8px", maxWidth: "160px" }}>Coordinates all agents end-to-end across every workstream</div>
                    </div>
                  </React.Fragment>
                )
                : (
                  <div key={agent.name} style={{ background: "var(--paper)", border: "1px solid var(--rule)", borderRadius: "10px", padding: "18px 20px", display: "flex", gap: "12px" }}>
                    <div style={{ width: "36px", height: "36px", borderRadius: "8px", background: "var(--bone)", border: "1px solid var(--rule-m)", display: "grid", placeItems: "center", flexShrink: 0 }}>{agent.icon}</div>
                    <div>
                      <div style={{ fontFamily: "var(--mono)", fontSize: "12px", fontWeight: 600, color: "var(--ink)", marginBottom: "3px" }}>{agent.name}</div>
                      <div style={{ fontSize: "12px", color: "var(--ink2)", lineHeight: 1.45 }}>{agent.desc}</div>
                    </div>
                  </div>
                )
            ))}
            {[
              { name: "Adversus", desc: "Attacks every hypothesis from three angles — empirical, logical, contextual. Identifies the weakest link before it reaches you.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M7 7l10 10M17 7L7 17" stroke="#1A1814" strokeWidth="1.5" strokeLinecap="round"/></svg> },
              { name: "Merlin", desc: "Evaluates whether findings form a coherent, MECE argument. Issues an investment recommendation: Invest, Invest with conditions, Do not invest, or Insufficient evidence.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 3L21 20H3L12 3z" stroke="#1A1814" strokeWidth="1.5" strokeLinejoin="round"/><path d="M8.5 15h7" stroke="#1A1814" strokeWidth="1.5" strokeLinecap="round"/></svg> },
              { name: "Papyrus", desc: "Assembles the full mission state into PDF report, executive summary deck, and data book. Runs pre-flight checks before generation.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><rect x="4" y="2" width="16" height="20" rx="2" stroke="#1A1814" strokeWidth="1.5"/><path d="M8 7h8M8 11h8M8 15h5" stroke="#1A1814" strokeWidth="1.5" strokeLinecap="round"/></svg> },
            ].map((agent) => (
              <div key={agent.name} style={{ background: "var(--paper)", border: "1px solid var(--rule)", borderRadius: "10px", padding: "18px 20px", display: "flex", gap: "12px" }}>
                <div style={{ width: "36px", height: "36px", borderRadius: "8px", background: "var(--bone)", border: "1px solid var(--rule-m)", display: "grid", placeItems: "center", flexShrink: 0 }}>{agent.icon}</div>
                <div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: "12px", fontWeight: 600, color: "var(--ink)", marginBottom: "3px" }}>{agent.name}</div>
                  <div style={{ fontSize: "12px", color: "var(--ink2)", lineHeight: 1.45 }}>{agent.desc}</div>
                </div>
              </div>
            ))}
            <div style={{ background: "var(--bone)", border: "1px dashed var(--rule-m)", borderRadius: "10px", padding: "18px 20px", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: "10px", color: "var(--muted)", textAlign: "center", lineHeight: 1.5 }}>More agents<br />in development</span>
            </div>
          </div>

          <div className="team-gate reveal">
            <p className="team-gate-copy">
              At every gate, your team validates what matters.<br />
              Findings are reviewed. Storylines are challenged. Decisions are human.
            </p>
          </div>
        </div>
      </section>

      {/* 8. Footer CTA */}
      <footer className="footer">
        <div className="wrap">
          <h2 className="reveal">Ready to run your next engagement?</h2>
          <div className="footer-ctas reveal reveal-delay-1">
            <a href="/missions" className="btn primary" style={{ color: "#1A1814" }}>
              Start a mission{" "}
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </a>
            <button className="btn ghost" onClick={() => setContactOpen(!contactOpen)}>
              Contact
            </button>
          </div>


          <div className="footer-note">
            <span>MARVIN · H&amp;ai</span>
            <em>We believe human judgment matters.</em>
          </div>
        </div>
      </footer>

      {/* Contact modal */}
      {contactOpen && (
        <div
          onClick={() => setContactOpen(false)}
          style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(26,24,20,.55)", backdropFilter: "blur(8px)", padding: "24px" }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{ width: "100%", maxWidth: "560px", background: "#1A1814", border: "1px solid rgba(244,240,234,.12)", borderRadius: "18px", overflow: "hidden", boxShadow: "0 32px 80px rgba(0,0,0,.45)" }}
          >
            {/* Header band */}
            <div style={{ background: "rgba(244,240,234,.04)", borderBottom: "1px solid rgba(244,240,234,.08)", padding: "18px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: "9px", fontWeight: 600, letterSpacing: ".14em", textTransform: "uppercase", color: "rgba(244,240,234,.35)" }}>Builder</div>
              <button onClick={() => setContactOpen(false)} style={{ width: "24px", height: "24px", borderRadius: "50%", background: "rgba(244,240,234,.08)", border: "none", cursor: "pointer", display: "grid", placeItems: "center", color: "rgba(244,240,234,.5)", transition: "background .15s" }}>
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1 1l8 8M9 1L1 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
              </button>
            </div>

            {/* Body */}
            <div style={{ padding: "28px 24px 32px" }}>
              {/* Avatar + name */}
              <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "20px" }}>
                <div style={{ width: "52px", height: "52px", borderRadius: "14px", background: "linear-gradient(135deg, rgba(244,240,234,.15) 0%, rgba(244,240,234,.06) 100%)", border: "1px solid rgba(244,240,234,.12)", display: "grid", placeItems: "center", flexShrink: 0 }}>
                  <span style={{ fontFamily: "var(--display)", fontSize: "18px", fontWeight: 700, color: "rgba(244,240,234,.8)", letterSpacing: "-.02em" }}>LD</span>
                </div>
                <div>
                  <div style={{ fontFamily: "var(--display)", fontSize: "20px", fontWeight: 700, letterSpacing: "-.025em", color: "#F4F0EA", lineHeight: 1.1, marginBottom: "4px" }}>Loïc Djayep</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: "10px", color: "rgba(244,240,234,.35)", letterSpacing: ".06em" }}>H&amp;ai · Builder</div>
                </div>
              </div>

              {/* Bio */}
              <div style={{ fontSize: "13.5px", lineHeight: 1.65, color: "rgba(244,240,234,.6)", marginBottom: "24px", paddingBottom: "24px", borderBottom: "1px solid rgba(244,240,234,.08)" }}>
                <div>Harvard MBA Student. Ex-Manager McKinsey&nbsp;&amp;&nbsp;Company</div>
                <div style={{ marginTop: "6px", color: "rgba(244,240,234,.4)", fontSize: "12px" }}>Built with Claude Code, Codex, Antigravity, Cursor, and Gigi (my hermes agent)</div>
              </div>

              {/* Actions */}
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {/* Email row */}
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <a
                    href="mailto:gldjayep@mba2027.hbs.edu"
                    style={{ flex: 1, display: "flex", alignItems: "center", gap: "10px", padding: "13px 16px", borderRadius: "10px", border: "1px solid rgba(244,240,234,.12)", textDecoration: "none", transition: "border-color .15s" }}
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="3" width="12" height="8" rx="1.5" stroke="rgba(244,240,234,.6)" strokeWidth="1.4"/><path d="M1 4l6 4 6-4" stroke="rgba(244,240,234,.6)" strokeWidth="1.4" strokeLinecap="round"/></svg>
                    <span style={{ fontFamily: "var(--sans)", fontSize: "12.5px", fontWeight: 500, color: "rgba(244,240,234,.7)" }}>Send email</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "10px", color: "rgba(244,240,234,.3)", marginLeft: "auto", letterSpacing: ".02em" }}>gldjayep@mba2027.hbs.edu</span>
                  </a>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText("gldjayep@mba2027.hbs.edu");
                      setEmailCopied(true);
                      setTimeout(() => setEmailCopied(false), 2000);
                    }}
                    title="Copy email"
                    style={{ width: "44px", height: "44px", borderRadius: "10px", border: "1px solid rgba(244,240,234,.12)", background: emailCopied ? "rgba(45,122,78,.15)" : "transparent", cursor: "pointer", display: "grid", placeItems: "center", flexShrink: 0, transition: "background .2s" }}
                  >
                    {emailCopied
                      ? <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M2 7l4 4 6-6" stroke="rgba(45,122,78,.9)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      : <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><rect x="4" y="1" width="9" height="9" rx="1.5" stroke="rgba(244,240,234,.5)" strokeWidth="1.3"/><rect x="1" y="4" width="9" height="9" rx="1.5" stroke="rgba(244,240,234,.5)" strokeWidth="1.3"/></svg>
                    }
                  </button>
                </div>

                {/* LinkedIn */}
                <a
                  href="https://www.linkedin.com/in/gilles-lo%C3%AFc-djayep-873992a8"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: "flex", alignItems: "center", gap: "10px", padding: "13px 16px", borderRadius: "10px", border: "1px solid rgba(244,240,234,.12)", textDecoration: "none", transition: "border-color .15s, background .15s" }}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="1" width="12" height="12" rx="2.5" stroke="rgba(244,240,234,.6)" strokeWidth="1.4"/><path d="M4 6v4M4 4.2v.2M7 10V7.5c0-.83.67-1.5 1.5-1.5S10 6.67 10 7.5V10" stroke="rgba(244,240,234,.6)" strokeWidth="1.4" strokeLinecap="round"/></svg>
                  <span style={{ fontFamily: "var(--sans)", fontSize: "12.5px", fontWeight: 500, color: "rgba(244,240,234,.7)" }}>LinkedIn</span>
                  <svg style={{ marginLeft: "auto" }} width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 8L8 2M8 2H4M8 2v4" stroke="rgba(244,240,234,.3)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
