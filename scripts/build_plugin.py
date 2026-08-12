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
    text = value.decode("utf-8")
    if path == "scripts/qwen-runner.mjs":
        old = "install Qwen Code, then run /cc-suite:qwen-preflight"
        if text.count(old) != 1:
            raise ValueError("upstream Qwen preflight hint changed; review the runtime transform")
        text = text.replace(old, "install Qwen Code, then invoke $cc-suite-codex:qwen-preflight")

        old_timeouts = '''const DEFAULT_JOB_TIMEOUT_MS = 15 * 60 * 1000;
const DEFAULT_ATTEMPT_TIMEOUT_MS = 5 * 60 * 1000;
const DEFAULT_IDLE_TIMEOUT_MS = 4 * 60 * 1000;'''
        new_timeouts = '''const DEFAULT_JOB_TIMEOUT_MS = 20 * 60 * 1000;
const DEFAULT_ATTEMPT_TIMEOUT_MS = 10 * 60 * 1000;
const DEFAULT_IDLE_TIMEOUT_MS = 8 * 60 * 1000;'''
        if text.count(old_timeouts) != 1:
            raise ValueError("upstream Qwen timeout defaults changed; review the runtime transform")
        text = text.replace(old_timeouts, new_timeouts)

        old_stream_args = '''    "--output-format", "stream-json",
    "--max-wall-time", `${Math.max(1, Math.ceil(attemptTimeoutMs / 1000))}s`,'''
        new_stream_args = '''    "--output-format", "stream-json",
    "--include-partial-messages",
    "--max-wall-time", `${Math.max(1, Math.ceil(attemptTimeoutMs / 1000))}s`,'''
        if text.count(old_stream_args) != 1:
            raise ValueError("upstream Qwen stream arguments changed; review the runtime transform")
        text = text.replace(old_stream_args, new_stream_args)
    elif path == "scripts/lib/qwen-stream.mjs":
        stream_validator_anchor = "\nexport function consumeQwenEvent(state, event) {"
        stream_validator = '''
const PASSIVE_STREAM_EVENT_TYPES = new Set([
  "goal_state",
  "active_goal",
  "message_start",
  "content_block_start",
  "content_block_delta",
  "content_block_stop",
  "message_stop",
  "tool_progress",
]);

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function validateStreamIndex(payload) {
  if (!Number.isInteger(payload.index) || payload.index < 0) {
    throw new QwenStreamError(
      "malformed_stream_event",
      `Qwen emitted ${payload.type} without a valid non-negative index`
    );
  }
}

function validatePassiveStreamEvent(state, event) {
  const payload = event.event;
  if (!isObject(payload)) {
    throw new QwenStreamError(
      "malformed_stream_event",
      "Qwen emitted a malformed stream event"
    );
  }
  if (!PASSIVE_STREAM_EVENT_TYPES.has(payload.type)) {
    throw new QwenStreamError(
      "unsupported_stream_event",
      `Qwen emitted unsupported stream event type: ${payload.type ?? "(missing)"}`
    );
  }
  if (event.parent_tool_use_id !== null && event.parent_tool_use_id !== undefined) {
    throw new QwenStreamError(
      "unsupported_stream_event",
      "Qwen emitted a nested partial event even though subagents are disabled"
    );
  }

  switch (payload.type) {
    case "goal_state":
      if (!isObject(payload.goal_state)) {
        throw new QwenStreamError("malformed_stream_event", "Qwen emitted malformed goal_state progress");
      }
      return;
    case "active_goal":
      if (payload.active_goal !== null && payload.active_goal !== undefined && !isObject(payload.active_goal)) {
        throw new QwenStreamError("malformed_stream_event", "Qwen emitted malformed active_goal progress");
      }
      return;
    case "message_start":
      if (!isObject(payload.message) || payload.message.role !== "assistant" || !Array.isArray(payload.message.content)) {
        throw new QwenStreamError("malformed_stream_event", "Qwen emitted malformed message_start progress");
      }
      return;
    case "content_block_start": {
      validateStreamIndex(payload);
      const block = payload.content_block;
      if (!isObject(block) || !["text", "thinking", "tool_use"].includes(block.type)) {
        throw new QwenStreamError("malformed_stream_event", "Qwen emitted malformed content_block_start progress");
      }
      if (block.type === "tool_use" && block.name !== "read_file") {
        throw new QwenStreamError(
          "forbidden_tool",
          `Qwen attempted forbidden tool in partial output: ${block.name || "(unknown)"}`
        );
      }
      if (block.type === "tool_use" && state.allowedTargets.size === 0) {
        throw new QwenStreamError(
          "forbidden_tool",
          "Qwen attempted read_file in partial output, but this review declared no file targets"
        );
      }
      return;
    }
    case "content_block_delta": {
      validateStreamIndex(payload);
      const delta = payload.delta;
      if (!isObject(delta)) {
        throw new QwenStreamError("malformed_stream_event", "Qwen emitted malformed content_block_delta progress");
      }
      const field = {
        text_delta: "text",
        thinking_delta: "thinking",
        input_json_delta: "partial_json",
      }[delta.type];
      if (!field || typeof delta[field] !== "string") {
        throw new QwenStreamError("malformed_stream_event", "Qwen emitted unsupported content_block_delta progress");
      }
      return;
    }
    case "content_block_stop":
      validateStreamIndex(payload);
      return;
    case "message_stop":
      return;
    case "tool_progress": {
      const callId = payload.tool_use_id ?? null;
      if (callId === null || !state.pendingToolCallIds.has(callId)) {
        throw new QwenStreamError(
          "unsolicited_tool_progress",
          "Qwen emitted tool progress with no matching validated read_file call"
        );
      }
      return;
    }
    default:
      throw new Error("unreachable");
  }
}

export function consumeQwenEvent(state, event) {'''
        if text.count(stream_validator_anchor) != 1:
            raise ValueError("upstream Qwen stream consumer changed; review the runtime transform")
        text = text.replace(stream_validator_anchor, "\n" + stream_validator)

        old_switch = '''    case "result":
      inspectResult(state, event);
      return;
    default:'''
        new_switch = '''    case "stream_event": {
      if (!state.initSeen) {
        throw new QwenStreamError(
          "stream_event_before_init",
          "Qwen emitted a stream event before init"
        );
      }
      validatePassiveStreamEvent(state, event);
      return;
    }
    case "result":
      inspectResult(state, event);
      return;
    default:'''
        if text.count(old_switch) != 1:
            raise ValueError("upstream Qwen stream switch changed; review the runtime transform")
        text = text.replace(old_switch, new_switch)

        old_description = '''export function describeQwenEvent(event) {
  if (event.type === "system") return `event system/${event.subtype ?? "unknown"}`;'''
        new_description = '''export function describeQwenEvent(event) {
  if (event.type === "system") return `event system/${event.subtype ?? "unknown"}`;
  if (event.type === "stream_event") {
    return `event stream_event/${event.event?.type ?? "unknown"}`;
  }'''
        if text.count(old_description) != 1:
            raise ValueError("upstream Qwen event description changed; review the runtime transform")
        text = text.replace(old_description, new_description)
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
        version = adapter_version(lock["upstream"]["version"], config["adapter_revision"])
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
            "ref": lock["upstream"]["ref"],
            "source": lock["upstream"]["repository"],
            "version": lock["upstream"]["version"],
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
        source = extract_archive(args.archive, lock["upstream"]["commit"], Path(temp))
        print(build(source, lock))


if __name__ == "__main__":
    main()
