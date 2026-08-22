from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import adapter_version, package_release, package_version, parse_head, tree_hash


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = json.loads((ROOT / "provenance.lock.json").read_text())
        self.plugin = ROOT / self.lock["artifact"]["plugin_path"]

    def write_package(self, path: Path, version: str) -> None:
        path.write_text(json.dumps({"name": "cc-suite", "version": version}), encoding="utf-8")

    def test_main_discovery_requires_a_full_commit(self) -> None:
        commit = "a03fbb4d175141f38a605698054191c834802d8a"
        self.assertEqual(parse_head(f"{commit}\trefs/heads/main\n"), commit)
        with self.assertRaises(ValueError):
            parse_head("a03fbb4\trefs/heads/main\n")

    def test_package_version_requires_cc_suite_semver(self) -> None:
        self.assertEqual(package_version('{"name":"cc-suite","version":"2.0.0"}'), "2.0.0")
        with self.assertRaises(ValueError):
            package_version('{"name":"other","version":"2.0.0"}')
        with self.assertRaises(ValueError):
            package_version('{"name":"cc-suite","version":"next"}')
        with self.assertRaises(ValueError):
            package_release("a03fbb4", '{"name":"cc-suite","version":"2.0.0"}')

    def test_adapter_version_uses_codex_cachebuster(self) -> None:
        self.assertEqual(adapter_version("2.0.0", 7), "2.0.0+codex.adapter-7")
        self.assertEqual(adapter_version("2.0.0+build.1", 7), "2.0.0+build.1.codex.adapter-7")

    def test_generated_tree_matches_lock(self) -> None:
        self.assertEqual(tree_hash(self.plugin), self.lock["artifact"]["tree_sha256"])

    def test_only_qwen_runtime_is_packaged(self) -> None:
        for name in ("commands", "hooks", "agents"):
            self.assertFalse((self.plugin / name).exists(), name)
        expected = set(self.lock["adapter"]["runtime_files"])
        actual = {
            path.relative_to(self.plugin).as_posix()
            for path in (self.plugin / "scripts").rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, expected)

    def test_all_skills_are_explicit_only(self) -> None:
        for skill in (self.plugin / "skills").iterdir():
            if skill.is_dir():
                sidecar = (skill / "agents/openai.yaml").read_text()
                self.assertIn("allow_implicit_invocation: false", sidecar)
                self.assertIn(f"Use ${skill.name}", sidecar)

    def test_no_unported_slash_command_reference(self) -> None:
        for skill_file in (self.plugin / "skills").glob("*/SKILL.md"):
            self.assertNotIn("/cc-suite:", skill_file.read_text(), skill_file.name)
            self.assertNotIn("\nversion:", skill_file.read_text().split("\n---\n", 1)[0])

    def test_claude_delegation_skills_are_absent(self) -> None:
        removed = {
            "audit", "audit-fix", "claude-debug", "claude-implement",
            "claude-plan", "claude-review", "verify",
        }
        actual = {path.name for path in (self.plugin / "skills").iterdir() if path.is_dir()}
        self.assertFalse(actual & removed)

    def test_qwen_skills_are_native_and_explicit(self) -> None:
        audit_fix = (self.plugin / "skills/qwen-audit-fix/SKILL.md").read_text()
        review = (self.plugin / "skills/qwen-review/SKILL.md").read_text()
        preflight = (self.plugin / "skills/qwen-preflight/SKILL.md").read_text()
        self.assertIn("maximum total Qwen calls", audit_fix)
        self.assertIn(".cc-suite/audits/qwen-audit-fix-", audit_fix)
        self.assertIn("Qwen output is a hypothesis, not proof.", audit_fix)
        self.assertIn("Start a fresh Qwen review", audit_fix)
        self.assertIn("every authorized batch", audit_fix)
        self.assertIn("Run 1–3 fix/test/re-audit rounds", audit_fix)
        self.assertIn("--result-format json-object", audit_fix)
        self.assertIn("--timeout-ms 2147483647", audit_fix)
        self.assertIn("--background", audit_fix)
        self.assertIn("Poll the returned state", audit_fix)
        self.assertIn("set the audit state to `paused`", audit_fix)
        self.assertIn("Each planned review job may", audit_fix)
        self.assertIn("at most one fresh automatic recovery job", audit_fix)
        self.assertIn("automatically start one", audit_fix)
        self.assertIn("A successful replacement", audit_fix)
        self.assertIn("An anomaly in the\nrecovery job is always a hard stop.", audit_fix)
        self.assertIn("Never launch a second recovery", audit_fix)
        self.assertIn("Codex owns", review)
        self.assertIn("explicitly asks Qwen", review)
        self.assertIn("without sending a model prompt", preflight)

    def test_qwen_node_security_suite_passes(self) -> None:
        result = subprocess.run(
            [
                "node", "--test",
                "tests/qwen-runner.test.mjs",
                "tests/qwen-stream.test.mjs",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dry_run_update_check(self) -> None:
        upstream = self.lock["upstream"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "package.json"
            self.write_package(path, upstream["version"])
            changed_commit = "f" * 40 if upstream["commit"] != "f" * 40 else "e" * 40
            result = subprocess.run(
                [
                    sys.executable, "scripts/check_update.py",
                    "--package-file", str(path),
                    "--commit", changed_commit,
                ],
                cwd=ROOT, check=True, text=True, capture_output=True,
            )
        payload = json.loads(result.stdout)
        self.assertFalse(payload["update_available"])
        self.assertTrue(payload["source_commit_changed"])

    def test_update_check_uses_package_version_as_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "package.json"
            self.write_package(path, "99.0.0")
            result = subprocess.run(
                [
                    sys.executable, "scripts/check_update.py",
                    "--package-file", str(path),
                    "--commit", "f" * 40,
                ],
                cwd=ROOT, check=True, text=True, capture_output=True,
            )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["update_available"])
        self.assertEqual(payload["latest_version"], "99.0.0")

    def test_validator_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/validate_adapter.py"], cwd=ROOT, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
