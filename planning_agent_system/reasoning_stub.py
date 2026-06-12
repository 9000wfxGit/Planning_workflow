"""Deterministic local stand-in for the semantic Reasoning Agent.

This module is not the Python interview engine. It intentionally represents the
semantic actor that can later be replaced by an LLM-backed adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import core
from .structured_yaml import load_yaml_file, write_yaml_file


def initial_reasoning(project_path: Path) -> None:
    core.require_reasoning_allowed(project_path, "initial_reasoning")
    idea = _read_initial_idea(project_path)
    batch_id = core.next_batch_id(project_path)

    _write_initial_semantic_files(project_path, idea)
    core.write_question_batch(project_path, _initial_questions(batch_id))
    core.mark_reasoning_completed(project_path, produced_questions=True)


def revise(project_path: Path) -> None:
    core.require_reasoning_allowed(
        project_path, "revise_plan_and_generate_next_question_batch"
    )
    context = _load_context(project_path)
    answers = _load_latest_answers(project_path, context)
    batch_id = core.next_batch_id(project_path)

    _write_interpreted_answers(project_path, context, answers)
    _append_decision_log(project_path, answers)
    _append_plan_revision(project_path, answers, batch_id)
    _update_project_state(project_path, "v0.2", "question batch revised after user-approved continue")
    core.write_question_batch(project_path, _revision_questions(batch_id))
    core.mark_reasoning_completed(project_path, produced_questions=True)


def finalize(project_path: Path) -> None:
    core.require_reasoning_allowed(project_path, "finalize_project_spec")
    context = _load_context(project_path)
    answers = _load_latest_answers(project_path, context)
    project_state = _safe_yaml(project_path / "project_state.yaml")
    rule_set = _safe_yaml(project_path / "rule_set.yaml")

    spec_md = _final_spec_markdown(project_path, project_state, rule_set, answers)
    exports = project_path / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    (exports / "final_project_spec.md").write_text(spec_md, encoding="utf-8")
    write_yaml_file(
        exports / "final_project_spec.yaml",
        {
            "core_idea": project_state.get("core_goal", "System-first planning workflow"),
            "system_principle": "Model thinks. Python routes. UI displays. User controls proceed/finalize.",
            "mvp_scope": [
                "file_based_core",
                "mechanical_interview_runner",
                "explicit_user_continue_or_finalize",
                "separate_side_question_log",
            ],
            "latest_answer_count": len(answers),
        },
    )
    core.mark_reasoning_completed(project_path, produced_questions=False)


def _write_initial_semantic_files(project_path: Path, idea: str) -> None:
    (project_path / "plan.md").write_text(
        "\n".join(
            [
                "# Plan",
                "",
                "## Core Idea",
                "",
                idea,
                "",
                "## System Principle",
                "",
                "Model thinks. Python routes. UI displays. User controls proceed/finalize.",
                "",
                "## MVP Direction",
                "",
                "- Build the file-based core before any UI.",
                "- Keep Python responsible for routing, state, validation, and raw storage.",
                "- Keep semantic interpretation in the Reasoning Agent.",
                "- Ask focused batches of 3-7 questions.",
                "- Wait for explicit user control before another reasoning pass.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_yaml_file(
        project_path / "roadmap.yaml",
        {
            "version": "v0.1",
            "stages": [
                {
                    "id": "v1",
                    "name": "Core Workflow",
                    "status": "active",
                    "items": [
                        "file_based_project_structure",
                        "question_batch_generation",
                        "mechanical_interview_runner",
                        "raw_answer_storage",
                        "explicit_continue_or_finalize",
                    ],
                },
                {
                    "id": "v2",
                    "name": "Local Web UI Adapter",
                    "status": "later",
                    "items": ["display_state", "display_question", "forward_commands"],
                },
            ],
        },
    )
    (project_path / "decision_log.md").write_text(
        "\n".join(
            [
                "# Decision Log",
                "",
                "- The core must work without a UI.",
                "- Python must not interpret semantic meaning.",
                "- The interview engine must not use an LLM by default.",
                "- The user controls continue, proceed, and finalize.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_path / "risk_register.md").write_text(
        "\n".join(
            [
                "# Risk Register",
                "",
                "## RISK-001: UI-first drift",
                "",
                "Mitigation: keep UI as an adapter over files and runtime state.",
                "",
                "## RISK-002: Python starts interpreting answers",
                "",
                "Mitigation: keep answer handling limited to raw storage and state transitions.",
                "",
                "## RISK-003: Scope creep",
                "",
                "Mitigation: route interesting but unrelated ideas to idea_backlog.md.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_yaml_file(
        project_path / "project_state.yaml",
        {
            "project_version": "v0.1",
            "core_goal": "Build a system-first workflow that turns rough ideas into precise, realistic, buildable project plans.",
            "current_focus": "Clarify core boundaries and MVP mechanics.",
            "semantic_status": "initial architecture drafted",
        },
    )


def _initial_questions(batch_id: str) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "batch_goal": "Confirm the system-first boundaries for the MVP.",
        "questions": [
            {
                "id": "Q1",
                "question": "Should the core system work without any UI attached?",
                "scope": "system architecture",
                "reason_for_model_later": "Confirms whether UI is an adapter or part of the core.",
            },
            {
                "id": "Q2",
                "question": "Should Python only route existing questions and answers without interpreting them?",
                "scope": "Python responsibility",
                "reason_for_model_later": "Confirms the boundary between deterministic code and model reasoning.",
            },
            {
                "id": "Q3",
                "question": "Should version 1 use a terminal adapter before any web UI is built?",
                "scope": "MVP interface",
                "reason_for_model_later": "Keeps the first version focused on the backend workflow.",
            },
            {
                "id": "Q4",
                "question": "Which files should be most visible when the user inspects project state?",
                "scope": "inspection",
                "reason_for_model_later": "Guides the inspect adapter without moving logic into the UI.",
            },
            {
                "id": "Q5",
                "question": "Should side questions be logged separately and never modify the roadmap automatically?",
                "scope": "side question handling",
                "reason_for_model_later": "Confirms how curiosity is separated from project decisions.",
            },
        ],
    }


def _revision_questions(batch_id: str) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "batch_goal": "Narrow the implementation plan without expanding MVP scope.",
        "questions": [
            {
                "id": "Q1",
                "question": "What is the smallest successful end-to-end demo for version 1?",
                "scope": "MVP success",
                "reason_for_model_later": "Defines a concrete completion target.",
            },
            {
                "id": "Q2",
                "question": "Which user commands are required in the first terminal adapter?",
                "scope": "commands",
                "reason_for_model_later": "Keeps command handling explicit and finite.",
            },
            {
                "id": "Q3",
                "question": "What should happen when a question batch is structurally invalid?",
                "scope": "error handling",
                "reason_for_model_later": "Clarifies visible failure behavior.",
            },
            {
                "id": "Q4",
                "question": "What information should be included in the final project spec?",
                "scope": "finalization",
                "reason_for_model_later": "Defines the final output shape.",
            },
            {
                "id": "Q5",
                "question": "Which tempting features should stay in idea_backlog.md for now?",
                "scope": "scope creep protection",
                "reason_for_model_later": "Prevents unrelated ideas from entering the active roadmap.",
            },
        ],
    }


def _write_interpreted_answers(
    project_path: Path, context: dict[str, Any], answers: list[dict[str, Any]]
) -> None:
    lines = [
        "# Interpreted Answers",
        "",
        f"Requested action: {context.get('requested_action')}",
        "",
        "This file is owned by the Reasoning Agent. The Python core only supplied raw answers.",
        "",
    ]
    for item in answers:
        lines.extend(
            [
                f"## {item.get('question_id')}",
                "",
                f"Question: {item.get('question_text')}",
                "",
                f"Raw answer: {item.get('answer_text')}",
                "",
                "Interpretation: accepted for the next planning revision.",
                "",
            ]
        )
    (project_path / "interpreted_answers.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8"
    )


def _append_decision_log(project_path: Path, answers: list[dict[str, Any]]) -> None:
    with (project_path / "decision_log.md").open("a", encoding="utf-8") as handle:
        handle.write("\n## User-approved Answer Batch\n\n")
        for item in answers:
            handle.write(
                f"- {item.get('question_id')}: recorded answer for later planning precision.\n"
            )


def _append_plan_revision(project_path: Path, answers: list[dict[str, Any]], batch_id: str) -> None:
    with (project_path / "plan.md").open("a", encoding="utf-8") as handle:
        handle.write(
            "\n## Revision After User-approved Continue\n\n"
            f"The latest completed answer batch contained {len(answers)} raw answers. "
            f"The next focused question batch is `{batch_id}`.\n"
        )


def _update_project_state(project_path: Path, version: str, focus: str) -> None:
    state = _safe_yaml(project_path / "project_state.yaml")
    state.update(
        {
            "project_version": version,
            "current_focus": focus,
            "semantic_status": "revised after explicit user approval",
        }
    )
    write_yaml_file(project_path / "project_state.yaml", state)


def _final_spec_markdown(
    project_path: Path,
    project_state: dict[str, Any],
    rule_set: dict[str, Any],
    answers: list[dict[str, Any]],
) -> str:
    rules = rule_set.get("core_rules", [])
    rule_lines = [
        f"- {item.get('id')}: {item.get('rule')}"
        for item in rules
        if isinstance(item, dict)
    ]
    sections = [
        ("Core idea", project_state.get("core_goal", "System-first planning workflow.")),
        ("System principle", "Model thinks. Python routes. UI displays. User controls proceed/finalize."),
        ("Agent roles", "Reasoning owns meaning. Python owns mechanics. Interview plays questions. Side Clarifier logs explanations. UI adapts."),
        ("File structure", "Use projects/<project-id> with answers, questions, side_questions, exports, and explicit state files."),
        ("Workflow loop", "Idea -> reasoning -> question batch -> mechanical interview -> raw answers -> user command -> reasoning."),
        ("State transitions", "The system waits after a completed batch until continue, proceed, revise, or finalize is explicitly requested."),
        ("Model usage rules", "The interview engine uses no model. Side clarification may use a cheaper model. Main reasoning uses a model only on allowed triggers."),
        ("Python responsibilities", "Create folders, read/write structured files, validate structure, route questions, save raw answers, and build reasoning context."),
        ("Side Clarifier rules", "Side questions are logged separately and never modify plan or roadmap automatically."),
        ("MVP scope", "File-based core, terminal adapter, question queue, raw answers, visible errors, explicit user control."),
        ("Not included yet", "Voice mode, complex web UI, database-first storage, autonomous multi-agent expansion, and automatic internet research."),
        ("Implementation plan", "Keep replacing the local reasoning stub with a model adapter while preserving the core file/state contract."),
        ("Prompt for coding agent", "Build the backend workflow first. Do not move workflow ownership into the UI. Do not let Python interpret answers."),
    ]
    lines = ["# Final Project Specification", ""]
    for index, (title, body) in enumerate(sections, start=1):
        lines.extend([f"## {index}. {title}", "", str(body), ""])
    lines.extend(["## Confirmed Rules", "", *rule_lines, ""])
    lines.extend(["## Latest Raw Answer Count", "", str(len(answers)), ""])
    return "\n".join(lines)


def _read_initial_idea(project_path: Path) -> str:
    path = project_path / "initial_idea.md"
    text = path.read_text(encoding="utf-8").strip()
    return text.replace("# Initial Idea", "").strip() or "No initial idea supplied."


def _load_context(project_path: Path) -> dict[str, Any]:
    return _safe_yaml(project_path / "reasoning_context.yaml")


def _load_latest_answers(project_path: Path, context: dict[str, Any]) -> list[dict[str, Any]]:
    answer_path = context.get("latest_answer_batch", {}).get("answers_json")
    if not answer_path:
        return []
    path = project_path / answer_path
    if not path.exists():
        return []
    return core.load_json(path).get("answers", [])


def _safe_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_yaml_file(path)
    return data if isinstance(data, dict) else {}
