"use client";

import { useState, type KeyboardEvent } from "react";
import Link from "next/link";
import "./Homepage.css";

type PreviewView = "framing" | "review" | "brief";
const VIEWS: PreviewView[] = ["framing", "review", "brief"];

export default function Homepage() {
  const [view, setView] = useState<PreviewView>("framing");

  function selectView(next: PreviewView, focus = false) {
    setView(next);
    if (focus) document.getElementById(`tab-${next}`)?.focus();
  }

  function handleTabKey(event: KeyboardEvent<HTMLButtonElement>, current: PreviewView) {
    const index = VIEWS.indexOf(current);
    let next: PreviewView;
    if (event.key === "ArrowRight") next = VIEWS[(index + 1) % VIEWS.length];
    else if (event.key === "ArrowLeft") next = VIEWS[(index + VIEWS.length - 1) % VIEWS.length];
    else if (event.key === "Home") next = VIEWS[0];
    else if (event.key === "End") next = VIEWS[VIEWS.length - 1];
    else return;
    event.preventDefault();
    selectView(next, true);
  }

  function exploreExample() {
    selectView("framing");
    document.getElementById("mission")?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "center",
    });
    document.getElementById("tab-framing")?.focus({ preventScroll: true });
  }

  return (
    <div className="marvin-landing">
<div className="wrap">
<header className="nav"><Link className="brand" href="#"><strong>MARVIN</strong><span>by H&ai</span></Link><nav aria-label="Main navigation"><Link href="#mission">See a mission</Link><Link className="open-link" href="/missions">Open Marvin</Link></nav></header>
<main className="hero">
<div className="statement"><h1><span>Your consulting</span><span>operating system</span></h1><p>MARVIN assigns the research and analysis for your mission to AI agents, then brings their work back for your review.</p><div className="hero-actions"><Link className="primary" href="/missions">Start a mission<svg className="arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg></Link><button className="secondary" id="explore-review" onClick={exploreExample}>See an example</button></div></div>
<div className="conversation" id="mission">
<div className="conversation-top"><span className="conversation-title">Example mission</span><span className="preview-label">Illustrative</span></div>
<div className="exchange"><span className="avatar" aria-hidden="true">You</span><div className="user-content"><strong>You</strong><div className="user-prompt">Should we invest in this software company?</div></div></div>
<div className="agent"><span className="logo-tile" aria-hidden="true">M</span><div><div className="agent-name">MARVIN</div>
<div className="bubble panel" id="panel-framing" role="tabpanel" aria-labelledby="tab-framing" tabIndex={0} hidden={view !== "framing"}><h2>Here is the proposed research plan</h2><p>I'll start with these questions. Check the scope before I begin researching.</p><ul className="hypotheses"><li><span>1</span>Where does revenue growth come from?</li><li><span>2</span>Are customers staying?</li><li><span>3</span>How dependent is revenue on a few customers?</li><li><span>4</span>Can the company sustain its margins?</li><li><span>5</span>What could prevent the investment?</li></ul><div className="review-summary"><span>Research has not started</span><button className="review-link" id="show-review" onClick={() => selectView("review", true)}>Review this plan<svg className="arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg></button></div></div>
<div className="bubble panel" id="panel-review" role="tabpanel" aria-labelledby="tab-review" tabIndex={0} hidden={view !== "review"}><h2>Does this cover the assignment?</h2><div className="phase"><span className="phase-dot" aria-hidden="true"></span>Your decision</div><p>You can approve the plan or ask MARVIN to change it. Research starts after your approval.</p><div className="decision-paths"><div className="decision-path"><strong>Approve the plan</strong><span>Start research</span></div><div className="decision-path"><strong>Request changes</strong><span>Revise the plan</span></div></div><div className="file"><svg viewBox="0 0 24 30" fill="none" aria-hidden="true"><path d="M4 2h10l6 6v20H4V2Zm10 0v7h6M8 15h8m-8 5h8" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg><div><strong>Mission brief</strong><span>The question and scope in one document</span></div></div><div className="review-summary"><span>Try a mission in Marvin</span><Link className="review-link" href="/missions">Open Marvin<svg className="arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg></Link></div></div>
<div className="bubble panel" id="panel-brief" role="tabpanel" aria-labelledby="tab-brief" tabIndex={0} hidden={view !== "brief"}><h2>Mission brief</h2><p>The brief records the question being investigated and the agreed research scope.</p><ul className="brief-list"><li>Investment question</li><li>Research questions</li><li>Available evidence</li><li>Scope and constraints</li></ul><div className="review-summary"><span>Available for review</span><button className="review-link" id="back-to-review" onClick={() => selectView("review", true)}>See the review<svg className="arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg></button></div></div>
</div></div>
<p className="note">Explore the example using the views below.</p>
<div className="views" role="tablist" aria-label="Mission preview"><button className="view" id="tab-framing" role="tab" aria-selected={view === "framing"} aria-controls="panel-framing" tabIndex={view === "framing" ? 0 : -1} onClick={() => selectView("framing")} onKeyDown={(event) => handleTabKey(event, "framing")}>Research plan</button><button className="view" id="tab-review" role="tab" aria-selected={view === "review"} aria-controls="panel-review" tabIndex={view === "review" ? 0 : -1} onClick={() => selectView("review")} onKeyDown={(event) => handleTabKey(event, "review")}>Your decision</button><button className="view" id="tab-brief" role="tab" aria-selected={view === "brief"} aria-controls="panel-brief" tabIndex={view === "brief" ? 0 : -1} onClick={() => selectView("brief")} onKeyDown={(event) => handleTabKey(event, "brief")}>Mission brief</button></div>
</div>
</main>
<footer className="bottom"><span className="footer-brand">MARVIN</span><p>The demo can reset. Save any work you need.</p><p><Link href="/missions">Open workspace</Link></p></footer>
</div>
    </div>
  );
}
