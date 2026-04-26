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
});
