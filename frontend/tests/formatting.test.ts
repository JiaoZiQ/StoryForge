import { describe, expect, it } from "vitest";
import { clipText, formatDate, formatScore, humanize } from "@/lib/formatting";

describe("formatting helpers", () => {
  it("formats scores and absent values", () => {
    expect(formatScore(7.126)).toBe("7.13");
    expect(formatScore(null)).toBe("—");
    expect(humanize("needs_human_review")).toBe("Needs Human Review");
    expect(humanize(undefined)).toBe("—");
  });

  it("clips long text without changing short text", () => {
    expect(clipText("short", 10)).toBe("short");
    expect(clipText("a long sentence", 8)).toBe("a long…");
  });

  it("handles invalid and valid dates", () => {
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("not-a-date")).toBe("—");
    expect(formatDate("2026-01-02T03:04:05Z")).not.toBe("—");
  });
});
