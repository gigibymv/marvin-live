"use client";

import React, { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import Link from "next/link";
import InteractiveMissionLink from "./InteractiveMissionLink";
import MissionArrow from "./MissionArrow";
import "./Homepage.css";

type Stage = "brief" | "research" | "review" | "report";
const STAGES: { id: Stage; label: string; title: string; description: string }[] = [
  { id: "brief", label: "The brief", title: "Should we invest in this company?", description: "You ask Marvin to check whether revenue growth is durable before making a recommendation." },
  { id: "research", label: "The analysis", title: "What the figures tell us", description: "Marvin’s agents check the figures and flag the missing retention data." },
  { id: "review", label: "Your review", title: "Is this enough to conclude?", description: "You decide whether to request more evidence or keep the open question explicit." },
  { id: "report", label: "The report", title: "A report with an open question", description: "Marvin brings the figures, findings and their limits into one document." },
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
  const activeStage = STAGES.find(item => item.id === stage)!;

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
          <nav aria-label="Main navigation"><Link className="open-link" href="/missions?welcome=1">Open Marvin <MissionArrow direction="up-right" /></Link></nav>
        </header>
        <main className="hero product-hero">
          <div className="statement">
            <h1><span>Your consulting</span><span>operating system</span></h1>
            <div className="statement-aside"><p>AI agents work on your mission. You review the evidence and decide what comes next.</p><div className="hero-actions"><InteractiveMissionLink /><a className="example-jump" href="#mission-example" onClick={() => { setStage("brief"); setPlaying(true); }}>See an example <MissionArrow direction="down" /></a></div></div>

          </div>
          <div className="mission-example" id="mission-example" data-ui="illustrative-mission" ref={exampleRef} onMouseLeave={() => setPlaying(true)} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setPlaying(true); }} data-auto-playing={autoPlaying} style={{ "--stage-duration": `${STAGE_DURATION[stage]}ms` } as CSSProperties}>
            <div className="example-header"><div className="example-intro"><strong>Interactive example: <span className="stage-name" key={stage}>{activeStage.label.toLowerCase()}</span></strong><p>A software investment review, using fictional data.</p></div></div>
            <div className="example-tabs" onFocus={() => setPlaying(false)} role="tablist" aria-label="Explore an example mission">
              {STAGES.map((item, index) => <button key={item.id} id={`stage-${item.id}`} role="tab" aria-selected={stage === item.id} aria-controls={`example-${item.id}`} tabIndex={stage === item.id ? 0 : -1} onClick={() => select(item.id)} onKeyDown={event => handleKey(event, index)}><span className="tab-dot" aria-hidden="true" />{item.label}</button>)}
            </div>
            <div className="dossier-layout">
              <aside className="dossier-margin" key={stage}>
                <h2>{activeStage.title}</h2>
                <p className="margin-note">{activeStage.description}</p>
              </aside>
            <div className="example-body" onFocus={() => setPlaying(false)} onPointerDown={() => setPlaying(false)}>
              <div id="example-brief" role="tabpanel" aria-labelledby="stage-brief" className="example-stage" hidden={stage !== "brief"} data-active={stage === "brief"} aria-hidden={stage !== "brief"} tabIndex={stage === "brief" ? 0 : -1}>
                <div className="sample-sheet"><div className="sheet-title"><span><svg width="20" height="24" viewBox="0 0 20 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" aria-hidden="true"><path d="M3 2h9l5 5v15H3Z" /><path d="M12 2v6h5M6 12h8M6 16h8" /></svg>Financial brief.xlsx</span><span>Supplied figures</span></div><dl><div className="revenue-metric"><dt>2024 revenue</dt><dd>€8.0m</dd></div><div className="revenue-metric"><dt>2025 revenue</dt><dd>€10.0m</dd></div><div><dt>Largest customer</dt><dd>45% of revenue</dd></div><div><dt>Customer retention</dt><dd className="missing-data">Not supplied</dd></div></dl></div>
                <button className="example-next" onClick={() => select("research", true)}>See the analysis <MissionArrow /></button>
              </div>
              <div id="example-research" role="tabpanel" aria-labelledby="stage-research" className="example-stage" hidden={stage !== "research"} data-active={stage === "research"} aria-hidden={stage !== "research"} tabIndex={stage === "research" ? 0 : -1}>
                <div className="revenue-comparison" aria-label="Revenue increased from 8 million euros in 2024 to 10 million euros in 2025, up 25 percent"><div><span>2024</span><div className="revenue-bar" style={{width:"80%"}}><strong>€8.0m</strong></div></div><div><span>2025</span><div className="revenue-bar current"><strong>€10.0m</strong><span>+25%</span></div></div></div>
                <div className="analysis-finding"><span className="finding-mark"><MissionArrow direction="up-right" /></span><div><div className="finding-heading"><h3>Revenue grew 25%</h3><span>Calculus</span></div><p>€10.0m ÷ €8.0m − 1</p><button className="source-link" onClick={() => select("brief", true)}>Source: sample financial brief <MissionArrow direction="up-right" /></button></div></div>
                <div className="analysis-finding"><span className="finding-mark" aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.5" /><path d="M12 3.5a8.5 8.5 0 0 0 0 17Z" fill="currentColor" /></svg></span><div><div className="finding-heading"><h3>One customer accounts for 45%</h3><span>Calculus</span></div><p>The investment depends heavily on one relationship.</p><button className="source-link" onClick={() => select("brief", true)}>Source: sample financial brief <MissionArrow direction="up-right" /></button></div></div>
                <div className="analysis-finding"><span className="finding-mark missing-data" aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M8 8a4 4 0 1 1 6.5 3.1C13 12.2 12 12.5 12 15" /><path d="M12 19h.01" /></svg></span><div><div className="finding-heading"><h3>Retention remains unverified</h3><span>Adversus</span></div><p>Growth alone does not establish that customers stay.</p><span className="evidence-gap">Missing evidence · customer retention data</span></div></div>
                <button className="example-next" onClick={() => select("review", true)}>Review the open question <MissionArrow /></button>
              </div>
              <div id="example-review" role="tabpanel" aria-labelledby="stage-review" className="example-stage" hidden={stage !== "review"} data-active={stage === "review"} aria-hidden={stage !== "review"} tabIndex={stage === "review" ? 0 : -1}>
                <div className="review-conversation"><span className="logo-tile" aria-hidden="true">M</span><div><span className="conversation-speaker">Marvin</span><p>Revenue grew, but we don’t know whether customers stay. Request retention data, or keep this gap explicit in the report?</p></div></div>
                <div className="example-choices"><button aria-pressed={requested} onClick={() => setRequested(true)}>Request retention data <MissionArrow direction="up-right" /></button><button onClick={() => select("report", true)}>Preview the report with this gap <MissionArrow /></button></div>
                {requested && <p className="example-feedback" role="status">Example updated: request customer retention figures before concluding on revenue resilience.</p>}
                <p className="example-disclaimer">These controls explore the example. They do not start a live mission.</p>
              </div>
              <div id="example-report" role="tabpanel" aria-labelledby="stage-report" className="example-stage" hidden={stage !== "report"} data-active={stage === "report"} aria-hidden={stage !== "report"} tabIndex={stage === "report" ? 0 : -1}>
                <div className="report-preview"><div className="report-meta">MARVIN <span>Investment review</span></div><h3 className="report-title">Revenue resilience</h3><p className="report-lead">Growth is supported by the supplied figures. Customer durability is still an open question.</p><h3>What the figures show</h3><p>Revenue increased from €8.0m to €10.0m, a 25% increase. The largest customer represents 45% of revenue.</p><h3>What needs to be checked</h3><p>Customer retention data was not supplied. Obtain it before concluding that growth is durable.</p><div className="report-footnote">Source: sample financial brief · All figures are illustrative</div></div>
                <a className="example-next" href="/examples/marvin-illustrative-report.md" download>Download this example <MissionArrow direction="down" /></a>
              </div>
            </div>
            </div>
          </div>
        </main>
        <footer className="bottom"><Link className="footer-brand" href="/">MARVIN</Link><p>A resettable demo. Save the work you want to keep.</p><Link href="/missions?welcome=1">Open workspace <MissionArrow direction="up-right" /></Link></footer>
      </div>
    </div>
  );
}
