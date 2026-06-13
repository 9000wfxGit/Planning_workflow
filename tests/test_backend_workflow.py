from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from planning_workflow.agents.questioning import QuestioningAgentResult
from planning_workflow.agents.reasoning import ReasoningAgentResult
from planning_workflow.application.service import PlanningWorkflowService
from planning_workflow.domain.errors import ModelOutputError
from planning_workflow.domain.models import (
    QuestionBatch,
    QuestionItem,
    ReasoningOutput,
    SearchResult,
    normalize_answer_text,
)
from planning_workflow.storage.file_repository import FileRepository


@dataclass
class FakeReasoningAgent:
    fail: bool = False
    question_count: int = 2

    def run(self, context, cycle_id: str, batch_id: str) -> ReasoningAgentResult:
        if self.fail:
            raise ModelOutputError("invalid model json")
        questions = [
            QuestionItem(id=f"Q{index}", question=f"Question {index}?")
            for index in range(1, self.question_count + 1)
        ]
        output = ReasoningOutput(
            plan_markdown="# Current Plan\n\nThis is a concrete backend plan for the supplied idea.",
            handoff_markdown="# Coding Agent Handoff\n\nBuild from this concrete backend plan and current state.",
            question_batch=QuestionBatch(
                batch_id=batch_id,
                cycle_id=cycle_id,
                batch_goal="Clarify the backend plan.",
                questions=questions,
            ),
        )
        return ReasoningAgentResult(
            request={"fake": "request"},
            response={"fake": "response"},
            output=output,
            usage={"total_tokens": 0},
        )


class FakeQuestioningAgent:
    def answer(self, context, user_question: str) -> QuestioningAgentResult:
        citation = SearchResult(
            title="Local project context",
            url="project://current",
            snippet="Read-only clarification",
            source="local",
        )
        return QuestioningAgentResult(
            request={"question": user_question},
            response={"answer": "ok"},
            answer_markdown="This clarification is based on the current project context.",
            citations=[citation],
            search_results=[],
            usage={},
        )


