/**
 * Integration tests for the MissionRepository.
 * Verifies that HTTP repository uses the real API contract.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  createHttpMissionRepository,
  createLocalMissionRepository,
} from "@/lib/missions/repository";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("MissionRepository", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("HTTP repository", () => {
    const repo = createHttpMissionRepository();

    it("uses GET /api/v1/missions for listMissions", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          missions: [
            {
              id: "m-test-123",
              client: "Test Client",
              target: "Test Target",
              mission_type: "cdd",
              status: "active",
              progress: 0.25,
              next_checkpoint: "Hypothesis confirmation",
              created_at: "2026-04-26T00:00:00Z",
            },
          ],
        }),
      });

      const missions = await repo.listMissions();

      expect(mockFetch).toHaveBeenCalledWith("/api/v1/missions");
      expect(missions).toHaveLength(1);
      expect(missions[0].id).toBe("m-test-123");
      expect(missions[0].name).toBe("Test Target CDD");
      expect(missions[0].template).toBe("cdd");
    });

    it("uses POST /api/v1/missions for createMission", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          mission_id: "m-new-20260426-xyz",
          status: "active",
          client: "New Client",
          target: "New Target",
        }),
      });

      const mission = await repo.createMission({
        client: "New Client",
        target: "New Target",
        template: "cdd",
      });

      expect(mockFetch).toHaveBeenCalledWith(
        "/api/v1/missions",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            client: "New Client",
            target: "New Target",
            ic_question: "",
            mission_type: "cdd",
          }),
        })
      );

      expect(mission.id).toBe("m-new-20260426-xyz");
      expect(mission.client).toBe("New Client");
    });

    it("uses GET /api/v1/missions/{id} for getMission", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: "m-test-456",
          client: "Test",
          target: "Target",
          mission_type: "cdd",
          ic_question: "Test question?",
          status: "active",
          created_at: "2026-04-26T00:00:00Z",
          updated_at: "2026-04-26T00:00:00Z",
        }),
      });

      const mission = await repo.getMission("m-test-456");

      expect(mockFetch).toHaveBeenCalledWith("/api/v1/missions/m-test-456");
      expect(mission).not.toBeNull();
      expect(mission?.id).toBe("m-test-456");
    });

    it("returns null for 404 from getMission", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      const mission = await repo.getMission("nonexistent");

      expect(mission).toBeNull();
    });
  });

  describe("Local repository", () => {
    // Mock localStorage
    const localStorageMock = (() => {
      let store: Record<string, string> = {};
      return {
        getItem: (key: string) => store[key] || null,
        setItem: (key: string, value: string) => {
          store[key] = value;
        },
        removeItem: (key: string) => {
          delete store[key];
        },
        clear: () => {
          store = {};
        },
      };
    })();

    Object.defineProperty(global, "localStorage", {
      value: localStorageMock,
      writable: true,
    });

    const repo = createLocalMissionRepository();

    beforeEach(() => {
      localStorageMock.clear();
    });

    it("stores missions in localStorage", async () => {
      const mission = await repo.createMission({
        client: "Local Client",
        target: "Local Target",
        template: "cdd",
      });

      expect(mission.id).toBeDefined();
      expect(mission.client).toBe("Local Client");

      const missions = await repo.listMissions();
      expect(missions).toHaveLength(1);
      expect(missions[0].id).toBe(mission.id);
    });

    it("retrieves mission by id", async () => {
      const created = await repo.createMission({
        client: "Find Me",
        target: "Find Target",
        template: "cdd",
      });

      const found = await repo.getMission(created.id);
      expect(found).not.toBeNull();
      expect(found?.client).toBe("Find Me");
    });
  });
});
