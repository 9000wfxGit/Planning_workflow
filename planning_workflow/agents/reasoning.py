"""Reasoning agent adapter backed by DeepSeek strict JSON output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from planning_workflow.domain.errors import ModelOutputError
from planning_workflow.domain.models import ReasoningOutput
from planning_workflow.providers.deepseek import DeepSeekClient


@dataclass(frozen=True)
class ReasoningAgentResult:
    request: dict[str, Any]
    response: dict[str, Any]
    output: ReasoningOutput
    usage: dict[str, Any]


class ReasoningAgent:
    def __init__(self, client: DeepSeekClient) -> None:
        self.client = client

    def run(self, context: dict[str, Any], cycle_id: str, batch_id: str) -> ReasoningAgentResult:
        system_prompt = (
            "You are the Reasoning Agent for a private backend-first planning workflow. "
            "You own semantic planning, answer interpretation, contradiction handling, "
            "and question generation. Deterministic backend code owns state, routing, "
            "validation, and storage. Return JSON only. Do not include placeholders, "
            "fake errors, template text, or invented implementation results. Generate "
            "at most seven concrete questions. The project folder must be usable after "
            "this cycle without a finalize step."
        )
        user_payload = {
            "task": "run_reasoning_cycle",
            "cycle_id": cycle_id,
            "required_batch_id": batch_id,
            "json_contract": {
                "plan_markdown": "complete current plan as Markdown",
                "handoff_markdown": "concise coding-agent handoff as Markdown",
                "question_batch": {
                    "batch_id": batch_id,
                    "cycle_id": cycle_id,
                    "batch_goal": "why this question batch matters",
                    "questions": [
                        {"id": "Q1", "question": "one user-facing question"}
                    ],
                },
            },
            "constraints": [
                "Return a JSON object matching the contract exactly.",
                "question_batch.batch_id must equal required_batch_id.",
                "question_batch.cycle_id must equal cycle_id.",
                "Use between one and seven questions.",
                "Do not add UI, HTTP API, speech, database, auth, or productization scope.",
                "Treat blank answers as unknown, not as approval.",
            ],
            "project_context": context,
        }
        result = self.client.complete_json(system_prompt, user_payload)
        try:
            output = ReasoningOutput.model_validate(result.data)
        except (ValidationError, ModelOutputError) as exc:
            raise ModelOutputError(f"Reasoning output failed validation: {exc}") from exc
        if output.question_batch.batch_id != batch_id:
            raise ModelOutputError("Reasoning output used the wrong batch_id.")
        if output.question_batch.cycle_id != cycle_id:
            raise ModelOutputError("Reasoning output used the wrong cycle_id.")
        return ReasoningAgentResult(
            request=result.request,
            response=result.response,
            output=output,
            usage=result.usage,
        )
