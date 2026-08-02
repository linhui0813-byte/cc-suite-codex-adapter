from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import latest_stable, parse_ls_remote, tree_hash
from build_plugin import inject_boundary, transform_upstream_skill


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

    def test_transform_injects_boundary_after_frontmatter(self) -> None:
        source = "---\nname: demo\ndescription: demo\n---\n\n# Demo\n"
        result = inject_boundary(source)
        self.assertIn("Codex adapter boundary", result)
        self.assertLess(result.index("Codex adapter boundary"), result.index("# Demo"))

    def test_transform_removes_unported_refresh_command(self) -> None:
        source = "---\nname: demo\ndescription: demo\n---\nRun /cc-suite:refresh-knowledge to update from latest docs.\n"
        result = transform_upstream_skill("claude-code-conventions", source)
        self.assertNotIn("/cc-suite:refresh-knowledge", result)

    def test_generated_tree_matches_lock(self) -> None:
        self.assertEqual(tree_hash(self.plugin), self.lock["artifact"]["tree_sha256"])

    def test_no_runtime_component_directories(self) -> None:
        for name in ("commands", "hooks", "scripts", "agents"):
            self.assertFalse((self.plugin / name).exists(), name)

    def test_all_skills_are_explicit_only(self) -> None:
        for skill in (self.plugin / "skills").iterdir():
            if skill.is_dir():
                self.assertIn("allow_implicit_invocation: false", (skill / "agents/openai.yaml").read_text())

    def test_no_unported_slash_command_reference(self) -> None:
        for skill_file in (self.plugin / "skills").glob("*/SKILL.md"):
            self.assertNotIn("/cc-suite:", skill_file.read_text(), skill_file.name)
            self.assertNotIn("\nversion:", skill_file.read_text().split("\n---\n", 1)[0])

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
