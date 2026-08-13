from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from rusty.db import session
from rusty.models import ChapterAIOutputs, ChapterError, ChapterRecord, StageStatus, count_text_units
from rusty.services.ai_client import AIClient, AIResponse, OpenAICompatibleClient
from rusty.services.anchor_service import AnchorService, CharacterCard, OutlineTemplate
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.model_service import ModelConfig, ModelService
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService
from rusty.services.prompt_compiler import CompiledRequest, PromptCompiler
from rusty.services.prompt_service import PromptService, PromptTemplate
from rusty.services.style_service import StyleTemplate, StyleTemplateService


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
        self.chapter_versions = ChapterVersionService(self.database_path)
        self.model_service = ModelService(self.database_path)
        self.prompt_service = PromptService(self.database_path)
        self.style_service = StyleTemplateService(self.database_path)
        self.anchor_service = AnchorService(self.database_path)
        self.prompt_compiler = PromptCompiler()
        self.ai_client = ai_client or OpenAICompatibleClient()

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
            self._summary_request,
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
            self._scene_request,
            self._save_scene_analysis,
        )

    def rewrite_chapter(
        self,
        chapter_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
    ) -> str:
        return self._run_rewrite_stage(chapter_id, model_id, template_id)

    def expand_chapter_plot(
        self,
        chapter_id: int,
        enabled: bool = True,
        model_id: int | None = None,
        template_id: int | None = None,
    ) -> str:
        if not enabled:
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO chapter_plot_expansions (chapter_id, enabled, expanded_plot, updated_at)
                    VALUES (?, 0, '', CURRENT_TIMESTAMP)
                    ON CONFLICT(chapter_id)
                    DO UPDATE SET enabled = 0, expanded_plot = '', updated_at = CURRENT_TIMESTAMP
                    """,
                    (chapter_id,),
                )
            self._mark_stage(chapter_id, "plot_expansion", "completed", metadata={"enabled": False})
            return ""
        return self._run_chapter_stage(
            chapter_id,
            "plot_expansion",
            model_id,
            template_id,
            self._plot_expansion_request,
            self._save_plot_expansion,
        )

    def save_target_skeleton(self, chapter_id: int, text: str, enabled: bool = True) -> None:
        chapter = self.project_service.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError(f"Chapter not found: {chapter_id}")
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_plot_expansions (
                    chapter_id, enabled, expanded_plot, prompt_snapshot_json, updated_at
                ) VALUES (?, ?, ?, '{"source":"manual"}', CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id)
                DO UPDATE SET enabled = excluded.enabled, expanded_plot = excluded.expanded_plot,
                    model_id = NULL, prompt_template_id = NULL,
                    prompt_snapshot_json = excluded.prompt_snapshot_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chapter_id, 1 if enabled else 0, text),
            )

    def confirm_rewrite(self, chapter_id: int) -> None:
        chapter = self.project_service.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError(f"Chapter not found: {chapter_id}")
        if not (chapter.rewritten_text or "").strip():
            raise ValueError("No rewritten text is available to confirm.")
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE chapter_rewrites SET confirmed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE chapter_id = ?",
                (chapter_id,),
            )
            connection.execute(
                "UPDATE chapters SET status = 'confirmed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (chapter_id,),
            )

    def run_project(
        self,
        project_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
        should_pause: Callable[[], bool] | None = None,
    ) -> PipelineResult:
        resolved_model = self._resolve_model(model_id, project_id)
        resolved_template = self._resolve_template(template_id, project_id)
        settings = self.project_service.get_project_settings(project_id)
        concurrency = max(1, settings.concurrency if settings else 1)
        chapters = self.project_service.list_chapters(project_id)
        failed_ids: set[int] = set()
        skipped = 0
        self.set_project_paused(project_id, False)
        self._set_project_status(project_id, "processing")

        self._set_project_stage(project_id, "summary")
        summary_results, paused = self._run_chapter_batch(
            chapters,
            lambda chapter: self.summarize_chapter(chapter.id, resolved_model.id, resolved_template.id),
            concurrency,
            should_pause,
        )
        failed_ids.update(chapter.id for chapter in chapters if chapter.id not in summary_results)
        if paused:
            self.set_project_paused(project_id, True)
            return PipelineResult(len(summary_results), skipped, len(failed_ids), paused=True)

        eligible = [chapter for chapter in chapters if chapter.id in summary_results]
        self._set_project_stage(project_id, "scene_detection")
        scene_results, paused = self._run_chapter_batch(
            eligible,
            lambda chapter: self.detect_scene(chapter.id, resolved_model.id, resolved_template.id),
            concurrency,
            should_pause,
        )
        failed_ids.update(chapter.id for chapter in eligible if chapter.id not in scene_results)
        if paused:
            self.set_project_paused(project_id, True)
            return PipelineResult(len(scene_results), skipped, len(failed_ids), paused=True)

        rewrite_chapters: list[ChapterRecord] = []
        for chapter in eligible:
            scene_text = scene_results.get(chapter.id)
            if scene_text is None:
                continue
            if self._scene_needs_rewrite(scene_text):
                rewrite_chapters.append(chapter)
            else:
                self._mark_chapter_kept_original(chapter.id)
                skipped += 1

        self._set_project_stage(project_id, "rewrite")
        rewrite_results, paused = self._run_chapter_batch(
            rewrite_chapters,
            lambda chapter: self.rewrite_chapter(chapter.id, resolved_model.id, resolved_template.id),
            concurrency,
            should_pause,
        )
        failed_ids.update(chapter.id for chapter in rewrite_chapters if chapter.id not in rewrite_results)
        if paused:
            self.set_project_paused(project_id, True)
            return PipelineResult(len(chapters) - len(failed_ids), skipped, len(failed_ids), paused=True)

        self._set_project_stage(project_id, "review")
        self._set_project_status(project_id, "processed" if not failed_ids else "partial")
        return PipelineResult(
            processed=len(chapters) - len(failed_ids),
            skipped=skipped,
            failed=len(failed_ids),
        )

    def run_document_analysis(
        self,
        project_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
        should_pause: Callable[[], bool] | None = None,
    ) -> PipelineResult:
        resolved_model = self._resolve_model(model_id, project_id)
        resolved_template = self._resolve_template(template_id, project_id)
        settings = self.project_service.get_project_settings(project_id)
        concurrency = max(1, settings.concurrency if settings else 1)
        chapters = self.project_service.list_chapters(project_id)
        self.set_project_paused(project_id, False)
        self._set_project_status(project_id, "processing")
        self._set_project_stage(project_id, "summary")
        results, paused = self._run_chapter_batch(
            chapters,
            lambda chapter: self.summarize_chapter(chapter.id, resolved_model.id, resolved_template.id),
            concurrency,
            should_pause,
        )
        failed = len(chapters) - len(results)
        if paused:
            self.set_project_paused(project_id, True)
            return PipelineResult(processed=len(results), skipped=0, failed=failed, paused=True)
        self._set_project_stage(project_id, "review")
        self._set_project_status(project_id, "summarized" if failed == 0 else "partial")
        return PipelineResult(processed=len(results), skipped=0, failed=failed)

    def run_summary_project(
        self,
        project_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
        should_pause: Callable[[], bool] | None = None,
    ) -> PipelineResult:
        """Compatibility alias for the retired extract-project entry point."""
        return self.run_document_analysis(
            project_id,
            model_id=model_id,
            template_id=template_id,
            should_pause=should_pause,
        )

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
        if stage == "plot_expansion":
            return self.expand_chapter_plot(chapter_id, True, model_id, template_id)
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

    def preview_chapter_prompt(self, chapter_id: int, stage: str) -> dict[str, Any]:
        chapter = self.project_service.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError(f"Chapter not found: {chapter_id}")
        template = self._resolve_template(None, chapter.project_id)
        if stage == "summary":
            compiled = self._summary_request(chapter, template)
        elif stage == "scene_detection":
            compiled = self._scene_request(chapter, template)
        elif stage == "plot_expansion":
            compiled = self._plot_expansion_request(chapter, template)
        elif stage == "rewrite":
            compiled = self._rewrite_request(chapter, template)
        else:
            raise ValueError(f"Unsupported prompt preview stage: {stage}")
        return compiled.snapshot()

    def list_generation_attempts(self, chapter_id: int, stage: str | None = None) -> list[dict[str, Any]]:
        where = "chapter_id = ?" if stage is None else "chapter_id = ? AND stage = ?"
        params: tuple[Any, ...] = (chapter_id,) if stage is None else (chapter_id, stage)
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT id, stage, attempt_number, request_json, response_text, parsed_json,
                       error_type, error_message, model_id, prompt_template_id,
                       token_usage_json, elapsed_ms, created_at
                FROM generation_attempts
                WHERE {where}
                ORDER BY id
                """,
                params,
            ).fetchall()
        return [
            {
                "id": row["id"],
                "stage": row["stage"],
                "attempt_number": row["attempt_number"],
                "request": _parse_json_object(row["request_json"]),
                "response_text": row["response_text"],
                "parsed": _parse_json_object(row["parsed_json"]),
                "error_type": row["error_type"],
                "error_message": row["error_message"],
                "model_id": row["model_id"],
                "prompt_template_id": row["prompt_template_id"],
                "token_usage": _parse_json_object(row["token_usage_json"]),
                "elapsed_ms": row["elapsed_ms"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_chapter_ai_outputs(self, chapter_id: int) -> ChapterAIOutputs:
        with session(self.database_path) as connection:
            summary = connection.execute(
                """
                SELECT plot_summary, characters_json
                FROM chapter_summaries
                WHERE chapter_id = ?
                """,
                (chapter_id,),
            ).fetchone()
            scene = connection.execute(
                """
                SELECT needs_rewrite, scene_labels_json, reasoning, context_markers_json
                FROM chapter_scene_analysis
                WHERE chapter_id = ?
                """,
                (chapter_id,),
            ).fetchone()
            plot_expansion = connection.execute(
                """
                SELECT enabled, expanded_plot
                FROM chapter_plot_expansions
                WHERE chapter_id = ?
                """,
                (chapter_id,),
            ).fetchone()
            rewrite = connection.execute(
                """
                SELECT rewrite_source, actual_word_count, expansion_ratio, elapsed_ms,
                       rewrite_mode, anchor_text, expanded_text
                FROM chapter_rewrites
                WHERE chapter_id = ?
                """,
                (chapter_id,),
            ).fetchone()
            style_analysis = connection.execute(
                """
                SELECT analysis_json, reviewed_json, status
                FROM chapter_style_analyses WHERE chapter_id = ?
                """,
                (chapter_id,),
            ).fetchone()

        scene_labels = _parse_json_list(scene["scene_labels_json"]) if scene is not None else None
        return ChapterAIOutputs(
            plot_summary=summary["plot_summary"] if summary is not None else None,
            plot_characters=_parse_json_dict_list(summary["characters_json"]) if summary is not None else None,
            needs_rewrite=bool(scene["needs_rewrite"]) if scene is not None else None,
            scene_labels=scene_labels,
            scene_reasoning=scene["reasoning"] if scene is not None else None,
            scene_markers=_parse_json_dict_list(scene["context_markers_json"]) if scene is not None else None,
            plot_expansion_enabled=bool(plot_expansion["enabled"]) if plot_expansion is not None else None,
            expanded_plot=plot_expansion["expanded_plot"] if plot_expansion is not None else None,
            rewrite_source=rewrite["rewrite_source"] if rewrite is not None else None,
            rewritten_word_count=rewrite["actual_word_count"] if rewrite is not None else None,
            expansion_ratio=rewrite["expansion_ratio"] if rewrite is not None else None,
            rewrite_elapsed_ms=rewrite["elapsed_ms"] if rewrite is not None else None,
            rewrite_mode=rewrite["rewrite_mode"] if rewrite is not None else None,
            rewrite_anchor=rewrite["anchor_text"] if rewrite is not None else None,
            rewrite_expanded=rewrite["expanded_text"] if rewrite is not None else None,
            style_analysis=_parse_json_object(style_analysis["analysis_json"]) if style_analysis is not None else None,
            reviewed_style_analysis=_parse_json_object(style_analysis["reviewed_json"]) if style_analysis is not None else None,
            style_analysis_status=style_analysis["status"] if style_analysis is not None else None,
        )

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
        self._mark_stage(chapter_id, stage, "running")
        try:
            model = self._resolve_model(model_id, chapter.project_id)
            template = self._resolve_template(template_id, chapter.project_id)
            api_key = self.model_service.get_api_key(model.id)
            compiled = message_builder(chapter, template)
            if not isinstance(compiled, CompiledRequest):
                raise TypeError(f"Prompt builder for {stage} did not return CompiledRequest")
            attempt_number = self._next_attempt_number(chapter.id, stage)
            try:
                response = self.ai_client.chat(model, api_key, compiled.message_list())
            except Exception as exc:
                self._record_generation_attempt(
                    chapter.id,
                    stage,
                    attempt_number,
                    compiled,
                    model,
                    template,
                    error=exc,
                )
                raise
            self._record_generation_attempt(
                chapter.id,
                stage,
                attempt_number,
                compiled,
                model,
                template,
                response=response,
                parsed=_parse_stage_response(stage, response.text),
            )
            saver(chapter, model, template, response, compiled)
            self._mark_stage(chapter_id, stage, "completed", response.elapsed_ms, response.token_usage)
            if stage == "summary":
                self.project_service.refresh_project_progress(chapter.project_id)
            self._resolve_stage_errors(chapter_id, stage)
            return response.text
        except Exception as exc:
            self._mark_stage(chapter_id, stage, "failed")
            self._record_error(chapter_id, stage, exc)
            raise

    def _run_rewrite_stage(
        self,
        chapter_id: int,
        model_id: int | None,
        template_id: int | None,
    ) -> str:
        chapter = self.project_service.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError(f"Chapter not found: {chapter_id}")
        self._mark_stage(chapter_id, "rewrite", "running")
        try:
            model = self._resolve_model(model_id, chapter.project_id)
            template = self._resolve_template(template_id, chapter.project_id)
            settings = self.project_service.get_project_settings(chapter.project_id)
            rewrite_mode = settings.rewrite_mode if settings else "anchor_expand"
            max_attempts = settings.max_attempts if settings else 2
            api_key = self.model_service.get_api_key(model.id)
            compiled = self._rewrite_request(chapter, template, rewrite_mode=rewrite_mode)
            last_error: Exception | None = None

            for _ in range(max_attempts):
                attempt_number = self._next_attempt_number(chapter.id, "rewrite")
                try:
                    response = self.ai_client.chat(model, api_key, compiled.message_list())
                except Exception as exc:
                    last_error = exc
                    self._record_generation_attempt(
                        chapter.id,
                        "rewrite",
                        attempt_number,
                        compiled,
                        model,
                        template,
                        error=exc,
                    )
                    continue

                try:
                    applied = _apply_rewrite_response(chapter.original_text, response.text, rewrite_mode)
                    self._validate_rewrite_targets(chapter, applied["rewritten_text"])
                except RewriteOutputError as exc:
                    last_error = exc
                    self._record_generation_attempt(
                        chapter.id,
                        "rewrite",
                        attempt_number,
                        compiled,
                        model,
                        template,
                        response=response,
                        parsed=exc.parsed,
                        error=exc,
                    )
                    compiled = compiled.repair(response.text, exc.code, str(exc))
                    continue

                self._record_generation_attempt(
                    chapter.id,
                    "rewrite",
                    attempt_number,
                    compiled,
                    model,
                    template,
                    response=response,
                    parsed=applied,
                )
                self._save_rewrite(
                    chapter,
                    model,
                    template,
                    response,
                    rewritten_text=applied["rewritten_text"],
                    rewrite_mode=rewrite_mode,
                    anchor=applied["anchor"],
                    expanded=applied["expanded"],
                    prompt_snapshot=compiled.snapshot(),
                )
                self._mark_stage(chapter.id, "rewrite", "completed", response.elapsed_ms, response.token_usage)
                self._resolve_stage_errors(chapter.id, "rewrite")
                return applied["rewritten_text"]

            if last_error is None:
                last_error = RewriteOutputError("rewrite_failed", "Rewrite failed without a response.")
            raise last_error
        except Exception as exc:
            self._mark_stage(chapter.id, "rewrite", "failed")
            self._record_error(chapter.id, "rewrite", exc)
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
        return self._apply_project_prompt_overrides(project_id, template)

    def _apply_project_prompt_overrides(self, project_id: int, template: PromptTemplate) -> PromptTemplate:
        prompts = self.prompt_service.list_project_prompts(project_id)
        if not prompts:
            return template

        global_rules = _append_prompt(
            template.global_rules,
            prompts.get("global_rules") or prompts.get("global") or prompts.get("global_override"),
        )
        summary_rules = _append_prompt(
            template.summary_rules,
            prompts.get("summary_rules") or prompts.get("summary") or prompts.get("summary_override"),
        )
        rewrite_rules = _append_prompt(
            template.rewrite_rules,
            prompts.get("rewrite_rules") or prompts.get("rewrite") or prompts.get("rewrite_override"),
        )
        return replace(
            template,
            global_rules=global_rules,
            summary_rules=summary_rules,
            rewrite_rules=rewrite_rules,
        )

    def _summary_request(self, chapter: ChapterRecord, template: PromptTemplate) -> CompiledRequest:
        return self.prompt_compiler.compile_summary(chapter, template)

    def _summary_messages(self, chapter: ChapterRecord, template: PromptTemplate) -> list[dict[str, str]]:
        return self._summary_request(chapter, template).message_list()

    def _scene_request(self, chapter: ChapterRecord, template: PromptTemplate) -> CompiledRequest:
        return self.prompt_compiler.compile_scene_detection(chapter, template)

    def _scene_messages(self, chapter: ChapterRecord, template: PromptTemplate) -> list[dict[str, str]]:
        return self._scene_request(chapter, template).message_list()

    def _plot_expansion_request(self, chapter: ChapterRecord, template: PromptTemplate) -> CompiledRequest:
        with session(self.database_path) as connection:
            scene = connection.execute(
                "SELECT scene_labels_json, reasoning FROM chapter_scene_analysis WHERE chapter_id = ?",
                (chapter.id,),
            ).fetchone()
            summary = connection.execute(
                "SELECT plot_summary, characters_json FROM chapter_summaries WHERE chapter_id = ?",
                (chapter.id,),
            ).fetchone()
        labels = _parse_json_list(scene["scene_labels_json"]) if scene is not None else []
        reasoning = scene["reasoning"] if scene is not None else ""
        return self.prompt_compiler.compile_plot_expansion(
            chapter,
            template,
            plot_summary=summary["plot_summary"] if summary is not None else "",
            characters_json=summary["characters_json"] if summary is not None else "[]",
            labels=labels,
            reasoning=reasoning,
        )

    def _plot_expansion_messages(self, chapter: ChapterRecord, template: PromptTemplate) -> list[dict[str, str]]:
        return self._plot_expansion_request(chapter, template).message_list()

    def _rewrite_request(
        self,
        chapter: ChapterRecord,
        template: PromptTemplate,
        *,
        rewrite_mode: str | None = None,
    ) -> CompiledRequest:
        settings = self.project_service.get_project_settings(chapter.project_id)
        style_template = self.style_service.get_project_style_template(chapter.project_id)
        outline_template = self.anchor_service.get_project_outline_template(chapter.project_id)
        character_cards = self.anchor_service.list_relevant_project_character_cards(
            chapter.project_id,
            chapter.original_text,
        )
        target_text = ""
        if settings and settings.target_word_count:
            target_text = f"\nTarget length: at least {settings.target_word_count} non-whitespace characters."
        if settings and settings.min_expansion_ratio:
            target_text += f"\nMinimum expansion ratio: {settings.min_expansion_ratio:.2f}x the original chapter length."
        style_text = self._style_rewrite_prompt(style_template)
        style_section = f"\n\nStyle template ({style_template.name}):\n{style_text}" if style_template and style_text else ""
        outline_section = self._outline_section(outline_template)
        character_section = self._character_cards_section(character_cards)
        package_sections = self._prompt_package_rewrite_sections(chapter, template)
        marker_section = self._scene_marker_section(chapter.id)
        return self.prompt_compiler.compile_rewrite(
            chapter,
            template,
            rewrite_mode=rewrite_mode or (settings.rewrite_mode if settings else "anchor_expand"),
            target_text=target_text,
            package_sections=package_sections,
            style_system_rules=style_template.global_prompt if style_template else "",
            style_section=style_section,
            outline_section=outline_section,
            character_section=character_section,
            marker_section=marker_section,
        )

    def _rewrite_messages(self, chapter: ChapterRecord, template: PromptTemplate) -> list[dict[str, str]]:
        return self._rewrite_request(chapter, template).message_list()

    def _scene_marker_section(self, chapter_id: int) -> str:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT context_markers_json FROM chapter_scene_analysis WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()
        markers = _parse_json_dict_list(row["context_markers_json"]) if row is not None else []
        if not markers:
            return ""
        return "\n\n## IDENTIFIED TARGET MARKERS\n" + json.dumps(markers, ensure_ascii=False, indent=2)

    def _prompt_package_rewrite_sections(self, chapter: ChapterRecord, template: PromptTemplate) -> str:
        with session(self.database_path) as connection:
            scene = connection.execute(
                "SELECT scene_labels_json FROM chapter_scene_analysis WHERE chapter_id = ?",
                (chapter.id,),
            ).fetchone()
            expansion = connection.execute(
                "SELECT enabled, expanded_plot FROM chapter_plot_expansions WHERE chapter_id = ?",
                (chapter.id,),
            ).fetchone()
            summary = connection.execute(
                "SELECT plot_summary, characters_json FROM chapter_summaries WHERE chapter_id = ?",
                (chapter.id,),
            ).fetchone()
        labels = set(_parse_json_list(scene["scene_labels_json"]) if scene is not None else [])
        specific_rules = [
            f"[{rule.display_name}]\n{rule.rewrite_prompt.strip()}"
            for rule in template.scene_rules
            if rule.scene_key in labels and rule.rewrite_prompt.strip()
        ]
        sections: list[str] = []
        if specific_rules:
            sections.append("场景具体改写规则：\n" + "\n\n".join(specific_rules))
        if summary is not None and summary["plot_summary"].strip():
            sections.append("本章原始剧情骨架：\n" + summary["plot_summary"].strip())
        chapter_characters = _parse_json_dict_list(summary["characters_json"]) if summary is not None else []
        if chapter_characters:
            sections.append("本章人物卡：\n" + json.dumps(chapter_characters, ensure_ascii=False, indent=2))
        if expansion is not None and bool(expansion["enabled"]) and expansion["expanded_plot"].strip():
            sections.append("本章剧情扩展方案：\n" + expansion["expanded_plot"].strip())
        return "\n\n" + "\n\n".join(sections) if sections else ""

    def _save_summary(
        self,
        chapter: ChapterRecord,
        model: ModelConfig,
        template: PromptTemplate,
        response: AIResponse,
        compiled: CompiledRequest,
    ) -> None:
        parsed = _parse_summary_response(response.text)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_summaries (
                    chapter_id,
                    plot_summary, characters_json, key_events_json,
                    model_id,
                    prompt_template_id,
                    token_usage_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id)
                DO UPDATE SET
                    plot_summary = excluded.plot_summary,
                    characters_json = excluded.characters_json,
                    key_events_json = excluded.key_events_json,
                    model_id = excluded.model_id,
                    prompt_template_id = excluded.prompt_template_id,
                    token_usage_json = excluded.token_usage_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    chapter.id,
                    parsed["plot_skeleton"],
                    json.dumps(parsed["characters"], ensure_ascii=False),
                    json.dumps(parsed["key_events"], ensure_ascii=False),
                    model.id,
                    template.id,
                    json.dumps(response.token_usage),
                ),
            )

    def _save_scene_analysis(
        self,
        chapter: ChapterRecord,
        model: ModelConfig,
        template: PromptTemplate,
        response: AIResponse,
        compiled: CompiledRequest,
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
                    context_markers_json,
                    model_id,
                    prompt_template_id,
                    token_usage_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id)
                DO UPDATE SET
                    needs_rewrite = excluded.needs_rewrite,
                    scene_labels_json = excluded.scene_labels_json,
                    reasoning = excluded.reasoning,
                    context_markers_json = excluded.context_markers_json,
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
                    json.dumps(parsed["markers"], ensure_ascii=False),
                    model.id,
                    template.id,
                    json.dumps(response.token_usage),
                ),
            )
            connection.execute(
                "UPDATE chapters SET needs_rewrite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (1 if parsed["needs_rewrite"] else 0, chapter.id),
            )

    def _save_plot_expansion(
        self,
        chapter: ChapterRecord,
        model: ModelConfig,
        template: PromptTemplate,
        response: AIResponse,
        compiled: CompiledRequest,
    ) -> None:
        prompt_snapshot = compiled.snapshot()
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_plot_expansions (
                    chapter_id, enabled, expanded_plot, model_id, prompt_template_id,
                    prompt_snapshot_json, token_usage_json, elapsed_ms, updated_at
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id)
                DO UPDATE SET enabled = 1, expanded_plot = excluded.expanded_plot,
                    model_id = excluded.model_id, prompt_template_id = excluded.prompt_template_id,
                    prompt_snapshot_json = excluded.prompt_snapshot_json,
                    token_usage_json = excluded.token_usage_json, elapsed_ms = excluded.elapsed_ms,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    chapter.id,
                    response.text,
                    model.id,
                    template.id,
                    json.dumps(prompt_snapshot, ensure_ascii=False),
                    json.dumps(response.token_usage),
                    response.elapsed_ms,
                ),
            )

    def _save_rewrite(
        self,
        chapter: ChapterRecord,
        model: ModelConfig,
        template: PromptTemplate,
        response: AIResponse,
        *,
        rewritten_text: str,
        rewrite_mode: str,
        anchor: str,
        expanded: str,
        prompt_snapshot: dict[str, Any],
    ) -> None:
        settings = self.project_service.get_project_settings(chapter.project_id)
        target_word_count = settings.target_word_count if settings else None
        with session(self.database_path) as connection:
            anchor_snapshot = self._anchor_snapshot_for_chapter(chapter)
            self.chapter_versions.append_pipeline_rewrite_version(
                connection,
                chapter_id=chapter.id,
                rewritten_text=rewritten_text,
                target_word_count=target_word_count,
                model_id=model.id,
                prompt_template_id=template.id,
                prompt_snapshot=prompt_snapshot,
                anchor_snapshot=anchor_snapshot,
                rewrite_mode=rewrite_mode,
                anchor_text=anchor,
                expanded_text=expanded,
                token_usage=response.token_usage,
                elapsed_ms=response.elapsed_ms,
            )
        self.project_service.refresh_project_progress(chapter.project_id)

    def _validate_rewrite_targets(self, chapter: ChapterRecord, rewritten_text: str) -> None:
        settings = self.project_service.get_project_settings(chapter.project_id)
        target_word_count = settings.target_word_count if settings else None
        min_expansion_ratio = settings.min_expansion_ratio if settings else None
        word_count = count_text_units(rewritten_text)
        ratio = word_count / chapter.word_count if chapter.word_count else None
        if target_word_count is not None and word_count < target_word_count:
            raise RewriteOutputError(
                "rewrite_too_short",
                f"Rewrite is shorter than target length: {word_count} < {target_word_count}",
            )
        if min_expansion_ratio is not None and ratio is not None and ratio < min_expansion_ratio:
            raise RewriteOutputError(
                "expansion_ratio_too_low",
                f"Rewrite expansion ratio is below minimum: {ratio:.2f} < {min_expansion_ratio:.2f}",
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

    def _next_attempt_number(self, chapter_id: int, stage: str) -> int:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM generation_attempts WHERE chapter_id = ? AND stage = ?",
                (chapter_id, stage),
            ).fetchone()
        return int(row[0])

    def _record_generation_attempt(
        self,
        chapter_id: int,
        stage: str,
        attempt_number: int,
        compiled: CompiledRequest,
        model: ModelConfig,
        template: PromptTemplate,
        *,
        response: AIResponse | None = None,
        parsed: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        error_type = _classify_generation_error(error) if error is not None else None
        request_snapshot = compiled.snapshot()
        request_snapshot["model"] = {
            "id": model.id,
            "display_name": model.display_name,
            "provider": model.provider,
            "base_url": model.base_url,
            "model_name": model.model_name,
            "temperature": model.temperature,
            "max_tokens": model.max_tokens,
            "timeout_seconds": model.timeout_seconds,
        }
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO generation_attempts (
                    chapter_id, stage, attempt_number, request_json, response_text,
                    parsed_json, error_type, error_message, model_id, prompt_template_id,
                    token_usage_json, elapsed_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    stage,
                    attempt_number,
                    json.dumps(request_snapshot, ensure_ascii=False),
                    response.text if response is not None else "",
                    json.dumps(parsed or {}, ensure_ascii=False),
                    error_type,
                    str(error) if error is not None else None,
                    model.id,
                    template.id,
                    json.dumps(response.token_usage if response is not None else {}, ensure_ascii=False),
                    response.elapsed_ms if response is not None else None,
                ),
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

    def _run_chapter_batch(
        self,
        chapters: list[ChapterRecord],
        worker: Callable[[ChapterRecord], str],
        concurrency: int,
        should_pause: Callable[[], bool] | None,
    ) -> tuple[dict[int, str], bool]:
        results: dict[int, str] = {}
        if not chapters:
            return results, False
        if should_pause and should_pause():
            return results, True
        if self.is_project_paused(chapters[0].project_id):
            return results, True

        if concurrency <= 1:
            for chapter in chapters:
                if should_pause and should_pause():
                    return results, True
                if self.is_project_paused(chapter.project_id):
                    return results, True
                try:
                    results[chapter.id] = worker(chapter)
                except Exception:
                    continue
            return results, False

        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="rusty-stage") as executor:
            futures = {executor.submit(worker, chapter): chapter for chapter in chapters}
            for future in as_completed(futures):
                chapter = futures[future]
                try:
                    results[chapter.id] = future.result()
                except Exception:
                    continue
        return results, False

    def _set_project_stage(self, project_id: int, stage: str) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE projects SET current_stage = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (stage, project_id),
            )

    def _set_project_status(self, project_id: int, status: str) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, project_id),
            )

    def _mark_chapter_kept_original(self, chapter_id: int) -> None:
        chapter = self.project_service.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError(f"Chapter not found: {chapter_id}")
        # This legacy pipeline outcome selects the immutable original for export; it
        # does not create formal rewritten content, so the compatibility projection
        # intentionally remains NULL.
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE chapters
                SET status = 'kept_original', rewritten_text = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (chapter_id,),
            )
        self.project_service.refresh_project_progress(chapter.project_id)

    @staticmethod
    def _scene_needs_rewrite(scene_text: str) -> bool:
        return bool(_parse_scene_response(scene_text)["needs_rewrite"])

    @staticmethod
    def _style_rewrite_prompt(style_template: StyleTemplate | None) -> str:
        if style_template is None:
            return ""
        return (style_template.generated_prompt or style_template.rewrite_prompt).strip()

    def _style_snapshot_for_project(self, project_id: int) -> dict:
        style_template = self.style_service.get_project_style_template(project_id)
        if style_template is None:
            return {"style_template": None}
        return {
            "style_template": {
                "id": style_template.id,
                "name": style_template.name,
                "version": style_template.version,
                "detail_level": style_template.detail_level,
                "style_profile_json": style_template.style_profile_json,
            }
        }

    @staticmethod
    def _outline_section(outline_template: OutlineTemplate | None) -> str:
        if outline_template is None:
            return ""
        parts = [outline_template.anchor_prompt.strip()]
        outline_text = outline_template.outline_json.strip()
        if outline_text and outline_text != "{}":
            parts.append(f"Structured outline JSON:\n{outline_text}")
        text = "\n\n".join(part for part in parts if part)
        return f"\n\nPlot outline anchor ({outline_template.name}):\n{text}" if text else ""

    @staticmethod
    def _character_cards_section(character_cards: list[CharacterCard]) -> str:
        if not character_cards:
            return ""
        sections = []
        for card in character_cards:
            details = [
                f"Name: {card.name}",
                f"Aliases: {', '.join(card.aliases)}" if card.aliases else "",
                f"Priority: {card.priority}",
                f"Main character: {'yes' if card.is_main else 'no'}",
                f"Description: {card.description}" if card.description else "",
                f"Relationships: {card.relationship_notes}" if card.relationship_notes else "",
                f"Personality: {card.personality}" if card.personality else "",
                f"Speech style: {card.speech_style}" if card.speech_style else "",
                f"Action constraints: {card.action_constraints}" if card.action_constraints else "",
                f"Anti-OOC rules: {card.anti_ooc_rules}" if card.anti_ooc_rules else "",
                f"Structured profile JSON:\n{card.profile_json}" if card.profile_json and card.profile_json != "{}" else "",
            ]
            sections.append("\n".join(item for item in details if item))
        return "\n\nCharacter anchors:\n" + "\n\n".join(sections)

    def _anchor_snapshot_for_chapter(self, chapter: ChapterRecord) -> dict:
        snapshot = self._style_snapshot_for_project(chapter.project_id)
        outline_template = self.anchor_service.get_project_outline_template(chapter.project_id)
        character_cards = self.anchor_service.list_relevant_project_character_cards(
            chapter.project_id,
            chapter.original_text,
        )
        snapshot["outline_template"] = (
            {
                "id": outline_template.id,
                "name": outline_template.name,
                "version": outline_template.version,
                "detail_level": outline_template.detail_level,
                "outline_json": outline_template.outline_json,
                "anchor_prompt": outline_template.anchor_prompt,
            }
            if outline_template is not None
            else None
        )
        snapshot["character_cards"] = [
            {
                "id": card.id,
                "name": card.name,
                "aliases_json": card.aliases_json,
                "version": card.version,
                "priority": card.priority,
                "is_main": card.is_main,
                "relationship_notes": card.relationship_notes,
                "personality": card.personality,
                "speech_style": card.speech_style,
                "action_constraints": card.action_constraints,
                "anti_ooc_rules": card.anti_ooc_rules,
                "profile_json": card.profile_json,
            }
            for card in character_cards
        ]
        return snapshot


