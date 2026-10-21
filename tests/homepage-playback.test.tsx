import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Homepage from "@/components/marvin/Homepage";

let notifyIntersection: IntersectionObserverCallback;
let reducedMotion = false;
function intersect(ratio: number) {
  act(() => notifyIntersection([{ isIntersecting: ratio > 0, intersectionRatio: ratio } as IntersectionObserverEntry], {} as IntersectionObserver));
}
function advance(ms: number) { act(() => vi.advanceTimersByTime(ms)); }
function selected(name: string) { expect(screen.getByRole("tab", { name })).toHaveAttribute("aria-selected", "true"); }

beforeEach(() => {
  vi.useFakeTimers();
  reducedMotion = false;
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: IntersectionObserverCallback) { notifyIntersection = callback; }
    observe() { notifyIntersection([{ isIntersecting: true, intersectionRatio: 1 } as IntersectionObserverEntry], {} as IntersectionObserver); }
    disconnect() {}
  });
  vi.stubGlobal("matchMedia", () => ({ matches: reducedMotion, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("Landing example playback", () => {
  it("cycles through the whole mission in order", () => {
    render(<Homepage />);
    selected("The brief");
    advance(6000); selected("The analysis");
    advance(8000); selected("Your review");
    advance(7000); selected("The report");
    advance(8000); selected("The brief");
  });

  it("updates the example title, stops on a manual selection and resumes on leaving", () => {
    render(<Homepage />);
    expect(screen.queryByRole("button", { name: /pause example|play example/i })).not.toBeInTheDocument();
    expect(screen.getByText("Interactive example:")).toHaveTextContent("the brief");
    advance(6000);
    expect(screen.getByText("Interactive example:")).toHaveTextContent("the analysis");
    fireEvent.click(screen.getByRole("tab", { name: "The brief" }));
    advance(60000); selected("The brief");
    fireEvent.mouseLeave(document.querySelector(".mission-example")!);
    advance(6000); selected("The analysis");
  });

  it("stops while offscreen or in a hidden document", () => {
    render(<Homepage />);
    intersect(0.1);
    advance(60000); selected("The brief");
    intersect(1);
    advance(6000); selected("The analysis");
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    advance(60000); selected("The analysis");
    hidden.mockReturnValue(false);
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    advance(8000); selected("Your review");
  });

  it("respects reduced motion and keeps keyboard navigation usable", () => {
    reducedMotion = true;
    render(<Homepage />);
    advance(60000); selected("The brief");
    fireEvent.keyDown(screen.getByRole("tab", { name: "The brief" }), { key: "ArrowRight" });
    selected("The analysis");
  });
});
