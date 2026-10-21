import React from "react";

// SVG from the existing Magic UI Interactive Hover Button adaptation on 21st.dev.
// https://21st.dev/@dillionverma/components/interactive-hover-button
// MIT license: see InteractiveMissionLink.LICENSE.txt.
export default function MissionArrow({ direction = "right" }: { direction?: "right" | "up-right" | "down" }) {
  return <svg className={`mission-arrow mission-arrow-${direction}`} width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
