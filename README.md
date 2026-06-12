# System-first Idea-to-Plan Agent Workflow

This repository implements the MVP described in the handout:

> Model thinks. Python routes. UI displays. User controls proceed/finalize.

The first version is deliberately backend-first. The terminal scripts are only
adapters over a file-based core workflow; they do not own project logic.

## MVP Flow

1. Create a project and store the raw idea.
2. Run a reasoning adapter to create semantic planning files and a question batch.
3. Validate the question file structurally.
4. Parse the questions into a mechanical queue.
5. Ask one question at a time and save raw answers.
6. Wait after the batch is complete.
7. Continue/proceed/finalize only when the user explicitly asks.
8. Build a compact reasoning context for the next reasoning pass.

## Core Principle

- Reasoning Agent: owns semantic work such as plans, risks, decisions, question
  generation, answer interpretation, and final specs.
- Python Core: owns mechanics such as folders, structured files, queues, raw
  answer storage, structural validation, and state transitions.
- Interview Engine: plays back one existing question at a time.
- Side Clarifier: logs side questions separately and never changes the main plan.
- UI/Terminal: displays state and forwards input.
- User: controls `continue`, `proceed`, `pause`, `inspect`, and `finalize`.

## Quick Start

```powershell
python scripts/create_project.py --project-id project-001 --idea "Build a planning agent for rough project ideas."
python scripts/reasoning_agent_stub.py --project-id project-001 --mode initial
python scripts/validate_structure.py --project-id project-001
python scripts/parse_questions.py --project-id project-001
python scripts/run_interview.py --project-id project-001
python scripts/build_reasoning_context.py --project-id project-001 --command continue
python scripts/reasoning_agent_stub.py --project-id project-001 --mode revise
```

To finalize instead of generating another question batch:

```powershell
python scripts/build_reasoning_context.py --project-id project-001 --command finalize
python scripts/reasoning_agent_stub.py --project-id project-001 --mode finalize
```

The explicit user-command adapter supports:

```powershell
python scripts/apply_command.py --project-id project-001 --command pause
python scripts/apply_command.py --project-id project-001 --command continue
python scripts/apply_command.py --project-id project-001 --command proceed
python scripts/apply_command.py --project-id project-001 --command revise
python scripts/apply_command.py --project-id project-001 --command finalize
python scripts/inspect_project.py --project-id project-001
```

`scripts/reasoning_agent_stub.py` is a deterministic local stand-in for a real
reasoning model. It is intentionally outside the interview engine so the core
can later call DeepSeek, Claude, GPT, or another reasoning model without moving
workflow ownership into the UI.

## Project Layout

```text
projects/
  project-001/
    answers/
    questions/
    side_questions/
    exports/
    initial_idea.md
    plan.md
    roadmap.yaml
    decision_log.md
    risk_register.md
    interpreted_answers.md
    runtime_state.yaml
    project_state.yaml
    rule_set.yaml
    reasoning_context.yaml
    question_queue.json
    raw_answers.json
    raw_answers.md
templates/
scripts/
planning_agent_system/
tests/
```

## No External Runtime Dependencies

The core uses only the Python standard library. A tiny structured YAML reader
and writer is included for the simple YAML subset used by the workflow files.

## Verify

Run the full test suite before pushing:

```powershell
python -m unittest discover -s tests
```

Expected result:

```text
OK
```
