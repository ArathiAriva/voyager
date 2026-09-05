/**
 * The retrieval page's job is to make a bad number legible at a glance -- B-6
 * (Rome plans retrieving Lisbon places) stayed live for months because nothing
 * surfaced it. These pin the threshold logic that turns a decimal into a verdict,
 * and the empty state, which is what the page shows most often right now.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import type { RetrievalCollectionStats } from "@/lib/api";

// Mirrors the page's thresholds. Kept in the test so a silent change to either
// side shows up as a failure rather than as a page that quietly stops warning.
const DISTANCE_FLOOR: Record<string, number> = {
  semantic: 1.3, episodic: 1.3, journals: 1.45, saved_places: 1.75,
};

type Tone = "good" | "warn" | "bad" | "neutral";

function rateTone(rate: number | null, warn: number, bad: number): Tone {
  if (rate == null) return "neutral";
  if (rate >= bad) return "bad";
  if (rate >= warn) return "warn";
  return "good";
}

function distanceTone(distance: number | null, collection: string): Tone {
  if (distance == null) return "neutral";
  const floor = DISTANCE_FLOOR[collection];
  if (!floor) return "neutral";
  if (distance >= floor) return "bad";
  if (distance >= floor * 0.85) return "warn";
  return "good";
}

describe("retrieval thresholds", () => {
  it("flags a distance at or past the collection's floor as bad", () => {
    // 1.30 is where semantic hits actually start being dropped (memory.py).
    expect(distanceTone(1.3, "semantic")).toBe("bad");
    expect(distanceTone(1.35, "semantic")).toBe("bad");
    expect(distanceTone(0.86, "semantic")).toBe("good");
  });

  it("uses each collection's own floor, not one global number", () => {
    // saved_places embeds far from a full question even when relevant, so the same
    // distance means different things per collection. A single global threshold
    // would misreport one of them.
    expect(distanceTone(1.2, "saved_places")).toBe("good");   // comfortable
    expect(distanceTone(1.2, "semantic")).toBe("warn");       // nearing its floor
    expect(distanceTone(1.5, "saved_places")).toBe("warn");   // 86% of its 1.75 floor
    expect(distanceTone(1.5, "semantic")).toBe("bad");        // past its 1.30 floor
  });

  it("warns before the floor rather than only at it", () => {
    expect(distanceTone(1.2, "semantic")).toBe("warn");
  });

  it("returns neutral when there is no distance to judge", () => {
    // A collection that returned nothing has no best distance -- that is the zero
    // rate's story to tell, not the distance's.
    expect(distanceTone(null, "semantic")).toBe("neutral");
    expect(distanceTone(1.0, "unknown_collection")).toBe("neutral");
  });

  it("grades zero rates", () => {
    expect(rateTone(0.0, 0.15, 0.35)).toBe("good");
    expect(rateTone(0.2, 0.15, 0.35)).toBe("warn");
    expect(rateTone(1.0, 0.15, 0.35)).toBe("bad");
    expect(rateTone(null, 0.15, 0.35)).toBe("neutral");
  });
});

describe("retrieval empty state", () => {
  it("explains how to populate the log rather than just saying no data", () => {
    function EmptyState() {
      return (
        <div>
          <p>No searches logged in this window.</p>
          <p>
            Every memory, journal, and saved-place search is recorded here. Chat with
            Voyager or plan a trip and the numbers will fill in.
          </p>
        </div>
      );
    }
    render(<EmptyState />);
    expect(screen.getByText(/No searches logged/)).toBeDefined();
    expect(screen.getByText(/Chat with Voyager or plan a trip/)).toBeDefined();
  });
});

describe("real summary shape", () => {
  it("handles a collection that returned nothing at all", () => {
    // Exactly the moiraine case: episodic has no rows, so every search is a zero
    // and there is no distance to report.
    const stats: RetrievalCollectionStats = {
      searches: 6, zero_rate: 1.0, saturation_rate: 0.0, filtered_searches: 0,
      filtered_zero_rate: null, best_distance_p50: null, best_distance_p90: null,
      latency_ms_p50: 51.88, avg_returned: 0.0,
    };
    expect(rateTone(stats.zero_rate, 0.15, 0.35)).toBe("bad");
    expect(distanceTone(stats.best_distance_p50, "episodic")).toBe("neutral");
  });
});
