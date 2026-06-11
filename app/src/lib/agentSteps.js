// Step lifecycle status — the `status` field on STEP_* SSE events, shared by the
// audit + content workspaces. Mirrors StepStatus in backend/agents/core/events.py.
// "error" is the canonical failed state (content historically emitted "failed").

export const StepStatus = Object.freeze({
  RUNNING: "running",
  SUCCESS: "success",
  ERROR:   "error",
});
