// Codex-native delegation boundary for the optional Qwen critic.

export const DELEGATION_BOUNDARY = [
  "This request was delegated to you by Codex for independent critique.",
  "You are the reviewer that does the analysis, not a router for it.",
  "Perform the analysis yourself and return the result directly.",
  "Do not delegate this work to Codex, Claude Code, or another agent.",
  "Codex retains final judgment and all implementation authority.",
].join(" ");

export function withDelegationBoundary(prompt) {
  if (!prompt || !prompt.trim()) return DELEGATION_BOUNDARY;
  return `${DELEGATION_BOUNDARY}\n\n${prompt}`;
}
