/**
 * Tests for gate validation flow.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { validateGate } from "@/lib/missions/api";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("Gate validation", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("POSTs APPROVED verdict to validate endpoint", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "resumed",
        mission_id: "m-test-123",
        gate_id: "gate-1",
        resume_id: "resume-abc123",
      }),
    });

    const result = await validateGate("m-test-123", "gate-1", "APPROVED", "Looks good");

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/missions/m-test-123/gates/gate-1/validate",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdict: "APPROVED", notes: "Looks good" }),
      }
    );

    expect(result.status).toBe("resumed");
    expect(result.resume_id).toBe("resume-abc123");
  });

  it("POSTs REJECTED verdict to validate endpoint", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "resumed",
        mission_id: "m-test-123",
        gate_id: "gate-1",
        resume_id: "resume-xyz789",
      }),
    });

    const result = await validateGate("m-test-123", "gate-1", "REJECTED", "Needs more work");

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/missions/m-test-123/gates/gate-1/validate",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ verdict: "REJECTED", notes: "Needs more work" }),
      }
    );

    expect(result.status).toBe("resumed");
  });

  it("handles already processed gate (idempotency)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "already_processed",
        mission_id: "m-test-123",
        gate_id: "gate-1",
        resume_id: "resume-123",
      }),
    });

    const result = await validateGate("m-test-123", "gate-1", "APPROVED", "");

    expect(result.status).toBe("already_processed");
  });
});
