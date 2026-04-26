"use client";

import type { ComponentType } from "react";
import RawMissionOnboardingView from "../../UI Marvin/MissionOnboarding.jsx";
import type { CreateMissionInput } from "@/lib/missions/types";

const MissionOnboardingView = RawMissionOnboardingView as unknown as ComponentType<{
  onClose: () => void;
  onLaunch: (input: CreateMissionInput) => void;
}>;

export default function MissionOnboarding({
  onClose,
  onLaunch,
}: {
  onClose: () => void;
  onLaunch: (input: CreateMissionInput) => void;
}) {
  return <MissionOnboardingView onClose={onClose} onLaunch={onLaunch} />;
}
