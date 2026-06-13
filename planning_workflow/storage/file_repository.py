"""File repository for backend workflow projects."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from planning_workflow.domain.errors import WorkflowError
from planning_workflow.domain.models import (
    AnswerRecord,
    ClarificationCloseResult,
    ClarificationMessage,
    ClarificationSession,
    CycleResult,
    ProjectSnapshot,
    QuestionAdvanceResult,
    QuestionBatch,
    QuestionPrompt,
    ReasoningOutput,
    normalize_answer_text,
    utc_now,
)


PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class FileRepository:
    def __init__(self, repo_root: str | Path, projects_dir_name: str = "projects") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.projects_root = self.repo_root / projects_dir_name

    def create_project(self, project_id: str, initial_message: str) -> ProjectSnapshot:
        self._validate_project_id(project_id)
        project_path = self.project_path(project_id)
        if project_path.exists():
            raise WorkflowError(f"Project already exists: {project_id}")
        for relative in [
            "handoff",
            "questions/batches",
            "answers/batches",
            "clarifications",
            "reasoning/cycles",
        ]:
            (project_path / relative).mkdir(parents=True, exist_ok=False)
        self._write_json(
            project_path / "project.json",
            {
                "project_id": project_id,
                "created_at": utc_now(),
                "initial_message": initial_message,
            },
        )
        self._write_json(
            project_path / "state.json",
            {
                "phase": "created",
                "active_batch_id": None,
                "current_question_id": None,
                "current_question_index": 0,
                "batch_complete": False,
                "reasoning_needed": True,
                "closed_clarifications_by_question": {},
                "created_at": utc_now(),
                "updated_at": utc_now(),
            },
        )
        self._write_json(
            project_path / "questions" / "queue.json",
            {"batch_id": None, "items": [], "current_index": 0},
        )
        (project_path / "events.jsonl").write_text("", encoding="utf-8")
        self.append_event(project_id, "project_created", {"initial_message_length": len(initial_message)})
        return self.snapshot(project_id)

    def snapshot(self, project_id: str) -> ProjectSnapshot:
        state = self.load_state(project_id)
        return ProjectSnapshot(
            project_id=project_id,
            project_path=self.project_path(project_id),
            phase=state["phase"],
            active_batch_id=state.get("active_batch_id"),
            current_question_id=state.get("current_question_id"),
            current_question_index=int(state.get("current_question_index") or 0),
            batch_complete=bool(state.get("batch_complete")),
            reasoning_needed=bool(state.get("reasoning_needed", True)),
        )

    def project_path(self, project_id: str) -> Path:
        self._validate_project_id(project_id)
        return self.projects_root / project_id

    def require_project(self, project_id: str) -> Path:
        path = self.project_path(project_id)
        if not path.is_dir():
            raise WorkflowError(f"Project does not exist: {project_id}")
        return path

    def load_state(self, project_id: str) -> dict[str, Any]:
        return self._read_json(self.require_project(project_id) / "state.json")

    def save_state(self, project_id: str, state: dict[str, Any]) -> None:
        state["updated_at"] = utc_now()
        self._write_json(self.require_project(project_id) / "state.json", state)

    def build_reasoning_context(self, project_id: str) -> dict[str, Any]:
        project_path = self.require_project(project_id)
        context: dict[str, Any] = {
            "project": self._read_json(project_path / "project.json"),
            "state": self._read_json(project_path / "state.json"),
            "current_plan_markdown": self._read_text_if_exists(project_path / "current_plan.md"),
            "question_queue": self._read_json(project_path / "questions" / "queue.json"),
            "answer_batches": [],
            "clarifications": [],
        }
        for path in sorted((project_path / "answers" / "batches").glob("*.json")):
            context["answer_batches"].append(self._read_json(path))
        for path in sorted((project_path / "clarifications").glob("*.json")):
            context["clarifications"].append(self._read_json(path))
        return context

    def build_questioning_context(self, project_id: str, question_id: str) -> dict[str, Any]:
        context = self.build_reasoning_context(project_id)
        context["active_question"] = self._find_question(project_id, question_id)
        return context

    def next_cycle_id(self, project_id: str) -> str:
        project_path = self.require_project(project_id)
        return f"cycle_{self._next_index(project_path / 'reasoning' / 'cycles', 'cycle_'):04d}"

    def next_batch_id(self, project_id: str) -> str:
        project_path = self.require_project(project_id)
        return f"batch_{self._next_index(project_path / 'questions' / 'batches', 'batch_'):04d}"

    def store_reasoning_success(
        self,
        project_id: str,
        cycle_id: str,
        request: dict[str, Any],
        response: dict[str, Any],
        output: ReasoningOutput,
        usage: dict[str, Any],
    ) -> CycleResult:
        project_path = self.require_project(project_id)
        cycle_dir = project_path / "reasoning" / "cycles" / cycle_id
        cycle_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(cycle_dir / "request.json", request)
        self._write_json(cycle_dir / "response.json", response)
        self._write_json(cycle_dir / "validated_output.json", output.model_dump(mode="json"))
        self._write_json(cycle_dir / "usage.json", usage)

        self._write_text(project_path / "current_plan.md", output.plan_markdown.rstrip() + "\n")
        self._write_text(project_path / "handoff" / "current_project_brief.md", output.handoff_markdown.rstrip() + "\n")
        self._write_json(
            project_path / "questions" / "batches" / f"{output.question_batch.batch_id}.json",
            output.question_batch.model_dump(mode="json"),
        )
        queue = {
            "batch_id": output.question_batch.batch_id,
            "items": [item.model_dump(mode="json") for item in output.question_batch.questions],
            "current_index": 0,
        }
        self._write_json(project_path / "questions" / "queue.json", queue)
        state = self.load_state(project_id)
        first = output.question_batch.questions[0]
        state.update(
            {
                "phase": "asking_questions",
                "active_batch_id": output.question_batch.batch_id,
                "current_question_id": first.id,
                "current_question_index": 0,
                "batch_complete": False,
                "reasoning_needed": False,
            }
        )
        self.save_state(project_id, state)
        self.append_event(
            project_id,
            "reasoning_cycle_completed",
            {
                "cycle_id": cycle_id,
                "batch_id": output.question_batch.batch_id,
                "question_count": len(output.question_batch.questions),
            },
        )
        return CycleResult(
            project_id=project_id,
            cycle_id=cycle_id,
            batch_id=output.question_batch.batch_id,
            question_count=len(output.question_batch.questions),
            plan_path=project_path / "current_plan.md",
            handoff_path=project_path / "handoff" / "current_project_brief.md",
            phase="asking_questions",
        )

    def store_reasoning_error(self, project_id: str, cycle_id: str, error: Exception) -> None:
        project_path = self.require_project(project_id)
        cycle_dir = project_path / "reasoning" / "cycles" / cycle_id
        cycle_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(
            cycle_dir / "error.json",
            {"error_type": type(error).__name__, "message": str(error), "created_at": utc_now()},
        )
        self.append_event(project_id, "reasoning_cycle_failed", {"cycle_id": cycle_id, "error_type": type(error).__name__})

    def current_question(self, project_id: str) -> QuestionPrompt | None:
        project_path = self.require_project(project_id)
        queue = self._read_json(project_path / "questions" / "queue.json")
        items = queue.get("items", [])
        index = int(queue.get("current_index") or 0)
        if not items or index >= len(items):
            return None
        item = items[index]
        return QuestionPrompt(
            project_id=project_id,
            batch_id=queue["batch_id"],
            question_id=item["id"],
            question=item["question"],
            index=index + 1,
            total=len(items),
        )

    def submit_answer(self, project_id: str, answer_text: str | None) -> QuestionAdvanceResult:
        project_path = self.require_project(project_id)
        queue_path = project_path / "questions" / "queue.json"
        queue = self._read_json(queue_path)
        items = queue.get("items", [])
        index = int(queue.get("current_index") or 0)
        if not items or index >= len(items):
            raise WorkflowError("No active question is available.")

        item = items[index]
        answer_kind, normalized_text = normalize_answer_text(answer_text)
        item["status"] = answer_kind
        batch_id = queue["batch_id"]
        state = self.load_state(project_id)
        clarification_ids = (
            state.get("closed_clarifications_by_question", {})
            .get(item["id"], [])
        )
        answer = AnswerRecord(
            question_id=item["id"],
            question_text=item["question"],
            answer_kind=answer_kind,
            answer_text=normalized_text,
            clarification_session_ids=list(clarification_ids),
        )
        answers_path = project_path / "answers" / "batches" / f"{batch_id}.json"
        answers_payload = (
            self._read_json(answers_path)
            if answers_path.exists()
            else {"batch_id": batch_id, "answers": []}
        )
        answers_payload["answers"] = [
            existing
            for existing in answers_payload.get("answers", [])
            if existing.get("question_id") != item["id"]
        ]
        answers_payload["answers"].append(answer.model_dump(mode="json"))

        next_index = index + 1
        queue["current_index"] = next_index
        self._write_json(queue_path, queue)
        self._write_json(answers_path, answers_payload)

        if next_index >= len(items):
            state.update(
                {
                    "phase": "batch_complete",
                    "current_question_id": None,
                    "current_question_index": next_index,
                    "batch_complete": True,
                    "reasoning_needed": True,
                }
            )
        else:
            state.update(
                {
                    "phase": "asking_questions",
                    "current_question_id": items[next_index]["id"],
                    "current_question_index": next_index,
                    "batch_complete": False,
                    "reasoning_needed": False,
                }
            )
        self.save_state(project_id, state)
        self.append_event(project_id, "answer_saved", {"batch_id": batch_id, "question_id": item["id"], "answer_kind": answer_kind})
        return QuestionAdvanceResult(
            project_id=project_id,
            phase=state["phase"],
            batch_complete=bool(state["batch_complete"]),
            current_question=self.current_question(project_id),
        )

    def create_clarification_session(
        self, project_id: str, question_id: str, user_question: str
    ) -> ClarificationSession:
        self.require_project(project_id)
        self._find_question(project_id, question_id)
        session_id = f"clarification_{self._next_index(self.project_path(project_id) / 'clarifications', 'clarification_'):04d}"
        session = ClarificationSession(
            session_id=session_id,
            project_id=project_id,
            question_id=question_id,
            messages=[ClarificationMessage(role="user", content=user_question)],
        )
        self._write_json(
            self.project_path(project_id) / "clarifications" / f"{session_id}.json",
            session.model_dump(mode="json"),
        )
        self.append_event(project_id, "clarification_started", {"session_id": session_id, "question_id": question_id})
        return session

    def append_clarification_message(
        self,
        project_id: str,
        session_id: str,
        message: ClarificationMessage,
    ) -> ClarificationSession:
        path = self.project_path(project_id) / "clarifications" / f"{session_id}.json"
        data = self._read_json(path)
        session = ClarificationSession.model_validate(data)
        if session.status != "active":
            raise WorkflowError("Clarification session is closed.")
        session.messages.append(message)
        self._write_json(path, session.model_dump(mode="json"))
        return session

    def find_clarification(self, session_id: str) -> ClarificationSession:
        for path in self.projects_root.glob(f"*/clarifications/{session_id}.json"):
            return ClarificationSession.model_validate(self._read_json(path))
        raise WorkflowError(f"Clarification session does not exist: {session_id}")

    def close_clarification(
        self,
        session_id: str,
        final_answer: str | None = None,
    ) -> ClarificationCloseResult:
        session = self.find_clarification(session_id)
        project_id = session.project_id
        path = self.project_path(project_id) / "clarifications" / f"{session_id}.json"
        session.status = "closed"
        if final_answer is not None:
            session.final_answer = final_answer
        self._write_json(path, session.model_dump(mode="json"))

        state = self.load_state(project_id)
        mapping = state.setdefault("closed_clarifications_by_question", {})
        ids = mapping.setdefault(session.question_id, [])
        if session_id not in ids:
            ids.append(session_id)
        self.save_state(project_id, state)
        self.append_event(project_id, "clarification_closed", {"session_id": session_id, "question_id": session.question_id})
        return ClarificationCloseResult(
            session_id=session_id,
            project_id=project_id,
            question_id=session.question_id,
            status="closed",
            attached_to_answer_context=True,
        )

    def append_event(self, project_id: str, event_type: str, payload: dict[str, Any]) -> None:
        project_path = self.project_path(project_id)
        event = {"type": event_type, "created_at": utc_now(), "payload": payload}
        with (project_path / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def _find_question(self, project_id: str, question_id: str) -> dict[str, Any]:
        queue = self._read_json(self.project_path(project_id) / "questions" / "queue.json")
        for item in queue.get("items", []):
            if item.get("id") == question_id:
                return item
        raise WorkflowError(f"Question does not exist in the active queue: {question_id}")

    def _validate_project_id(self, project_id: str) -> None:
        if not PROJECT_ID_RE.match(project_id):
            raise WorkflowError("Project id must start with a letter/number and contain only letters, numbers, dots, dashes, or underscores.")

    def _next_index(self, directory: Path, prefix: str) -> int:
        directory.mkdir(parents=True, exist_ok=True)
        highest = 0
        for path in directory.iterdir():
            if not path.name.startswith(prefix):
                continue
            digits = "".join(ch for ch in path.stem[len(prefix):] if ch.isdigit())
            if digits:
                highest = max(highest, int(digits))
        return highest + 1

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowError(f"Could not read JSON file {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise WorkflowError(f"JSON file must contain an object: {path}")
        return data

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        self._write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    def _read_text_if_exists(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""
