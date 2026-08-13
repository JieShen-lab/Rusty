from __future__ import annotations

from pathlib import Path
from typing import Any

from rusty.db import default_database_path
from rusty.services.document_library_service import CleanupResult, DocumentLibraryService
from rusty.services.structured_model_service import StructuredModelService


DEFAULT_CLEANUP_PROMPT = (
    "只整理空白、段落、标点间距和明显排版问题。"
    "禁止改变剧情，禁止改写句子，禁止添加内容，禁止删除有效正文，禁止改变人物、设定和事实。"
)

CLEANUP_SCHEMA = {
    "type": "object",
    "required": ["text"],
    "properties": {"text": {"type": "string"}},
}


class DocumentCleanupAIService:
    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        structured_model_service: StructuredModelService | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.document_service = DocumentLibraryService(self.database_path)
        self.model_service = structured_model_service or StructuredModelService(self.database_path)

    def apply(
        self,
        document_id: int,
        *,
        chapter_id: int | None,
        prompt: str = DEFAULT_CLEANUP_PROMPT,
        model_id: int | None = None,
    ) -> CleanupResult:
        content = self.document_service.get_content(document_id, chapter_id)
        instruction = prompt.strip() or DEFAULT_CLEANUP_PROMPT
        result = self.model_service.run(
            invocation_kind="document_cleanup",
            stage="formatting_cleanup",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Clean formatting only. Preserve every meaningful sentence, fact, character, "
                        "and event. Do not summarize, rewrite, add, or remove content. Return strict JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Title: {content.title}\n"
                        f"Cleanup requirement: {instruction}\n"
                        "Return {\"text\": \"...\"}.\n\n"
                        f"Source text:\n{content.body_text}"
                    ),
                },
            ],
            output_schema=CLEANUP_SCHEMA,
            validator=_validate_cleanup,
            model_id=model_id,
            document_id=document_id,
        )
        return self.document_service.apply_prompt_cleanup(
            document_id,
            chapter_id=chapter_id,
            title=content.title,
            cleaned_text=str(result.value["text"]),
            prompt=instruction,
        )


def _validate_cleanup(value: dict[str, Any]) -> dict[str, str]:
    text = value.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Cleanup result must contain non-empty text.")
    return {"text": text}
