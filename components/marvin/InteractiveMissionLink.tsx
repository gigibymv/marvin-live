import React from "react";
import Link from "next/link";
import MissionArrow from "./MissionArrow";

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
        <MissionArrow />
      </span>
    </Link>
  );
}
