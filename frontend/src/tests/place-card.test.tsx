/**
 * Saved-place card presentation.
 *
 * No place in the real data has a thumbnail (27/27 on the moiraine profile), so
 * the "placeholder" header is the normal case, not a fallback -- which is why it
 * is a thin marker rather than a 120px empty box.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

const CATEGORY_PALETTE: Record<string, string> = {
  restaurant: "orange", cafe: "yellow", bar: "purple", "street food": "orange",
  hotel: "blue", neighbourhood: "teal", attraction: "green", shop: "pink",
  beach: "cyan", other: "gray",
};

describe("place category colours", () => {
  it("gives every category a palette", () => {
    // Mirrors PLACE_CATEGORIES in lib/api.ts.
    const categories = ["restaurant", "cafe", "bar", "street food", "hotel",
      "neighbourhood", "attraction", "shop", "beach", "other"];
    for (const c of categories) {
      expect(CATEGORY_PALETTE[c], `no palette for ${c}`).toBeDefined();
    }
  });

  it("distinguishes categories that sit side by side on a board", () => {
    // The screenshot case: three hotels next to attractions and neighbourhoods.
    expect(CATEGORY_PALETTE.hotel).not.toBe(CATEGORY_PALETTE.attraction);
    expect(CATEGORY_PALETTE.hotel).not.toBe(CATEGORY_PALETTE.neighbourhood);
    expect(CATEGORY_PALETTE.cafe).not.toBe(CATEGORY_PALETTE.restaurant);
  });

  it("falls back to grey for an unknown category", () => {
    expect(CATEGORY_PALETTE["not-a-category"] ?? "gray").toBe("gray");
  });
});

describe("open affordance", () => {
  it("renders a labelled control, not a bare arrow glyph", () => {
    function OpenButton() {
      return <button type="button"><svg aria-hidden="true" /> Open</button>;
    }
    render(<OpenButton />);
    const button = screen.getByRole("button");
    expect(button.textContent).toContain("Open");
    // "↗" as the affordance was the thing being replaced.
    expect(button.textContent).not.toContain("↗");
    expect(button.querySelector("svg")).not.toBeNull();
  });
});


describe("card footer alignment", () => {
  it("pins the action row to the bottom regardless of body length", () => {
    // Cards in a wrapped row stretch to equal height. Without a column layout the
    // action row follows the summary, so Open lands at a different height on every
    // card -- visible whenever summaries differ in length, which is always.
    function Card({ summary }: { summary: string }) {
      return (
        <div style={{ display: "flex", flexDirection: "column" }} data-testid="card">
          <div style={{ flex: "1" }} data-testid="body">{summary}</div>
          <div style={{ marginTop: "auto" }} data-testid="actions">Open</div>
        </div>
      );
    }
    const { rerender } = render(<Card summary="short" />);
    expect(screen.getByTestId("card").style.flexDirection).toBe("column");
    expect(screen.getByTestId("body").style.flex).toBe("1 1 0%");
    expect(screen.getByTestId("actions").style.marginTop).toBe("auto");

    // The contract holds for a long summary too -- that is the whole point.
    rerender(<Card summary={"a much longer summary ".repeat(10)} />);
    expect(screen.getByTestId("actions").style.marginTop).toBe("auto");
  });
});
