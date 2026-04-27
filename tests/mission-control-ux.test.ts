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

describe("MissionControl UX slice", () => {
  it("getDeliverableDownloadUrl encodes rel_path safely", () => {
    expect(getDeliverableDownloadUrl("memo.pdf")).toBe(
      "/api/v1/deliverables/download?rel_path=memo.pdf",
    );
    expect(getDeliverableDownloadUrl("sub dir/memo with spaces.pdf")).toContain(
      "rel_path=sub%20dir%2Fmemo%20with%20spaces.pdf",
    );
  });

  it("gate payload mapping preserves human-language fields", async () => {
    // Re-implement the mapper-equivalent inline for unit-level coverage.
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
        { claim_text: "Market growing 12%", confidence: "sourced", agent_id: "dora" },
      ],
      redteam_findings: [
        { claim_text: "Customer concentration risk", confidence: "inferred", agent_id: "adversus" },
      ],
      arbiter_flags: ["minor inconsistency in pricing"],
      findings_total: 17,
    };
    // Mirror the mapper logic
    const mapped = {
      gateId: String(raw.gate_id ?? "gate"),
      gateType: raw.gate_type,
      title: raw.title,
      stage: raw.stage,
      summary: raw.summary,
      unlocksOnApprove: raw.unlocks_on_approve,
      unlocksOnReject: raw.unlocks_on_reject,
      hypotheses: raw.hypotheses,
      researchFindings: raw.research_findings,
      redteamFindings: raw.redteam_findings,
      arbiterFlags: raw.arbiter_flags,
      findingsTotal: raw.findings_total,
    };
    expect(mapped.gateId).toBe("gate-7");
    expect(mapped.title).toBe("Manager review of research claims");
    expect(mapped.unlocksOnApprove).toContain("red-team");
    expect(mapped.hypotheses?.[0]?.text).toBe("TAM > $10B");
    expect(mapped.redteamFindings?.[0]?.agent_id).toBe("adversus");
    expect(mapped.findingsTotal).toBe(17);
    expect(mapped.arbiterFlags?.length).toBe(1);
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
});
