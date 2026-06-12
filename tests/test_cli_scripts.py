from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class CliScriptTests(unittest.TestCase):
    def test_cli_happy_path_continue_and_revise(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            common = ["--root", temp, "--project-id", "project-001"]

            self.run_script(
                "create_project.py",
                *common,
                "--idea",
                "Create precise plans from rough ideas.",
            )
            self.run_script("reasoning_agent_stub.py", *common, "--mode", "initial")
            self.run_script("validate_structure.py", *common)
            self.run_script("parse_questions.py", *common)
            for index in range(1, 6):
                self.run_script("save_answer.py", *common, "--answer", f"answer {index}")

            inspect = self.run_script("inspect_project.py", *common)
            self.assertIn("current_phase: waiting_for_user_continue", inspect.stdout)
            self.assertIn("reasoning_allowed: False", inspect.stdout)

            self.run_script("apply_command.py", *common, "--command", "continue")
            self.run_script("reasoning_agent_stub.py", *common, "--mode", "revise")
            self.run_script("validate_structure.py", *common)

    def test_cli_pause_command_does_not_build_reasoning_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            common = ["--root", temp, "--project-id", "project-001"]
            self.run_script(
                "create_project.py",
                *common,
                "--idea",
                "Create precise plans from rough ideas.",
            )
            result = self.run_script("apply_command.py", *common, "--command", "pause")
            self.assertIn("current_phase=paused", result.stdout)
            self.assertFalse((Path(temp) / "projects" / "project-001" / "reasoning_context.yaml").exists())

    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / name), *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
