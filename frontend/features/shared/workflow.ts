const terminalStatuses = new Set([
  "completed",
  "completed_needs_review",
  "failed",
  "cancelled",
]);

export function isWorkflowTerminal(status: string | undefined): boolean {
  return status ? terminalStatuses.has(status) : false;
}

export function workflowActions(status: string): {
  canResume: boolean;
  canCancel: boolean;
} {
  return {
    canResume: status === "paused",
    canCancel: status === "running" || status === "pending",
  };
}

export function validateGraphHops(value: number): 1 | 2 {
  if (value !== 1 && value !== 2)
    throw new Error("Graph traversal supports only one or two hops.");
  return value;
}
