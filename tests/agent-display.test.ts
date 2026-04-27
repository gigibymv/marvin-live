// Bug 5 regression: agent name casing must be consistent — Title Case for
// the working agents (Dora, Calculus, Adversus, Merlin, Papyrus); MARVIN
// stays uppercase as a brand exception.
import { describe, it, expect } from "vitest";
import { normalizeAgentName } from "@/lib/missions/agent-display";

describe("normalizeAgentName", () => {
  it.each([
    ["dora", "Dora"],
    ["DORA", "Dora"],
    ["Dora", "Dora"],
    ["calculus", "Calculus"],
    ["CALCULUS", "Calculus"],
    ["adversus", "Adversus"],
    ["merlin", "Merlin"],
    ["papyrus", "Papyrus"],
    ["papyrus_phase0", "Papyrus"],
    ["papyrus_delivery", "Papyrus"],
  ])("maps %s -> %s", (raw, expected) => {
    expect(normalizeAgentName(raw)).toBe(expected);
  });

  it("preserves MARVIN as uppercase", () => {
    expect(normalizeAgentName("marvin")).toBe("MARVIN");
    expect(normalizeAgentName("MARVIN")).toBe("MARVIN");
    expect(normalizeAgentName("orchestrator")).toBe("MARVIN");
    expect(normalizeAgentName("orchestrator_qa")).toBe("MARVIN");
    expect(normalizeAgentName("framing")).toBe("MARVIN");
  });

  it("falls back to MARVIN for empty input rather than 'AGENT'", () => {
    expect(normalizeAgentName("")).toBe("MARVIN");
    expect(normalizeAgentName(null)).toBe("MARVIN");
    expect(normalizeAgentName(undefined)).toBe("MARVIN");
  });

  it("title-cases unknown snake_case identifiers", () => {
    expect(normalizeAgentName("new_agent")).toBe("New Agent");
  });

  it("never returns the raw uppercase identifier", () => {
    for (const raw of ["dora", "calculus", "adversus", "merlin", "papyrus"]) {
      const out = normalizeAgentName(raw);
      expect(out).not.toBe(raw.toUpperCase());
      expect(out).not.toBe(raw); // not lowercase either
    }
  });
});
