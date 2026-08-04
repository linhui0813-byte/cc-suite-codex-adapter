# Porting decisions

The exact official `xiaolai/cc-suite` source release is recorded in
`provenance.lock.json`.

| Upstream component | Adapter decision | Reason |
|---|---|---|
| `init`, `diagnose`, `repair` | Native overlays | They inspect this Codex package and the optional local Qwen prerequisite without running bridges. |
| `agent-design` | Knowledge-only overlay | Design guidance is portable; automatic advisor registration is not. |
| `qwen-preflight`, `qwen-review` | Native overlays | Codex invocation, consent, and adjudication differ from Claude slash commands. |
| `qwen-audit-fix` | Native workflow | Recreates the audit, fix, test, and re-audit loop with bounded read-only Qwen calls and durable state; Codex alone edits and adjudicates. |
| Skill sidecars | Rewritten | Every skill is explicit-only, preventing circular delegation and surprise mutation. |
| Claude delegation skills, commands, and agents | Omitted | Codex is the primary agent; this adapter replaces the useful audit-fix mechanism with a Qwen-native workflow instead of requiring Claude. |
| Qwen runtime dependency closure | Pinned and packaged | The upstream fail-closed runner is required; prompt-only delegation would weaken its safety. |
| Qwen delegation boundary | Native runtime overlay | The upstream wording assumes Claude is the caller; the adapter names Codex as caller and final judge. |
| Other runtime scripts | Omitted | They bridge other hosts and make host-specific assumptions. |
| MCP registration | Omitted | Authentication and configuration require a separate reviewed decision. |
| Hooks | Omitted | Upstream hooks implement Claude lifecycle behavior; this package needs none. |
| Vocabulary skill | Omitted | It depends on NLPM paths and Claude project configuration. |

Omission is not a defect claim. These features remain available from the
official upstream Claude plugin under its own runtime and installation model.
