from __future__ import annotations

import argparse

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a mechanical queue from questions.yaml.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--questions", default=None)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    project_path = core.project_dir(args.root, args.project_id)
    queue = core.create_question_queue(project_path, args.questions)
    print(f"Queued {len(queue['items'])} questions from {queue['source_file']}")


if __name__ == "__main__":
    main()
