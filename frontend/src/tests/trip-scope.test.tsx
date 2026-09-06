/**
 * Trip scoping on chats.
 *
 * The subtlety is the three-state default: `undefined` means "the user has not
 * chosen", which is what lets a live trip default in without overriding a
 * deliberate "No specific trip". Collapsing that to `null` would make the live
 * trip un-deselectable.
 */
import { describe, it, expect } from "vitest";

/** Mirrors the chats page's resolution. */
function resolveScope(
  picked: string | null | undefined,
  liveTripId: string | null,
): string | null {
  return picked === undefined ? liveTripId : picked;
}

describe("new-chat trip default", () => {
  it("defaults to the live trip when the user has not chosen", () => {
    expect(resolveScope(undefined, "halifax")).toBe("halifax");
  });

  it("respects an explicit 'No specific trip' over the live trip", () => {
    // The case a two-state boolean would get wrong: null is a real choice, not
    // an absence, so it must win against the live-trip default.
    expect(resolveScope(null, "halifax")).toBeNull();
  });

  it("respects an explicitly picked different trip", () => {
    expect(resolveScope("kyoto", "halifax")).toBe("kyoto");
  });

  it("is unscoped when nothing is live and nothing is chosen", () => {
    expect(resolveScope(undefined, null)).toBeNull();
  });
});
