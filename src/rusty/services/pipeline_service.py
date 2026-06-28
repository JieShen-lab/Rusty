from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rusty.db import initialize_database, session
from rusty.models import ChapterError, ChapterRecord, StageStatus, count_text_units
from rusty.services.ai_client import AIClient, AIResponse, OpenAICompatibleClient
from rusty.services.model_service import ModelConfig, ModelService
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.prompt_service import PromptService, PromptTemplate


@dataclass(frozen=True)
class PipelineResult:
    processed: int
    skipped: int
    failed: int
    paused: bool = False


class PipelineService:
    def __init__(
        self,
        database_path: str | Path | None = None,
        ai_client: AIClient | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.project_service = ProjectService(self.database_path)
        self.model_service = ModelService(self.database_path)
        self.prompt_service = PromptService(self.database_path)
        self.ai_client = ai_client or OpenAICompatibleClient()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def summarize_chapter(
        self,
        chapter_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
    ) -> str:
        return self._run_chapter_stage(
            chapter_id,
            "summary",
            model_id,
            template_id,
            self._summary_messages,
            self._save_summary,
        )

    def detect_scene(
        self,
        chapter_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
    ) -> str:
        return self._run_chapter_stage(
            chapter_id,
            "scene_detection",
            model_id,
            template_id,
            self._scene_messages,
            self._save_scene_analysis,
        )

    def rewrite_chapter(
        self,
        chapter_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
    ) -> str:
        return self._run_chapter_stage(
            chapter_id,
            "rewrite",
            model_id,
            template_id,
            self._rewrite_messages,
            self._save_rewrite,
        )

    def run_project(
        self,
        project_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
        should_pause: Callable[[], bool] | None = None,
    ) -> PipelineResult:
        processed = 0
        failed = 0
        self.set_project_paused(project_id, False)
        self._set_project_status(project_id, "processing")
        for chapter in self.project_service.list_chapters(project_id):
            if should_pause and should_pause():
                self.set_project_paused(project_id, True)
                return PipelineResult(processed=processed, skipped=0, failed=failed, paused=True)
            if self.is_project_paused(project_id):
                return PipelineResult(processed=processed, skipped=0, failed=failed, paused=True)
            try:
                self.summarize_chapter(chapter.id, model_id, template_id)
                scene_text = self.detect_scene(chapter.id, model_id, template_id)
                if self._scene_needs_rewrite(scene_text):
                    self.rewrite_chapter(chapter.id, model_id, template_id)
                processed += 1
            except Exception:
                failed += 1
        self._set_project_status(project_id, "processed" if failed == 0 else "partial")
        return PipelineResult(processed=processed, skipped=0, failed=failed)

    def retry_chapter_stage(
        self,
        chapter_id: int,
        stage: str,
        model_id: int | None = None,
        template_id: int | None = None,
    ) -> str:
        if stage == "summary":
            return self.summarize_chapter(chapter_id, model_id, template_id)
        if stage == "scene_detection":
            return self.detect_scene(chapter_id, model_id, template_id)
        if stage == "rewrite":
            return self.rewrite_chapter(chapter_id, model_id, template_id)
        raise ValueError(f"Unsupported retry stage: {stage}")

    def set_project_paused(self, project_id: int, paused: bool) -> None:
        self._set_project_status(project_id, "paused" if paused else "ready")

    def is_project_paused(self, project_id: int) -> bool:
        project = self.project_service.get_project(project_id)
        return project is not None and project.status == "paused"

    def merge_project_text(self, project_id: int) -> str:
        parts: list[str] = []
        for chapter in self.project_service.list_chapters(project_id):
            text = chapter.rewritten_text or chapter.original_text
            parts.append(f"{chapter.title}\n\n{text.strip()}")
        return "\n\n".join(parts).strip() + "\n"

    def list_chapter_stage_statuses(self, chapter_id: int) -> list[StageStatus]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT stage, status, retry_count, elapsed_ms, started_at, finished_at
                FROM chapter_stage_status
                WHERE chapter_id = ?
                ORDER BY stage
                """,
                (chapter_id,),
            ).fetchall()
        return [
            StageStatus(
                stage=row["stage"],
                status=row["status"],
                retry_count=row["retry_count"],
                elapsed_ms=row["elapsed_ms"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in rows
        ]

    def list_chapter_errors(self, chapter_id: int, include_resolved: bool = False) -> list[ChapterError]:
        where = "chapter_id = ?" if include_resolved else "chapter_id = ? AND resolved_at IS NULL"
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT id, stage, error_type, message, created_at, resolved_at
                FROM chapter_errors
                WHERE {where}
                ORDER BY created_at DESC, id DESC
                """,
                (chapter_id,),
            ).fetchall()
        return [
            ChapterError(
                id=row["id"],
                stage=row["stage"],
                error_type=row["error_type"],
                message=row["message"],
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
            )
            for row in rows
        ]

    def _run_chapter_stage(
        self,
        chapter_id: int,
        stage: str,
        model_id: int | None,
        template_id: int | None,
        message_builder,
        saver,
    ) -> str:
        chapter = self.project_service.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError(f"Chapter not found: {chapter_id}")
        model = self._resolve_model(model_id, chapter.project_id)
        template = self._resolve_template(template_id, chapter.project_id)
        api_key = self.model_service.get_api_key(model.id)
        self._mark_stage(chapter_id, stage, "running")
        try:
            response = self.ai_client.chat(model, api_key, message_builder(chapter, template))
            saver(chapter, model, template, response)
            self._mark_stage(chapter_id, stage, "completed", response.elapsed_ms, response.token_usage)
            self._resolve_stage_errors(chapter_id, stage)
            return response.text
        except Exception as exc:
            self._mark_stage(chapter_id, stage, "failed")
            self._record_error(chapter_id, stage, exc)
            raise

    def _resolve_model(self, model_id: int | None, project_id: int) -> ModelConfig:
        settings = self.project_service.get_project_settings(project_id)
        effective_model_id = model_id if model_id is not None else (settings.model_id if settings else None)
        model = (
            self.model_service.get_model(effective_model_id)
            if effective_model_id is not None
            else self.model_service.get_default_model()
        )
        if model is None:
            raise ValueError("No model configured.")
        return model

    def _resolve_template(self, template_id: int | None, project_id: int) -> PromptTemplate:
        settings = self.project_service.get_project_settings(project_id)
        effective_template_id = (
            template_id if template_id is not None else (settings.prompt_template_id if settings else None)
        )
        template = (
            self.prompt_service.get_template(effective_template_id)
            if effective_template_id is not None
            else self.prompt_service.get_default_template()
        )
        if template is None:
            raise ValueError("No prompt template configured.")
        return template

    @staticmethod
    def _summary_messages(chapter: ChapterRecord, template: PromptTemplate) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": template.global_rules},
            {
                "role": "user",
                "content": f"{template.summary_rules}\n\nSummarize this chapter:\n# {chapter.title}\n{chapter.original_text}",
            },
        ]

    @staticmethod
    def _scene_messages(chapter: ChapterRecord, template: PromptTemplate) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": template.global_rules},
            {
                "role": "user",
                "content": (
                    f"{template.scene_detection_rules}\n\n"
                    "Return JSON with needs_rewrite, labels, and reasoning.\n"
                    f"# {chapter.title}\n{chapter.original_text}"
                ),
            },
        ]

    def _rewrite_messages(self, chapter: ChapterRecord, template: PromptTemplate) -> list[dict[str, str]]:
        settings = self.project_service.get_project_settings(chapter.project_id)
        target_text = ""
        if settings and settings.target_word_count:
            target_text = f"\nTarget length: at least {settings.target_word_count} non-whitespace characters."
        if settings and settings.min_expansion_ratio:
            target_text += f"\nMinimum expansion ratio: {settings.min_expansion_ratio:.2f}x the original chapter length."
        return [
            {"role": "system", "content": template.global_rules},
            {
                "role": "user",
                "content": (
                    f"{template.rewrite_rules}{target_text}\n\n"
                    f"Rewrite this chapter:\n# {chapter.title}\n{chapter.original_text}"
                ),
            },
        ]

    def _save_summary(
        self,
        chapter: ChapterRecord,
        model: ModelConfig,
        template: PromptTemplate,
        response: AIResponse,
    ) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_summaries (
                    chapter_id,
                    plot_summary,
                    model_id,
                    prompt_template_id,
                    token_usage_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id)
                DO UPDATE SET
                    plot_summary = excluded.plot_summary,
                    model_id = excluded.model_id,
                    prompt_template_id = excluded.prompt_template_id,
                    token_usage_json = excluded.token_usage_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chapter.id, response.text, model.id, template.id, json.dumps(response.token_usage)),
            )

    def _save_scene_analysis(
        self,
        chapter: ChapterRecord,
        model: ModelConfig,
        template: PromptTemplate,
        response: AIResponse,
    ) -> None:
        parsed = _parse_scene_response(response.text)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_scene_analysis (
                    chapter_id,
                    needs_rewrite,
                    scene_labels_json,
                    reasoning,
                    model_id,
                    prompt_template_id,
                    token_usage_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id)
                DO UPDATE SET
                    needs_rewrite = excluded.needs_rewrite,
                    scene_labels_json = excluded.scene_labels_json,
                    reasoning = excluded.reasoning,
                    model_id = excluded.model_id,
                    prompt_template_id = excluded.prompt_template_id,
                    token_usage_json = excluded.token_usage_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    chapter.id,
                    1 if parsed["needs_rewrite"] else 0,
                    json.dumps(parsed["labels"], ensure_ascii=False),
                    parsed["reasoning"],
                    model.id,
                    template.id,
                    json.dumps(response.token_usage),
                ),
            )
            connection.execute(
                "UPDATE chapters SET needs_rewrite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (1 if parsed["needs_rewrite"] else 0, chapter.id),
            )

    def _save_rewrite(
        self,
        chapter: ChapterRecord,
        model: ModelConfig,
        template: PromptTemplate,
        response: AIResponse,
    ) -> None:
        settings = self.project_service.get_project_settings(chapter.project_id)
        target_word_count = settings.target_word_count if settings else None
        min_expansion_ratio = settings.min_expansion_ratio if settings else None
        word_count = count_text_units(response.text)
        ratio = word_count / chapter.word_count if chapter.word_count else None
        if target_word_count is not None and word_count < target_word_count:
            raise ValueError(f"Rewrite is shorter than target length: {word_count} < {target_word_count}")
        if min_expansion_ratio is not None and ratio is not None and ratio < min_expansion_ratio:
            raise ValueError(f"Rewrite expansion ratio is below minimum: {ratio:.2f} < {min_expansion_ratio:.2f}")
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_rewrites (
                    chapter_id,
                    rewritten_text,
                    target_word_count,
                    actual_word_count,
                    expansion_ratio,
                    model_id,
                    prompt_template_id,
                    token_usage_json,
                    elapsed_ms,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id)
                DO UPDATE SET
                    rewritten_text = excluded.rewritten_text,
                    target_word_count = excluded.target_word_count,
                    actual_word_count = excluded.actual_word_count,
                    expansion_ratio = excluded.expansion_ratio,
                    model_id = excluded.model_id,
                    prompt_template_id = excluded.prompt_template_id,
                    token_usage_json = excluded.token_usage_json,
                    elapsed_ms = excluded.elapsed_ms,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    chapter.id,
                    response.text,
                    target_word_count,
                    word_count,
                    ratio,
                    model.id,
                    template.id,
                    json.dumps(response.token_usage),
                    response.elapsed_ms,
                ),
            )
            connection.execute(
                """
                UPDATE chapters
                SET rewritten_text = ?, status = 'rewritten', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (response.text, chapter.id),
            )

    def _mark_stage(
        self,
        chapter_id: int,
        stage: str,
        status: str,
        elapsed_ms: int | None = None,
        metadata: dict | None = None,
    ) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_stage_status (
                    chapter_id,
                    stage,
                    status,
                    started_at,
                    finished_at,
                    retry_count,
                    elapsed_ms,
                    metadata_json
                ) VALUES (
                    ?,
                    ?,
                    ?,
                    CASE WHEN ? = 'running' THEN CURRENT_TIMESTAMP ELSE NULL END,
                    CASE WHEN ? IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE NULL END,
                    0,
                    ?,
                    ?
                )
                ON CONFLICT(chapter_id, stage)
                DO UPDATE SET
                    status = excluded.status,
                    started_at = CASE WHEN excluded.status = 'running' THEN CURRENT_TIMESTAMP ELSE chapter_stage_status.started_at END,
                    finished_at = CASE WHEN excluded.status IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE NULL END,
                    retry_count = CASE WHEN excluded.status = 'running' THEN chapter_stage_status.retry_count + 1 ELSE chapter_stage_status.retry_count END,
                    elapsed_ms = excluded.elapsed_ms,
                    metadata_json = excluded.metadata_json
                """,
                (
                    chapter_id,
                    stage,
                    status,
                    status,
                    status,
                    elapsed_ms,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )

    def _record_error(self, chapter_id: int, stage: str, exc: Exception) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_errors (chapter_id, stage, error_type, message)
                VALUES (?, ?, ?, ?)
                """,
                (chapter_id, stage, type(exc).__name__, str(exc)),
            )

    def _resolve_stage_errors(self, chapter_id: int, stage: str) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE chapter_errors
                SET resolved_at = CURRENT_TIMESTAMP
                WHERE chapter_id = ? AND stage = ? AND resolved_at IS NULL
                """,
                (chapter_id, stage),
            )

    def _set_project_status(self, project_id: int, status: str) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, project_id),
            )

    @staticmethod
    def _scene_needs_rewrite(scene_text: str) -> bool:
        return bool(_parse_scene_response(scene_text)["needs_rewrite"])


def _parse_scene_response(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"needs_rewrite": True, "labels": ["unspecified"], "reasoning": text}
    labels = data.get("labels") or data.get("scene_labels") or []
    if isinstance(labels, str):
        labels = [labels]
    return {
        "needs_rewrite": bool(data.get("needs_rewrite")),
        "labels": labels,
        "reasoning": str(data.get("reasoning", "")),
    }
