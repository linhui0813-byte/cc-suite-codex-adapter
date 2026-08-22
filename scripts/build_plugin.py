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

        old_usage = '''//     [--attempt-timeout-ms <ms>] [--idle-timeout-ms <ms>]
//     [--timeout-ms <ms>] [--debug-capture] [--background]'''
        new_usage = '''//     [--attempt-timeout-ms <ms>] [--idle-timeout-ms <ms>]
//     [--timeout-ms <ms>] [--result-format text|json-object]
//     [--debug-capture] [--background]'''
        if text.count(old_usage) != 1:
            raise ValueError("upstream Qwen runner usage changed; review the result-format transform")
        text = text.replace(old_usage, new_usage)

        old_limits = '''const MAX_RESUMES_LIMIT = 5;

// Qwen 0.21.0 through 0.21.2 ignore --core-tools in Safe Mode.'''
        new_limits = '''const MAX_RESUMES_LIMIT = 5;
const MAX_TIMER_MS = 2_147_483_647;
const RESULT_FORMATS = new Set(["text", "json-object"]);

// Qwen 0.21.0 through 0.21.2 ignore --core-tools in Safe Mode.'''
        if text.count(old_limits) != 1:
            raise ValueError("upstream Qwen runner limits changed; review the result-format transform")
        text = text.replace(old_limits, new_limits)

        old_timeout_flags = '''      case "--attempt-timeout-ms":
        args.attemptTimeoutMs = parseIntegerFlag(arg, optionValue(argv, i, arg), 1);
        i += 2;
        continue;
      case "--idle-timeout-ms":
        args.idleTimeoutMs = parseIntegerFlag(arg, optionValue(argv, i, arg), 1);
        i += 2;
        continue;'''
        new_timeout_flags = '''      case "--attempt-timeout-ms":
        args.attemptTimeoutMs = parseIntegerFlag(arg, optionValue(argv, i, arg), 1, MAX_TIMER_MS);
        i += 2;
        continue;
      case "--idle-timeout-ms":
        args.idleTimeoutMs = parseIntegerFlag(arg, optionValue(argv, i, arg), 1, MAX_TIMER_MS);
        i += 2;
        continue;'''
        if text.count(old_timeout_flags) != 1:
            raise ValueError("upstream Qwen attempt or idle timeout argument changed; review the timer transform")
        text = text.replace(old_timeout_flags, new_timeout_flags)

        old_resume_prompt = '''const AUTO_RESUME_PROMPT = [
  "The previous headless turn ended without a valid terminal result event.",
  "Continue the same bounded review from the restored session.",
  "Do not repeat file reads unless the review cannot be completed from restored context.",
  "Return the final review directly.",
].join(" ");'''
        new_resume_prompt = '''const AUTO_RESUME_PROMPT = [
  "The previous headless turn ended without a valid terminal result event.",
  "Continue the same bounded review from the restored session.",
  "Do not repeat file reads unless the review cannot be completed from restored context.",
  "Return the final review directly.",
].join(" ");

const JSON_FORMAT_REPAIR_PROMPT = [
  "Your previous result was rejected only because it was not exactly one JSON object.",
  "Do not repeat the analysis or call any tool.",
  "Restate the same review as exactly one valid JSON object, with no Markdown fence and no prose before or after it.",
  "Preserve the meaning and every finding; do not add, remove, or change findings.",
].join(" ");'''
        if text.count(old_resume_prompt) != 1:
            raise ValueError("upstream Qwen resume prompt changed; review the result-format transform")
        text = text.replace(old_resume_prompt, new_resume_prompt)

        old_arg_default = '''    timeoutMs: DEFAULT_JOB_TIMEOUT_MS,
    debugCapture: false,'''
        new_arg_default = '''    timeoutMs: DEFAULT_JOB_TIMEOUT_MS,
    resultFormat: "text",
    debugCapture: false,'''
        if text.count(old_arg_default) != 1:
            raise ValueError("upstream Qwen argument defaults changed; review the result-format transform")
        text = text.replace(old_arg_default, new_arg_default)

        old_timeout_case = '''      case "--timeout-ms":
        args.timeoutMs = parseIntegerFlag(arg, optionValue(argv, i, arg), 1);
        i += 2;
        continue;
      case "--debug-capture":'''
        new_timeout_case = '''      case "--timeout-ms":
        args.timeoutMs = parseIntegerFlag(arg, optionValue(argv, i, arg), 1, MAX_TIMER_MS);
        i += 2;
        continue;
      case "--result-format": {
        const value = optionValue(argv, i, arg);
        if (!RESULT_FORMATS.has(value)) {
          throw new QwenStreamError(
            "invalid_arguments",
            `${arg} must be one of: ${[...RESULT_FORMATS].join(", ")}`
          );
        }
        args.resultFormat = value;
        i += 2;
        continue;
      }
      case "--debug-capture":'''
        if text.count(old_timeout_case) != 1:
            raise ValueError("upstream Qwen timeout argument changed; review the result-format transform")
        text = text.replace(old_timeout_case, new_timeout_case)

        old_bounded_prompt = '''function boundedPrompt(prompt, targets) {
  return withDelegationBoundary(
    `${reviewPolicyPrompt(targets)} The calling agent retains final judgment; your output is critique, not evidence.\\n\\n${prompt}`
  );
}

function buildQwenArgs(args, targets, resumeId, prompt, attemptTimeoutMs) {'''
        new_bounded_prompt = '''function resultFormatPrompt(resultFormat) {
  if (resultFormat !== "json-object") return "";
  return [
    "Your final result must be exactly one valid JSON object.",
    "Do not include Markdown fences or any prose before or after the object.",
  ].join(" ");
}

function normalizeJsonObjectResult(rawOutput) {
  const trimmed = rawOutput.trim();
  const fenced = trimmed.match(/^```(?:json)?[ \\t]*\\r?\\n([\\s\\S]*?)\\r?\\n```$/i);
  const candidate = fenced ? fenced[1].trim() : trimmed;
  let parsed;
  try {
    parsed = JSON.parse(candidate);
  } catch {
    return { ok: false, error: "Qwen result was not exactly one valid JSON object" };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, error: "Qwen result JSON must be an object" };
  }
  return { ok: true, value: JSON.stringify(parsed) };
}

function boundedPrompt(prompt, targets, resultFormat) {
  return withDelegationBoundary(
    `${reviewPolicyPrompt(targets)} The calling agent retains final judgment; your output is critique, not evidence. ${resultFormatPrompt(resultFormat)}\\n\\n${prompt}`
  );
}

function buildQwenArgs(args, targets, resumeId, prompt, attemptTimeoutMs) {'''
        if text.count(old_bounded_prompt) != 1:
            raise ValueError("upstream Qwen bounded prompt changed; review the result-format transform")
        text = text.replace(old_bounded_prompt, new_bounded_prompt)

        old_prompt_call = '''  qwenArgs.push("--prompt", boundedPrompt(prompt, targets));'''
        new_prompt_call = '''  qwenArgs.push("--prompt", boundedPrompt(prompt, targets, args.resultFormat));'''
        if text.count(old_prompt_call) != 1:
            raise ValueError("upstream Qwen prompt call changed; review the result-format transform")
        text = text.replace(old_prompt_call, new_prompt_call)

        old_execute_start = '''async function executeQwen(cwd, args, targets, integrityTargets, logFile) {
  const jobStarted = Date.now();
  let resumeId = null;
  let prompt = args.prompt;
  const attempts = [];'''
        new_execute_start = '''async function executeQwen(cwd, args, targets, integrityTargets, logFile) {
  const jobStarted = Date.now();
  let resumeId = null;
  let prompt = args.prompt;
  let formatRepairActive = false;
  const attempts = [];'''
        if text.count(old_execute_start) != 1:
            raise ValueError("upstream Qwen execution setup changed; review the result-format transform")
        text = text.replace(old_execute_start, new_execute_start)

        old_execute_attempt = '''    const result = await executeQwenAttempt(
      cwd,
      args,
      targets,
      logFile,'''
        new_execute_attempt = '''    const result = await executeQwenAttempt(
      cwd,
      args,
      formatRepairActive ? [] : targets,
      logFile,'''
        if text.count(old_execute_attempt) != 1:
            raise ValueError("upstream Qwen attempt call changed; review the result-format transform")
        text = text.replace(old_execute_attempt, new_execute_attempt)

        old_attempt_record = '''    attempts.push({
      attempt,
      outcome: result.outcome,
      errorCode: result.errorCode ?? null,'''
        new_attempt_record = '''    attempts.push({
      attempt,
      purpose: formatRepairActive ? "format-repair" : "review",
      outcome: result.outcome,
      errorCode: result.errorCode ?? null,'''
        if text.count(old_attempt_record) != 1:
            raise ValueError("upstream Qwen attempt record changed; review the result-format transform")
        text = text.replace(old_attempt_record, new_attempt_record)

        old_completed = '''    if (result.outcome === "completed") {
      appendLog(logFile, `Attempt ${attempt}: completed with verified terminal result and unchanged targets`);
      return {
        status: "completed",
        sessionId: result.sessionId,
        rawOutput: result.rawOutput,
        usage: result.usage ?? null,
        attempts,
      };
    }'''
        new_completed = '''    if (result.outcome === "completed") {
      if (args.resultFormat === "json-object") {
        const normalized = normalizeJsonObjectResult(result.rawOutput);
        if (!normalized.ok) {
          attempts.at(-1).outcome = "incomplete";
          attempts.at(-1).errorCode = "invalid_result_format";
          appendLog(logFile, `Attempt ${attempt}: invalid_result_format`);
          if (formatRepairActive || !result.sessionId || index >= args.maxResumes) {
            return {
              status: "failed",
              errorCode: "invalid_result_format",
              errorMessage: formatRepairActive
                ? `Qwen format repair failed: ${normalized.error}`
                : `${normalized.error}; no format-repair attempt was available`,
              sessionId: result.sessionId,
              rawOutput: result.rawOutput,
              attempts,
            };
          }
          formatRepairActive = true;
          resumeId = result.sessionId;
          prompt = JSON_FORMAT_REPAIR_PROMPT;
          appendLog(logFile, `Attempt ${attempt}: requesting one tool-free same-session format repair`);
          continue;
        }
        appendLog(logFile, `Attempt ${attempt}: completed with a verified JSON-object result and unchanged targets`);
        return {
          status: "completed",
          sessionId: result.sessionId,
          rawOutput: normalized.value,
          usage: result.usage ?? null,
          attempts,
        };
      }
      appendLog(logFile, `Attempt ${attempt}: completed with verified terminal result and unchanged targets`);
      return {
        status: "completed",
        sessionId: result.sessionId,
        rawOutput: result.rawOutput,
        usage: result.usage ?? null,
        attempts,
      };
    }'''
        if text.count(old_completed) != 1:
            raise ValueError("upstream Qwen completion branch changed; review the result-format transform")
        text = text.replace(old_completed, new_completed)

        old_incomplete_resume = '''    resumeId = result.sessionId;
    if (!resumeId || index >= args.maxResumes) {'''
        new_incomplete_resume = '''    resumeId = result.sessionId;
    if (formatRepairActive) {
      return {
        status: "stalled",
        errorCode: result.errorCode || "format_repair_incomplete",
        errorMessage: `${result.errorMessage}; the one format-repair attempt did not complete`,
        sessionId: resumeId || null,
        rawOutput: "",
        attempts,
      };
    }
    if (!resumeId || index >= args.maxResumes) {'''
        if text.count(old_incomplete_resume) != 1:
            raise ValueError("upstream Qwen incomplete branch changed; review the result-format transform")
        text = text.replace(old_incomplete_resume, new_incomplete_resume)

        old_child_args = '''    "--timeout-ms", String(args.timeoutMs),
  ];'''
        new_child_args = '''    "--timeout-ms", String(args.timeoutMs),
    "--result-format", args.resultFormat,
  ];'''
        if text.count(old_child_args) != 1:
            raise ValueError("upstream Qwen background args changed; review the result-format transform")
        text = text.replace(old_child_args, new_child_args)

        old_state_imports = '''  createJobLogFile,
  resolveJobLogFile,
  upsertJob,
  writeJobFile,'''
        new_state_imports = '''  createJobLogFile,
  resolveJobFile,
  resolveJobLogFile,
  resolveStateFile,
  upsertJob,
  writeJobFile,'''
        if text.count(old_state_imports) != 1:
            raise ValueError("upstream Qwen state imports changed; review the monitoring-path transform")
        text = text.replace(old_state_imports, new_state_imports)

        old_background_result = '''      process.stdout.write(JSON.stringify({
        jobId,
        status: "queued",
        message: `Job ${jobId} started in background.`,
      }) + "\\n");'''
        new_background_result = '''      process.stdout.write(JSON.stringify({
        jobId,
        status: "queued",
        stateFile: resolveStateFile(cwd),
        jobFile: resolveJobFile(cwd, jobId),
        logFile,
        message: `Job ${jobId} started in background.`,
      }) + "\\n");'''
        if text.count(old_background_result) != 1:
            raise ValueError("upstream Qwen background result changed; review the monitoring-path transform")
        text = text.replace(old_background_result, new_background_result)

        old_success_persistence = '''    upsertJob(cwd, {
      id: jobId,
      status: result.status,
      phase: result.status,
      threadId: result.sessionId || null,
      attempts: result.attempts.length,
      completedAt: new Date().toISOString(),
      ...(result.errorMessage ? { errorMessage: result.errorMessage, errorCode: result.errorCode } : {}),
    });
    writeJobFile(cwd, jobId, jobPayload(result));'''
        new_success_persistence = '''    writeJobFile(cwd, jobId, jobPayload(result));
    upsertJob(cwd, {
      id: jobId,
      status: result.status,
      phase: result.status,
      threadId: result.sessionId || null,
      attempts: result.attempts.length,
      completedAt: new Date().toISOString(),
      ...(result.errorMessage ? { errorMessage: result.errorMessage, errorCode: result.errorCode } : {}),
    });'''
        if text.count(old_success_persistence) != 2:
            raise ValueError("upstream Qwen success persistence changed; review the monitoring-order transform")
        text = text.replace(old_success_persistence, new_success_persistence)
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
