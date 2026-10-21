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
function selected(name: string) {
  const activeTab = screen.getByRole("tab", { name });
  expect(activeTab).toHaveAttribute("aria-selected", "true");
  for (const tab of screen.getAllByRole("tab")) {
    expect(tab).toHaveAttribute("aria-selected", String(tab === activeTab));
    expect(tab).toHaveAttribute("tabindex", tab === activeTab ? "0" : "-1");
  }
  const activePanel = document.getElementById(activeTab.getAttribute("aria-controls")!);
  const panels = screen.getAllByRole("tabpanel", { hidden: true });
  expect(panels).toHaveLength(4);
  expect(screen.getAllByRole("tabpanel")).toEqual([activePanel]);
  for (const panel of panels) {
    expect(panel).toHaveAttribute("aria-hidden", String(panel !== activePanel));
    expect(panel).toHaveAttribute("tabindex", panel === activePanel ? "0" : "-1");
    if (panel === activePanel) {
      expect(panel).not.toHaveAttribute("hidden");
      expect(panel).toBeVisible();
    } else {
      expect(panel).toHaveAttribute("hidden");
      expect(panel).not.toBeVisible();
    }
  }
}

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

  it("links to the example and restarts it from the brief", () => {
    render(<Homepage />);
    fireEvent.click(screen.getByRole("tab", { name: "The report" }));
    const link = screen.getByRole("link", { name: "See an example" });
    expect(link).toHaveAttribute("href", "#mission-example");
    const click = new MouseEvent("click", { bubbles: true, cancelable: true });
    fireEvent(link, click);
    expect(click.defaultPrevented).toBe(false);
    selected("The brief");
    expect(document.querySelector("#mission-example")).toBeInTheDocument();
    advance(6000); selected("The analysis");
  });

  it("opens the welcome flow from every workspace call to action", () => {
    render(<Homepage />);
    for (const name of ["Start a mission", "Open Marvin", "Open workspace"]) {
      expect(screen.getByRole("link", { name })).toHaveAttribute("href", "/missions?welcome=1");
    }
  });

  it("uses SVGs for the example and navigation icons", () => {
    const { container } = render(<Homepage />);
    const findingIcons = container.querySelectorAll(".finding-mark");
    expect(findingIcons).toHaveLength(3);
    const iconHosts = [
      ...["Start a mission", "Open Marvin", "Open workspace", "See an example"].map(name => screen.getByRole("link", { name })),
      ...findingIcons,
      ...container.querySelectorAll(".source-link, .example-next, .example-choices button"),
    ];
    for (const host of iconHosts) {
      const icon = host.querySelector("svg");
      expect(icon).toBeInTheDocument();
      expect(icon?.namespaceURI).toBe("http://www.w3.org/2000/svg");
      expect(host.textContent).not.toMatch(/[\p{Extended_Pictographic}\u2190-\u21ff]/u);
    }
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

  it("respects reduced motion and supports arrow wrap, Home and End with roving focus", () => {
    reducedMotion = true;
    render(<Homepage />);
    advance(60000); selected("The brief");
    act(() => screen.getByRole("tab", { name: "The brief" }).focus());
    for (const [key, name] of [
      ["ArrowLeft", "The report"],
      ["Home", "The brief"],
      ["End", "The report"],
      ["ArrowRight", "The brief"],
      ["ArrowRight", "The analysis"],
    ]) {
      fireEvent.keyDown(document.activeElement!, { key });
      selected(name);
      expect(screen.getByRole("tab", { name })).toHaveFocus();
    }
  });
});
