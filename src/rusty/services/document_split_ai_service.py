from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.document_library_service import DocumentLibraryService
from rusty.services.project_service import default_database_path
from rusty.services.structured_model_service import StructuredModelService


AI_SPLIT_SCHEMA = {
    "type": "object",
    "required": ["chapters"],
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "required": ["title", "start_offset", "end_offset", "reason"],
            },
        }
    },
}


class DocumentSplitAIService:
    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        structured_model_service: StructuredModelService | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.document_service = DocumentLibraryService(self.database_path)
        self.model_service = structured_model_service or StructuredModelService(self.database_path)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def preview(self, document_id: int, *, model_id: int | None = None) -> dict[str, Any]:
        content = self.document_service.get_content(document_id)
        result = self.model_service.run(
            invocation_kind="document_ai_split",
            stage="chapter_boundaries",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Propose chapter boundaries for the exact source text. Boundaries must start "
                        "at 0, be continuous and non-overlapping, and end at the source length. "
                        "Return strict JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Source length: {len(content.text)} characters.\n"
                        "Return chapters[{title,start_offset,end_offset,reason}].\n\n"
                        f"Source text:\n{content.text}"
                    ),
                },
            ],
            output_schema=AI_SPLIT_SCHEMA,
            validator=lambda value: _validate_split(value, len(content.text)),
            model_id=model_id,
            document_id=document_id,
        )
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO document_split_proposals (
                    document_id, source_revision_id, proposal_kind,
                    boundaries_json, unmatched_json, model_invocation_id
                ) VALUES (?, ?, 'ai', ?, '{}', ?)
                """,
                (
                    document_id,
                    content.revision_id,
                    json.dumps(result.value["chapters"], ensure_ascii=False),
                    result.invocation_id,
                ),
            )
            proposal_id = int(cursor.lastrowid)
        return {
            "proposal_id": proposal_id,
            "document_id": document_id,
            "source_revision_id": content.revision_id,
            "chapters": result.value["chapters"],
            "model_invocation_id": result.invocation_id,
        }

    def apply(self, proposal_id: int, *, chapters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        with session(self.database_path) as connection:
            proposal = connection.execute(
                "SELECT * FROM document_split_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
        if proposal is None:
            raise FileNotFoundError(f"Document split proposal not found: {proposal_id}")
        if proposal["status"] != "draft":
            raise ValueError("Only draft document split proposals can be applied.")
        content = self.document_service.get_content(int(proposal["document_id"]))
        boundaries = chapters or json.loads(str(proposal["boundaries_json"]))
        validated = _validate_split({"chapters": boundaries}, len(content.text))["chapters"]
        revision, saved_chapters = self.document_service.apply_split_boundaries(
            int(proposal["document_id"]),
            source_revision_id=int(proposal["source_revision_id"]),
            boundaries=validated,
            revision_type="ai_split",
            metadata={
                "proposal_id": proposal_id,
                "model_invocation_id": proposal["model_invocation_id"],
            },
        )
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE document_split_proposals
                SET status = 'applied', boundaries_json = ?, applied_revision_id = ?,
                    applied_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(validated, ensure_ascii=False), revision.id, proposal_id),
            )
        return {
            "proposal_id": proposal_id,
            "document_id": int(proposal["document_id"]),
            "revision_id": revision.id,
            "chapters": [chapter.__dict__ for chapter in saved_chapters],
        }


def _validate_split(value: dict[str, Any], text_length: int) -> dict[str, Any]:
    chapters = value.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("chapters must be a non-empty array.")
    normalized = sorted(
        (
            {
                "title": str(item.get("title") or "").strip(),
                "start_offset": int(item.get("start_offset", -1)),
                "end_offset": int(item.get("end_offset", -1)),
                "reason": str(item.get("reason") or "").strip(),
            }
            for item in chapters
            if isinstance(item, dict)
        ),
        key=lambda item: item["start_offset"],
    )
    if len(normalized) != len(chapters):
        raise ValueError("Each chapter must be an object.")
    expected = 0
    for index, chapter in enumerate(normalized):
        if not chapter["title"]:
            raise ValueError(f"chapters[{index}].title is required.")
        if chapter["start_offset"] != expected or chapter["end_offset"] <= expected:
            raise ValueError("Chapter boundaries must be continuous and non-overlapping.")
        if chapter["end_offset"] > text_length:
            raise ValueError("Chapter boundary exceeds source length.")
        expected = chapter["end_offset"]
    if expected != text_length:
        raise ValueError("Chapter boundaries must cover the complete source text.")
    return {"chapters": normalized}
