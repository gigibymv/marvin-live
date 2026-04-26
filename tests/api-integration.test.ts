/**
 * Integration tests for the API client.
 * Uses fetch mocking to simulate backend responses.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  createMission,
  listMissions,
  getMission,
  getMissionProgress,
  validateGate,
  sendChatMessage,
  BackendOfflineError,
} from "@/lib/missions/api";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("API client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("createMission", () => {
    it("POSTs to /api/v1/missions and returns mission data", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          mission_id: "m-novasec-20260426-abc123",
          status: "active",
          client: "Meridian Capital",
          target: "NovaSec",
        }),
      });

      const result = await createMission({
        client: "Meridian Capital",
        target: "NovaSec",
        ic_question: "Is NovaSec a good investment?",
        mission_type: "cdd",
      });

      expect(mockFetch).toHaveBeenCalledWith("/api/v1/missions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client: "Meridian Capital",
          target: "NovaSec",
          ic_question: "Is NovaSec a good investment?",
          mission_type: "cdd",
        }),
      });

      expect(result).toEqual({
        mission_id: "m-novasec-20260426-abc123",
        status: "active",
        client: "Meridian Capital",
        target: "NovaSec",
      });
    });

    it("throws BackendOfflineError when status is 0", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 0,
      });

      await expect(createMission({
        client: "Test",
        target: "Test",
        ic_question: "Test?",
      })).rejects.toThrow(BackendOfflineError);
    });
  });

  describe("listMissions", () => {
    it("GETs from /api/v1/missions and returns mission list", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          missions: [
            {
              id: "m-test-20260426-abc",
              client: "Client A",
              target: "Target A",
              mission_type: "cdd",
              status: "active",
              progress: 0.5,
              next_checkpoint: "Hypothesis confirmation",
              created_at: "2026-04-26T00:00:00Z",
            },
          ],
        }),
      });

      const result = await listMissions();

      expect(mockFetch).toHaveBeenCalledWith("/api/v1/missions");
      expect(result.missions).toHaveLength(1);
      expect(result.missions[0].id).toBe("m-test-20260426-abc");
    });
  });

  describe("getMission", () => {
    it("GETs from /api/v1/missions/{id}", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: "m-test-123",
          client: "Test Client",
          target: "Test Target",
          mission_type: "cdd",
          ic_question: "Test question?",
          status: "active",
          created_at: "2026-04-26T00:00:00Z",
          updated_at: "2026-04-26T00:00:00Z",
        }),
      });

      const result = await getMission("m-test-123");

      expect(mockFetch).toHaveBeenCalledWith("/api/v1/missions/m-test-123");
      expect(result.id).toBe("m-test-123");
      expect(result.client).toBe("Test Client");
    });

    it("throws error for 404", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      await expect(getMission("nonexistent")).rejects.toThrow("Mission not found");
    });
  });

  describe("getMissionProgress", () => {
    it("GETs from /api/v1/missions/{id}/progress", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          mission: {
            id: "m-test-123",
            client: "Test",
            target: "Test",
            created_at: "2026-04-26T00:00:00Z",
            status: "active",
          },
          gates: [],
          milestones: [],
          findings: [],
        }),
      });

      const result = await getMissionProgress("m-test-123");

      expect(mockFetch).toHaveBeenCalledWith("/api/v1/missions/m-test-123/progress");
      expect(result.mission.id).toBe("m-test-123");
    });
  });

  describe("validateGate", () => {
    it("POSTs to /api/v1/missions/{id}/gates/{gateId}/validate", async () => {
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
  });

  describe("sendChatMessage", () => {
    it("POSTs to /api/v1/missions/{id}/chat and yields SSE events", async () => {
      // Create a mock ReadableStream with SSE data
      const encoder = new TextEncoder();
      const events = [
        "event: run_start\ndata: {}\n\n",
        "event: text\ndata: {\"agent\":\"Dora\",\"text\":\"Hello\"}\n\n",
        "event: run_end\ndata: {}\n\n",
      ];
      
      let eventIndex = 0;
      const mockReader = {
        read: vi.fn(async () => {
          if (eventIndex < events.length) {
            const value = encoder.encode(events[eventIndex]);
            eventIndex++;
            return { done: false, value };
          }
          return { done: true, value: undefined };
        }),
        releaseLock: vi.fn(),
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        body: {
          getReader: () => mockReader,
        },
      });

      const collectedEvents = [];
      for await (const event of sendChatMessage("m-test-123", "Hello")) {
        collectedEvents.push(event);
      }

      expect(mockFetch).toHaveBeenCalledWith(
        "/api/v1/missions/m-test-123/chat?reset=false",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ text: "Hello" }),
        })
      );

      expect(collectedEvents).toHaveLength(3);
      expect(collectedEvents[0].type).toBe("run_start");
      expect(collectedEvents[1].type).toBe("text");
      expect((collectedEvents[1] as any).text).toBe("Hello");
      expect(collectedEvents[2].type).toBe("run_end");
    });
  });
});
