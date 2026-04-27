import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import MissionControlView from "../UI Marvin/MissionControl.jsx";
import type { Mission } from "@/lib/missions/types";

const mission: Mission = {
  id: "mission-1",
  name: "NovaSec CDD",
  client: "Meridian Capital",
  target: "NovaSec",
  template: "cdd",
  status: "active",
  checkpoint: "Hypothesis confirmation",
  progress: 0.32,
  createdAt: "2026-04-26T00:00:00.000Z",
  fileAttached: false,
  briefReceived: false,
};

describe("mission control view", () => {
  it("renders the mission from props", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
      }),
    );

    expect(screen.getByText("NovaSec CDD")).toBeInTheDocument();
    expect(screen.getAllByText("Meridian Capital").length).toBeGreaterThan(0);
  });

  it("does not show fallback ready deliverables or hardcoded checkpoint copy", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        deliverables: [],
        checkpoints: [],
        nextCheckpointLabel: null,
      }),
    );

    expect(screen.queryByText("Engagement brief")).not.toBeInTheDocument();
    expect(screen.queryByText("Review claims")).not.toBeInTheDocument();
    expect(screen.getByText("No open checkpoint")).toBeInTheDocument();
  });

  it("does not mark the brief tab complete before framing exists", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        briefStatus: "now",
      }),
    );

    expect(screen.getByText("Brief")).toBeInTheDocument();
    expect(screen.queryByText("✓ Brief")).not.toBeInTheDocument();
  });

  it("does not expose milestone counters in the visible agent roster", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        agents: [
          {
            id: "dora",
            name: "Dora",
            role: "Market evidence",
            status: "idle",
            milestonesDelivered: 1,
            milestonesTotal: 3,
          },
        ],
      }),
    );

    expect(screen.getByText("Dora")).toBeInTheDocument();
    expect(screen.queryByText("1/3")).not.toBeInTheDocument();
    expect(screen.queryByTestId("milestone-counter-dora")).not.toBeInTheDocument();
  });

  it("does not render a pending deliverable as openable", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        deliverables: [{ id: "d1", label: "Engagement brief", status: "pending" }],
      }),
    );

    expect(screen.getByText("Engagement brief")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Engagement brief/i })).not.toBeInTheDocument();
  });

  it("sends chat through the provided handler", async () => {
    const onSendMessage = vi.fn();
    const user = userEvent.setup();

    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "Status on TAM?",
        onChatDraftChange: vi.fn(),
        onSendMessage,
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
      }),
    );

    await user.click(screen.getAllByRole("button", { name: /send/i })[0]);
    expect(onSendMessage).toHaveBeenCalledWith("Status on TAM?");
  });

  it("shows the gate modal when gateModal is set", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        gateModal: {
          gateId: "gate-1",
          title: "Review claims",
          summary: "Human validation is required before moving ahead.",
        },
        onGateClose: vi.fn(),
      }),
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "Review claims" })).toBeInTheDocument();
    expect(within(dialog).getByText(/Gate ID: gate-1/)).toBeInTheDocument();
  });

  it("renders gate banners with review context", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        pendingGateBanner: {
          onResume: vi.fn(),
          title: "Hypothesis confirmation",
          summary: "Three hypotheses are ready for review.",
        },
      }),
    );

    expect(screen.getByText("Hypothesis confirmation")).toBeInTheDocument();
    expect(screen.getByText(/Three hypotheses are ready for review/)).toBeInTheDocument();
    expect(screen.queryByText("A gate is pending review. Mission is paused until you decide.")).not.toBeInTheDocument();
  });

  it("renders operational activity separately from completed findings", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws1",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        activity: [{ id: "a1", ag: "DORA", text: "Dora started" }],
        findings: [{ id: "f1", ag: "DORA", text: "Market is growing", ts: "" }],
      }),
    );

    expect(screen.getByText("Dora started")).toBeInTheDocument();
    expect(screen.getByText("Market is growing")).toBeInTheDocument();
  });
});
