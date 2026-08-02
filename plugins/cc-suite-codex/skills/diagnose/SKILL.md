---
name: diagnose
description: "Use when diagnosing the native cc-suite Codex adapter, checking skill visibility and provenance, or explaining why the optional bounded Qwen reviewer cannot run."
---

# Diagnose the Native Codex Adapter

> Adapter boundary: this skill is explicit-only and read-only. It does not run
> upstream bridge scripts, send a model prompt, or inspect credentials.

## 1. Verify visible package facts

Use the installed skill path shown in Codex's skill catalog to locate this
`SKILL.md`. The plugin root is three parent directories above this file. Read
`UPSTREAM_PROVENANCE.json` there and verify that `plugin_name` is
`cc-suite-codex` and that the recorded tag, commit, and archive hash are
non-empty.

## 2. Verify the packaged Qwen runtime

Confirm that `scripts/qwen-preflight.sh`, `scripts/qwen-runner.mjs`, and the four
declared files under `scripts/lib/` exist beneath the same plugin root. Run the
preflight script and parse its single JSON result. Preflight checks only the
local Qwen version and sandbox provider; it does not send a prompt or test
authentication.

## 3. Report bounded conclusions

Report package provenance, visible skills, packaged runtime integrity, Qwen
preflight status, and any broken local reference. A failed Qwen preflight means
the optional critic is unavailable; it does not mean the Codex adapter's
knowledge workflows are corrupt. Do not claim provider authentication is
healthy until a user-authorized review succeeds.