def _parse_scene_response(text: str) -> dict:
    try:
        data = json.loads(_strip_json_fence(text))
    except json.JSONDecodeError:
        return {
            "needs_rewrite": True,
            "labels": ["unspecified"],
            "reasoning": text,
            "markers": [{"category_id": "unspecified", "expand_description": text}],
        }
    if not isinstance(data, dict):
        data = {}
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else data
    labels = analysis.get("categories") or analysis.get("labels") or analysis.get("scene_labels") or []
    if isinstance(labels, str):
        labels = [labels]
    raw_markers = analysis.get("markers") if isinstance(analysis.get("markers"), list) else []
    markers = []
    for item in raw_markers:
        if not isinstance(item, dict):
            continue
        category_id = item.get("category_id") or item.get("categoryId") or item.get("scene_key") or "unspecified"
        markers.append(
            {
                "category_id": str(category_id),
                "category_name": str(item.get("category_name") or item.get("categoryName") or ""),
                "expand_description": str(
                    item.get("expand_description") or item.get("expandDescription") or item.get("description") or ""
                ),
                "evidence": str(item.get("evidence") or item.get("excerpt") or ""),
            }
        )
    reasoning = str(analysis.get("reasoning", ""))
    if not markers and labels:
        markers = [
            {
                "category_id": str(label),
                "category_name": "",
                "expand_description": reasoning,
                "evidence": "",
            }
            for label in labels
        ]
    return {
        "needs_rewrite": bool(
            analysis.get("has_target_content", analysis.get("hasTargetContent", analysis.get("needs_rewrite")))
        ),
        "labels": [str(label) for label in labels],
        "reasoning": reasoning,
        "markers": markers,
    }


