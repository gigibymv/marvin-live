"use client";

import React, { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import Link from "next/link";
import InteractiveMissionLink from "./InteractiveMissionLink";
import "./Homepage.css";

type Stage = "brief" | "research" | "review" | "report";
const STAGES: { id: Stage; label: string }[] = [
  { id: "brief", label: "The brief" },
  { id: "research", label: "The analysis" },
  { id: "review", label: "Your review" },
  { id: "report", label: "The report" },
];

const STAGE_DURATION: Record<Stage, number> = { brief: 6000, research: 8000, review: 7000, report: 8000 };

export default function Homepage() {
  const [stage, setStage] = useState<Stage>("brief");
  const [requested, setRequested] = useState(false);
  const [playing, setPlaying] = useState(true);
  const [inView, setInView] = useState(false);
  const [pageVisible, setPageVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(true);
  const exampleRef = useRef<HTMLDivElement>(null);
  const autoPlaying = playing && inView && pageVisible && !reducedMotion;

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncMotion = () => setReducedMotion(preference.matches);
    const syncVisibility = () => setPageVisible(!document.hidden);
    syncMotion();
    syncVisibility();
    preference.addEventListener("change", syncMotion);
    document.addEventListener("visibilitychange", syncVisibility);
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting && entry.intersectionRatio >= 0.2), { threshold: 0.2 });
    if (exampleRef.current) observer.observe(exampleRef.current);
    return () => {
      preference.removeEventListener("change", syncMotion);
      document.removeEventListener("visibilitychange", syncVisibility);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!autoPlaying) return;
    const timer = window.setTimeout(() => {
      const nextIndex = (STAGES.findIndex(item => item.id === stage) + 1) % STAGES.length;
      setStage(STAGES[nextIndex].id);
    }, STAGE_DURATION[stage]);
    return () => window.clearTimeout(timer);
  }, [stage, autoPlaying]);

  function select(next: Stage, focus = false) {
    setPlaying(false);
    setStage(next);
    if (focus) document.getElementById(`stage-${next}`)?.focus();
  }

  function handleKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    if (event.key === "ArrowRight") next = (index + 1) % STAGES.length;
    else if (event.key === "ArrowLeft") next = (index + STAGES.length - 1) % STAGES.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = STAGES.length - 1;
    else return;
    event.preventDefault();
    select(STAGES[next].id, true);
  }

  return (
    <div className="marvin-landing">
      <div className="wrap">
        <header className="nav">
          <Link className="brand" href="/"><strong>MARVIN</strong><span>by H&ai</span></Link>
          <nav aria-label="Main navigation"><Link className="open-link" href="/missions?welcome=1">Open Marvin</Link></nav>
        </header>
        <main className="hero product-hero">
          <div className="statement">
            <h1><span>Your consulting</span><span>operating system</span></h1>
            <p>MARVIN assigns the research and analysis for your mission to AI agents, then brings their work back for your review.</p>
            <div className="hero-actions"><InteractiveMissionLink /></div>

          </div>
          <div className="mission-example" ref={exampleRef} data-auto-playing={autoPlaying} style={{ "--stage-duration": `${STAGE_DURATION[stage]}ms` } as CSSProperties}>
            <div className="example-header"><span className="logo-tile" aria-hidden="true">M</span><strong>A software investment review</strong><span className="preview-label">Illustrative</span><button className="example-playback" aria-label={reducedMotion ? "Automatic playback disabled for reduced motion" : playing ? "Pause example" : "Play example"} aria-pressed={playing && !reducedMotion} disabled={reducedMotion} onClick={() => setPlaying(value => !value)}><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">{playing && !reducedMotion ? <path d="M4 3h3v10H4zm5 0h3v10H9z" /> : <path d="m5 3 8 5-8 5z" />}</svg></button></div>
            <div className="example-tabs" onFocus={() => setPlaying(false)} role="tablist" aria-label="Explore an example mission">
              {STAGES.map((item, index) => <button key={item.id} id={`stage-${item.id}`} role="tab" aria-selected={stage === item.id} aria-controls={`example-${item.id}`} tabIndex={stage === item.id ? 0 : -1} onClick={() => select(item.id)} onKeyDown={event => handleKey(event, index)}><span aria-hidden="true">0{index + 1}</span>{item.label}</button>)}
            </div>
            <div className="example-body" onFocus={() => setPlaying(false)} onPointerDown={() => setPlaying(false)}>
              <div id="example-brief" role="tabpanel" aria-labelledby="stage-brief" className="example-stage" data-active={stage === "brief"} aria-hidden={stage !== "brief"} tabIndex={stage === "brief" ? 0 : -1}>
                <h2>Should we invest in this company?</h2>
                <p className="sample-question">Assess revenue resilience. Check growth, customer concentration and retention before making a recommendation.</p>
                <div className="sample-sheet"><div className="sheet-title">Sample financial brief <span>.xlsx</span></div><dl><div><dt>2024 revenue</dt><dd>€8.0m</dd></div><div><dt>2025 revenue</dt><dd>€10.0m</dd></div><div><dt>Largest customer</dt><dd>45% of revenue</dd></div><div><dt>Customer retention</dt><dd className="missing-data">Not supplied</dd></div></dl></div>
                <button className="example-next" onClick={() => select("research", true)}>See what MARVIN finds <span aria-hidden="true">→</span></button>
              </div>
              <div id="example-research" role="tabpanel" aria-labelledby="stage-research" className="example-stage" data-active={stage === "research"} aria-hidden={stage !== "research"} tabIndex={stage === "research" ? 0 : -1}>
                <h2>Revenue growth and customer risk</h2>
                <div className="analysis-finding"><span className="finding-mark" aria-hidden="true">↗</span><div><div className="finding-heading"><h3>Revenue grew 25%</h3><span>Calculus</span></div><p>€10.0m ÷ €8.0m − 1</p><button className="source-link" onClick={() => select("brief", true)}>Source: sample financial brief ↗</button></div></div>
                <div className="analysis-finding"><span className="finding-mark" aria-hidden="true">◐</span><div><div className="finding-heading"><h3>One customer accounts for 45%</h3><span>Calculus</span></div><p>The investment depends heavily on one relationship.</p><button className="source-link" onClick={() => select("brief", true)}>Source: sample financial brief ↗</button></div></div>
                <div className="analysis-finding"><span className="finding-mark missing-data" aria-hidden="true">?</span><div><div className="finding-heading"><h3>Retention remains unverified</h3><span>Adversus</span></div><p>Growth alone does not establish that customers stay.</p><span className="evidence-gap">Missing evidence · customer retention data</span></div></div>
                <button className="example-next" onClick={() => select("review", true)}>Review the open question <span aria-hidden="true">→</span></button>
              </div>
              <div id="example-review" role="tabpanel" aria-labelledby="stage-review" className="example-stage" data-active={stage === "review"} aria-hidden={stage !== "review"} tabIndex={stage === "review" ? 0 : -1}>
                <h2>You decide what needs more work</h2>
                <div className="review-conversation"><span className="logo-tile" aria-hidden="true">M</span><p>We have revenue growth and concentration figures, but no retention data. Should the report leave this question open, or should we request the figures first?</p></div>
                <div className="example-choices"><button aria-pressed={requested} onClick={() => setRequested(true)}>Request retention data <span aria-hidden="true">↗</span></button><button onClick={() => select("report", true)}>Preview the report with this gap <span aria-hidden="true">→</span></button></div>
                {requested && <p className="example-feedback" role="status">Example updated: request customer retention figures before concluding on revenue resilience.</p>}
                <p className="example-disclaimer">These controls explore the example. They do not start a live mission.</p>
              </div>
              <div id="example-report" role="tabpanel" aria-labelledby="stage-report" className="example-stage" data-active={stage === "report"} aria-hidden={stage !== "report"} tabIndex={stage === "report" ? 0 : -1}>
                <div className="report-preview"><div className="report-meta">MARVIN <span>Illustrative report · 01</span></div><h2>Revenue resilience</h2><p className="report-lead">Growth is supported by the supplied figures. Customer durability is still an open question.</p><h3>What the figures show</h3><p>Revenue increased from €8.0m to €10.0m, a 25% increase. The largest customer represents 45% of revenue.</p><h3>What needs to be checked</h3><p>Customer retention data was not supplied. Obtain it before concluding that growth is durable.</p><div className="report-footnote">Source: sample financial brief · All figures are illustrative</div></div>
                <a className="example-next" href="/examples/marvin-illustrative-report.md" download>Download this example <span aria-hidden="true">↓</span></a>
              </div>
            </div>
            <p className="example-caption">Explore the same mission from input to report. All figures are sample data.</p>
          </div>
        </main>
        <footer className="bottom"><span className="footer-brand">MARVIN</span><p>The demo can reset. Save any work you need.</p><p><Link href="/missions?welcome=1">Open workspace</Link></p></footer>
      </div>
    </div>
  );
}
