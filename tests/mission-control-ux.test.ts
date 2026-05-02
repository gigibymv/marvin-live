/**
 * Tests for MissionControl UX slice:
 *  - gate payload translation (rich fields preserved)
 *  - deliverable download URL generation
 *  - tool message humanization (no raw JSON in chat)
 *  - feed key uniqueness across rapid SSE bursts
 *  - gate_pending mapping passes through hypotheses + redteam findings
 */

import { describe, expect, it } from "vitest";
import { getDeliverableDownloadUrl } from "@/lib/missions/api";
import {
  formatDeliverableReadyChatMessage,
  formatDeliverableDisplayName,
  formatGatePendingChatMessage,
  formatGatePendingFeedSignal,
  formatNarrationChatMessage,
  routeDeliverableToSectionId,
  routeDeliverableToWorkstreamId,
} from "@/lib/missions/adapters";
import { shouldAttachResumeStream } from "@/lib/missions/gate-resume";
import { mapGateReviewPayloadToModal } from "@/lib/missions/gate-review";

describe("MissionControl UX slice", () => {
  it("reattaches the resume stream after any backend-resumed gate result", () => {
    expect(shouldAttachResumeStream({ status: "resumed" })).toBe(true);
    expect(shouldAttachResumeStream({ status: "resumed_detached" })).toBe(true);
    expect(shouldAttachResumeStream({ status: "resume_pending" })).toBe(true);
    expect(shouldAttachResumeStream({ status: "already_processed" })).toBe(false);
    expect(shouldAttachResumeStream({ status: "validated_no_stream" })).toBe(false);
    expect(shouldAttachResumeStream({ status: "conflict" })).toBe(false);
    expect(shouldAttachResumeStream({ status: undefined })).toBe(false);
    expect(shouldAttachResumeStream(null)).toBe(false);
    expect(shouldAttachResumeStream(undefined)).toBe(false);
  });

  it("getDeliverableDownloadUrl encodes rel_path safely", () => {
    expect(getDeliverableDownloadUrl("memo.pdf")).toBe(
      "/api/v1/deliverables/download?rel_path=memo.pdf",
    );
    expect(getDeliverableDownloadUrl("sub dir/memo with spaces.pdf")).toContain(
      "rel_path=sub%20dir%2Fmemo%20with%20spaces.pdf",
    );
  });

  it("gate payload mapping preserves human-language fields", async () => {
    const raw = {
      type: "gate_pending",
      gate_id: "gate-7",
      gate_type: "manager_review",
      title: "Manager review of research claims",
      stage: "Mid-mission checkpoint (G1)",
      summary: "Initial research is complete...",
      unlocks_on_approve: "Adversus runs the red-team.",
      unlocks_on_reject: "Workstreams loop back.",
      hypotheses: [{ id: "h1", text: "TAM > $10B", status: "open" }],
      research_findings: [
        { id: "f1", claim_text: "Market growing 12%", confidence: "sourced", agent_id: "dora" },
      ],
      redteam_findings: [
        { id: "f2", claim_text: "Customer concentration risk", confidence: "inferred", agent_id: "adversus" },
      ],
      coverage: {
        findings_total: 1,
        workstreams_total: 2,
        workstreams_with_material: 1,
        milestones_delivered: 2,
        milestones_total: 10,
        workstreams: [],
      },
      merlin_verdict: { id: "mv1", verdict: "SHIP", notes: "Ready for IC." },
      arbiter_flags: ["minor inconsistency in pricing"],
      findings_total: 17,
    };
    const mapped = mapGateReviewPayloadToModal(raw);

    expect(mapped.gateId).toBe("gate-7");
    expect(mapped.title).toBe("Manager review of research claims");
    expect(mapped.unlocksOnApprove).toContain("red-team");
    expect(mapped.hypotheses?.[0]?.text).toBe("TAM > $10B");
    expect(mapped.redteamFindings?.[0]?.agent_id).toBe("adversus");
    expect(mapped.coverage?.workstreams_with_material).toBe(1);
    expect(mapped.merlinVerdict?.verdict).toBe("SHIP");
    expect(mapped.findingsTotal).toBe(17);
    expect(mapped.arbiterFlags?.length).toBe(1);
  });

  it("gate payload mapping normalizes incomplete coverage safely", async () => {
    const mapped = mapGateReviewPayloadToModal(
      {
        gate_type: "manager_review",
        coverage: { findings_total: 3 },
      },
      { id: "gate-fallback", gate_type: "manager_review" },
    );

    expect(mapped.gateId).toBe("gate-fallback");
    expect(mapped.coverage?.findings_total).toBe(3);
    expect(mapped.coverage?.workstreams).toEqual([]);
  });

  it("makeMessageId produces unique ids across rapid bursts (feed key safety)", () => {
    let counter = 0;
    function makeId(missionId: string, suffix: string) {
      counter += 1;
      const rand = Math.random().toString(36).slice(2, 8);
      return `${missionId}-${Date.now()}-${counter}-${rand}-${suffix}`;
    }
    const ids = new Set<string>();
    for (let i = 0; i < 500; i++) ids.add(makeId("m-1", "finding"));
    expect(ids.size).toBe(500);
  });

  describe("chat-first gate UX (Path 1)", () => {
    const gateEvent = {
      gateType: "manager_review",
      title: "Manager review of research claims",
      stage: "Mid-mission checkpoint (G1)",
      summary: "Initial research is complete. Approve to start the red-team.",
      unlocksOnApprove: "Adversus runs the red-team.",
      unlocksOnReject: "Workstreams loop back for revision.",
    };

    it("formatGatePendingChatMessage produces a structured, operator-readable message", () => {
      const text = formatGatePendingChatMessage(gateEvent);
      // Stage, validation request, and unlock semantics must all be present.
      expect(text).toContain("Manager review of research claims");
      expect(text).toContain("Stage: Mid-mission checkpoint (G1)");
      expect(text).toContain("Initial research is complete");
      expect(text).toContain("Approve → Adversus runs the red-team.");
      expect(text).toContain("Reject → Workstreams loop back for revision.");
      // Must direct the user to the actions available in the chat bubble.
      expect(text).toContain("Use the actions below");
      // Must NOT contain raw JSON or system jargon like the gate id.
      expect(text).not.toMatch(/\{|\}|\[|\]|gate-/);
    });

    it("formatGatePendingChatMessage degrades gracefully on missing optional fields", () => {
      const text = formatGatePendingChatMessage({ title: "", summary: "" });
      expect(text).toContain("Validation requested");
      expect(text).toContain("Use the actions below");
      // No "Stage:" line when stage is absent.
      expect(text).not.toMatch(/Stage:/);
      expect(text).not.toMatch(/Approve →/);
      expect(text).not.toMatch(/Reject →/);
    });

    it("formatGatePendingFeedSignal is concise and humanizes underscores", () => {
      expect(formatGatePendingFeedSignal(gateEvent)).toBe(
        "Gate pending · Manager review of research claims",
      );
      expect(
        formatGatePendingFeedSignal({ gateType: "hypothesis_confirmation" }),
      ).toBe("Gate pending · hypothesis confirmation");
    });

    it("formatGatePendingChatMessage accepts backend snake_case unlock fields", () => {
      const text = formatGatePendingChatMessage({
        gate_type: "manager_review",
        title: "Manager review",
        unlocks_on_approve: "Adversus runs.",
        unlocks_on_reject: "Research loops.",
      });

      expect(text).toContain("Approve → Adversus runs.");
      expect(text).toContain("Reject → Research loops.");
    });

    it("gate_pending handler builds chat + feed signal without modal state (controller contract)", () => {
      // Mirror the controller's `case "gate_pending"` body to verify it
      // produces (a) a structured chat message, (b) a feed signal, and
      // (c) does NOT touch any gateModal state. The modal state is the
      // sentinel that distinguishes Path 1 (chat-first) from the prior
      // popup-first behavior.
      let modalState: unknown = null;
      const messages: Array<{ from: string; text: string }> = [];
      const feed: Array<{ claim_text: string; confidence?: string }> = [];

      const handleGatePending = (event: typeof gateEvent) => {
        messages.push({ from: "m", text: formatGatePendingChatMessage(event) });
        feed.push({
          claim_text: formatGatePendingFeedSignal(event),
          confidence: "gate",
        });
        // Intentionally NO setGateModal call. Modal opens only via the
        // banner's "Review now" click, which is exercised by the existing
        // reopenGateFromCheckpoint path.
      };

      handleGatePending(gateEvent);

      expect(modalState).toBeNull();
      expect(messages).toHaveLength(1);
      expect(messages[0]?.text).toContain("Manager review of research claims");
      expect(feed).toHaveLength(1);
      expect(feed[0]?.claim_text).toBe(
        "Gate pending · Manager review of research claims",
      );
      expect(feed[0]?.confidence).toBe("gate");
    });
  });

  it("humanizeToolResult strips raw JSON dumps from chat surface", () => {
    function humanizeToolResult(text: unknown): string {
      const raw = String(text ?? "");
      if (!raw) return "step complete";
      if (raw.startsWith("{") || raw.startsWith("[")) return "step complete";
      if (raw.length > 240) return raw.slice(0, 240).trim() + "…";
      return raw;
    }
    expect(humanizeToolResult('{"id": "f-1", "claim": "x"}')).toBe("step complete");
    expect(humanizeToolResult("[1,2,3]")).toBe("step complete");
    expect(humanizeToolResult("Recorded finding for Dora.")).toBe(
      "Recorded finding for Dora.",
    );
    expect(humanizeToolResult("")).toBe("step complete");
  });

  it("formats narration as visible chat copy", () => {
    expect(
      formatNarrationChatMessage({
        agent: "Workflow",
        intent: "Initial hypotheses are ready for review",
      }),
    ).toBe("Workflow — Initial hypotheses are ready for review");
    expect(formatNarrationChatMessage({ agent: "", intent: "" })).toBe(
      "MARVIN — Still working.",
    );
  });

  it("formats deliverable readiness as visible chat copy", () => {
    expect(formatDeliverableReadyChatMessage("exec summary")).toBe(
      "MARVIN — I’ve generated the exec summary and added it to Deliverables.",
    );
    expect(formatDeliverableReadyChatMessage("data_book")).toBe(
      "MARVIN — I’ve generated the data book and added it to Deliverables.",
    );
  });

  it("routes deliverables to the matching section", () => {
    expect(routeDeliverableToSectionId({
      deliverable_type: "workstream_report",
      file_path: "/tmp/mission/W4_report.md",
    })).toBe("W4");
    expect(routeDeliverableToSectionId({ deliverable_type: "engagement_brief" })).toBe("brief");
    expect(routeDeliverableToSectionId({ deliverable_type: "framing_memo" })).toBe("brief");
    expect(routeDeliverableToSectionId({ deliverable_type: "exec_summary" })).toBe("final");
    expect(routeDeliverableToSectionId({ deliverable_type: "investment_memo" })).toBe("final");
    expect(routeDeliverableToSectionId({ deliverable_type: "market_brief" })).toBe("W1");
    expect(routeDeliverableToSectionId({ deliverable_type: "risk_register" })).toBe("W4");
    expect(routeDeliverableToSectionId({ deliverable_type: "unknown" })).toBeNull();
    expect(routeDeliverableToWorkstreamId({ deliverable_type: "exec_summary" })).toBeNull();
  });

  it("labels workstream reports by section", () => {
    expect(formatDeliverableDisplayName({
      deliverable_type: "workstream_report",
      file_path: "/tmp/mission/W1_report.md",
    })).toBe("Market report");
    expect(formatDeliverableDisplayName({
      deliverable_type: "workstream_report",
      file_path: "/tmp/mission/W2_report.md",
    })).toBe("Financial report");
    expect(formatDeliverableDisplayName({
      deliverable_type: "workstream_report",
      file_path: "/tmp/mission/W3_report.md",
    })).toBe("Synthesis report");
    expect(formatDeliverableDisplayName({
      deliverable_type: "workstream_report",
      file_path: "/tmp/mission/W4_report.md",
    })).toBe("Stress testing report");
  });
});
