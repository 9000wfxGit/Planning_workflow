# Planning Workflow Backend

Backend-first workflow for turning rough project ideas into precise, handoff-ready plans.

The package exposes a Python service API. It stores every project as a folder under `projects/`, with JSON as the machine-readable source of truth and Markdown as the human/coding-agent handoff.

## Core Loop

1. Create a project with the raw idea.
2. Run a DeepSeek-backed reasoning cycle.
3. Store the current plan, coding-agent handoff, and a validated question batch.
4. Ask one queued question at a time through any future adapter.
5. Save raw answers mechanically, including blank answers.
6. Run the next reasoning cycle when the batch is complete.

There is no finalize command. After every successful reasoning cycle, the project folder is already usable as a handoff artifact.

## Service Entry Point

```python
from planning_workflow import PlanningWorkflowService

service = PlanningWorkflowService.from_repo(r"D:\user\Github\Planning_workflow")
service.create_project("my-project", "Raw idea text")
service.run_reasoning_cycle("my-project")
question = service.get_current_question("my-project")
service.submit_answer("my-project", "My answer")
```

## Configuration

Local credentials live in `.env`, which is intentionally ignored by Git. `.env.example` documents the expected keys without real secrets.

DeepSeek defaults to `deepseek-v4-pro` with thinking enabled. The deprecated `deepseek-reasoner` name is not used.

## Gateway and UI Attachment

The backend remains framework-free. A gateway should import
`PlanningWorkflowService`, expose thin HTTP routes, and keep the UI in a
separate `UI/` folder.

- `create_auto_project(initial_message)` creates a new project folder for an
  instant "new project" UI flow.
- `get_project_ui_state(project_id)` returns the compact screen state:
  project phase, question timeline, current question, answer status, and branch
  indicators.
- `get_question(project_id, question_id)` returns one question, its saved
  answer, and its clarification branch sessions.
- `get_previous_question(...)` and `get_next_question(...)` support back/next
  controls without mutating workflow state.
- `submit_answer_for_question(project_id, question_id, answer_text)` lets a UI
  save the answer for a selected question while the backend moves to the first
  remaining pending question.
- `open_clarification(...)`, `send_clarification_message(...)`, and
  `close_clarification(...)` back the per-question branch chat window.

The UI should call the gateway only. It should not read or write `projects/`
files directly.

## Testing

```powershell
python -m unittest discover -s tests
```

Set `RUN_LIVE_DEEPSEEK_TESTS=1` in `.env` to run the live DeepSeek smoke test. Set `RUN_LIVE_SEARCH_TESTS=1` to test configured search providers.