class RewriteOutputError(ValueError):
    def __init__(self, code: str, message: str, parsed: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.parsed = parsed or {}


def _apply_rewrite_response(original_text: str, response_text: str, rewrite_mode: str) -> dict[str, str]:
    stripped = response_text.strip()
    if not stripped:
        raise RewriteOutputError("empty_response", "The model returned an empty rewrite.")
    if _looks_like_refusal(stripped):
        raise RewriteOutputError("refusal_detected", "The model response appears to be a refusal.")
    if rewrite_mode == "full_rewrite":
        return {"rewritten_text": stripped, "anchor": original_text, "expanded": stripped}

    try:
        parsed = json.loads(_strip_json_fence(stripped))
    except json.JSONDecodeError as exc:
        raise RewriteOutputError("invalid_json", f"Rewrite response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RewriteOutputError("invalid_json_shape", "Rewrite response must be a JSON object.")
    payload = parsed.get("rewrite") if isinstance(parsed.get("rewrite"), dict) else parsed
    anchor = payload.get("anchor")
    expanded = payload.get("expanded")
    if not isinstance(anchor, str) or not anchor:
        raise RewriteOutputError("empty_anchor", "Rewrite anchor must be a non-empty string.", parsed)
    if not isinstance(expanded, str) or not expanded.strip():
        raise RewriteOutputError("empty_expanded", "Expanded replacement must be a non-empty string.", parsed)
    occurrences = original_text.count(anchor)
    if occurrences == 0:
        raise RewriteOutputError("anchor_missing", "Rewrite anchor was not found in the original chapter.", parsed)
    if occurrences > 1:
        raise RewriteOutputError(
            "anchor_ambiguous",
            f"Rewrite anchor occurs {occurrences} times; it must be unique.",
            parsed,
        )
    return {
        "rewritten_text": original_text.replace(anchor, expanded, 1),
        "anchor": anchor,
        "expanded": expanded,
    }


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    return stripped


def _looks_like_refusal(text: str) -> bool:
    prefix = text.strip().lower()[:500]
    return any(
        prefix.startswith(phrase)
        for phrase in (
            "i can't assist",
            "i cannot assist",
            "i'm unable to",
            "i am unable to",
            "i'm sorry, but i can't",
            "i'm sorry, but i cannot",
            "我不能协助",
            "我无法协助",
            "抱歉，我不能",
            "很抱歉，我无法",
        )
    )


def _classify_generation_error(error: Exception | None) -> str | None:
    if error is None:
        return None
    if isinstance(error, RewriteOutputError):
        return error.code
    name = type(error).__name__.lower()
    message = str(error).lower()
    if "timeout" in name or "timeout" in message:
        return "timeout"
    if "http" in name or "status" in message:
        return "provider_error"
    return "execution_error"


def _parse_stage_response(stage: str, text: str) -> dict[str, Any]:
    if stage == "summary":
        return _parse_summary_response(text)
    if stage == "scene_detection":
        return _parse_scene_response(text)
    if stage == "plot_expansion":
        return {"expanded_plot": text.strip()}
    return {}


def _parse_summary_response(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return {"plot_skeleton": text.strip(), "key_events": [], "characters": []}
    if not isinstance(data, dict):
        return {"plot_skeleton": text.strip(), "key_events": [], "characters": []}
    skeleton = data.get("plot_skeleton") or data.get("plot_summary") or data.get("skeleton") or ""
    events = data.get("key_events") if isinstance(data.get("key_events"), list) else []
    characters = data.get("characters") if isinstance(data.get("characters"), list) else []
    return {
        "plot_skeleton": str(skeleton),
        "key_events": [item for item in events],
        "characters": [item for item in characters if isinstance(item, dict)],
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_json_dict_list(text: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _append_prompt(base: str, override: str | None) -> str:
    override_text = (override or "").strip()
    if not override_text:
        return base
    base_text = base.strip()
    if not base_text:
        return override_text
    return f"{base_text}\n\n{override_text}"


def _parse_json_list(text: str) -> list[str]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []
