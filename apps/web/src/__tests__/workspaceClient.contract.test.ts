import { afterEach, describe, expect, it, vi } from "vitest";
import { workspaceClient } from "../api/workspaceClient";

describe("workspaceClient API contract (real client + mocked fetch)", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("calls GET /api/v1/workspace/tasks/{task_id}/briefs/{version}/export with explicit version", async () => {
    const mockResponse = {
      task_id: 10,
      version: 2,
      human_status: "ready_for_handoff",
      handoff_mode: "manual_copy_only",
      rendered_text: "# Task Brief v2",
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const result = await workspaceClient.exportTaskBrief(10, 2);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/workspace/tasks/10/briefs/2/export");
    expect(init.credentials).toBe("include");
    expect(result).toEqual(mockResponse);
  });

  it("calls workspace mutation endpoints with X-CSRF-Token and expected paths", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 1 }),
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await workspaceClient.createTaskBrief(
      5,
      {
        purpose: "Contract check",
        scope: "",
        excluded_scope: "",
        input_references: [],
        acceptance_checks: [],
        security_constraints: "",
        rollback_plan: "",
        human_status: "draft",
        expected_latest_version: 0,
      },
      "csrf-abc",
    );

    const [briefUrl, briefInit] = fetchMock.mock.calls[0];
    expect(briefUrl).toBe("/api/v1/workspace/tasks/5/briefs");
    expect(briefInit.method).toBe("POST");
    expect((briefInit.headers as Headers).get("X-CSRF-Token")).toBe("csrf-abc");

    await workspaceClient.listArtifacts({
      kind: "plan",
      tag: "phase-04",
      limit: 20,
      offset: 20,
    });
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/v1/workspace/artifacts?kind=plan&tag=phase-04&limit=20&offset=20",
    );

    await workspaceClient.updateProvenance(
      7,
      { review_status: "approved" },
      "csrf-abc",
    );
    const [provUrl, provInit] = fetchMock.mock.calls[2];
    expect(provUrl).toBe("/api/v1/workspace/provenance/7");
    expect(provInit.method).toBe("PATCH");
    expect((provInit.headers as Headers).get("X-CSRF-Token")).toBe("csrf-abc");
  });
});
