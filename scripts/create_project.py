from __future__ import annotations

import argparse

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a planning workflow project.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--idea", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    project_path = core.create_project(args.root, args.project_id, args.idea)
    print(f"Created project: {project_path}")


if __name__ == "__main__":
    main()
