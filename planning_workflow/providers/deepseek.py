"""DeepSeek chat-completions client with strict JSON handling."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx

from planning_workflow.domain.errors import ConfigurationError, ModelOutputError, WorkflowError

from .config import Settings


@dataclass(frozen=True)
class DeepSeekJSONResult:
    request: dict[str, Any]
    response: dict[str, Any]
    data: dict[str, Any]
    usage: dict[str, Any]


class DeepSeekClient:
    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._http_client = http_client

    def complete_json(self, system_prompt: str, user_payload: dict[str, Any]) -> DeepSeekJSONResult:
        api_key = self.settings.deepseek_api_key.strip()
        if not api_key or api_key == "put_api_key_here":
            raise ConfigurationError("DEEPSEEK_API_KEY is not configured.")

        payload: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": self.settings.deepseek_max_tokens,
        }
        if self.settings.deepseek_thinking == "enabled":
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = self.settings.deepseek_reasoning_effort
        else:
            payload["thinking"] = {"type": "disabled"}

        base_url = self.settings.deepseek_base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._http_client is not None:
                response = self._http_client.post(url, headers=headers, json=payload)
            else:
                with httpx.Client(timeout=self.settings.deepseek_timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WorkflowError(f"DeepSeek request failed: {exc}") from exc

        body = response.json()
        content = _extract_content(body)
        if not content.strip():
            raise ModelOutputError("DeepSeek returned empty JSON content.")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelOutputError(f"DeepSeek returned invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ModelOutputError("DeepSeek JSON response must be an object.")
        return DeepSeekJSONResult(
            request=payload,
            response=body,
            data=data,
            usage=body.get("usage", {}) if isinstance(body.get("usage"), dict) else {},
        )


def _extract_content(body: dict[str, Any]) -> str:
    try:
        choices = body["choices"]
        message = choices[0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelOutputError("DeepSeek response did not contain choices[0].message.content.") from exc
    if not isinstance(content, str):
        raise ModelOutputError("DeepSeek message content must be a string.")
    return content
