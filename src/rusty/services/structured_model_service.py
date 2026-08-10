from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rusty.db import initialize_database, session
from rusty.services.ai_client import AIClient, OpenAICompatibleClient
from rusty.services.model_service import ModelConfig, ModelService
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService


Validator = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class StructuredModelResult:
    invocation_id: int
    model_id: int
    value: dict[str, Any]
    raw_response: str
    token_usage: dict[str, Any]
    elapsed_ms: int
    repaired: bool


class StructuredModelService:
    """Execute auditable JSON model calls with one schema-repair attempt."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        ai_client: AIClient | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.model_service = ModelService(self.database_path)
        self.project_service = ProjectService(self.database_path)
        self.ai_client = ai_client or OpenAICompatibleClient()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def run(
        self,
        *,
        invocation_kind: str,
        stage: str,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
        validator: Validator,
        model_id: int | None = None,
        project_id: int | None = None,
        document_id: int | None = None,
        chapter_id: int | None = None,
        scene_id: int | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
    ) -> StructuredModelResult:
        model = self.resolve_model(model_id=model_id, project_id=project_id)
        request = {
            "messages": messages,
            "output_schema": output_schema,
            "model": {
                "id": model.id,
                "name": model.model_name,
                "temperature": model.temperature,
                "max_tokens": model.max_tokens,
            },
        }
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO model_invocations (
                    invocation_kind, project_id, document_id, chapter_id, scene_id,
                    resource_type, resource_id, model_id, stage, request_json,
                    output_schema_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invocation_kind,
                    project_id,
                    document_id,
                    chapter_id,
                    scene_id,
                    resource_type,
                    resource_id,
                    model.id,
                    stage,
                    json.dumps(request, ensure_ascii=False),
                    json.dumps(output_schema, ensure_ascii=False),
                ),
            )
            invocation_id = int(cursor.lastrowid)
        token_usage: dict[str, Any] = {}
        elapsed_ms = 0
        raw_response = ""
        try:
            response = self.ai_client.chat(model, self.model_service.get_api_key(model.id), messages)
            raw_response = response.text
            token_usage = dict(response.token_usage)
            elapsed_ms = response.elapsed_ms
            try:
                parsed = _parse_json_object(raw_response)
                value = validator(parsed)
                repaired = False
                validation = {"valid": True, "repaired": False}
            except (TypeError, ValueError, json.JSONDecodeError) as first_error:
                repair_messages = [
                    {
                        "role": "system",
                        "content": (
                            "Repair the supplied response to match the JSON schema exactly. "
                            "Return JSON only; do not add facts or prose."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Schema:\n{json.dumps(output_schema, ensure_ascii=False)}\n\n"
                            f"Validation error:\n{first_error}\n\n"
                            f"Invalid response:\n{raw_response}"
                        ),
                    },
                ]
                repaired_response = self.ai_client.chat(
                    model,
                    self.model_service.get_api_key(model.id),
                    repair_messages,
                )
                token_usage = _merge_usage(token_usage, repaired_response.token_usage)
                elapsed_ms += repaired_response.elapsed_ms
                parsed = _parse_json_object(repaired_response.text)
                value = validator(parsed)
                validation = {
                    "valid": True,
                    "repaired": True,
                    "initial_error": str(first_error),
                    "repair_response": repaired_response.text,
                }
                repaired = True
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    UPDATE model_invocations
                    SET status = 'completed', response_text = ?, parsed_json = ?,
                        validation_json = ?, token_usage_json = ?, elapsed_ms = ?,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        raw_response,
                        json.dumps(value, ensure_ascii=False),
                        json.dumps(validation, ensure_ascii=False),
                        json.dumps(token_usage, ensure_ascii=False),
                        elapsed_ms,
                        invocation_id,
                    ),
                )
            return StructuredModelResult(
                invocation_id=invocation_id,
                model_id=model.id,
                value=value,
                raw_response=raw_response,
                token_usage=token_usage,
                elapsed_ms=elapsed_ms,
                repaired=repaired,
            )
        except Exception as exc:
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    UPDATE model_invocations
                    SET status = 'failed', response_text = ?, token_usage_json = ?,
                        elapsed_ms = ?, error_type = ?, error_message = ?,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        raw_response,
                        json.dumps(token_usage, ensure_ascii=False),
                        elapsed_ms or None,
                        type(exc).__name__,
                        str(exc),
                        invocation_id,
                    ),
                )
            raise

    def resolve_model(self, *, model_id: int | None, project_id: int | None) -> ModelConfig:
        selected_id = model_id
        if selected_id is None and project_id is not None:
            settings = self.project_service.get_project_settings(project_id)
            selected_id = settings.model_id if settings is not None else None
        model = self.model_service.get_model(selected_id) if selected_id is not None else self.model_service.get_default_model()
        if model is None:
            raise ValueError("No model configured.")
        return model


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValueError("Model response must be a JSON object.")
    return value


def _merge_usage(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    keys = set(first) | set(second)
    merged: dict[str, Any] = {}
    for key in keys:
        left, right = first.get(key), second.get(key)
        merged[key] = left + right if isinstance(left, (int, float)) and isinstance(right, (int, float)) else right or left
    return merged
