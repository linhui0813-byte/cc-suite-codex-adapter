# Porting decisions

The exact official `xiaolai/cc-suite` source release is recorded in
`provenance.lock.json`.

| Upstream component | Adapter decision | Reason |
|---|---|---|
| Codex-facing skills | Selected and pinned | They are natural-language workflows already intended for Codex. |
| `init`, `diagnose`, `repair` | Native overlays | Upstream resolves a Claude plugin root and runs bridge scripts. |
| `agent-design` | Knowledge-only overlay | Design guidance is portable; automatic advisor registration is not. |
| Skill sidecars | Rewritten | Every skill is explicit-only, preventing circular delegation and surprise mutation. |
| Claude commands and agents | Omitted | Blind copying would preserve the wrong runtime contract. |
| Runtime scripts | Omitted | They bridge several hosts and make host-specific assumptions. |
| MCP registration | Omitted | Authentication and configuration require a separate reviewed decision. |
| Hooks | Omitted | Upstream hooks implement Claude lifecycle behavior; this package needs none. |
| Qwen reviewer | Omitted | Its fail-closed controls cannot be preserved by copying prompts alone. |
| Vocabulary skill | Omitted | It depends on NLPM paths and Claude project configuration. |

Omission is not a defect claim. These features remain available from the
official upstream Claude plugin under its own runtime and installation model.
