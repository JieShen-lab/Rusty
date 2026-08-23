from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rusty.db import default_database_path
from rusty.services.ai_request_executor import AIRequestExecutor


Validator = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class StructuredModelResult:
    value: dict[str, Any]


class StructuredModelService:
    """Parse and validate JSON responses, with one executor-backed repair attempt."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        executor: AIRequestExecutor | None = None,
        ai_client: Any | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.executor = executor or AIRequestExecutor(self.database_path, ai_client=ai_client)

    def run(
        self,
        *,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
        validator: Validator,
        model_id: int | None = None,
        project_id: int | None = None,
    ) -> StructuredModelResult:
        response = self.executor.execute(messages, model_id=model_id, project_id=project_id)
        raw_response = response.text
        try:
            value = validator(_parse_json_object(raw_response))
        except (TypeError, ValueError, json.JSONDecodeError) as first_error:
            repair = self.executor.execute(
                [
                    {"role": "assistant", "content": raw_response},
                    {
                        "role": "user",
                        "content": (
                            "[TASK: JSON REPAIR]\n"
                            "Repair the previous response to match the JSON schema exactly. "
                            "Return JSON only and do not add facts.\n\n"
                            f"Schema:\n{json.dumps(output_schema, ensure_ascii=False)}\n\n"
                            f"Validation error:\n{first_error}"
                        ),
                    },
                ],
                model_id=model_id,
                project_id=project_id,
            )
            value = validator(_parse_json_object(repair.text))
        return StructuredModelResult(value=value)


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
