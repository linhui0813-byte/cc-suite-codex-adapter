---
name: init
description: "Use when checking prerequisites for the native cc-suite Codex adapter, preparing a project, or explaining how its optional bounded Qwen reviewer is enabled without changing global configuration."
---

# Initialize the Native Codex Adapter

> Adapter boundary: this skill is explicit-only. Installing the plugin already
> exposes its skills. This workflow never edits project instructions, another
> cc-suite installation, Qwen settings, or global Codex configuration.

## 1. Check the project

Read `AGENTS.md` and report whether `.codex/config.toml` exists. Do not create or
rewrite either file unless the user separately asks for that project change.

## 2. Check the optional Qwen critic

Check Node.js 18.18.0 or newer, then run the packaged Qwen preflight. It checks
the local `qwen` version and sandbox provider without sending a model request or
inspecting credentials. Qwen is optional: a failed preflight disables only the
independent Qwen review lane.

## 3. Report

Report: plugin skills visible, project instructions present or absent, Node.js
version, Qwen preflight status, and any manual next step. No MCP server, hook,
or automatic bridge is installed by this adapter.
