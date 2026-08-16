# cc-suite Codex adapter

This is an independent Codex adapter for the official
[`xiaolai/cc-suite`](https://github.com/xiaolai/cc-suite). It watches the
version in upstream `package.json`, pins the exact `main` commit for each new
version, applies native Codex overlays, and packages the upstream bounded Qwen
review runtime. It is not a fork and does not modify upstream.

## Architecture

```text
upstream package.json version on main
  -> resolve and pin the exact full commit
  -> download and SHA-256 that commit's source archive
  -> apply seven native Codex skill overlays
  -> copy the exact allowlisted Qwen runtime dependency closure
  -> replace only the Claude-specific delegation boundary
  -> force every skill to explicit-only
  -> generate plugin.json + repo marketplace.json
  -> validate provenance, imports, schemas, links, and safety boundaries
```

The current pin is in `provenance.lock.json`. Generated output lives in
`plugins/cc-suite-codex/`; the repo marketplace is
`.agents/plugins/marketplace.json`.

## Runtime boundary

The upstream release is a Claude Code plugin with several cross-runtime paths.
Blind copying would carry Claude commands, agents, bridges, MCP assumptions,
and hooks into Codex. This adapter packages seven native, explicit-only skills
and only the seven files required by the bounded Qwen review runner.

Qwen is optional and read-only. It never runs without an explicit skill
request, receives no files without explicit user authorization, and has no
write-enabled mode. The runner uses Safe Mode, Plan mode, sandboxing, an empty
MCP set, exact tool discovery, isolated file copies, bounded `read_file` calls,
hash verification, and strict terminal-result validation.
Structured audit jobs additionally validate that the entire terminal result is
one JSON object. Mixed prose is never extracted; the runner permits at most one
tool-free same-session format restatement and fails closed if that is invalid.
`$qwen-audit-fix` composes those calls into a durable audit, adjudication, fix,
test, and re-audit loop. Codex remains the primary agent, only editor, evidence
verifier, and final judge.

## Update and verify

Check without changing files:

```bash
python3 scripts/check_update.py
```

Sync the package version at the current upstream `main` commit, rebuild, and
update the lock:

```bash
python3 scripts/sync_upstream.py
```

Validate the package and run tests:

```bash
python3 scripts/validate_adapter.py
python3 -m unittest discover -s tests -v
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py \
  plugins/cc-suite-codex
```

The lock records the upstream package version, source ref, exact commit,
archive SHA-256, ISC license SHA-256, adapter version, sync time, and generated
tree hash. Commit-only changes do not trigger an update until upstream changes
its `package.json` version. Every candidate remains pinned to one immutable
commit and is never activated automatically. The write-enabled update job does
not execute newly imported upstream JavaScript; full runtime tests run in a
separate CI workflow with read-only repository permission.

## Local install after review

From the adapter repository root, add this non-default repository marketplace,
then install the plugin:

```bash
codex plugin marketplace add .
codex plugin add cc-suite-codex@cc-suite-codex-adapter
```

Start a new thread, select `$diagnose`, and verify its provenance report. Use
`$qwen-preflight` for a zero-prompt local readiness check and `$qwen-review`
only when you intentionally want a critique without edits. Use
`$qwen-audit-fix` when you authorize exact files for repeated review while
Codex fixes accepted findings and runs tests. For an upgrade, sync and validate
first, reinstall from the same marketplace, then start a new thread.

## Intentionally not ported

- Claude slash commands, delegation skills, and native agent definitions
- every upstream runtime except the exact bounded Qwen dependency closure
- automatic `.mcp.json` or `.codex/config.toml` registration
- Grok, Antigravity, opencode, Kimi, and Claude runners or bridges
- upstream Claude hooks (`SessionStart`, `SessionEnd`, and `Stop`)
- the vocabulary skill, which assumes NLPM and Claude-specific paths

See `PORTING.md` for the component decision record.
