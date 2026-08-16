from __future__ import annotations

import json
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


class AIConnectTimeoutError(TimeoutError):
    """The provider could not be reached within the connection window."""


class AIReadTimeoutError(TimeoutError):
    """The provider accepted the connection but did not finish responding in time."""


class AIAuthenticationError(RuntimeError):
    """The provider rejected the configured credentials."""


class AIProviderError(RuntimeError):
    """The provider returned a non-authentication HTTP error."""


class AIResponseParseError(RuntimeError):
    """The provider response did not match the chat-completions envelope."""


class OpenAICompatibleClient(AIClient):
    def __init__(self, *, purpose: str = "generation") -> None:
        self.purpose = purpose

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
        use_streaming = self.purpose != "connection_test"
        if use_streaming:
            payload["stream"] = True

        url = model.base_url.rstrip("/") + "/chat/completions"
        connect_seconds = min(10.0, max(1.0, float(model.timeout_seconds)))
        read_seconds = (
            min(15.0, max(3.0, float(model.timeout_seconds)))
            if self.purpose == "connection_test"
            else max(15.0, float(model.timeout_seconds))
        )
        timeout = httpx.Timeout(
            connect=connect_seconds,
            read=read_seconds,
            write=connect_seconds,
            pool=connect_seconds,
        )
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout) as client:
                if use_streaming:
                    with client.stream("POST", url, headers=headers, json=payload) as response:
                        response.raise_for_status()
                        text, token_usage = self._read_stream(response.iter_lines())
                else:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    text, token_usage = self._read_response(data)
        except httpx.ConnectTimeout as exc:
            raise AIConnectTimeoutError(
                f"无法建立模型连接：{connect_seconds:g} 秒内未连接到服务。"
            ) from exc
        except httpx.ReadTimeout as exc:
            raise AIReadTimeoutError(
                f"模型已连接但响应超时：连续 {read_seconds:g} 秒未收到响应数据。"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                raise AIAuthenticationError("模型服务认证失败，请检查当前模型的 API Key。") from exc
            raise AIProviderError(f"模型服务返回错误（HTTP {status}）。") from exc
        except httpx.RequestError as exc:
            raise AIProviderError(f"模型请求失败：{exc}") from exc
        except ValueError as exc:
            raise AIResponseParseError("模型返回的响应不是有效 JSON。") from exc
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return AIResponse(text=text, token_usage=token_usage, elapsed_ms=elapsed_ms)

    @staticmethod
    def _read_response(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIResponseParseError("模型返回内容缺少 choices[0].message.content。") from exc
        return str(text), data.get("usage", {})

    @staticmethod
    def _read_stream(lines: Any) -> tuple[str, dict[str, Any]]:
        parts: list[str] = []
        usage: dict[str, Any] = {}
        for line in lines:
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                break
            chunk = json.loads(raw)
            if chunk.get("error"):
                message = chunk["error"].get("message") if isinstance(chunk["error"], dict) else chunk["error"]
                raise AIProviderError(f"模型服务返回错误：{message}")
            if isinstance(chunk.get("usage"), dict):
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if choices and isinstance(choices[0], dict):
                content = (choices[0].get("delta") or {}).get("content")
                if content:
                    parts.append(str(content))
        if not parts:
            raise AIResponseParseError("模型流式响应未返回 choices[0].delta.content。")
        return "".join(parts), usage


def create_ai_client(*, purpose: str = "generation") -> AIClient:
    """Create the shared OpenAI-compatible transport used by tests and real tasks."""
    return OpenAICompatibleClient(purpose=purpose)
