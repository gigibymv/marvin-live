import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MissionDashboard from "@/components/marvin/MissionDashboard";
import type { CreateMissionInput, Mission } from "@/lib/missions/types";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

describe("mission creation flow", () => {
  beforeEach(() => {
    pushMock.mockReset();
  });

  it("submits a new mission, shows it in the list, preserves required fields, and navigates to the route id", async () => {
    const missions: Mission[] = [];

    const repository = {
      kind: "local" as const,
      listMissions: vi.fn(async () => [...missions]),
      createMission: vi.fn(async (input: CreateMissionInput) => {
        const mission: Mission = {
          id: "mission-123",
          name: `${input.target} CDD`,
          client: input.client,
          target: input.target,
          template: input.template,
          status: "active",
          checkpoint: "Hypothesis confirmation",
          progress: 0,
          createdAt: "2026-04-26T00:00:00.000Z",
          fileAttached: Boolean(input.fileAttached),
          briefReceived: false,
        };

        missions.unshift(mission);
        return mission;
      }),
      getMission: vi.fn(),
    };

    render(React.createElement(MissionDashboard, { repository }));

    await screen.findByText("No active missions yet.");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /new mission/i }));
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.type(screen.getByPlaceholderText("e.g. Meridian Capital"), "Meridian Capital");
    await user.type(screen.getByPlaceholderText("e.g. NovaSec"), "NovaSec");
    await user.click(screen.getByRole("button", { name: /open mission/i }));

    await waitFor(() => expect(screen.getByText("NovaSec CDD")).toBeInTheDocument());
    expect(screen.getByText("Meridian Capital")).toBeInTheDocument();
    expect(repository.createMission).toHaveBeenCalledTimes(1);
    expect(missions[0]).toMatchObject({
      client: "Meridian Capital",
      target: "NovaSec",
      id: "mission-123",
      status: "active",
    });
    expect(pushMock).toHaveBeenCalledWith("/missions/mission-123");
  });
});
