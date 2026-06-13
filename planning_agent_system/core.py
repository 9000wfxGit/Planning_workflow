"""Mechanical orchestration for the system-first planning workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from .structured_yaml import StructuredYamlError, load_yaml_file, write_yaml_file


PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
QUESTION_MIN = 3
QUESTION_DEFAULT = 5
QUESTION_MAX = 7
PROJECT_SETTINGS_DEFAULTS = {"suppress_incomplete_batch_warning": False}


class WorkflowError(RuntimeError):
    """Raised for mechanical workflow errors."""


@dataclass(frozen=True)
class CurrentQuestion:
    batch_id: str
    question_id: str
    question: str
    index: int
    total: int
    scope: str | None = None


def workspace_root(path: str | Path | None = None) -> Path:
    return Path(path or ".").resolve()


def projects_dir(root: str | Path | None = None) -> Path:
    return workspace_root(root) / "projects"


def require_project_id(project_id: str) -> str:
    if not PROJECT_ID_RE.match(project_id):
        raise WorkflowError(
            "Project id must start with a letter/number and contain only "
            "letters, numbers, dots, dashes, or underscores."
        )
    return project_id


def project_dir(root: str | Path | None, project_id: str) -> Path:
    return projects_dir(root) / require_project_id(project_id)


def initialize_planning(
    project_path: str | Path,
    project_name: str | None = None,
    initial_prompt: str | None = None,
) -> Path:
    path = Path(project_path).resolve()
    if path.exists() and not path.is_dir():
        raise WorkflowError(f"Project path is not a directory: {path}")
    if path.exists() and any(path.iterdir()):
        if get_project_status(path)["is_initialized"]:
            raise WorkflowError(f"Project already initialized: {path}")
        raise WorkflowError(
            f"Project directory is not empty and is not initialized: {path}"
        )

    name = project_name or path.name
    prompt = (initial_prompt or "").strip()
    for directory in [
        path,
        path / "answers",
        path / "questions",
        path / "side_questions",
        path / "exports",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    _write_text(
        path / "initial_idea.md",
        "# Initial Idea\n\n" + prompt + "\n",
    )
    _write_text(
        path / "side_questions" / "side_questions_log.md",
        "# Side Questions Log\n",
    )
    _write_text(
        path / "side_questions" / "archived_side_questions.md",
        "# Archived Side Questions\n",
    )
    _write_text(path / "idea_backlog.md", "# Idea Backlog\n")
    _write_text(path / "interpreted_answers.md", "# Interpreted Answers\n")

    write_yaml_file(path / "rule_set.yaml", default_rule_set())
    write_yaml_file(path / "runtime_state.yaml", initial_runtime_state())
    write_yaml_file(path / "project_state.yaml", initial_project_state(name))
    write_yaml_file(path / "project_settings.yaml", default_project_settings())
    write_yaml_file(
        path / "side_questions" / "active_side_questions.yaml",
        {"active_side_questions": []},
    )

    _write_json(
        path / "question_queue.json",
        {"batch_id": None, "source_file": None, "items": [], "current_index": 0},
    )
    _write_json(path / "raw_answers.json", {"batch_id": None, "answers": []})
    _write_json(path / "side_threads.json", {"threads": []})
    _write_text(path / "raw_answers.md", "# Raw Answers\n")
    return path


def start_or_resume_project(
    project_path: str | Path,
    project_name: str | None = None,
    initial_prompt: str | None = None,
) -> dict[str, Any]:
    path = Path(project_path).resolve()
    if not path.exists() or (path.is_dir() and not any(path.iterdir())):
        initialize_planning(path, project_name, initial_prompt)
        return get_project_status(path)
    if not path.is_dir():
        raise WorkflowError(f"Project path is not a directory: {path}")

    status = get_project_status(path)
    if not status["is_initialized"]:
        raise WorkflowError(f"Project exists but is not initialized: {path}")
    return status


def get_project_status(project_path: str | Path) -> dict[str, Any]:
    path = Path(project_path).resolve()
    missing = {
        "exists": False,
        "current_phase": None,
        "is_initialized": False,
        "has_questions": False,
        "current_question_id": None,
    }
    if not path.is_dir():
        return missing
    if validate_project_structure(path):
        return missing

    try:
        state = _load_runtime_state(path)
        queue = _load_queue(path)
    except WorkflowError:
        return missing

    items = queue.get("items", [])
    current_question_id = state.get("current_question_id") or _current_question_id_from_queue(
        queue
    )
    return {
        "exists": True,
        "current_phase": state.get("current_phase"),
        "is_initialized": True,
        "has_questions": bool(items),
        "current_question_id": current_question_id,
    }


def create_project(root: str | Path | None, project_id: str, idea: str) -> Path:
    project_path = project_dir(root, project_id)
    if project_path.exists():
        raise WorkflowError(f"Project already exists: {project_path}")
    return initialize_planning(project_path, project_id, idea)


def default_rule_set() -> dict[str, Any]:
    rules = [
        ("R001", "critical", "The system is designed around the backend workflow, not the UI."),
        ("R002", "critical", "The Reasoning Agent must revise for precision, not novelty."),
        ("R003", "critical", "Python must not interpret semantic meaning."),
        ("R004", "critical", "The Interview Engine must not use an LLM by default."),
        ("R005", "high", "Side questions are logged but do not automatically modify the plan."),
        ("R006", "critical", "The user controls continue, proceed, and finalize actions."),
        ("R007", "critical", "Do not add a new idea just because it is interesting."),
        (
            "R008",
            "high",
            "New ideas must clarify the system, reduce risk, improve implementation precision, or support the confirmed core goal.",
        ),
        ("R009", "high", "Cool but unrelated ideas belong into idea_backlog.md, not into the active plan."),
        (
            "R010",
            "critical",
            "Only the Reasoning Agent may interpret answers, detect contradictions, judge scope, evaluate feasibility, update the roadmap, or decide what questions should be asked next.",
        ),
    ]
    return {
        "version": "0.1",
        "core_rules": [
            {"id": rule_id, "priority": priority, "rule": rule}
            for rule_id, priority, rule in rules
        ],
        "proposed_rule_changes": [],
    }


def initial_runtime_state() -> dict[str, Any]:
    return {
        "current_phase": "initialized",
        "active_batch_id": None,
        "current_question_id": None,
        "current_question_index": None,
        "questions": [],
        "batch_complete": False,
        "waiting_for_user_continue": False,
        "user_approved_continue": False,
        "user_approved_finalize": False,
        "reasoning_needed": True,
        "reasoning_allowed": True,
        "requested_action": "initial_reasoning",
        "broken_file": None,
        "error": None,
        "safe_to_continue": True,
        "user_options": [],
    }


def initial_project_state(project_name: str | None = None) -> dict[str, Any]:
    return {
        "project_name": project_name or "",
        "project_version": "v0.0",
        "core_goal": "",
        "current_focus": "awaiting initial reasoning",
        "semantic_status": "not_interpreted_by_python",
    }


def default_project_settings() -> dict[str, Any]:
    return dict(PROJECT_SETTINGS_DEFAULTS)


def validate_project_structure(project_path: Path) -> list[str]:
    errors: list[str] = []
    for relative in ["answers", "questions", "side_questions", "exports"]:
        if not (project_path / relative).is_dir():
            errors.append(f"Missing directory: {relative}")
    for relative in [
        "initial_idea.md",
        "runtime_state.yaml",
        "rule_set.yaml",
        "project_state.yaml",
        "project_settings.yaml",
        "question_queue.json",
        "raw_answers.json",
        "side_threads.json",
    ]:
        if not (project_path / relative).is_file():
            errors.append(f"Missing file: {relative}")
    for relative in [
        "runtime_state.yaml",
        "rule_set.yaml",
        "project_state.yaml",
        "project_settings.yaml",
    ]:
        path = project_path / relative
        if path.exists():
            try:
                load_yaml_file(path)
            except StructuredYamlError as exc:
                errors.append(str(exc))
    for relative in ["question_queue.json", "raw_answers.json", "side_threads.json"]:
        path = project_path / relative
        if path.exists():
            try:
                load_json(path)
            except WorkflowError as exc:
                errors.append(str(exc))
    return errors


def resolve_questions_path(project_path: Path, questions_path: str | Path | None = None) -> Path:
    if questions_path is None:
        active = project_path / "questions.yaml"
        if active.exists():
            return active
        candidates = sorted((project_path / "questions").glob("*_questions.yaml"))
        if candidates:
            return candidates[-1]
        return active
    path = Path(questions_path)
    if not path.is_absolute():
        path = project_path / path
    return path


def validate_questions_file(
    project_path: Path, questions_path: str | Path | None = None
) -> dict[str, Any]:
    path = resolve_questions_path(project_path, questions_path)
    try:
        data = load_yaml_file(path)
        _validate_questions_data(data, path)
    except (OSError, StructuredYamlError, WorkflowError) as exc:
        _set_validation_failed(project_path, path, str(exc))
        raise WorkflowError(str(exc)) from exc
    return data


def create_question_queue(
    project_path: Path, questions_path: str | Path | None = None
) -> dict[str, Any]:
    path = resolve_questions_path(project_path, questions_path)
    data = validate_questions_file(project_path, path)
    batch_id = data["batch_id"]
    questions = data["questions"]
    items = [
        {
            "id": item["id"],
            "question": item["question"],
            "scope": item.get("scope"),
            "status": "pending",
        }
        for item in questions
    ]
    queue = {
        "batch_id": batch_id,
        "source_file": _relative_to_project(project_path, path),
        "items": items,
        "current_index": 0,
    }
    _write_json(project_path / "question_queue.json", queue)
    _write_answers(project_path, batch_id, [])

    first = items[0]
    state = _load_runtime_state(project_path)
    state.update(
        {
            "current_phase": "asking_questions",
            "active_batch_id": batch_id,
            "current_question_id": first["id"],
            "current_question_index": 0,
            "batch_complete": False,
            "waiting_for_user_continue": False,
            "user_approved_continue": False,
            "user_approved_finalize": False,
            "reasoning_needed": False,
            "reasoning_allowed": False,
            "requested_action": None,
            "broken_file": None,
            "error": None,
            "safe_to_continue": True,
            "user_options": [],
        }
    )
    _write_runtime_state(project_path, state)
    return queue


def current_question(project_path: Path) -> CurrentQuestion | None:
    queue = _load_queue(project_path)
    items = queue.get("items", [])
    index = int(queue.get("current_index", 0) or 0)
    if not items or index >= len(items):
        return None
    item = items[index]
    return CurrentQuestion(
        batch_id=queue["batch_id"],
        question_id=item["id"],
        question=item["question"],
        scope=item.get("scope"),
        index=index,
        total=len(items),
    )


def save_answer(project_path: Path, answer_text: str) -> dict[str, Any]:
    if answer_text is None or answer_text.strip() == "":
        raise WorkflowError("Answer text is required.")
    queue = _load_queue(project_path)
    items = queue.get("items", [])
    if not items:
        raise WorkflowError("No question queue is active.")
    index = int(queue.get("current_index", 0) or 0)
    if index >= len(items):
        raise WorkflowError("The active question batch is already complete.")

    item = items[index]
    item["status"] = "answered"
    answer_record = {
        "question_id": item["id"],
        "question_text": item["question"],
        "answer_text": answer_text,
        "status": "answered",
    }
    answers = _load_answers(project_path).get("answers", [])
    answers = [
        existing
        for existing in answers
        if existing.get("question_id") != answer_record["question_id"]
    ]
    answers.append(answer_record)

    next_index = index + 1
    queue["current_index"] = next_index
    _write_json(project_path / "question_queue.json", queue)
    _write_answers(project_path, queue["batch_id"], answers)

    state = _load_runtime_state(project_path)
    if next_index >= len(items):
        state.update(
            {
                "current_phase": "waiting_for_user_continue",
                "current_question_id": None,
                "current_question_index": next_index,
                "batch_complete": True,
                "waiting_for_user_continue": True,
                "user_approved_continue": False,
                "reasoning_needed": True,
                "reasoning_allowed": False,
                "requested_action": None,
            }
        )
    else:
        state.update(
            {
                "current_phase": "asking_questions",
                "current_question_id": items[next_index]["id"],
                "current_question_index": next_index,
                "batch_complete": False,
                "waiting_for_user_continue": False,
                "reasoning_needed": False,
                "reasoning_allowed": False,
                "requested_action": None,
            }
        )
    _write_runtime_state(project_path, state)
    return state


def apply_user_command(project_path: Path, command: str) -> dict[str, Any]:
    normalized = command.strip().lower()
    if normalized not in {"continue", "proceed", "revise", "finalize", "pause"}:
        raise WorkflowError(f"Unsupported command: {command}")
    state = _load_runtime_state(project_path)

    if normalized == "pause":
        state.update(
            {
                "current_phase": "paused",
                "waiting_for_user_continue": bool(state.get("batch_complete")),
                "reasoning_allowed": False,
                "requested_action": None,
            }
        )
        _write_runtime_state(project_path, state)
        return state

    if normalized in {"continue", "proceed"} and not state.get("batch_complete"):
        raise WorkflowError("continue/proceed requires a completed question batch.")

    if normalized in {"continue", "proceed"}:
        requested_action = "revise_plan_and_generate_next_question_batch"
        state.update(
            {
                "current_phase": "reasoning",
                "waiting_for_user_continue": False,
                "user_approved_continue": True,
                "reasoning_needed": True,
                "reasoning_allowed": True,
                "requested_action": requested_action,
            }
        )
    elif normalized == "revise":
        requested_action = "revise_plan_and_generate_next_question_batch"
        state.update(
            {
                "current_phase": "reasoning",
                "reasoning_needed": True,
                "reasoning_allowed": True,
                "requested_action": requested_action,
            }
        )
    else:
        requested_action = "finalize_project_spec"
        state.update(
            {
                "current_phase": "reasoning",
                "waiting_for_user_continue": False,
                "user_approved_finalize": True,
                "reasoning_needed": True,
                "reasoning_allowed": True,
                "requested_action": requested_action,
            }
        )
    _write_runtime_state(project_path, state)
    return state


def build_reasoning_context(
    project_path: Path, command: str | None = None
) -> dict[str, Any]:
    if command:
        state = apply_user_command(project_path, command)
    else:
        state = _load_runtime_state(project_path)

    if not state.get("reasoning_allowed"):
        raise WorkflowError("Reasoning is not allowed by the current runtime state.")

    project_state = _load_optional_yaml(project_path / "project_state.yaml")
    rule_set = _load_optional_yaml(project_path / "rule_set.yaml")
    active_side = _load_optional_yaml(
        project_path / "side_questions" / "active_side_questions.yaml"
    )
    batch_id = state.get("active_batch_id")
    answer_md = f"answers/{batch_id}_answers.md" if batch_id else None
    answer_json = f"answers/{batch_id}_answers.json" if batch_id else None
    context = {
        "project_id": project_path.name,
        "current_phase": state.get("current_phase"),
        "current_version": project_state.get("project_version"),
        "current_goal": project_state.get("core_goal"),
        "current_focus": project_state.get("current_focus"),
        "latest_answer_batch": {
            "batch_id": batch_id,
            "answers_file": answer_md,
            "answers_json": answer_json,
        },
        "active_side_questions": active_side.get("active_side_questions", []),
        "active_rules": [
            item.get("rule")
            for item in rule_set.get("core_rules", [])
            if isinstance(item, dict) and item.get("rule")
        ],
        "requested_action": state.get("requested_action"),
        "source_files": {
            "initial_idea": "initial_idea.md",
            "runtime_state": "runtime_state.yaml",
            "project_state": "project_state.yaml",
            "rule_set": "rule_set.yaml",
        },
    }
    write_yaml_file(project_path / "reasoning_context.yaml", context)
    return context


def log_side_question(
    project_path: Path, question: str, answer_summary: str = ""
) -> dict[str, Any]:
    if not question.strip():
        raise WorkflowError("Side question text is required.")
    active_path = project_path / "side_questions" / "active_side_questions.yaml"
    active = _load_optional_yaml(active_path)
    entries = active.get("active_side_questions", [])
    next_id = f"SQ{len(entries) + 1:03d}"
    state = _load_runtime_state(project_path)
    entry = {
        "side_question_id": next_id,
        "current_main_question": state.get("current_question_id"),
        "question": question.strip(),
        "answer_summary": answer_summary.strip(),
        "status": "not_a_decision",
        "visibility_to_reasoning_agent": "active",
        "created_at": _timestamp(),
    }
    entries.append(entry)
    write_yaml_file(active_path, {"active_side_questions": entries})

    log_path = project_path / "side_questions" / "side_questions_log.md"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n"
            f"## {next_id}\n\n"
            f"- Current main question: {entry['current_main_question']}\n"
            f"- Question: {entry['question']}\n"
            f"- Answer summary: {entry['answer_summary']}\n"
            "- Status: not_a_decision\n"
        )
    return entry


def mark_reasoning_completed(project_path: Path, produced_questions: bool) -> dict[str, Any]:
    state = _load_runtime_state(project_path)
    state.update(
        {
            "current_phase": "reasoning_output_ready" if produced_questions else "finalized",
            "reasoning_needed": False,
            "reasoning_allowed": False,
            "waiting_for_user_continue": False,
        }
    )
    _write_runtime_state(project_path, state)
    return state


def require_reasoning_allowed(project_path: Path, expected_action: str | None = None) -> dict[str, Any]:
    state = _load_runtime_state(project_path)
    if not state.get("reasoning_allowed"):
        raise WorkflowError("Reasoning is not allowed by the current runtime state.")
    if expected_action and state.get("requested_action") != expected_action:
        raise WorkflowError(
            f"Expected requested_action={expected_action}, got {state.get('requested_action')}"
        )
    return state


def next_batch_id(project_path: Path) -> str:
    highest = 0
    for path in (project_path / "questions").glob("batch_*_questions.yaml"):
        match = re.search(r"batch_(\d+)_questions\.yaml$", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"batch_{highest + 1:03d}"


def write_question_batch(project_path: Path, batch: dict[str, Any]) -> Path:
    _validate_questions_data(batch, project_path / "questions.yaml")
    batch_id = batch["batch_id"]
    canonical = project_path / "questions" / f"{batch_id}_questions.yaml"
    write_yaml_file(canonical, batch)
    write_yaml_file(project_path / "questions.yaml", batch)
    return canonical


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Could not read JSON file {path}: {exc}") from exc


def _validate_questions_data(data: Any, path: Path) -> None:
    if not isinstance(data, dict):
        raise WorkflowError(f"{path}: questions file must be a mapping.")
    if not isinstance(data.get("batch_id"), str) or not data["batch_id"].strip():
        raise WorkflowError(f"{path}: missing required field: batch_id")
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise WorkflowError(f"{path}: questions must be a list.")
    if not QUESTION_MIN <= len(questions) <= QUESTION_MAX:
        raise WorkflowError(
            f"{path}: questions must contain {QUESTION_MIN}-{QUESTION_MAX} items."
        )
    seen_ids: set[str] = set()
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise WorkflowError(f"{path}: question {index} must be a mapping.")
        question_id = question.get("id")
        question_text = question.get("question")
        if not isinstance(question_id, str) or not question_id.strip():
            raise WorkflowError(f"{path}: question {index} is missing required field: id")
        if question_id in seen_ids:
            raise WorkflowError(f"{path}: duplicate question id: {question_id}")
        seen_ids.add(question_id)
        if not isinstance(question_text, str) or not question_text.strip():
            raise WorkflowError(
                f"{path}: question {question_id} is missing required field: question"
            )


def _set_validation_failed(project_path: Path, broken_file: Path, error: str) -> None:
    state = _load_runtime_state(project_path)
    state.update(
        {
            "current_phase": "validation_failed",
            "broken_file": _relative_to_project(project_path, broken_file),
            "error": error,
            "safe_to_continue": False,
            "reasoning_allowed": False,
            "user_options": [
                "inspect_broken_file",
                "attempt_model_repair",
                "rerun_reasoning_agent",
                "cancel_batch",
            ],
        }
    )
    _write_runtime_state(project_path, state)


def _load_runtime_state(project_path: Path) -> dict[str, Any]:
    data = _load_optional_yaml(project_path / "runtime_state.yaml")
    if not isinstance(data, dict):
        raise WorkflowError("runtime_state.yaml must be a mapping.")
    return data


def _write_runtime_state(project_path: Path, state: dict[str, Any]) -> None:
    write_yaml_file(project_path / "runtime_state.yaml", state)


def _load_optional_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_yaml_file(path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise WorkflowError(f"{path} must contain a mapping.")
    return data


def _load_queue(project_path: Path) -> dict[str, Any]:
    return load_json(project_path / "question_queue.json")


def _current_question_id_from_queue(queue: dict[str, Any]) -> str | None:
    items = queue.get("items", [])
    index = int(queue.get("current_index", 0) or 0)
    if not items or index < 0 or index >= len(items):
        return None
    item = items[index]
    return item.get("id") if isinstance(item, dict) else None


def _load_answers(project_path: Path) -> dict[str, Any]:
    return load_json(project_path / "raw_answers.json")


def _write_answers(project_path: Path, batch_id: str | None, answers: list[dict[str, Any]]) -> None:
    payload = {"batch_id": batch_id, "answers": answers}
    _write_json(project_path / "raw_answers.json", payload)
    if batch_id:
        _write_json(project_path / "answers" / f"{batch_id}_answers.json", payload)
    _write_answers_markdown(project_path / "raw_answers.md", batch_id, answers)
    if batch_id:
        _write_answers_markdown(
            project_path / "answers" / f"{batch_id}_answers.md", batch_id, answers
        )


def _write_answers_markdown(path: Path, batch_id: str | None, answers: list[dict[str, Any]]) -> None:
    lines = [f"# Answer Batch {batch_id or ''}".rstrip(), ""]
    for index, answer in enumerate(answers, start=1):
        lines.extend(
            [
                f"## Q{index}",
                "",
                answer.get("question_text", ""),
                "",
                f"## A{index}",
                "",
                answer.get("answer_text", ""),
                "",
            ]
        )
    _write_text(path, "\n".join(lines).rstrip() + "\n")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _relative_to_project(project_path: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_path.resolve()).as_posix()
    except ValueError:
        return str(path)


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
