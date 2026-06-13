"""Stable Python service API for backend workflow adapters."""

from __future__ import annotations

from pathlib import Path

from planning_workflow.agents.questioning import QuestioningAgent
from planning_workflow.agents.reasoning import ReasoningAgent
from planning_workflow.domain.models import (
    ClarificationCloseResult,
    ClarificationMessage,
    ClarificationReply,
    ClarificationSession,
    CycleResult,
    ProjectSnapshot,
    QuestionAdvanceResult,
    QuestionPrompt,
)
from planning_workflow.providers.config import load_settings
from planning_workflow.providers.deepseek import DeepSeekClient
from planning_workflow.providers.search import build_search_provider
from planning_workflow.storage.file_repository import FileRepository


class PlanningWorkflowService:
    def __init__(
        self,
        repository: FileRepository,
        reasoning_agent: ReasoningAgent,
        questioning_agent: QuestioningAgent,
    ) -> None:
        self.repository = repository
        self.reasoning_agent = reasoning_agent
        self.questioning_agent = questioning_agent

    @classmethod
    def from_repo(cls, repo_root: str | Path = ".") -> "PlanningWorkflowService":
        settings = load_settings(repo_root)
        repository = FileRepository(settings.repo_root, settings.projects_dir_name)
        deepseek_client = DeepSeekClient(settings)
        search_provider = build_search_provider(settings)
        return cls(
            repository=repository,
            reasoning_agent=ReasoningAgent(deepseek_client),
            questioning_agent=QuestioningAgent(deepseek_client, search_provider),
        )

    def create_project(self, project_id: str, initial_message: str) -> ProjectSnapshot:
        return self.repository.create_project(project_id, initial_message)

    def run_reasoning_cycle(self, project_id: str) -> CycleResult:
        self.repository.require_project(project_id)
        cycle_id = self.repository.next_cycle_id(project_id)
        batch_id = self.repository.next_batch_id(project_id)
        context = self.repository.build_reasoning_context(project_id)
        try:
            result = self.reasoning_agent.run(context, cycle_id=cycle_id, batch_id=batch_id)
            return self.repository.store_reasoning_success(
                project_id=project_id,
                cycle_id=cycle_id,
                request=result.request,
                response=result.response,
                output=result.output,
                usage=result.usage,
            )
        except Exception as exc:
            self.repository.store_reasoning_error(project_id, cycle_id, exc)
            raise

    def get_current_question(self, project_id: str) -> QuestionPrompt | None:
        return self.repository.current_question(project_id)

    def submit_answer(self, project_id: str, answer_text: str | None = None) -> QuestionAdvanceResult:
        return self.repository.submit_answer(project_id, answer_text)

    def start_clarification(
        self,
        project_id: str,
        question_id: str,
        user_question: str,
    ) -> ClarificationSession:
        session = self.repository.create_clarification_session(project_id, question_id, user_question)
        context = self.repository.build_questioning_context(project_id, question_id)
        result = self.questioning_agent.answer(context, user_question)
        return self.repository.append_clarification_message(
            project_id,
            session.session_id,
            ClarificationMessage(
                role="assistant",
                content=result.answer_markdown,
                citations=result.citations,
            ),
        )

    def send_clarification_message(self, session_id: str, message: str) -> ClarificationReply:
        session = self.repository.find_clarification(session_id)
        self.repository.append_clarification_message(
            session.project_id,
            session_id,
            ClarificationMessage(role="user", content=message),
        )
        context = self.repository.build_questioning_context(session.project_id, session.question_id)
        result = self.questioning_agent.answer(context, message)
        self.repository.append_clarification_message(
            session.project_id,
            session_id,
            ClarificationMessage(
                role="assistant",
                content=result.answer_markdown,
                citations=result.citations,
            ),
        )
        return ClarificationReply(
            session_id=session_id,
            answer_markdown=result.answer_markdown,
            citations=result.citations,
        )

    def close_clarification(
        self,
        session_id: str,
        final_answer: str | None = None,
    ) -> ClarificationCloseResult:
        return self.repository.close_clarification(session_id, final_answer)
