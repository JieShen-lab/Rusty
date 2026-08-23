from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rusty.db import default_database_path
from rusty.services.ai_client import AIClient, AIResponse, create_ai_client
from rusty.services.model_service import ModelService, ModelTestResult
from rusty.services.prompt_slot_service import PromptSlotService


class AIRequestExecutor:
    """The only Rusty business boundary allowed to call the model transport."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        ai_client: AIClient | Any | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.client = ai_client or create_ai_client(purpose="generation")
        self.models = ModelService(self.database_path)
        self.prompts = PromptSlotService(self.database_path)

    def execute(
        self,
        task_messages: list[dict[str, str]],
        *,
        model_id: int | None = None,
        project_id: int | None = None,
    ) -> AIResponse:
        messages = self._messages(task_messages)
        model = self.models.resolve_model_config(model_id, project_id=project_id)
        return self.client.chat(model, self.models.get_api_key(model.id), messages)

    def test_connection(self, model_id: int) -> ModelTestResult:
        model = self.models.resolve_model_config(model_id)
        hostname = (urlparse(model.base_url).hostname or "").lower()
        if not self.models.get_api_key(model.id) and hostname not in {"localhost", "127.0.0.1", "::1"}:
            return ModelTestResult(
                ok=False,
                message="No API key is available in the system keyring. Enter and save the API key again.",
            )
        try:
            response = self.execute(
                [{"role": "user", "content": "Reply with OK only."}],
                model_id=model_id,
            )
        except Exception as exc:
            return ModelTestResult(ok=False, message=str(exc))
        message = response.text.strip()
        return ModelTestResult(
            ok=bool(message),
            message=message or "模型返回了空响应。",
            elapsed_ms=response.elapsed_ms,
        )

    def _messages(self, task_messages: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in task_messages:
            role = str(message.get("role") or "").strip()
            content = str(message.get("content") or "")
            if role == "system":
                raise ValueError("Business callers cannot provide a system message.")
            if role not in {"user", "assistant"}:
                raise ValueError(f"Unsupported AI message role: {role}")
            normalized.append({"role": role, "content": content})
        if not normalized:
            raise ValueError("An AI request requires at least one task message.")
        return [
            {"role": "system", "content": self.prompts.get_global_system_prompt()},
            *normalized,
        ]
