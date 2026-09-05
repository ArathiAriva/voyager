/**
 * Agent-traces page: recovering from a run that no longer exists.
 *
 * Seen live as a loop of 404s in the backend log -- an open page kept requesting
 * two runs that had been deleted server-side, because a failed fetch left the
 * stale rows in the list and every click re-requested them.
 */
import { describe, it, expect } from "vitest";

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

/** Mirrors the page's open() recovery path. */
function handleOpenFailure(
  runs: { id: string }[],
  id: string,
  error: unknown,
): { runs: { id: string }[]; message: string } {
  if (error instanceof ApiError && error.status === 404) {
    return {
      runs: runs.filter((r) => r.id !== id),
      message: "That run no longer exists — it has been removed from the list.",
    };
  }
  return { runs, message: "Couldn't load that run." };
}

describe("stale run handling", () => {
  const runs = [{ id: "gone" }, { id: "real" }];

  it("drops a run that 404s so it cannot be requested again", () => {
    const out = handleOpenFailure(runs, "gone", new ApiError("Planning API error: 404", 404));
    expect(out.runs.map((r) => r.id)).toEqual(["real"]);
    expect(out.message).toContain("no longer exists");
  });

  it("keeps the list intact when the backend is merely down", () => {
    // A 500 or a network failure is transient -- removing rows would lose the
    // user's list for a problem that resolves on its own.
    const out = handleOpenFailure(runs, "gone", new ApiError("Planning API error: 500", 500));
    expect(out.runs.map((r) => r.id)).toEqual(["gone", "real"]);
    expect(out.message).toBe("Couldn't load that run.");
  });

  it("treats a non-ApiError as transient too", () => {
    const out = handleOpenFailure(runs, "gone", new TypeError("network"));
    expect(out.runs).toHaveLength(2);
  });
});
