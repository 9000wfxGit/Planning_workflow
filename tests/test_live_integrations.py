from __future__ import annotations

from pathlib import Path
import unittest

from planning_workflow.providers.config import load_settings
from planning_workflow.providers.deepseek import DeepSeekClient
from planning_workflow.providers.search import build_search_provider


REPO_ROOT = Path(__file__).resolve().parents[1]


class LiveIntegrationTests(unittest.TestCase):
    def test_live_deepseek_strict_json_when_enabled(self) -> None:
        settings = load_settings(REPO_ROOT)
        if not settings.run_live_deepseek_tests:
            self.skipTest("RUN_LIVE_DEEPSEEK_TESTS is not enabled")
        result = DeepSeekClient(settings).complete_json(
            "Return JSON only. The response must be a json object.",
            {
                "task": "Return a JSON object with exactly one key named ok and value true.",
                "json_contract": {"ok": True},
            },
        )
        self.assertIs(result.data.get("ok"), True)

    def test_live_search_when_enabled(self) -> None:
        settings = load_settings(REPO_ROOT)
        if not settings.run_live_search_tests:
            self.skipTest("RUN_LIVE_SEARCH_TESTS is not enabled")
        results = build_search_provider(settings).search("DeepSeek API docs", max_results=3)
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
