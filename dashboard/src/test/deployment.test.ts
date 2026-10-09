import { describe, expect, it } from "vitest";
import { apiBase } from "../api";

describe("deployment API origin", () => {
  it("preserves the existing local proxy default", () => {
    expect(apiBase()).toBe("/api/v1");
  });
  it("uses the exact public HTTPS origin", () => {
    expect(apiBase("https://fleetpulse-api.onrender.com/")).toBe(
      "https://fleetpulse-api.onrender.com/api/v1",
    );
  });
  it.each([
    "http://localhost:8000",
    "https://host/api",
    "https://user@host",
    "https://host?x=1",
  ])("rejects malformed deployment origins: %s", (origin) => {
    expect(() => apiBase(origin)).toThrow();
  });
});
