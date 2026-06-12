from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core
from planning_agent_system.structured_yaml import load_yaml_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect project state or a project file.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--file", default=None)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    project_path = core.project_dir(args.root, args.project_id)
    if args.file:
        path = Path(args.file)
        if not path.is_absolute():
            path = project_path / path
        print(path.read_text(encoding="utf-8"))
        return

    state = load_yaml_file(project_path / "runtime_state.yaml")
    print(f"Project: {project_path}")
    print(f"current_phase: {state.get('current_phase')}")
    print(f"active_batch_id: {state.get('active_batch_id')}")
    print(f"current_question_id: {state.get('current_question_id')}")
    print(f"batch_complete: {state.get('batch_complete')}")
    print(f"reasoning_allowed: {state.get('reasoning_allowed')}")
    if state.get("broken_file"):
        print(f"broken_file: {state.get('broken_file')}")
        print(f"error: {state.get('error')}")


if __name__ == "__main__":
    main()
