# cc-suite Codex adapter

This is an independent, thin Codex adapter for the official
[`xiaolai/cc-suite`](https://github.com/xiaolai/cc-suite). It tracks an immutable
stable release tag, transforms selected Codex-facing skills, and builds a local
Codex plugin. It is not a fork, does not modify upstream, and is not globally
installed by this repository.

## Architecture

```text
official stable tag
  -> verify tag object + full commit
  -> download and SHA-256 the exact source archive
  -> copy selected skills + apply four native overlays
  -> force every skill to explicit-only
  -> generate plugin.json + repo marketplace.json
  -> validate provenance, schemas, links, and safety boundaries
```

The current pin is in `provenance.lock.json`. Generated output lives in
`plugins/cc-suite-codex/`; the repo marketplace is
`.agents/plugins/marketplace.json`.

## Why it is skills-only

The upstream release is a Claude Code plugin that also exposes some skills to
Codex. Blind copying would carry Claude commands, agents, bridge scripts,
environment-variable assumptions, and hooks into a different runtime. This
adapter packages 12 portable or usefully adaptable skills. `init`, `diagnose`,
`repair`, and `agent-design` are native overlays; they never execute the old
Claude bridge copy.

Every skill has `policy.allow_implicit_invocation: false`. Delegating skills
must be selected explicitly and require a separately configured `claude-code`
MCP server. Missing or broader-than-declared MCP tools are a hard stop; Codex
must not label self-review as independent Claude review.

## Update and verify

Check without changing files:

```bash
python3 scripts/check_update.py
```

Sync the latest stable release, rebuild, and update the lock:

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

The lock records the upstream tag, annotated-tag object, peeled commit, archive
SHA-256, ISC license SHA-256, adapter version, sync time, and generated tree
hash. The update check fails closed if the pinned tag disappears or moves. A
new candidate is never activated automatically.

## Local install after review

From the adapter repository root, add this non-default repository marketplace,
then install the plugin:

```bash
codex plugin marketplace add .
codex plugin add cc-suite-codex@cc-suite-codex-adapter
```

Start a new thread, select `$diagnose`, and verify its provenance report. These
are instructions only; this repository does not run them or modify global Codex
configuration. For an upgrade, sync and validate first, reinstall from the same
marketplace, then start a new thread.

## Intentionally not ported

- Claude slash commands and native agent definitions
- upstream runtime and bridge scripts
- automatic `.mcp.json` or `.codex/config.toml` registration
- Qwen, Grok, Antigravity, opencode, or Kimi runners and bridges
- upstream Claude hooks (`SessionStart`, `SessionEnd`, and `Stop`)
- the vocabulary skill, which assumes NLPM and Claude-specific paths

The Qwen reviewer is omitted rather than weakened. Its upstream safety depends
on exact tool/MCP verification, isolated targets, bounded reads, terminal-result
validation, and source-hash checks. A prompt-only copy would not preserve those
fail-closed guarantees.

See `PORTING.md` for the component decision record.
