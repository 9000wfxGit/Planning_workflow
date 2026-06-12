from __future__ import annotations

import argparse

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a side question without changing the plan.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--answer-summary", default="")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    project_path = core.project_dir(args.root, args.project_id)
    entry = core.log_side_question(project_path, args.question, args.answer_summary)
    print(f"Logged side question: {entry['side_question_id']}")


if __name__ == "__main__":
    main()
