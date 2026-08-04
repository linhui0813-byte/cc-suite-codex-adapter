from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import adapter_version, latest_stable, parse_ls_remote, tree_hash


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = json.loads((ROOT / "provenance.lock.json").read_text())
        self.plugin = ROOT / self.lock["artifact"]["plugin_path"]

    def current_remote_text(self, commit: str | None = None) -> str:
        upstream = self.lock["upstream"]
        commit = commit or upstream["commit"]
        return (
            f"{upstream['tag_object']}\trefs/tags/{upstream['tag']}\n"
            f"{commit}\trefs/tags/{upstream['tag']}^{{}}\n"
        )

    def test_stable_tag_discovery_ignores_prereleases(self) -> None:
        tags = parse_ls_remote((ROOT / "tests/fixtures/ls-remote.txt").read_text())
        tag, refs = latest_stable(tags)
        self.assertEqual(tag, "v1.5.0")
        self.assertEqual(refs["commit"], "a03fbb4d175141f38a605698054191c834802d8a")

    def test_adapter_version_uses_codex_cachebuster(self) -> None:
        self.assertEqual(adapter_version("v1.5.0", 4), "1.5.0+codex.adapter-4")

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
        self.assertIn("maximum Qwen calls", audit_fix)
        self.assertIn(".cc-suite/audits/qwen-audit-fix-", audit_fix)
        self.assertIn("Qwen output is a hypothesis, not proof.", audit_fix)
        self.assertIn("Start a fresh Qwen review", audit_fix)
        self.assertIn("every authorized batch", audit_fix)
        self.assertIn("Run 1–3 fix/test/re-audit rounds", audit_fix)
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
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "current.txt"
            path.write_text(self.current_remote_text())
            result = subprocess.run(
                [sys.executable, "scripts/check_update.py", "--remote-file", str(path)],
                cwd=ROOT, check=True, text=True, capture_output=True,
            )
        payload = json.loads(result.stdout)
        self.assertFalse(payload["update_available"])
        self.assertFalse(payload["pinned_tag_moved"])

    def test_update_check_fails_closed_if_pinned_tag_moves(self) -> None:
        fixture = self.current_remote_text("ffffffffffffffffffffffffffffffffffffffff")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "moved.txt"
            path.write_text(fixture)
            result = subprocess.run(
                [sys.executable, "scripts/check_update.py", "--remote-file", str(path)],
                cwd=ROOT, text=True, capture_output=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertTrue(json.loads(result.stdout)["pinned_tag_moved"])

    def test_validator_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/validate_adapter.py"], cwd=ROOT, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
