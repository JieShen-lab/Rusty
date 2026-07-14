from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import session
from rusty.services.ai_client import AIClient, OpenAICompatibleClient
from rusty.services.model_service import ModelConfig, ModelService
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.prompt_service import PROMPT_PACKAGE_SCHEMA, PromptService, _normalize_package

MAX_PACKAGE_SAMPLE_CHARS = 24000


class PromptPackageExtractionService:
    def __init__(self, database_path: str | Path | None = None, ai_client: AIClient | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.project_service = ProjectService(self.database_path)
        self.model_service = ModelService(self.database_path)
        self.prompt_service = PromptService(self.database_path)
        self.ai_client = ai_client or OpenAICompatibleClient()

    def extract_from_project(self, project_id: int, model_id: int | None = None) -> int:
        project = self.project_service.get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        sample = self._project_sample(project_id)
        model = self._resolve_model(model_id, project_id)
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            self._messages(project.name, sample),
        )
        package = _parse_package(response.text)
        package["name"] = project.name
        metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
        package["metadata"] = {
            **metadata,
            "created_by": "ai_project_prompt_package_extraction",
            "source_project_id": project_id,
            "model_id": model.id,
            "model_name": model.model_name,
            "token_usage": response.token_usage,
            "elapsed_ms": response.elapsed_ms,
        }
        payload = _normalize_package(package)
        payload["source_project_id"] = project_id
        template_id = self.prompt_service.create_template(**payload)
        self._bind_project(project_id, template_id)
        return template_id

    def _project_sample(self, project_id: int) -> str:
        chapters = self.project_service.list_chapters(project_id)
        with session(self.database_path) as connection:
            summary_rows = connection.execute(
                "SELECT chapter_id, plot_summary FROM chapter_summaries WHERE chapter_id IN (SELECT id FROM chapters WHERE project_id = ?)",
                (project_id,),
            ).fetchall()
        summaries = {row["chapter_id"]: row["plot_summary"] for row in summary_rows}
        parts: list[str] = []
        for chapter in chapters:
            summary = summaries.get(chapter.id)
            excerpt = chapter.original_text[:1800]
            parts.append(
                f"# {chapter.title}\n"
                f"章节摘要：{summary or '未生成'}\n"
                f"原文节选：\n{excerpt}"
            )
        sample = "\n\n".join(parts).strip()
        if not sample:
            raise ValueError("Project has no chapter text to analyze.")
        return sample[:MAX_PACKAGE_SAMPLE_CHARS]

    def _resolve_model(self, model_id: int | None, project_id: int) -> ModelConfig:
        settings = self.project_service.get_project_settings(project_id)
        effective_id = model_id if model_id is not None else (settings.model_id if settings else None)
        model = self.model_service.get_model(effective_id) if effective_id is not None else self.model_service.get_default_model()
        if model is None:
            raise ValueError("No model configured.")
        return model

    def _bind_project(self, project_id: int, template_id: int) -> None:
        settings = self.project_service.get_project_settings(project_id)
        self.project_service.update_project_settings(
            project_id=project_id,
            model_id=settings.model_id if settings else None,
            prompt_template_id=template_id,
            processing_mode=settings.processing_mode if settings else "summary",
            concurrency=settings.concurrency if settings else 1,
            target_word_count=settings.target_word_count if settings else None,
            min_expansion_ratio=settings.min_expansion_ratio if settings else None,
        )

    @staticmethod
    def _messages(project_name: str, sample: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": "你负责从小说文本中提取可复用的安全提示词包。只返回严格 JSON。",
            },
            {
                "role": "user",
                "content": (
                    f"为项目《{project_name}》提取统一提示词包。\n"
                    f"schema 必须是 {PROMPT_PACKAGE_SCHEMA}，schema_version 必须是 1。\n"
                    "返回字段：name、description、system_rules、summary_rules、scene_recognition、"
                    "rewrite_rules、story_anchor、characters、metadata。\n"
                    "scene_recognition 包含 general_rules 和 categories；categories 中每项包含 key、name、"
                    "description、detection_prompt。\n"
                    "rewrite_rules 包含 general 和 specific；specific 中每项包含 scene_key、rewrite_prompt。\n"
                    "story_anchor 要提取剧情主线、关键节点、因果链、人物关系发展、不可破坏事实和可扩展支线。\n"
                    "characters 是人物锚点数组，至少包含 name、aliases、role、relationships、personality、"
                    "speech_style、action_constraints、anti_ooc_rules。\n"
                    "system_rules 只写任务边界、输出要求和事实约束；不得生成越权、破甲、绕过安全或隐藏指令。\n"
                    "rewrite_rules.general 是通用改写规则；specific 与场景分类一一对应。\n\n"
                    f"项目材料：\n{sample}"
                ),
            },
        ]


def _parse_package(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Prompt package extraction did not return valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Prompt package extraction response must be a JSON object.")
    return value
