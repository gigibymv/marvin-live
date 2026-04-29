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

    expect(screen.getByText(/Brief/)).toBeInTheDocument();
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

  it("disables gate actions while approval is in flight", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const user = userEvent.setup();

    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "brief",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "brief",
        onGateClose: vi.fn(),
        pendingGateBanner: {
          onResume: vi.fn(),
          onApprove,
          onReject,
          actionInFlight: "approve",
          title: "Hypothesis confirmation",
        },
      }),
    );

    const approve = screen.getByRole("button", { name: "Approve gate" });
    expect(approve).toBeDisabled();
    expect(screen.getByText("Research starting...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject gate" })).toBeDisabled();
    await user.click(approve);
    expect(onApprove).not.toHaveBeenCalled();
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

  it("renders selected section outputs with a contextual title", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws4",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        completedTitle: "Stress testing outputs",
        findings: [
          {
            id: "adv-1",
            kind: "finding",
            ag: "Adversus",
            text: "Weakest link identified in H1",
            confidence: "REASONED",
          },
          {
            id: "w4-report",
            kind: "deliverable",
            ag: "MARVIN",
            text: "Deliverable ready · workstream report",
            confidence: "READY",
          },
          {
            id: "w4-milestone",
            kind: "milestone",
            ag: "MARVIN",
            text: "Milestone complete · Red-team challenge",
            confidence: "DONE",
          },
        ],
      }),
    );

    expect(screen.getByText("Stress testing outputs")).toBeInTheDocument();
    expect(screen.getByText("Weakest link identified in H1")).toBeInTheDocument();
    expect(screen.getByText("Deliverable ready · workstream report")).toBeInTheDocument();
    expect(screen.getByText("Milestone complete · Red-team challenge")).toBeInTheDocument();
  });

  it("renders the requested output tab order", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "brief",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "brief",
        onGateClose: vi.fn(),
        sectionTabs: [
          { id: "brief", label: "Brief", status: "completed" },
          { id: "ws1", label: "Market analysis", status: "completed" },
          { id: "ws2", label: "Financial analysis", status: "pending" },
          { id: "ws3", label: "Synthesis", status: "pending" },
          { id: "ws4", label: "Stress testing", status: "completed" },
          { id: "final", label: "Final deliverables", status: "completed" },
        ],
      }),
    );

    const tabs = screen.getAllByRole("button").filter((button) =>
      /Brief|Market analysis|Financial analysis|Synthesis|Stress testing|Final deliverables/.test(button.textContent ?? ""),
    );
    expect(tabs.map((button) => button.textContent?.replace(/^[✓●]\s*/, ""))).toEqual([
      "Brief",
      "Market analysis",
      "Financial analysis",
      "Synthesis",
      "Stress testing",
      "Final deliverables",
    ]);
  });

  it("treats an old persisted ws5 tab as final deliverables", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws5",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "brief",
        onGateClose: vi.fn(),
        sectionTabs: [
          { id: "brief", label: "Brief", status: "completed" },
          { id: "final", label: "Final deliverables", status: "completed" },
        ],
      }),
    );

    expect(screen.getByRole("button", { name: /Final deliverables/ })).toHaveClass("on");
  });

  it("shows an explicit empty state for sections without outputs", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws2",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        completedTitle: "Financial analysis outputs",
        completedEmptyText: "No outputs for Financial analysis yet.",
        findings: [],
      }),
    );

    expect(screen.getByText("Financial analysis outputs")).toBeInTheDocument();
    expect(screen.getByText("No outputs for Financial analysis yet.")).toBeInTheDocument();
  });

  it("shows a working state when a running section has no outputs yet", () => {
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
        isTyping: true,
        currentNarration: "Dora is mapping the competitive landscape.",
        defaultTab: "brief",
        onGateClose: vi.fn(),
        completedTitle: "Market analysis outputs",
        findings: [],
        waitState: {
          isWorking: true,
          showInOutputs: true,
          isStalled: false,
          elapsedLabel: "0:18",
          headline: "Dora is working",
          message: "Dora is mapping the competitive landscape. This can take a minute while agents search, reason, and write findings.",
        },
      }),
    );

    expect(screen.getAllByText(/Dora is working · 0:18/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/This can take a minute while agents search/).length).toBeGreaterThan(0);
  });

  it("keeps a quiet empty output pane when another section is working", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws2",
        onSelectTab: vi.fn(),
        isTyping: true,
        currentNarration: "Dora is mapping the competitive landscape.",
        defaultTab: "brief",
        onGateClose: vi.fn(),
        completedTitle: "Financial analysis outputs",
        completedEmptyText: "No outputs for Financial analysis yet.",
        findings: [],
        waitState: {
          isWorking: true,
          showInOutputs: false,
          isStalled: false,
          elapsedLabel: "0:18",
          headline: "Dora is working",
          message: "Dora is mapping the competitive landscape.",
        },
      }),
    );

    expect(screen.getByText("No outputs for Financial analysis yet.")).toBeInTheDocument();
    expect(screen.queryByText(/No output for this section yet/)).not.toBeInTheDocument();
  });

  it("opens deliverable outputs from the section pane", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "ws3",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "ws1",
        onGateClose: vi.fn(),
        findings: [
          {
            id: "exec-summary",
            kind: "deliverable",
            ag: "MARVIN",
            text: "Deliverable ready · exec summary",
            confidence: "READY",
            onOpen,
          },
        ],
      }),
    );

    await user.click(screen.getByRole("button", { name: "Open / Download" }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("keeps deliverable action separate from the title copy", () => {
    render(
      React.createElement(MissionControlView, {
        mission,
        initialMessages: [],
        messages: [],
        chatDraft: "",
        onChatDraftChange: vi.fn(),
        onSendMessage: vi.fn(),
        selectedTab: "final",
        onSelectTab: vi.fn(),
        isTyping: false,
        defaultTab: "brief",
        onGateClose: vi.fn(),
        findings: [
          {
            id: "data-book",
            kind: "deliverable",
            ag: "MARVIN",
            text: "Deliverable ready · data book",
            confidence: "READY",
            href: "/download/data-book",
          },
        ],
      }),
    );

    expect(screen.getByText("Deliverable ready · data book")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download ↗" })).toBeInTheDocument();
  });

  it("labels narration events clearly in the in-progress rail", () => {
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
        activity: [
          {
            id: "n1",
            kind: "narration",
            ag: "Workflow",
            text: "Initial hypotheses are ready for review",
          },
        ],
        findings: [],
      }),
    );

    expect(screen.getByText("Workflow")).toBeInTheDocument();
    expect(screen.getByText("Initial hypotheses are ready for review")).toBeInTheDocument();
  });

  it("shows current narration in the live typing bubble", () => {
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
        isTyping: true,
        currentNarration: "Workflow — Resuming the mission.",
        defaultTab: "ws1",
        onGateClose: vi.fn(),
      }),
    );

    expect(screen.getByText("Workflow — Resuming the mission.")).toBeInTheDocument();
  });
});
