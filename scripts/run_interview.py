from __future__ import annotations

import argparse

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mechanical interview adapter.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    project_path = core.project_dir(args.root, args.project_id)
    while True:
        current = core.current_question(project_path)
        if current is None:
            print("Question batch complete. Waiting for user continue/proceed/finalize.")
            return
        print(current.question)
        answer = input("> ")
        core.save_answer(project_path, answer)


if __name__ == "__main__":
    main()
