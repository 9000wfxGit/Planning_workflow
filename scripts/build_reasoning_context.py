from __future__ import annotations

import argparse

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a user command and build reasoning_context.yaml."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--command",
        choices=["continue", "proceed", "revise", "finalize"],
        default=None,
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    project_path = core.project_dir(args.root, args.project_id)
    context = core.build_reasoning_context(project_path, args.command)
    print(f"Built reasoning_context.yaml for {context.get('requested_action')}")


if __name__ == "__main__":
    main()
