from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rusty.services.ai_client import AIClient, create_ai_client
from rusty.services.model_service import ModelService
from rusty.db import default_database_path
from rusty.services.prompt_compiler import PromptCompiler
from rusty.services.prompt_definition_service import PromptDefinitionService


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
        self.client = ai_client or create_ai_client(purpose="generation")
        self.models = ModelService(self.database_path)
        self.compiler = PromptCompiler()
        self.prompts = PromptDefinitionService(self.database_path)

    def generate_json(
        self,
        *,
        project_id: int,
        stage: str,
        payload: dict[str, Any],
        output_contract: str,
        workflow_key: str | None = None,
        task_key: str | None = None,
        user_instruction: str = "",
        plain_context: bool = False,
    ) -> dict[str, Any]:
        fake_method = getattr(self.client, "generate_json", None)
        if callable(fake_method):
            value = fake_method(stage, payload)
            if not isinstance(value, dict):
                raise ValueError(f"{stage} must return a JSON object.")
            return value

        model = self.models.resolve_model_config(project_id=project_id)
        system_prompt = self._require_system_prompt()
        task_workflow = workflow_key if task_key not in {"chapter_summary", "writing"} else None
        definition = self.prompts.find_task(workflow_key=task_workflow, task_key=task_key) if task_key else None
        request = self.compiler.compile_creative_json(
            stage=stage,
            system_prompt=system_prompt,
            task_prompt=definition.content if definition else "",
            payload=payload,
            user_instruction=user_instruction,
            output_contract=output_contract,
            prompt_definition_id=definition.id if definition else None,
            plain_context=plain_context,
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

    def generate_text(
        self,
        *,
        project_id: int,
        stage: str,
        payload: dict[str, Any],
        output_contract: str,
        workflow_key: str | None = None,
        task_key: str | None = None,
        user_instruction: str = "",
    ) -> str:
        fake_method = getattr(self.client, "generate_text", None)
        if callable(fake_method):
            value = fake_method(stage, payload)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{stage} must return non-empty plain text.")
            return value.strip()

        model = self.models.resolve_model_config(project_id=project_id)
        system_prompt = self._require_system_prompt()
        task_workflow = workflow_key if task_key not in {"chapter_summary", "writing"} else None
        definition = self.prompts.find_task(workflow_key=task_workflow, task_key=task_key) if task_key else None
        request = self.compiler.compile_creative_text(
            stage=stage,
            system_prompt=system_prompt,
            task_prompt=definition.content if definition else "",
            payload=payload,
            user_instruction=user_instruction,
            output_contract=output_contract,
            prompt_definition_id=definition.id if definition else None,
        )
        response = self.client.chat(
            model,
            self.models.get_api_key(model.id),
            request.message_list(),
        )
        value = response.text.strip()
        if not value:
            raise ValueError(f"{stage} returned empty plain text.")
        return value

    def _require_system_prompt(self) -> str:
        definition = self.prompts.get_system_prompt()
        if definition is None or not definition.content.strip():
            raise ValueError("系统提示词不能为空；所有 AI 请求都必须携带系统提示词。")
        return definition.content.strip()


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
