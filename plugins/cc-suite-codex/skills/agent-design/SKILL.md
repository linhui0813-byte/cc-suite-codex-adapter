---
name: agent-design
description: "Use when designing or reviewing a cc-suite advisor definition, choosing a value-over-rules persona, restricting tools, scoping its working directory, or setting turn and budget caps."
---

# Design cc-suite Advisors Safely

> Adapter boundary: this knowledge skill is explicit-only. The native adapter
> can review advisor definitions but does not register them or run upstream
> `bridge_agents.py`.

## 1. Choose the right mechanism

Use an advisor for a persistent consultative viewpoint, a Codex subagent for a
bounded execution task, and a skill for static reusable instructions. Advisors
judge work; they do not edit it.

## 2. Default to read-only

Start with `allowed_tools: [Read, Grep, Glob]`, `permission_mode: plan`,
`max_turns: 5`, and an explicit budget cap. An empty allow-list is invalid if
the backing runtime interprets it as unrestricted. Reject unknown advertised
tools and MCP servers before accepting review output.

## 3. Write values, not checklists

State the principle the advisor protects, rank conflicting values, name what it
should ignore, and require evidence such as file and line locations. Use at
least two realistic invocation examples in the advisor description.

## 4. Keep activation separate

This adapter does not translate an advisor file into `.mcp.json` or
`.codex/config.toml`. After authoring, report that activation requires the
official upstream bridge or a separately reviewed MCP configuration. Never
silently invoke a stale Claude bridge copy.
