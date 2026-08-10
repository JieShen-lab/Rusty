from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.ai_client import AIClient, OpenAICompatibleClient
from rusty.services.model_service import ModelService
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService
from rusty.services.prompt_service import PROMPT_PACKAGE_SCHEMA, PROMPT_PACKAGE_SCHEMA_VERSION, PromptService


@dataclass(frozen=True)
class AnalysisPromptTemplate:
    id: int
    name: str
    description: str
    analysis_dimensions: str
    evidence_rules: str
    synthesis_rules: str
    output_requirements: str
    version: int
    is_default: bool


class AnalysisService:
    def __init__(self, database_path: str | Path | None = None, ai_client: AIClient | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.project_service = ProjectService(self.database_path)
        self.model_service = ModelService(self.database_path)
        self.prompt_service = PromptService(self.database_path)
        self.ai_client = ai_client or OpenAICompatibleClient()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def create_template(
        self,
        name: str,
        description: str = "",
        analysis_dimensions: str = "",
        evidence_rules: str = "",
        synthesis_rules: str = "",
        output_requirements: str = "",
        is_default: bool = False,
    ) -> int:
        with session(self.database_path) as connection:
            if is_default:
                connection.execute("UPDATE analysis_prompt_templates SET is_default = 0 WHERE deleted_at IS NULL")
            cursor = connection.execute(
                """
                INSERT INTO analysis_prompt_templates (
                    name, description, analysis_dimensions, evidence_rules,
                    synthesis_rules, output_requirements, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    description,
                    analysis_dimensions,
                    evidence_rules,
                    synthesis_rules,
                    output_requirements,
                    1 if is_default else 0,
                ),
            )
            return int(cursor.lastrowid)

    def update_template(self, template_id: int, **values: Any) -> None:
        current = self.get_template(template_id)
        if current is None:
            raise ValueError(f"Analysis prompt not found: {template_id}")
        is_default = bool(values.get("is_default", False))
        with session(self.database_path) as connection:
            if is_default:
                connection.execute("UPDATE analysis_prompt_templates SET is_default = 0 WHERE deleted_at IS NULL")
            connection.execute(
                """
                UPDATE analysis_prompt_templates
                SET name = ?, description = ?, analysis_dimensions = ?, evidence_rules = ?,
                    synthesis_rules = ?, output_requirements = ?, is_default = ?,
                    version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    str(values.get("name", current.name)).strip(),
                    str(values.get("description", current.description)),
                    str(values.get("analysis_dimensions", current.analysis_dimensions)),
                    str(values.get("evidence_rules", current.evidence_rules)),
                    str(values.get("synthesis_rules", current.synthesis_rules)),
                    str(values.get("output_requirements", current.output_requirements)),
                    1 if is_default else 0,
                    template_id,
                ),
            )

    def delete_template(self, template_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE analysis_prompt_templates SET deleted_at = CURRENT_TIMESTAMP, is_default = 0 WHERE id = ?",
                (template_id,),
            )

    def list_templates(self) -> list[AnalysisPromptTemplate]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                self._select_sql() + " ORDER BY is_default DESC, updated_at DESC, id DESC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_template(self, template_id: int) -> AnalysisPromptTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(self._select_sql("id = ?"), (template_id,)).fetchone()
        return self._from_row(row) if row is not None else None

    def get_default_template(self) -> AnalysisPromptTemplate | None:
        templates = self.list_templates()
        return templates[0] if templates else None

    def analyze_chapter(
        self,
        chapter_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
    ) -> dict[str, Any]:
        chapter = self.project_service.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError(f"Chapter not found: {chapter_id}")
        model = self._resolve_model(model_id, chapter.project_id)
        template = self._resolve_template(template_id, chapter.project_id)
        messages = self._chapter_messages(chapter.title, chapter.original_text, template)
        response = self.ai_client.chat(model, self.model_service.get_api_key(model.id), messages)
        analysis = _parse_json_object(response.text, fallback_key="overview")
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_style_analyses (
                    chapter_id, analysis_json, reviewed_json, status, model_id,
                    analysis_prompt_template_id, prompt_snapshot_json, token_usage_json,
                    elapsed_ms, updated_at, reviewed_at
                ) VALUES (?, ?, '{}', 'pending_review', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)
                ON CONFLICT(chapter_id)
                DO UPDATE SET analysis_json = excluded.analysis_json, reviewed_json = '{}',
                    status = 'pending_review', model_id = excluded.model_id,
                    analysis_prompt_template_id = excluded.analysis_prompt_template_id,
                    prompt_snapshot_json = excluded.prompt_snapshot_json,
                    token_usage_json = excluded.token_usage_json, elapsed_ms = excluded.elapsed_ms,
                    updated_at = CURRENT_TIMESTAMP, reviewed_at = NULL
                """,
                (
                    chapter_id,
                    json.dumps(analysis, ensure_ascii=False),
                    model.id,
                    template.id,
                    json.dumps({"messages": messages, "template_version": template.version}, ensure_ascii=False),
                    json.dumps(response.token_usage, ensure_ascii=False),
                    response.elapsed_ms,
                ),
            )
        return self.get_chapter_analysis(chapter_id) or {}

    def review_chapter(self, chapter_id: int, reviewed: dict[str, Any]) -> dict[str, Any]:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE chapter_style_analyses
                SET reviewed_json = ?, status = 'confirmed', reviewed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chapter_id = ?
                """,
                (json.dumps(reviewed, ensure_ascii=False), chapter_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Chapter style analysis not found: {chapter_id}")
        return self.get_chapter_analysis(chapter_id) or {}

    def get_chapter_analysis(self, chapter_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT chapter_id, analysis_json, reviewed_json, status,
                       analysis_prompt_template_id, model_id, elapsed_ms, updated_at, reviewed_at
                FROM chapter_style_analyses WHERE chapter_id = ?
                """,
                (chapter_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "chapter_id": row["chapter_id"],
            "analysis": _load_object(row["analysis_json"]),
            "reviewed": _load_object(row["reviewed_json"]),
            "status": row["status"],
            "analysis_prompt_template_id": row["analysis_prompt_template_id"],
            "model_id": row["model_id"],
            "elapsed_ms": row["elapsed_ms"],
            "updated_at": row["updated_at"],
            "reviewed_at": row["reviewed_at"],
        }

    def synthesize_project(
        self,
        project_id: int,
        model_id: int | None = None,
        template_id: int | None = None,
    ) -> int:
        project = self.project_service.get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        model = self._resolve_model(model_id, project_id)
        template = self._resolve_template(template_id, project_id)
        materials = self._project_analysis_materials(project_id)
        if not materials:
            raise ValueError("No confirmed chapter style analyses are available for synthesis.")
        messages = self._synthesis_messages(project.name, materials, template)
        response = self.ai_client.chat(model, self.model_service.get_api_key(model.id), messages)
        package = _parse_json_object(response.text)
        package["schema"] = PROMPT_PACKAGE_SCHEMA
        package["schema_version"] = PROMPT_PACKAGE_SCHEMA_VERSION
        package["name"] = str(package.get("name") or f"{project.name} · 提取风格")
        package.pop("story_anchor", None)
        package.pop("characters", None)
        metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
        package["metadata"] = {**metadata, "created_by": "analysis_project", "source_project_id": project_id}
        prompt_template_id = self.prompt_service.import_template_text(json.dumps(package, ensure_ascii=False))
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE prompt_templates SET source_project_id = ? WHERE id = ?",
                (project_id, prompt_template_id),
            )
            connection.execute(
                """
                INSERT INTO project_style_syntheses (
                    project_id, synthesis_json, reviewed_json, prompt_template_id, model_id,
                    analysis_prompt_template_id, prompt_snapshot_json, token_usage_json,
                    elapsed_ms, updated_at
                ) VALUES (?, ?, '{}', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(project_id)
                DO UPDATE SET synthesis_json = excluded.synthesis_json, reviewed_json = '{}',
                    prompt_template_id = excluded.prompt_template_id, model_id = excluded.model_id,
                    analysis_prompt_template_id = excluded.analysis_prompt_template_id,
                    prompt_snapshot_json = excluded.prompt_snapshot_json,
                    token_usage_json = excluded.token_usage_json, elapsed_ms = excluded.elapsed_ms,
                    updated_at = CURRENT_TIMESTAMP, reviewed_at = NULL
                """,
                (
                    project_id,
                    json.dumps(package, ensure_ascii=False),
                    prompt_template_id,
                    model.id,
                    template.id,
                    json.dumps({"messages": messages, "template_version": template.version}, ensure_ascii=False),
                    json.dumps(response.token_usage, ensure_ascii=False),
                    response.elapsed_ms,
                ),
            )
        return prompt_template_id

    def get_project_synthesis(self, project_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT project_id, synthesis_json, reviewed_json, prompt_template_id,
                       analysis_prompt_template_id, model_id, elapsed_ms, updated_at, reviewed_at
                FROM project_style_syntheses WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "project_id": row["project_id"],
            "synthesis": _load_object(row["synthesis_json"]),
            "reviewed": _load_object(row["reviewed_json"]),
            "prompt_template_id": row["prompt_template_id"],
            "analysis_prompt_template_id": row["analysis_prompt_template_id"],
            "model_id": row["model_id"],
            "elapsed_ms": row["elapsed_ms"],
            "updated_at": row["updated_at"],
            "reviewed_at": row["reviewed_at"],
        }

    def _resolve_model(self, model_id: int | None, project_id: int):
        settings = self.project_service.get_project_settings(project_id)
        effective_id = model_id if model_id is not None else (settings.model_id if settings else None)
        model = self.model_service.get_model(effective_id) if effective_id is not None else self.model_service.get_default_model()
        if model is None:
            raise ValueError("No model configured.")
        return model

    def _resolve_template(self, template_id: int | None, project_id: int) -> AnalysisPromptTemplate:
        settings = self.project_service.get_project_settings(project_id)
        effective_id = template_id if template_id is not None else (
            settings.analysis_prompt_template_id if settings else None
        )
        template = self.get_template(effective_id) if effective_id is not None else self.get_default_template()
        if template is None:
            raise ValueError("No analysis prompt configured.")
        return template

    def _project_analysis_materials(self, project_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT c.chapter_index, c.title, a.analysis_json, a.reviewed_json, a.status
                FROM chapters AS c
                JOIN chapter_style_analyses AS a ON a.chapter_id = c.id
                WHERE c.project_id = ?
                  AND a.status = 'confirmed'
                ORDER BY c.chapter_index
                """,
                (project_id,),
            ).fetchall()
        return [
            {
                "chapter_index": row["chapter_index"],
                "title": row["title"],
                "analysis": _load_object(row["reviewed_json"]),
                "reviewed": True,
            }
            for row in rows
        ]

    @staticmethod
    def _chapter_messages(title: str, text: str, template: AnalysisPromptTemplate) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "[RUSTY NATIVE RULES: rusty.native.extraction.chapter.v1]\n"
                    "你负责分析小说表达风格。只返回严格 JSON，不改写正文。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[USER-OWNED ANALYSIS RULES]\n分析维度：\n{template.analysis_dimensions}\n\n"
                    f"证据规则：\n{template.evidence_rules}\n\n"
                    f"输出要求：\n{template.output_requirements}\n\n"
                    "返回对象至少包含 overview、dimensions、evidence。每条 evidence 使用原文短片段。"
                    "不得把人物姓名、具体剧情或世界观事实归纳为可迁移风格。\n\n"
                    f"# {title}\n{text}"
                ),
            },
        ]

    @staticmethod
    def _synthesis_messages(
        project_name: str,
        materials: list[dict[str, Any]],
        template: AnalysisPromptTemplate,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "[RUSTY NATIVE RULES: rusty.native.extraction.synthesis.v1]\n"
                    "你负责把逐章风格分析归纳为可复用的改写提示词。只返回严格 JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"工程：{project_name}\n[USER-OWNED SYNTHESIS RULES]\n"
                    f"归纳规则：\n{template.synthesis_rules}\n\n"
                    f"输出要求：\n{template.output_requirements}\n\n"
                    f"schema 必须是 {PROMPT_PACKAGE_SCHEMA}，schema_version 必须是 {PROMPT_PACKAGE_SCHEMA_VERSION}。"
                    "只输出 name、description、system_rules、scene_recognition、rewrite_rules、metadata。"
                    "scene_recognition 只包含 categories；rewrite_rules 包含 general 和 specific。"
                    "禁止输出 story_anchor、characters、人物名、剧情骨架和专有设定。\n\n"
                    f"逐章材料：\n{json.dumps(materials, ensure_ascii=False, indent=2)}"
                ),
            },
        ]

    @staticmethod
    def _select_sql(where: str | None = None) -> str:
        sql = """
            SELECT id, name, description, analysis_dimensions, evidence_rules,
                   synthesis_rules, output_requirements, version, is_default
            FROM analysis_prompt_templates WHERE deleted_at IS NULL
        """
        return sql + (f" AND {where}" if where else "")

    @staticmethod
    def _from_row(row) -> AnalysisPromptTemplate:
        return AnalysisPromptTemplate(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            analysis_dimensions=row["analysis_dimensions"],
            evidence_rules=row["evidence_rules"],
            synthesis_rules=row["synthesis_rules"],
            output_requirements=row["output_requirements"],
            version=row["version"],
            is_default=bool(row["is_default"]),
        )


def _parse_json_object(text: str, fallback_key: str | None = None) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        if fallback_key is not None:
            return {fallback_key: text.strip(), "dimensions": [], "evidence": []}
        raise ValueError("AI analysis did not return valid JSON.")
    if not isinstance(parsed, dict):
        raise ValueError("AI analysis must return a JSON object.")
    return parsed


def _load_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
