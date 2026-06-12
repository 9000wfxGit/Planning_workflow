from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import bootstrap

bootstrap()

from planning_agent_system import core


def main() -> None:
    parser = argparse.ArgumentParser(description="Save one raw answer mechanically.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--answer", default=None)
    parser.add_argument("--answer-file", default=None)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    if args.answer_file:
        answer = Path(args.answer_file).read_text(encoding="utf-8")
    else:
        answer = args.answer
    if answer is None:
        raise SystemExit("Provide --answer or --answer-file.")

    project_path = core.project_dir(args.root, args.project_id)
    state = core.save_answer(project_path, answer)
    print(f"Saved answer. current_phase={state.get('current_phase')}")


if __name__ == "__main__":
    main()
