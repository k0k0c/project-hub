import unittest
from unittest.mock import patch

from scripts import git_safety_check


class GitSafetyCheckTests(unittest.TestCase):
    @patch("scripts.git_safety_check.staged_paths")
    def test_rejects_mass_deletion(self, staged_paths):
        staged_paths.return_value = [("D", f"src/file-{index}.py") for index in range(21)]
        self.assertIn("exceeds the safety limit", git_safety_check.check_staged()[0])

    @patch("scripts.git_safety_check.staged_paths")
    def test_rejects_policy_file_deletion(self, staged_paths):
        staged_paths.return_value = [("D", ".codex/config.toml")]
        self.assertIn("protected project policy file", git_safety_check.check_staged()[0])

    @patch("scripts.git_safety_check.staged_paths", return_value=[])
    def test_allows_normal_push_ref(self, _staged_paths):
        issues = git_safety_check.check_push("origin", "refs/heads/feature", "refs/heads/main")
        self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()
