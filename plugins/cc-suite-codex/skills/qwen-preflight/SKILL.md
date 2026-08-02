---
name: qwen-preflight
description: "Use when checking whether the optional bounded Qwen Code reviewer is locally ready, including its version and sandbox provider, without sending a model prompt or inspecting credentials."
---

# Check Qwen Review Readiness

This explicit-only workflow is local and read-only. It does not send a prompt,
test authentication, inspect credentials, or change Qwen configuration.

## 1. Locate the packaged script

Use this skill's absolute `SKILL.md` path from the Codex skill catalog. The
plugin root is three parent directories above that file. Do not assume a
checkout path or inspect another cc-suite installation.

## 2. Run the local preflight

Run `bash <plugin-root>/scripts/qwen-preflight.sh`. Parse its single JSON
object. This command may call only local binaries such as `qwen --version` and
the selected sandbox provider's local readiness check.

## 3. Explain the result

Report the status, installed and minimum Qwen Code versions, sandbox provider,
and the listed runner guarantees. Authentication is deliberately
`not_probed`; only a real Qwen request can test provider access.

If the status is `error`, report its exact `error_code` and remedy. Do not run a
model review after a failed preflight.
