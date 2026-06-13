"""Typed contracts for the backend workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ModelOutputError


QUESTION_MAX = 7


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_answer_text(answer_text: str | None) -> tuple[Literal["answered", "blank"], str]:
    if answer_text is None or answer_text.strip() == "":
        return "blank", ""
    return "answered", answer_text


def reject_placeholder_text(value: str, field_name: str) -> str:
    text = value.strip()
    if not text:
        raise ModelOutputError(f"{field_name} must not be empty.")
    lowered = text.lower()
    banned = (
        "{{",
        "}}",
        "[insert",
        "<insert",
        "lorem ipsum",
        "todo:",
        "tbd",
        "stub response",
        "template text",
        "[placeholder",
        "<placeholder",
        "{{placeholder",
    )
    if any(pattern in lowered for pattern in banned):
        raise ModelOutputError(f"{field_name} contains placeholder-like text.")
    return text


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchResult(StrictModel):
    title: str = ""
    url: str
    snippet: str = ""
    source: str = ""


class QuestionItem(StrictModel):
    id: str
    question: str
    status: Literal["pending", "answered", "blank"] = "pending"

    @field_validator("id", "question")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class QuestionBatch(StrictModel):
    batch_id: str
    cycle_id: str
    batch_goal: str = ""
    questions: list[QuestionItem]

    @model_validator(mode="after")
    def _validate_questions(self) -> "QuestionBatch":
        if not 1 <= len(self.questions) <= QUESTION_MAX:
            raise ValueError(f"question batch must contain 1-{QUESTION_MAX} questions")
        seen: set[str] = set()
        for item in self.questions:
            if item.id in seen:
                raise ValueError(f"duplicate question id: {item.id}")
            seen.add(item.id)
        return self


class ReasoningOutput(StrictModel):
    plan_markdown: str
    handoff_markdown: str
    question_batch: QuestionBatch

    @field_validator("plan_markdown", "handoff_markdown")
    @classmethod
    def _validate_markdown(cls, value: str, info: Any) -> str:
        text = reject_placeholder_text(value, info.field_name)
        if len(text) < 40:
            raise ModelOutputError(f"{info.field_name} is too short to be a real artifact.")
        return text


class QuestioningOutput(StrictModel):
    answer_markdown: str
    citations: list[SearchResult] = Field(default_factory=list)

    @field_validator("answer_markdown")
    @classmethod
    def _validate_answer(cls, value: str) -> str:
        text = reject_placeholder_text(value, "answer_markdown")
        if len(text) < 10:
            raise ModelOutputError("answer_markdown is too short.")
        return text


class ProjectSnapshot(StrictModel):
    project_id: str
    project_path: Path
    phase: str
    active_batch_id: str | None = None
    current_question_id: str | None = None
    current_question_index: int = 0
    batch_complete: bool = False
    reasoning_needed: bool = True


class QuestionPrompt(StrictModel):
    project_id: str
    batch_id: str
    question_id: str
    question: str
    index: int
    total: int


class AnswerRecord(StrictModel):
    question_id: str
    question_text: str
    answer_kind: Literal["answered", "blank"]
    answer_text: str
    clarification_session_ids: list[str] = Field(default_factory=list)
    answered_at: str = Field(default_factory=utc_now)


class QuestionAdvanceResult(StrictModel):
    project_id: str
    phase: str
    batch_complete: bool
    current_question: QuestionPrompt | None = None


class CycleResult(StrictModel):
    project_id: str
    cycle_id: str
    batch_id: str
    question_count: int
    plan_path: Path
    handoff_path: Path
    phase: str


class ClarificationMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str
    citations: list[SearchResult] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class ClarificationSession(StrictModel):
    session_id: str
    project_id: str
    question_id: str
    status: Literal["active", "closed"] = "active"
    messages: list[ClarificationMessage] = Field(default_factory=list)
    final_answer: str | None = None


class ClarificationReply(StrictModel):
    session_id: str
    answer_markdown: str
    citations: list[SearchResult] = Field(default_factory=list)


class ClarificationCloseResult(StrictModel):
    session_id: str
    project_id: str
    question_id: str
    status: Literal["closed"]
    attached_to_answer_context: bool


class QuestionTimelineItem(StrictModel):
    project_id: str
    batch_id: str | None = None
    question_id: str
    question: str
    index: int
    total: int
    status: Literal["pending", "answered", "blank"]
    is_current: bool
    answer_kind: Literal["answered", "blank"] | None = None
    has_branch: bool = False
    branch_count: int = 0
    active_branch_count: int = 0
    branch_label: str | None = None


class QuestionDetail(StrictModel):
    project_id: str
    batch_id: str | None = None
    question_id: str
    question: str
    index: int
    total: int
    status: Literal["pending", "answered", "blank"]
    is_current: bool
    answer: AnswerRecord | None = None
    clarifications: list[ClarificationSession] = Field(default_factory=list)
    has_branch: bool = False
    branch_count: int = 0
    active_branch_count: int = 0
    branch_label: str | None = None


class ProjectUiState(StrictModel):
    project: ProjectSnapshot
    timeline: list[QuestionTimelineItem] = Field(default_factory=list)
    current_question: QuestionDetail | None = None
    question_count: int = 0

