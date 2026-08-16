#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys

from _lib import ROOT, UPSTREAM_REF, adapter_version, load_config, sha256_file, tree_hash

SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
LOCAL_IMPORT = re.compile(r'from\s+["\'](\./[^"\']+)["\']')
REMOVED_CLAUDE_SKILLS = {
    "audit",
    "audit-fix",
    "claude-debug",
    "claude-implement",
    "claude-plan",
    "claude-review",
    "verify",
}


def main() -> int:
    errors: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    config = load_config()
    lock = json.loads((ROOT / "provenance.lock.json").read_text(encoding="utf-8"))
    plugin = ROOT / lock["artifact"]["plugin_path"]
    manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    provenance = json.loads((plugin / "UPSTREAM_PROVENANCE.json").read_text())

    check(lock.get("schema_version") == 2, "lock schema_version must be 2")
    check(SHA.fullmatch(lock["upstream"]["commit"]) is not None, "commit must be a full SHA")
    check(lock["upstream"].get("ref") == UPSTREAM_REF, "upstream ref must be main")
    check(lock["upstream"].get("package_path") == "package.json", "upstream package path mismatch")
    check(SEMVER.fullmatch(lock["upstream"].get("version", "")) is not None, "upstream version is not semver")
    check(SHA256.fullmatch(lock["upstream"]["archive_sha256"]) is not None, "archive hash must be SHA-256")
    check(lock["upstream"]["commit"] in lock["upstream"].get("archive_url", ""), "archive URL is not commit-pinned")
    expected_version = adapter_version(lock["upstream"]["version"], config["adapter_revision"])
    check(lock["adapter"]["version"] == expected_version, "adapter version mismatch")
    check(lock["adapter"].get("repository") == config["adapter_repository"], "adapter repository lock mismatch")
    check(lock["adapter"].get("runtime_files") == config["runtime_files"], "runtime lock mismatch")
    check(manifest["name"] == config["plugin_name"] == plugin.name, "plugin name mismatch")
    check(SEMVER.fullmatch(manifest["version"]) is not None, "plugin version is not semver")
    check(manifest["version"] == expected_version, "manifest version mismatch")
    check(manifest.get("repository") == config["adapter_repository"], "manifest repository mismatch")
    check(manifest.get("homepage") == config["adapter_repository"], "manifest homepage mismatch")
    check(manifest.get("skills") == "./skills/", "manifest skills path is not canonical")
    check(not any(key in manifest for key in ("hooks", "mcpServers", "apps")), "unverified runtime component in manifest")
    check(marketplace["name"] == config["marketplace_name"], "marketplace name mismatch")
    entry = marketplace["plugins"][0]
    check(entry["name"] == config["plugin_name"], "marketplace plugin name mismatch")
    check(entry["source"] == {"path": f"./plugins/{config['plugin_name']}", "source": "local"}, "marketplace source mismatch")
    check(entry["policy"] == {"authentication": "ON_INSTALL", "installation": "AVAILABLE"}, "marketplace policy mismatch")
    check(provenance["commit"] == lock["upstream"]["commit"], "plugin provenance commit mismatch")
    check(provenance.get("adapter_repository") == config["adapter_repository"], "plugin adapter repository mismatch")
    check(provenance["archive_sha256"] == lock["upstream"]["archive_sha256"], "plugin provenance archive mismatch")
    check(provenance.get("ref") == lock["upstream"]["ref"], "plugin provenance ref mismatch")
    check(provenance.get("version") == lock["upstream"]["version"], "plugin provenance version mismatch")
    check(sha256_file(plugin / "LICENSE") == lock["upstream"]["license_sha256"], "packaged license hash mismatch")
    check(tree_hash(plugin) == lock["artifact"]["tree_sha256"], "generated tree hash mismatch")

    selected = set(config["selected_skills"])
    check(not selected & REMOVED_CLAUDE_SKILLS, "Claude delegation skills remain selected")
    actual = {p.name for p in (plugin / "skills").iterdir() if p.is_dir()}
    check(actual == selected, f"skill set mismatch: expected {sorted(selected)}, got {sorted(actual)}")
    for skill in sorted(actual):
        skill_file = plugin / "skills" / skill / "SKILL.md"
        sidecar = plugin / "skills" / skill / "agents/openai.yaml"
        text = skill_file.read_text(encoding="utf-8")
        check(text.startswith("---\n") and "\nname:" in text and "\ndescription:" in text, f"{skill}: invalid frontmatter")
        check(sidecar.read_text().endswith("allow_implicit_invocation: false\n"), f"{skill}: not explicit-only")
        check(f"Use ${skill}" in sidecar.read_text(), f"{skill}: sidecar default prompt does not name the skill")
        if skill in config["overlay_skills"]:
            check("CLAUDE_PLUGIN_ROOT" not in text and ".claude/skills/cc-suite" not in text, f"{skill}: stale bridge-root resolution")
        check("/cc-suite:" not in text, f"{skill}: unported Claude slash command")

    audit_fix = plugin / "skills/qwen-audit-fix/SKILL.md"
    check(audit_fix.is_file(), "qwen-audit-fix skill is missing")
    if audit_fix.is_file():
        audit_text = audit_fix.read_text(encoding="utf-8")
        for marker in (
            "maximum Qwen calls",
            ".cc-suite/audits/qwen-audit-fix-",
            "Qwen output is a hypothesis, not proof.",
            "Start a fresh Qwen review",
            "every authorized batch",
            "Run 1–3 fix/test/re-audit rounds",
            "--result-format json-object",
        ):
            check(marker in audit_text, f"qwen-audit-fix missing workflow marker: {marker}")

    expected_runtime = set(config["runtime_files"])
    actual_runtime = {
        path.relative_to(plugin).as_posix()
        for path in (plugin / "scripts").rglob("*")
        if path.is_file()
    }
    check(actual_runtime == expected_runtime, f"runtime set mismatch: expected {sorted(expected_runtime)}, got {sorted(actual_runtime)}")
    runtime_records = {entry["path"]: entry for entry in provenance.get("runtime_files", [])}
    check(set(runtime_records) == expected_runtime, "runtime provenance set mismatch")
    for relative in sorted(expected_runtime):
        packaged = plugin / relative
        record = runtime_records.get(relative, {})
        if packaged.is_file():
            check(sha256_file(packaged) == record.get("packaged_sha256"), f"{relative}: packaged runtime hash mismatch")
        check(SHA256.fullmatch(record.get("upstream_sha256", "")) is not None, f"{relative}: invalid upstream runtime hash")
        expected_origin = "adapter-overlay" if relative in config["runtime_overlay_files"] else None
        if expected_origin:
            check(record.get("origin") == expected_origin, f"{relative}: runtime overlay provenance mismatch")

    for script in (plugin / "scripts").rglob("*.mjs"):
        text = script.read_text(encoding="utf-8")
        for target in LOCAL_IMPORT.findall(text):
            check((script.parent / target).resolve().is_file(), f"{script.relative_to(plugin)}: unresolved local import {target}")

    runner_text = (plugin / "scripts/qwen-runner.mjs").read_text(encoding="utf-8")
    stream_text = (plugin / "scripts/lib/qwen-stream.mjs").read_text(encoding="utf-8")
    boundary_text = (plugin / "scripts/lib/delegation-boundary.mjs").read_text(encoding="utf-8")
    preflight_text = (plugin / "scripts/qwen-preflight.sh").read_text(encoding="utf-8")
    for marker in (
        '"--safe-mode"',
        '"--sandbox"',
        '"--approval-mode", "plan"',
        '"--exclude-tools"',
        '"--max-tool-calls"',
        'verifyReviewTargets',
        'stageReviewTargets',
        'invalid_result_format',
        'format-repair',
    ):
        check(marker in runner_text, f"qwen runner missing safety marker: {marker}")
    for marker in (
        "tool_boundary_mismatch",
        "forbidden_tool_path",
        "result_before_init",
        "duplicate_result",
        "stream_event_before_init",
        "unsupported_stream_event",
    ):
        check(marker in stream_text, f"Qwen stream observer missing fail-closed marker: {marker}")
    check("Codex retains final judgment and all implementation authority." in boundary_text, "Codex-native delegation boundary missing")
    check("--prompt" not in preflight_text, "Qwen preflight must not send a prompt")
    check(len(manifest.get("interface", {}).get("defaultPrompt", [])) <= 3, "manifest exposes more than three default prompts")

    for path in plugin.rglob("*"):
        if path.is_symlink():
            check(False, f"symlink is not allowed in plugin: {path.relative_to(plugin)}")
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".yaml", ".yml", ".mjs", ".sh"}:
            continue
        text = path.read_text(encoding="utf-8")
        check("/Users/" not in text and "file:///" not in text, f"{path.relative_to(plugin)}: unsafe absolute path")
        check("CLAUDE_PLUGIN_ROOT" not in text, f"{path.relative_to(plugin)}: Claude-only runtime variable")
        check(".claude/skills/cc-suite" not in text, f"{path.relative_to(plugin)}: stale Claude bridge path")
        for target in LINK.findall(text):
            clean = target.split("#", 1)[0]
            if not clean or clean.startswith(("https://", "http://", "mailto:", "codex://", "#")):
                continue
            check((path.parent / clean).resolve().exists(), f"{path.relative_to(plugin)}: broken link {target}")

    for runtime_dir in ("hooks", "commands", "agents"):
        check(not (plugin / runtime_dir).exists(), f"accidental runtime directory: {runtime_dir}")
    if errors:
        print("adapter validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"adapter validation passed: {len(actual)} skills, {manifest['version']}, {tree_hash(plugin)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
