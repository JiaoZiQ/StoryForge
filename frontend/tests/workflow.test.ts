import { describe, expect, it } from "vitest";
import {
  isWorkflowTerminal,
  validateGraphHops,
  workflowActions,
} from "@/features/shared/workflow";

describe("workflow policy", () => {
  it.each(["completed", "completed_needs_review", "failed", "cancelled"])(
    "treats %s as terminal",
    (status) => expect(isWorkflowTerminal(status)).toBe(true),
  );

  it("permits actions only for legal statuses", () => {
    expect(workflowActions("paused")).toEqual({
      canResume: true,
      canCancel: false,
    });
    expect(workflowActions("running")).toEqual({
      canResume: false,
      canCancel: true,
    });
    expect(workflowActions("completed")).toEqual({
      canResume: false,
      canCancel: false,
    });
  });

  it("caps graph traversal at two hops", () => {
    expect(validateGraphHops(1)).toBe(1);
    expect(validateGraphHops(2)).toBe(2);
    expect(() => validateGraphHops(3)).toThrow(/one or two hops/);
  });
});
