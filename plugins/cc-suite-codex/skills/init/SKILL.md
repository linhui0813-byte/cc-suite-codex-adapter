---
name: init
description: "Use when checking prerequisites for the native cc-suite Codex adapter, explaining optional Claude MCP setup, or preparing a project without changing the existing Claude installation."
---

# Initialize the Native Codex Adapter

> Adapter boundary: this skill is explicit-only. Installing the plugin already
> exposes its skills. This workflow never edits `.claude/`, `CLAUDE.md`, the
> existing cc-suite installation, or global Codex configuration.

## 1. Check the project

Read `AGENTS.md` and report whether `.codex/config.toml` exists. Do not create or
rewrite either file unless the user separately asks for that project change.

## 2. Check optional delegation

The audit and `claude-*` skills require tools named
`mcp__claude-code__claude_code` and, for follow-ups,
`mcp__claude-code__claude_code_reply`. If they are unavailable, report that
delegation is unavailable and stop. Never fall back to Codex self-review while
claiming an independent Claude review.

If the tools exist, inspect only their callable schemas. Do not send a model
request as a readiness probe and do not reveal credentials or environment
values.

## 3. Report

Report: plugin skills visible, project instructions present or absent, optional
Claude MCP available or absent, and any manual next step. No bridge scripts are
run by this native adapter.

