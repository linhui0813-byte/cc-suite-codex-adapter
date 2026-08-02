#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from _lib import ROOT, adapter_version, extract_archive, load_config, tree_hash, write_json

BOUNDARY = """
> Codex adapter boundary: this imported upstream skill is explicit-only. It may
> use Claude only through separately configured `claude-code` MCP tools. If the
> required tool is unavailable or its permission boundary differs from the
> skill, stop and report the mismatch; never claim Codex self-review is an
> independent Claude review.
"""


def normalize_frontmatter(text: str) -> str:
    marker = "\n---\n"
    end = text.find(marker, 4)
    if not text.startswith("---\n") or end < 0:
        raise ValueError("SKILL.md frontmatter is malformed")
    frontmatter = "\n".join(
        line for line in text[4:end].splitlines() if not line.startswith("version:")
    )
    return "---\n" + frontmatter + text[end:]


def inject_boundary(text: str) -> str:
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end < 0:
        raise ValueError("SKILL.md frontmatter is malformed")
    insert = end + len(marker)
    return text[:insert] + "\n" + BOUNDARY + text[insert:]


def transform_upstream_skill(skill: str, text: str) -> str:
    if skill == "claude-code-conventions":
        text = text.replace(
            "Run /cc-suite:refresh-knowledge to update from latest docs.",
            "Refresh by syncing a newer verified upstream release through the adapter repository.",
        ).replace(
            "Run `/cc-suite:refresh-knowledge` to refresh.",
            "Refresh by syncing a newer verified upstream release through the adapter repository.",
        ).replace(
            "- Running `/cc-suite:audit-plugin`, `/cc-suite:audit-command`, `/cc-suite:audit-agent`, or `/cc-suite:audit-skill`",
            "- Reviewing Claude Code plugin, command, agent, or skill artifacts from Codex",
        )
    return inject_boundary(normalize_frontmatter(text))


def build(source: Path, lock: dict) -> str:
    config = load_config()
    plugin_name = config["plugin_name"]
    final = ROOT / "plugins" / plugin_name
    with tempfile.TemporaryDirectory(prefix="cc-suite-adapter-build-") as temp_name:
        temp = Path(temp_name) / plugin_name
        (temp / ".codex-plugin").mkdir(parents=True)
        (temp / "skills").mkdir()
        for skill in config["selected_skills"]:
            upstream = source / "skills" / "cc-suite" / skill
            target = temp / "skills" / skill
            if skill in config["overlay_skills"]:
                shutil.copytree(ROOT / "overlay" / "skills" / skill, target)
                skill_file = target / "SKILL.md"
                skill_file.write_text(normalize_frontmatter(skill_file.read_text(encoding="utf-8")), encoding="utf-8")
            else:
                shutil.copytree(upstream, target)
                skill_file = target / "SKILL.md"
                skill_file.write_text(
                    transform_upstream_skill(skill, skill_file.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
            sidecar = target / "agents" / "openai.yaml"
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            display_name = " ".join(part.capitalize() for part in skill.split("-"))
            sidecar.write_text(
                "# Adapter safety boundary: no imported skill runs implicitly.\n"
                "interface:\n"
                f"  display_name: \"{display_name}\"\n"
                "  short_description: \"Explicit-only cc-suite workflow\"\n"
                "policy:\n  allow_implicit_invocation: false\n",
                encoding="utf-8",
            )
        version = adapter_version(lock["upstream"]["tag"], config["adapter_revision"])
        manifest = {
            "author": {"name": "Independent cc-suite Codex adapter maintainers"},
            "description": "A thin Codex-native skills adapter for an immutable cc-suite release.",
            "homepage": "https://github.com/xiaolai/cc-suite",
            "interface": {
                "capabilities": ["Interactive", "Read", "Write"],
                "category": "Productivity",
                "defaultPrompt": ["Diagnose this cc-suite Codex adapter."],
                "developerName": "Independent cc-suite Codex adapter maintainers",
                "displayName": "cc-suite for Codex",
                "longDescription": "Explicit-only Codex skills adapted from a pinned cc-suite release. No hooks or automatic bridge activation.",
                "shortDescription": "Pinned cc-suite skills for Codex",
                "websiteURL": "https://github.com/xiaolai/cc-suite",
            },
            "keywords": ["codex", "cc-suite", "audit", "review"],
            "license": "ISC",
            "name": plugin_name,
            "skills": "./skills/",
            "version": version,
        }
        write_json(temp / ".codex-plugin" / "plugin.json", manifest)
        shutil.copy2(source / "LICENSE", temp / "LICENSE")
        shutil.copy2(ROOT / "NOTICE.md", temp / "NOTICE.md")
        provenance = {
            "adapter_version": version,
            "archive_sha256": lock["upstream"]["archive_sha256"],
            "commit": lock["upstream"]["commit"],
            "plugin_name": plugin_name,
            "source": lock["upstream"]["repository"],
            "tag": lock["upstream"]["tag"],
            "tag_object": lock["upstream"]["tag_object"],
        }
        write_json(temp / "UPSTREAM_PROVENANCE.json", provenance)
        (temp / ".generated-by-cc-suite-codex-adapter").write_text("1\n")
        if final.exists():
            sentinel = final / ".generated-by-cc-suite-codex-adapter"
            if not sentinel.exists():
                raise ValueError(f"refusing to replace non-generated directory: {final}")
            shutil.rmtree(final)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(temp, final)
    marketplace = {
        "interface": {"displayName": "cc-suite Codex Adapter"},
        "name": config["marketplace_name"],
        "plugins": [{
            "category": "Productivity",
            "name": plugin_name,
            "policy": {"authentication": "ON_INSTALL", "installation": "AVAILABLE"},
            "source": {"path": f"./plugins/{plugin_name}", "source": "local"},
        }],
    }
    write_json(ROOT / ".agents" / "plugins" / "marketplace.json", marketplace)
    return tree_hash(final)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Codex plugin from a verified archive")
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    lock = __import__("json").loads((ROOT / "provenance.lock.json").read_text())
    with tempfile.TemporaryDirectory(prefix="cc-suite-source-") as temp:
        source = extract_archive(args.archive, lock["upstream"]["tag"], Path(temp))
        print(build(source, lock))


if __name__ == "__main__":
    main()
