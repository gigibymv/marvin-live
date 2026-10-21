import React from "react";
import Link from "next/link";

// Adapted for Next navigation, keyboard focus and reduced motion from Magic UI's
// Interactive Hover Button, discovered on 21st.dev:
// https://21st.dev/@dillionverma/components/interactive-hover-button
// MIT license: see InteractiveMissionLink.LICENSE.txt.
export default function InteractiveMissionLink() {
  return (
    <Link className="mission-cta" href="/missions?welcome=1" aria-label="Start a mission">
      <span className="mission-cta-dot" aria-hidden="true" />
      <span className="mission-cta-label" aria-hidden="true">Start a mission</span>
      <span className="mission-cta-reveal" aria-hidden="true">
        Start a mission
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </Link>
  );
}
