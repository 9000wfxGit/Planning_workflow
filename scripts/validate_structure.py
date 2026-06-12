from __future__ import annotations

import argparse

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate project and question structure.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--questions", default=None)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    project_path = core.project_dir(args.root, args.project_id)
    errors = core.validate_project_structure(project_path)
    if errors:
        raise SystemExit("\n".join(errors))
    questions = core.validate_questions_file(project_path, args.questions)
    print(f"OK: {questions['batch_id']} has {len(questions['questions'])} questions")


if __name__ == "__main__":
    main()
