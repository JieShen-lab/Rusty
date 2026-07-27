from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from rusty.services.model_service import ModelConfig


@dataclass(frozen=True)
class AIResponse:
    text: str
    token_usage: dict[str, Any]
    elapsed_ms: int


class AIClient:
    def chat(self, model: ModelConfig, api_key: str | None, messages: list[dict[str, str]]) -> AIResponse:
        raise NotImplementedError


class OpenAICompatibleClient(AIClient):
    def chat(self, model: ModelConfig, api_key: str | None, messages: list[dict[str, str]]) -> AIResponse:
        import httpx

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload: dict[str, Any] = {
            "model": model.model_name,
            "messages": messages,
            "temperature": model.temperature,
        }
        if model.max_tokens:
            payload["max_tokens"] = model.max_tokens

        url = model.base_url.rstrip("/") + "/chat/completions"
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=model.timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ReadTimeout as exc:
            raise TimeoutError(
                f"模型响应超时：在 {model.timeout_seconds} 秒内未收到完整响应。"
                "请增大模型的 Timeout seconds 后重试本阶段。"
            ) from exc
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = data["choices"][0]["message"]["content"]
        return AIResponse(text=text, token_usage=data.get("usage", {}), elapsed_ms=elapsed_ms)
