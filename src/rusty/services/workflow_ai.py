from __future__ import annotations

from pathlib import Path
from typing import Any

from rusty.db import default_database_path
from rusty.services.ai_request_executor import AIRequestExecutor
from rusty.services.prompt_compiler import WorkflowPromptBuilder
from rusty.services.prompt_slot_service import PromptSlotService


class WorkflowAI:
    """Chapter-workflow facade built on the single AI request executor."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        ai_client: Any | None = None,
        executor: AIRequestExecutor | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.executor = executor or AIRequestExecutor(self.database_path, ai_client=ai_client)
        self.builder = WorkflowPromptBuilder()
        self.prompts = PromptSlotService(self.database_path)

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
        response = self.executor.execute(
            self._messages(stage, workflow_key, task_key, payload, user_instruction, output_contract),
            project_id=project_id,
        )
        value = response.text.strip()
        if not value:
            raise ValueError(f"{stage} returned empty plain text.")
        return value

    def _messages(
        self,
        stage: str,
        workflow_key: str | None,
        task_key: str | None,
        payload: dict[str, Any],
        user_instruction: str,
        output_contract: str,
    ) -> list[dict[str, str]]:
        slot_key = task_key if task_key in {"chapter_summary", "writing"} else workflow_key
        task_prompt = self.prompts.get_slot(str(slot_key)).content if slot_key else ""
        return self.builder.build(
            stage=stage,
            task_prompt=task_prompt,
            payload=payload,
            user_instruction=user_instruction,
            output_contract=output_contract,
        )
