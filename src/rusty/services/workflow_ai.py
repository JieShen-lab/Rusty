from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rusty.services.ai_client import AIClient, OpenAICompatibleClient
from rusty.services.model_service import ModelService
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService
from rusty.services.prompt_compiler import PromptCompiler


class WorkflowAI:
    """Shared structured AI boundary for all novel workflow orchestrators."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        ai_client: AIClient | Any | None = None,
    ) -> None:
        self.database_path = (
            Path(database_path) if database_path is not None else default_database_path()
        )
        self.client = ai_client or OpenAICompatibleClient()
        self.models = ModelService(self.database_path)
        self.projects = ProjectService(self.database_path)
        self.compiler = PromptCompiler()

    def generate_json(
        self,
        *,
        project_id: int,
        stage: str,
        payload: dict[str, Any],
        output_contract: str,
    ) -> dict[str, Any]:
        fake_method = getattr(self.client, "generate_json", None)
        if callable(fake_method):
            value = fake_method(stage, payload)
            if not isinstance(value, dict):
                raise ValueError(f"{stage} must return a JSON object.")
            return value

        settings = self.projects.get_project_settings(project_id)
        model = (
            self.models.get_model(settings.model_id)
            if settings is not None and settings.model_id is not None
            else self.models.get_default_model()
        )
        if model is None:
            raise ValueError("No AI model is configured for this workflow.")
        request = self.compiler.compile_workflow_json(
            stage=stage,
            payload=payload,
            output_contract=output_contract,
        )
        response = self.client.chat(
            model,
            self.models.get_api_key(model.id),
            request.message_list(),
        )
        parsed = _parse_json_object(response.text)
        if not isinstance(parsed, dict):
            raise ValueError(f"{stage} must return a JSON object.")
        return parsed


def _parse_json_object(text: str) -> dict[str, Any]:
    value = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.DOTALL)
    if fenced:
        value = fenced.group(1)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI returned invalid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("AI output must be a JSON object.")
    return parsed
