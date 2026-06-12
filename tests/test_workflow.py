from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from planning_agent_system import core, reasoning_stub
from planning_agent_system.structured_yaml import load_yaml_file, write_yaml_file


class WorkflowTests(unittest.TestCase):
    def test_end_to_end_batch_waits_for_continue(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = core.create_project(root, "project-001", "Make rough ideas buildable.")
            reasoning_stub.initial_reasoning(project)
            core.validate_questions_file(project)
            queue = core.create_question_queue(project)
            current = core.current_question(project)
            self.assertIsNotNone(current)
            self.assertEqual(current.question_id, "Q1")
            self.assertNotIn("reason_for_model_later", queue["items"][0])

            for item in queue["items"]:
                state = core.save_answer(project, f"Answer for {item['id']}")

            self.assertEqual(state["current_phase"], "waiting_for_user_continue")
            self.assertTrue(state["batch_complete"])
            self.assertFalse(state["reasoning_allowed"])
            raw_answers = json.loads((project / "raw_answers.json").read_text(encoding="utf-8"))
            self.assertEqual(
                sorted(raw_answers["answers"][0].keys()),
                ["answer_text", "question_id", "question_text", "status"],
            )
            self.assertNotIn("decision", raw_answers["answers"][0])
            self.assertNotIn("risk", raw_answers["answers"][0])

            with self.assertRaises(core.WorkflowError):
                reasoning_stub.revise(project)

            context = core.build_reasoning_context(project, "continue")
            self.assertEqual(
                context["requested_action"],
                "revise_plan_and_generate_next_question_batch",
            )
            reasoning_stub.revise(project)

            updated = load_yaml_file(project / "runtime_state.yaml")
            self.assertEqual(updated["current_phase"], "reasoning_output_ready")
            self.assertTrue((project / "questions" / "batch_002_questions.yaml").exists())

    def test_broken_questions_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = core.create_project(root, "project-001", "Test visible errors.")
            write_yaml_file(
                project / "questions.yaml",
                {
                    "batch_id": "batch_001",
                    "questions": [
                        {"id": "Q1", "question": "Valid?"},
                        {"id": "Q2"},
                        {"id": "Q3", "question": "Also valid?"},
                    ],
                },
            )

            with self.assertRaises(core.WorkflowError):
                core.validate_questions_file(project)

            state = load_yaml_file(project / "runtime_state.yaml")
            self.assertEqual(state["current_phase"], "validation_failed")
            self.assertEqual(state["broken_file"], "questions.yaml")
            self.assertFalse(state["safe_to_continue"])
            self.assertIn("inspect_broken_file", state["user_options"])

    def test_side_questions_are_logged_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = core.create_project(root, "project-001", "Test side question log.")
            before_plan = (project / "idea_backlog.md").read_text(encoding="utf-8")
            entry = core.log_side_question(
                project,
                "Could this use a web UI first?",
                "Possible, but it must remain an adapter.",
            )

            self.assertEqual(entry["status"], "not_a_decision")
            active = load_yaml_file(project / "side_questions" / "active_side_questions.yaml")
            self.assertEqual(active["active_side_questions"][0]["side_question_id"], "SQ001")
            after_plan = (project / "idea_backlog.md").read_text(encoding="utf-8")
            self.assertEqual(before_plan, after_plan)

    def test_finalize_requires_user_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = core.create_project(root, "project-001", "Prepare a final spec.")
            reasoning_stub.initial_reasoning(project)
            queue = core.create_question_queue(project)
            for item in queue["items"]:
                core.save_answer(project, f"Answer for {item['id']}")

            with self.assertRaises(core.WorkflowError):
                reasoning_stub.finalize(project)

            core.build_reasoning_context(project, "finalize")
            reasoning_stub.finalize(project)

            self.assertTrue((project / "exports" / "final_project_spec.md").exists())
            state = load_yaml_file(project / "runtime_state.yaml")
            self.assertEqual(state["current_phase"], "finalized")


if __name__ == "__main__":
    unittest.main()
