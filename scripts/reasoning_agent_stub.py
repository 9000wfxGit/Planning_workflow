from __future__ import annotations

import argparse

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core, reasoning_stub


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the local deterministic reasoning-agent stand-in."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--mode", choices=["initial", "revise", "finalize"], required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    project_path = core.project_dir(args.root, args.project_id)
    if args.mode == "initial":
        reasoning_stub.initial_reasoning(project_path)
    elif args.mode == "revise":
        reasoning_stub.revise(project_path)
    else:
        reasoning_stub.finalize(project_path)
    print(f"Reasoning stub completed: {args.mode}")


if __name__ == "__main__":
    main()
