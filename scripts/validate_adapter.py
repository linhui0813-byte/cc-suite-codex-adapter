#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys

from _lib import ROOT, adapter_version, load_config, sha256_file, tree_hash

SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


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

    check(lock.get("schema_version") == 1, "lock schema_version must be 1")
    check(SHA.fullmatch(lock["upstream"]["commit"]) is not None, "commit must be a full SHA")
    check(SHA.fullmatch(lock["upstream"]["tag_object"]) is not None, "tag object must be a full SHA")
    check(SHA256.fullmatch(lock["upstream"]["archive_sha256"]) is not None, "archive hash must be SHA-256")
    expected_version = adapter_version(lock["upstream"]["tag"], config["adapter_revision"])
    check(lock["adapter"]["version"] == expected_version, "adapter version mismatch")
    check(manifest["name"] == config["plugin_name"] == plugin.name, "plugin name mismatch")
    check(SEMVER.fullmatch(manifest["version"]) is not None, "plugin version is not semver")
    check(manifest["version"] == expected_version, "manifest version mismatch")
    check(manifest.get("skills") == "./skills/", "manifest skills path is not canonical")
    check(not any(key in manifest for key in ("hooks", "mcpServers", "apps")), "unverified runtime component in manifest")
    check(marketplace["name"] == config["marketplace_name"], "marketplace name mismatch")
    entry = marketplace["plugins"][0]
    check(entry["name"] == config["plugin_name"], "marketplace plugin name mismatch")
    check(entry["source"] == {"path": f"./plugins/{config['plugin_name']}", "source": "local"}, "marketplace source mismatch")
    check(entry["policy"] == {"authentication": "ON_INSTALL", "installation": "AVAILABLE"}, "marketplace policy mismatch")
    check(provenance["commit"] == lock["upstream"]["commit"], "plugin provenance commit mismatch")
    check(provenance["archive_sha256"] == lock["upstream"]["archive_sha256"], "plugin provenance archive mismatch")
    check(sha256_file(plugin / "LICENSE") == lock["upstream"]["license_sha256"], "packaged license hash mismatch")
    check(tree_hash(plugin) == lock["artifact"]["tree_sha256"], "generated tree hash mismatch")

    selected = set(config["selected_skills"])
    actual = {p.name for p in (plugin / "skills").iterdir() if p.is_dir()}
    check(actual == selected, f"skill set mismatch: expected {sorted(selected)}, got {sorted(actual)}")
    for skill in sorted(actual):
        skill_file = plugin / "skills" / skill / "SKILL.md"
        sidecar = plugin / "skills" / skill / "agents/openai.yaml"
        text = skill_file.read_text(encoding="utf-8")
        check(text.startswith("---\n") and "\nname:" in text and "\ndescription:" in text, f"{skill}: invalid frontmatter")
        check(sidecar.read_text().endswith("allow_implicit_invocation: false\n"), f"{skill}: not explicit-only")
        if skill in config["overlay_skills"]:
            check("CLAUDE_PLUGIN_ROOT" not in text and ".claude/skills/cc-suite" not in text, f"{skill}: stale bridge-root resolution")

    for path in plugin.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8")
        check("/Users/" not in text and "file:///" not in text, f"{path.relative_to(plugin)}: unsafe absolute path")
        if "claude-code-conventions" not in path.parts:
            check("CLAUDE_PLUGIN_ROOT" not in text, f"{path.relative_to(plugin)}: Claude-only runtime variable")
            check(".claude/skills/cc-suite" not in text, f"{path.relative_to(plugin)}: stale Claude bridge path")
        for target in LINK.findall(text):
            clean = target.split("#", 1)[0]
            if not clean or clean.startswith(("https://", "http://", "mailto:", "codex://", "#")):
                continue
            check((path.parent / clean).resolve().exists(), f"{path.relative_to(plugin)}: broken link {target}")

    for runtime_dir in ("hooks", "commands", "scripts", "agents"):
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
