#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path

from _lib import ROOT, adapter_version, extract_archive, load_config, tree_hash, write_json


def normalize_frontmatter(text: str) -> str:
    marker = "\n---\n"
    end = text.find(marker, 4)
    if not text.startswith("---\n") or end < 0:
        raise ValueError("SKILL.md frontmatter is malformed")
    frontmatter = "\n".join(
        line for line in text[4:end].splitlines() if not line.startswith("version:")
    )
    return "---\n" + frontmatter + text[end:]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def transform_runtime(path: str, value: bytes) -> bytes:
    if path != "scripts/qwen-runner.mjs":
        return value
    text = value.decode("utf-8")
    old = "install Qwen Code, then run /cc-suite:qwen-preflight"
    if text.count(old) != 1:
        raise ValueError("upstream Qwen preflight hint changed; review the runtime transform")
    text = text.replace(old, "install Qwen Code, then invoke $cc-suite-codex:qwen-preflight")
    return text.encode("utf-8")


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
                skill_file.write_text(normalize_frontmatter(skill_file.read_text(encoding="utf-8")), encoding="utf-8")
            sidecar = target / "agents" / "openai.yaml"
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            display_name = " ".join(part.capitalize() for part in skill.split("-"))
            sidecar.write_text(
                "# Adapter safety boundary: no imported skill runs implicitly.\n"
                "interface:\n"
                f"  display_name: \"{display_name}\"\n"
                "  short_description: \"Explicit-only cc-suite workflow\"\n"
                f"  default_prompt: \"Use ${skill} for this explicit cc-suite workflow.\"\n"
                "policy:\n  allow_implicit_invocation: false\n",
                encoding="utf-8",
            )
        runtime_provenance = []
        for relative in config["runtime_files"]:
            upstream_file = source / relative
            upstream_bytes = upstream_file.read_bytes()
            if relative in config["runtime_overlay_files"]:
                packaged_bytes = (ROOT / "overlay" / "runtime" / Path(relative).relative_to("scripts")).read_bytes()
                origin = "adapter-overlay"
            else:
                packaged_bytes = transform_runtime(relative, upstream_bytes)
                origin = "upstream" if packaged_bytes == upstream_bytes else "deterministic-transform"
            target = temp / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(packaged_bytes)
            if upstream_file.stat().st_mode & 0o111:
                target.chmod(target.stat().st_mode | 0o755)
            runtime_provenance.append({
                "origin": origin,
                "packaged_sha256": sha256_bytes(packaged_bytes),
                "path": relative,
                "upstream_sha256": sha256_bytes(upstream_bytes),
            })
        version = adapter_version(lock["upstream"]["tag"], config["adapter_revision"])
        manifest = {
            "author": {"name": "Independent cc-suite Codex adapter maintainers"},
            "description": "A Codex-native cc-suite adapter with bounded Qwen review and audit-fix workflows.",
            "homepage": config["adapter_repository"],
            "interface": {
                "capabilities": ["Interactive", "Read"],
                "category": "Productivity",
                "defaultPrompt": [
                    "Check Qwen review readiness.",
                    "Ask Qwen for a bounded read-only review.",
                    "Audit exact files with Qwen, fix accepted findings, and re-audit until clean.",
                ],
                "developerName": "Independent cc-suite Codex adapter maintainers",
                "displayName": "cc-suite for Codex",
                "longDescription": "Explicit-only Codex workflows adapted from a pinned cc-suite release. Qwen is an optional read-only critic for bounded review or audit-fix cycles; Codex remains the editor and final judge.",
                "shortDescription": "Codex workflows with Qwen review and audit-fix",
                "websiteURL": config["adapter_repository"],
            },
            "keywords": ["codex", "cc-suite", "qwen", "review"],
            "license": "ISC",
            "name": plugin_name,
            "repository": config["adapter_repository"],
            "skills": "./skills/",
            "version": version,
        }
        write_json(temp / ".codex-plugin" / "plugin.json", manifest)
        shutil.copy2(source / "LICENSE", temp / "LICENSE")
        shutil.copy2(ROOT / "NOTICE.md", temp / "NOTICE.md")
        provenance = {
            "adapter_repository": config["adapter_repository"],
            "adapter_version": version,
            "archive_sha256": lock["upstream"]["archive_sha256"],
            "commit": lock["upstream"]["commit"],
            "plugin_name": plugin_name,
            "source": lock["upstream"]["repository"],
            "tag": lock["upstream"]["tag"],
            "tag_object": lock["upstream"]["tag_object"],
            "runtime_files": runtime_provenance,
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
