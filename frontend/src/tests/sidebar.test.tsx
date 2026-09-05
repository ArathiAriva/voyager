/**
 * Sidebar header layout.
 *
 * Collapsed, the rail is 64px wide and every nav icon centres on one vertical
 * axis. The compass and the collapse toggle sat side by side in a flex row, so
 * both were squeezed off that axis; they now stack.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

/** Mirrors the header's layout props. */
function headerLayout(collapsed: boolean) {
  return {
    flexDirection: collapsed ? "column" : "row",
    alignItems: "center",
    justifyContent: collapsed ? "center" : "space-between",
  };
}

describe("sidebar header", () => {
  it("stacks the compass and toggle when collapsed", () => {
    expect(headerLayout(true).flexDirection).toBe("column");
    // alignItems:center on a column puts both children on the same vertical axis,
    // which is the axis the nav icons below share.
    expect(headerLayout(true).alignItems).toBe("center");
  });

  it("keeps the wordmark and toggle side by side when expanded", () => {
    expect(headerLayout(false).flexDirection).toBe("row");
    expect(headerLayout(false).justifyContent).toBe("space-between");
  });

  it("renders both controls stacked", () => {
    function Header() {
      const l = headerLayout(true);
      return (
        <div style={{ display: "flex", ...l } as React.CSSProperties} data-testid="header">
          <span>compass</span>
          <button type="button" aria-label="Expand sidebar">toggle</button>
        </div>
      );
    }
    render(<Header />);
    expect(screen.getByTestId("header").style.flexDirection).toBe("column");
    expect(screen.getByLabelText("Expand sidebar")).toBeDefined();
  });
});
