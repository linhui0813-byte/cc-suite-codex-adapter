---
name: diagnose
description: "Use when diagnosing the native cc-suite Codex adapter, checking skill visibility, provenance, optional Claude MCP tools, or explaining why an adapter workflow cannot run."
---

# Diagnose the Native Codex Adapter

> Adapter boundary: this skill is explicit-only and read-only. It does not run
> upstream bridge scripts or inspect the existing Claude plugin cache.

## 1. Verify visible package facts

Use the installed skill path shown in Codex's skill catalog to locate this
`SKILL.md`. The plugin root is three parent directories above this file. Read
`UPSTREAM_PROVENANCE.json` there and verify that `plugin_name` is
`cc-suite-codex` and that the recorded tag, commit, and archive hash are
non-empty.

## 2. Verify optional tools

Check whether `mcp__claude-code__claude_code` and
`mcp__claude-code__claude_code_reply` are callable in the current session.
Do not call them merely to test availability. Missing tools are a capability
limit, not an adapter corruption.

## 3. Report bounded conclusions

Report package provenance, visible skills, optional MCP availability, and any
broken local reference. Do not claim the upstream Claude bridge, Qwen runner,
hooks, or MCP registrations are healthy; those components are intentionally not
packaged here.

