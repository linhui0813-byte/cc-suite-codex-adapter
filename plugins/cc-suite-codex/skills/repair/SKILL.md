---
name: repair
description: "Use when the native cc-suite Codex adapter is missing skills, has invalid provenance, or needs a safe reinstall plan without touching the existing Claude installation."
---

# Repair the Native Codex Adapter

> Adapter boundary: this skill is explicit-only. It never edits plugin cache
> files in place and never runs upstream Claude bridge scripts.

## 1. Diagnose first

Run the read-only checks from `$diagnose`. If only optional Claude MCP tools are
missing, report the missing prerequisite; reinstalling this skills-only plugin
will not create that server.

## 2. Use package-manager boundaries

If package files are missing or provenance is invalid, instruct the user to
rebuild and validate the adapter repository, then reinstall through the
configured `cc-suite-codex-adapter` marketplace. Do not hand-edit Codex's plugin
cache or global configuration.

## 3. Verify in a new thread

After an authorized reinstall, start a new thread and rerun `$diagnose` so the
new skill catalog is loaded. Preserve the repository's existing
`.agents/skills` directory and its `cc-suite` entry.
