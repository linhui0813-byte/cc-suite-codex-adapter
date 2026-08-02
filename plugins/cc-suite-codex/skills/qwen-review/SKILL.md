---
name: qwen-review
description: "Use only when the user explicitly asks Codex to obtain an optional independent Qwen Code critique of a prompt or exact workspace files, with Qwen kept read-only and Codex retaining implementation authority."
---

# Run a Bounded Qwen Review

Qwen is an optional critic, not the primary agent or an editor. Codex owns the
plan, file changes, testing, evidence checks, and final judgment. This skill is
explicit-only and never runs automatically.

## 1. Establish authorization and scope

Identify the review prompt, optional Qwen model id, and every exact target
file. A user request that explicitly asks Qwen to review named files authorizes
sending those files. Otherwise, obtain permission before sending file contents
to Qwen.

Never include `.env` files, credentials, tokens, cookies, private keys,
directories, globs, symlinks, files outside the workspace, or unrelated files.
Omitting `--model` uses Qwen Code's configured default model.

## 2. Locate and preflight the runtime

Use this skill's absolute `SKILL.md` path from the Codex skill catalog. The
plugin root is three parent directories above that file. Run
`bash <plugin-root>/scripts/qwen-preflight.sh` and parse its single JSON object.
Stop on any non-`ok` status. Preflight is local and sends no model prompt.

## 3. Run the bounded foreground review

Invoke the runner directly with an argument-safe command equivalent to:

```text
node <plugin-root>/scripts/qwen-runner.mjs
  --kind qwen-review
  [--model <model-id>]
  [--target <exact-workspace-file>]...
  --max-resumes 2
  --attempt-timeout-ms 300000
  --idle-timeout-ms 240000
  --timeout-ms 900000
  --summary <short-summary>
  -- <review-prompt>
```

Do not enable `--background` or `--debug-capture` in this adapter workflow.
Quote every argument safely; never concatenate untrusted paths or prompt text
into executable shell syntax.

The runner gives Qwen zero tools for prompt-only review. For file review it
stages private read-only copies and permits exactly `read_file` on those copies.
It rejects unexpected tools, MCP servers, paths, events, empty results, bad exit
codes, and changed hashes. It can resume only genuinely incomplete output and
never retries policy or integrity failures.

## 4. Adjudicate, then report

Parse the runner's single JSON object. Treat the review as complete only when
`status` is `completed`, `targetsVerified` is true, and `rawOutput` is non-empty.
Otherwise report `errorCode`, `error`, job id, and attempt summary; do not
substitute another model while claiming Qwen completed.

Present Qwen's critique separately from Codex's judgment. Independently verify
material findings against the target files or primary sources and label each
accepted, rejected, or unresolved. Do not edit files unless the user separately
asked Codex to implement changes.
