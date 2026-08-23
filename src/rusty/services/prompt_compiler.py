from __future__ import annotations

import json
from typing import Any


class WorkflowPromptBuilder:
    """Build task messages without creating or loading a system prompt."""

    def build(
        self,
        *,
        stage: str,
        task_prompt: str,
        payload: dict[str, Any],
        user_instruction: str,
        output_contract: str,
    ) -> list[dict[str, str]]:
        task_rules = "Return plain text only. Use only the supplied context and do not introduce unsupported story facts."
        context = "\n\n".join(
            f"## {self._title(key)}\n{self._text(value)}"
            for key, value in payload.items()
            if self._text(value)
        )
        content = (
            f"[TASK: {stage.upper()}]\n\n"
            f"[TASK RULES]\n{task_rules}\n\n"
            f"[TASK PROMPT]\n{task_prompt.strip() or 'None'}\n\n"
            f"[RUNTIME CONTEXT]\n{context or 'None'}\n\n"
            f"[USER REQUIREMENT]\n{user_instruction.strip() or 'None'}\n\n"
            f"[PROGRAM OUTPUT CONTRACT]\n{output_contract}"
        )
        return [{"role": "user", "content": content}]

    @staticmethod
    def _title(key: str) -> str:
        return {
            "source_text": "当前章节原文",
            "document_text": "整本小说原文",
            "source_outline": "旧大纲",
            "target_outline": "新大纲及细节",
            "author_style": "作者风格",
            "sample_text": "样本文本",
        }.get(key, key)

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value).strip()