class BackendWorkflowTests(unittest.TestCase):
    def make_service(self, root: Path, reasoning_agent=None) -> PlanningWorkflowService:
        return PlanningWorkflowService(
            repository=FileRepository(root),
            reasoning_agent=reasoning_agent or FakeReasoningAgent(),
            questioning_agent=FakeQuestioningAgent(),
        )

    def test_project_creation_creates_raw_state_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root)
            snapshot = service.create_project("project-001", "Build a planner.")

            self.assertEqual(snapshot.phase, "created")
            project = root / "projects" / "project-001"
            self.assertTrue((project / "project.json").exists())
            self.assertTrue((project / "state.json").exists())
            self.assertFalse((project / "current_plan.md").exists())
            self.assertFalse((project / "handoff" / "current_project_brief.md").exists())

    def test_auto_project_creation_allocates_initialized_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root)
            snapshot = service.create_auto_project(
                "Build a planner from the UI.",
                project_id_prefix="ui-project",
            )

            self.assertTrue(snapshot.project_id.startswith("ui-project-"))
            self.assertEqual(snapshot.phase, "created")
            self.assertTrue(snapshot.project_path.is_dir())

    def test_reasoning_cycle_writes_plan_handoff_and_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root)
            service.create_project("project-001", "Build a planner.")
            result = service.run_reasoning_cycle("project-001")

            self.assertEqual(result.question_count, 2)
            self.assertTrue(result.plan_path.exists())
            self.assertTrue(result.handoff_path.exists())
            current = service.get_current_question("project-001")
            self.assertIsNotNone(current)
            self.assertEqual(current.question_id, "Q1")

    def test_ui_state_navigation_selected_answer_and_branch_indicator(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root, FakeReasoningAgent(question_count=3))
            service.create_project("project-001", "Build a planner.")
            service.run_reasoning_cycle("project-001")

            session = service.open_clarification("project-001", "Q1")
            self.assertEqual(session.messages, [])

            state = service.get_project_ui_state("project-001")
            self.assertEqual(state.question_count, 3)
            self.assertIsNotNone(state.current_question)
            self.assertEqual(state.current_question.question_id, "Q1")
            self.assertEqual(state.timeline[0].branch_label, "BQ1")
            self.assertEqual(state.timeline[0].branch_count, 1)
            self.assertEqual(state.timeline[0].active_branch_count, 1)

            self.assertIsNone(service.get_previous_question("project-001", "Q1"))
            self.assertEqual(service.get_next_question("project-001", "Q1").question_id, "Q2")

            service.submit_answer_for_question("project-001", "Q2", "Answer Q2 first.")
            state = service.get_project_ui_state("project-001")
            self.assertEqual(state.current_question.question_id, "Q1")
            self.assertEqual(state.timeline[1].answer_kind, "answered")
            detail = service.get_question("project-001", "Q2")
            self.assertIsNotNone(detail.answer)
            self.assertEqual(detail.answer.answer_text, "Answer Q2 first.")

            service.close_clarification(session.session_id, "Q1 is now clear.")
            state = service.get_project_ui_state("project-001")
            self.assertEqual(state.timeline[0].active_branch_count, 0)

    def test_question_batch_rejects_more_than_seven_questions(self) -> None:
        questions = [
            QuestionItem(id=f"Q{index}", question=f"Question {index}?")
            for index in range(1, 9)
        ]
        with self.assertRaises(ValueError):
            QuestionBatch(
                batch_id="batch_0001",
                cycle_id="cycle_0001",
                questions=questions,
            )

    def test_blank_answer_normalization(self) -> None:
        self.assertEqual(normalize_answer_text(None), ("blank", ""))
        self.assertEqual(normalize_answer_text("   "), ("blank", ""))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root)
            service.create_project("project-001", "Build a planner.")
            service.run_reasoning_cycle("project-001")
            service.submit_answer("project-001", "   ")

            answers = service.repository._read_json(
                root / "projects" / "project-001" / "answers" / "batches" / "batch_0001.json"
            )
            self.assertEqual(answers["answers"][0]["answer_kind"], "blank")
            self.assertEqual(answers["answers"][0]["answer_text"], "")

    def test_clarification_is_read_only_and_attached_to_answer_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root)
            service.create_project("project-001", "Build a planner.")
            service.run_reasoning_cycle("project-001")
            project = root / "projects" / "project-001"
            plan_before = (project / "current_plan.md").read_text(encoding="utf-8")

            session = service.start_clarification("project-001", "Q1", "What does this question mean?")
            self.assertEqual(session.status, "active")
            self.assertEqual(len(session.messages), 2)
            close_result = service.close_clarification(session.session_id, "Now I can answer.")
            self.assertTrue(close_result.attached_to_answer_context)

            plan_after = (project / "current_plan.md").read_text(encoding="utf-8")
            self.assertEqual(plan_before, plan_after)
            service.submit_answer("project-001", "Answer with context.")
            answers = service.repository._read_json(project / "answers" / "batches" / "batch_0001.json")
            self.assertEqual(
                answers["answers"][0]["clarification_session_ids"],
                [session.session_id],
            )

    def test_invalid_model_output_does_not_update_plan_or_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root, reasoning_agent=FakeReasoningAgent(fail=True))
            service.create_project("project-001", "Build a planner.")

            with self.assertRaises(ModelOutputError):
                service.run_reasoning_cycle("project-001")

            project = root / "projects" / "project-001"
            self.assertFalse((project / "current_plan.md").exists())
            state = service.repository._read_json(project / "state.json")
            self.assertEqual(state["phase"], "created")
            queue = service.repository._read_json(project / "questions" / "queue.json")
            self.assertEqual(queue["items"], [])

    def test_backend_package_does_not_import_ui_frameworks(self) -> None:
        package_root = Path(__file__).resolve().parents[1] / "planning_workflow"
        forbidden = ("fastapi", "flask", "streamlit", "gradio", "tkinter")
        for path in package_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for name in forbidden:
                self.assertNotIn(name, text, f"{path} imports or mentions {name}")


if __name__ == "__main__":
    unittest.main()
