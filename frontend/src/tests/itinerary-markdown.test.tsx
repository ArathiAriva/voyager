/**
 * The planner writes markdown into itinerary day plans (**bold** place names).
 * The trip page rendered day.plan as a raw <Text>, so the asterisks showed up
 * literally on screen. These pin the rendering, not the styling.
 */
import { render, screen } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import { describe, it, expect } from "vitest";

// Mirrors how the trip page renders a day plan.
function DayPlan({ plan }: { plan: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown>{plan}</ReactMarkdown>
    </div>
  );
}

describe("itinerary day plan rendering", () => {
  it("renders **bold** as strong rather than literal asterisks", () => {
    // Real text from the Halifax itinerary that surfaced this.
    render(<DayPlan plan="Head downtown to the **Halifax Waterfront** for an easy walk." />);

    const strong = screen.getByText("Halifax Waterfront");
    expect(strong.tagName).toBe("STRONG");
    expect(document.body.textContent).not.toContain("**");
  });

  it("leaves plain text untouched", () => {
    // Older profiles' itineraries contain no markdown at all, so the markdown
    // path must be a no-op for them.
    const plain = "Arrive afternoon and settle into your accommodation.";
    render(<DayPlan plan={plain} />);
    expect(screen.getByText(plain)).toBeDefined();
  });

  it("renders lists, which the planner also emits", () => {
    render(<DayPlan plan={"Options:\n\n- Hemlocks Trail\n- Mersey River Trail"} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
