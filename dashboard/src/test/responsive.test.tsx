import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import postcss from "postcss";

// jsdom cannot render pixels or evaluate media queries. Apply only the CSS
// rules matching each width, then verify structural computed-style behavior.
// This is intentionally not a substitute for browser screenshots/visual QA.
function cssAtWidth(width: number) {
  const tree = postcss.parse(
    readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8"),
  );
  tree.walkAtRules((rule) => {
    if (rule.name !== "media") {
      rule.remove();
      return;
    }
    const min = /min-width:\s*(\d+)px/.exec(rule.params),
      max = /max-width:\s*(\d+)px/.exec(rule.params);
    if (
      (!min && !max) ||
      (min && width < Number(min[1])) ||
      (max && width > Number(max[1]))
    )
      rule.remove();
    else rule.replaceWith(...rule.nodes!);
  });
  return tree.toString();
}
describe("responsive CSS structure (not visual rendering)", () => {
  it.each([360, 768, 1440])(
    "applies sidebar, KPI, feature-grid and overflow rules at %ipx",
    (width) => {
      const style = document.createElement("style");
      style.textContent = cssAtWidth(width);
      document.head.appendChild(style);
      try {
        render(
          <>
            <aside className="sidebar" data-testid="sidebar" />
            <div className="main-shell" data-testid="main" />
            <div className="kpi-grid" data-testid="kpis" />
            <div className="feature-grid" data-testid="features" />
            <div className="table-wrap" data-testid="table" />
            <button className="mobile-only" data-testid="mobile" />
            <div className="prediction-quick-demo">
              <div className="actions">
                <button className="button primary" data-testid="quick-demo" />
              </div>
            </div>
          </>,
        );
        const computed = (id: string) =>
          getComputedStyle(screen.getByTestId(id));
        expect(computed("quick-demo").width).toBe(width <= 600 ? "100%" : "");
        expect(computed("kpis").gridTemplateColumns.replace(/\s+/g, "")).toBe(
          width <= 900 ? "repeat(2,minmax(0,1fr))" : "repeat(4,minmax(0,1fr))",
        );
        expect(computed("features").gridTemplateColumns.replace(/\s+/g, "")).toBe(
          width <= 600
            ? "1fr"
            : width <= 1200
              ? "repeat(2,minmax(0,1fr))"
              : "repeat(3,minmax(0,1fr))",
        );
        expect(computed("sidebar").transform).toBe(
          width <= 900 ? "translateX(-100%)" : "",
        );
        expect(computed("mobile").display).toBe(
          width <= 900 ? "inline-flex" : "none",
        );
        expect(computed("table").overflow).toBe("auto");
        expect(computed("main").minWidth).toBe("0");
      } finally {
        style.remove();
      }
    },
  );
});
