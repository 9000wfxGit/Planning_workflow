"""Read-only questioning agent for side-branch clarification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from planning_workflow.domain.errors import ModelOutputError
from planning_workflow.domain.models import QuestioningOutput, SearchResult
from planning_workflow.providers.deepseek import DeepSeekClient
from planning_workflow.providers.search import SearchProvider


@dataclass(frozen=True)
class QuestioningAgentResult:
    request: dict[str, Any]
    response: dict[str, Any]
    answer_markdown: str
    citations: list[SearchResult]
    search_results: list[SearchResult]
    usage: dict[str, Any]


class QuestioningAgent:
    def __init__(self, client: DeepSeekClient, search_provider: SearchProvider | None = None) -> None:
        self.client = client
        self.search_provider = search_provider

    def answer(self, context: dict[str, Any], user_question: str) -> QuestioningAgentResult:
        search_results: list[SearchResult] = []
        if self.search_provider is not None:
            search_results = self.search_provider.search(user_question, max_results=5)

        system_prompt = (
            "You are the read-only Questioning Agent for a private planning workflow. "
            "You may explain, compare, and clarify using the project context and supplied "
            "search results. You must not edit the plan, make decisions, or claim that "
            "state has changed. Return JSON only."
        )
        user_payload = {
            "task": "answer_clarification_question",
            "json_contract": {
                "answer_markdown": "direct answer to the user's side question",
                "citations": [{"title": "source title", "url": "source url", "snippet": "short support", "source": "provider"}],
            },
            "project_context": context,
            "user_question": user_question,
            "search_results": [item.model_dump() for item in search_results],
        }
        result = self.client.complete_json(system_prompt, user_payload)
        try:
            output = QuestioningOutput.model_validate(result.data)
        except (ValidationError, ModelOutputError) as exc:
            raise ModelOutputError(f"Questioning output failed validation: {exc}") from exc
        return QuestioningAgentResult(
            request=result.request,
            response=result.response,
            answer_markdown=output.answer_markdown,
            citations=output.citations,
            search_results=search_results,
            usage=result.usage,
        )
