from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rusty.content_hash import hash_text
from rusty.db import default_database_path, session
from rusty.models import count_text_units
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.author_style_extraction_service import AuthorStyleExtractionService
from rusty.services.ai_request_executor import AIRequestExecutor
from rusty.services.material_service import MaterialService
from rusty.services.workflow_ai import WorkflowAI


STRATEGIES = {"plot_adjust", "expansion", "plot_rewrite"}
STAGES = {"not_started", "summary", "direction", "special_analysis", "style", "writing", "review", "confirmed"}


def normalize_style_profile(snapshot: object) -> dict[str, Any]:
    """Return the user-facing style fields from either supported snapshot shape."""
    source = snapshot if isinstance(snapshot, dict) else {}
    nested = source.get("profile")
    profile = nested if isinstance(nested, dict) else source

    def text(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    def strings(value: object) -> list[str]:
        return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []

    raw_dimensions = profile.get("dimensions")
    dimensions: list[dict[str, Any]] = []
    for item in raw_dimensions if isinstance(raw_dimensions, list) else []:
        if not isinstance(item, dict):
            continue
        name = text(item.get("name"))
        if not name:
            continue
        dimensions.append({
            "id": text(item.get("id")),
            "name": name,
            "analysis": text(item.get("analysis")),
            "features": strings(item.get("features")),
            "examples": strings(item.get("examples")),
        })
    return {
        "overall_style": text(profile.get("overall_style")) or text(source.get("overall_style")),
        "dimensions": dimensions,
        "work": text(profile.get("work")) or text(source.get("work")),
    }


class WorkflowSourceConflict(ValueError):
    """The current chapter text no longer matches the workflow source."""


class CreativeWorkflowService:
    """The chapter-level creative workflow used by the desktop application."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        ai_client: Any | None = None,
        executor: AIRequestExecutor | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client, executor=executor)
        self.versions = ChapterVersionService(self.database_path)
        self.materials = MaterialService(self.database_path)
        self.author_styles = AuthorStyleExtractionService(
            self.database_path, executor=self.ai.executor
        )

    def get_chapter_workflow(self, chapter_id: int) -> dict[str, Any]:
        source = self.versions.resolve_chapter_source(chapter_id)
        with session(self.database_path) as connection:
            self._ensure_state(connection, source)
            state = connection.execute("SELECT * FROM chapter_workflow_state WHERE chapter_id=?", (chapter_id,)).fetchone()
            summary = connection.execute("SELECT * FROM chapter_workflow_summaries WHERE chapter_id=?", (chapter_id,)).fetchone()
            intent = connection.execute("SELECT * FROM chapter_creative_intents WHERE chapter_id=?", (chapter_id,)).fetchone()
            analysis = connection.execute("SELECT * FROM chapter_special_analyses WHERE chapter_id=?", (chapter_id,)).fetchone()
            style = connection.execute("SELECT * FROM chapter_style_contexts WHERE chapter_id=?", (chapter_id,)).fetchone()
            writing = connection.execute("SELECT * FROM chapter_writings WHERE chapter_id=?", (chapter_id,)).fetchone()
            if self._is_confirmed_output(state, writing, source):
                self._adopt_source(connection, source)
                state = connection.execute("SELECT * FROM chapter_workflow_state WHERE chapter_id=?", (chapter_id,)).fetchone()
        return {
            "chapter_id": chapter_id,
            "current_stage": str(state["current_stage"]),
            "source_base_kind": state["source_base_kind"],
            "source_base_version_id": state["source_base_version_id"],
            "source_hash": str(state["source_hash"] or ""),
            "source_changed": bool(state["source_hash"] and state["source_hash"] != source.content_hash),
            "summary": self._summary_out(summary),
            "direction": self._intent_out(intent),
            "special_analysis": self._analysis_out(analysis),
            "style": self._style_out(style),
            "writing": self._writing_out(writing),
            "updated_at": str(state["updated_at"]),
        }

    def run_chapter_summary(self, chapter_id: int) -> dict[str, Any]:
        source = self.versions.resolve_chapter_source(chapter_id)
        response = self.ai.generate_text(
            project_id=source.project_id, stage="chapter_summary", workflow_key=None,
            task_key="chapter_summary", payload={"source_text": source.text},
            output_contract=("按以下纯文本分段返回，标题必须保留：\n"
                             "【剧情总结】\n...\n【关键事件】\n...\n【主要人物与设定】\n..."),
        )
        sections = self._parse_sections(response, ("剧情总结", "关键事件", "主要人物与设定"))
        summary = {
            "plot_summary": sections["剧情总结"],
            "key_events": sections["关键事件"],
            "main_characters": sections["主要人物与设定"],
        }
        with session(self.database_path) as connection:
            self._reset_for_source(connection, source)
            self._write_summary(connection, chapter_id, source.content_hash, summary)
            self._set_stage(connection, chapter_id, "summary")
        return self.get_chapter_summary(chapter_id) or {}

    def get_chapter_summary(self, chapter_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM chapter_workflow_summaries WHERE chapter_id=?", (chapter_id,)).fetchone()
        return self._summary_out(row)

    def save_chapter_summary(self, chapter_id: int, value: dict[str, Any]) -> dict[str, Any]:
        source = self.versions.resolve_chapter_source(chapter_id)
        with session(self.database_path) as connection:
            self._reset_for_source(connection, source)
            self._write_summary(connection, chapter_id, source.content_hash, self._normalize_summary(value))
            self._set_stage(connection, chapter_id, "summary")
        return self.get_chapter_summary(chapter_id) or {}

    def save_chapter_direction(self, chapter_id: int, *, strategy: str, user_instruction: str) -> dict[str, Any]:
        strategy = self._strategy(strategy)
        self._require_current_source(chapter_id)
        if self.get_chapter_summary(chapter_id) is None:
            raise ValueError("Run chapter summary before choosing a direction.")
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO chapter_creative_intents(chapter_id,strategy,user_instruction) VALUES(?,?,?)
                   ON CONFLICT(chapter_id) DO UPDATE SET strategy=excluded.strategy,
                   user_instruction=excluded.user_instruction,updated_at=CURRENT_TIMESTAMP""",
                (chapter_id, strategy, user_instruction.strip()),
            )
            for table in ("chapter_writings", "chapter_style_contexts", "chapter_special_analyses"):
                connection.execute(f"DELETE FROM {table} WHERE chapter_id=?", (chapter_id,))
            self._set_stage(connection, chapter_id, "direction")
        return self.get_chapter_direction(chapter_id) or {}

    def get_chapter_direction(self, chapter_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM chapter_creative_intents WHERE chapter_id=?", (chapter_id,)).fetchone()
        return self._intent_out(row)

    def run_special_analysis(self, chapter_id: int) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        intent = self.get_chapter_direction(chapter_id)
        if intent is None:
            raise ValueError("Direction is required before special analysis.")
        strategy = intent["strategy"]
        payload = (
            {"document_text": self._document_text(source)}
            if strategy == "expansion"
            else {"source_text": source.text}
        )
        output_contract = (
            "按以下纯文本分段返回，标题必须保留：\n【旧大纲】\n...\n【新大纲及细节】\n..."
            if strategy == "plot_adjust"
            else "只返回一份可直接编辑的新大纲纯文本，不要添加JSON、代码围栏或解释。"
        )
        response = self.ai.generate_text(
            project_id=source.project_id, stage="special_analysis", workflow_key=intent["strategy"],
            task_key="special_analysis", user_instruction=intent["user_instruction"],
            payload=payload,
            output_contract=output_contract,
        )
        if strategy == "plot_adjust":
            sections = self._parse_sections(response, ("旧大纲", "新大纲及细节"))
            source_outline, target_outline = sections["旧大纲"], sections["新大纲及细节"]
        else:
            source_outline, target_outline = "", response.strip()
        return self.save_special_analysis(
            chapter_id,
            {"strategy": strategy, "source_outline": source_outline, "target_outline": target_outline},
        )

    def save_special_analysis(self, chapter_id: int, value: dict[str, Any]) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        intent = self.get_chapter_direction(chapter_id)
        if intent is None:
            raise ValueError("Direction is required before special analysis.")
        strategy = self._strategy(str(value.get("strategy") or intent["strategy"]))
        if strategy != intent["strategy"]:
            raise ValueError("Special analysis strategy must match the direction.")
        raw_source_outline = value.get("source_outline")
        if not isinstance(raw_source_outline, str):
            raise ValueError("Special analysis source_outline must be plain text.")
        source_outline = raw_source_outline.strip() if strategy == "plot_adjust" else ""
        if strategy == "plot_adjust" and not source_outline:
            raise ValueError("Plot adjustment requires a non-empty source outline.")
        raw_outline = value.get("target_outline")
        if not isinstance(raw_outline, str):
            raise ValueError("Special analysis target_outline must be plain text.")
        target_outline = raw_outline.strip()
        if not target_outline:
            raise ValueError("Special analysis requires non-empty target_outline text.")
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO chapter_special_analyses(chapter_id,strategy,source_outline,target_outline,source_hash)
                   VALUES(?,?,?,?,?) ON CONFLICT(chapter_id) DO UPDATE SET
                   strategy=excluded.strategy,source_outline=excluded.source_outline,
                   target_outline=excluded.target_outline,
                   source_hash=excluded.source_hash,updated_at=CURRENT_TIMESTAMP""",
                (chapter_id, strategy, source_outline, target_outline, source.content_hash),
            )
            connection.execute("DELETE FROM chapter_style_contexts WHERE chapter_id=?", (chapter_id,))
            connection.execute("DELETE FROM chapter_writings WHERE chapter_id=?", (chapter_id,))
            self._set_stage(connection, chapter_id, "special_analysis")
        return self.get_special_analysis(chapter_id) or {}

    def get_special_analysis(self, chapter_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM chapter_special_analyses WHERE chapter_id=?", (chapter_id,)
            ).fetchone()
        return self._analysis_out(row)

    def resolve_style(self, chapter_id: int, *, author_style_material_id: int | None = None) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        intent = self.get_chapter_direction(chapter_id)
        analysis = self.get_special_analysis(chapter_id)
        if intent is None or analysis is None:
            raise ValueError("Special analysis is required before resolving style.")
        strategy = intent["strategy"]
        if author_style_material_id is not None:
            material = self.materials.get_material(author_style_material_id)
            if material is None:
                raise ValueError("Selected author style material does not exist.")
            mode = "selected_author_style"
            snapshot = {"name": material.name, "raw_text": material.raw_text,
                        "profile": self._load(material.content_json, {})}
            settings_snapshot: dict[str, Any] = {}
            guidance = self._style_guidance(snapshot)
        else:
            if strategy == "plot_rewrite":
                raise ValueError("重写剧情需要选择一个作者风格。")
            outcome = self.author_styles.extract(self._document_text(source))
            settings_snapshot = outcome.settings_snapshot
            snapshot = outcome.result.to_dict()
            guidance = self._style_guidance(snapshot)
            mode, author_style_material_id = "source_auto", None
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO chapter_style_contexts(chapter_id,strategy,style_mode,
                   author_style_material_id,style_snapshot_json,extraction_settings_snapshot_json,
                   generated_guidance,source_hash) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(chapter_id) DO UPDATE SET strategy=excluded.strategy,style_mode=excluded.style_mode,
                   author_style_material_id=excluded.author_style_material_id,
                   style_snapshot_json=excluded.style_snapshot_json,
                   extraction_settings_snapshot_json=excluded.extraction_settings_snapshot_json,
                   generated_guidance=excluded.generated_guidance,source_hash=excluded.source_hash,
                   created_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP""",
                (chapter_id, strategy, mode, author_style_material_id, self._dump(snapshot),
                 self._dump(settings_snapshot), guidance, source.content_hash),
            )
            connection.execute("DELETE FROM chapter_writings WHERE chapter_id=?", (chapter_id,))
            self._set_stage(connection, chapter_id, "style")
        return self.get_style(chapter_id) or {}

    def get_style(self, chapter_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM chapter_style_contexts WHERE chapter_id=?", (chapter_id,)).fetchone()
        return self._style_out(row)

    def generate_chapter(self, chapter_id: int, *, replace_existing: bool = False) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        intent, analysis, style = self.get_chapter_direction(chapter_id), self.get_special_analysis(chapter_id), self.get_style(chapter_id)
        existing = self.get_writing(chapter_id)
        if intent is None or analysis is None or style is None:
            raise ValueError("Direction, special analysis, and style are required before writing.")
        if existing is not None and not replace_existing:
            raise ValueError("A writing result already exists.")
        strategy = intent["strategy"]
        if strategy == "plot_rewrite" and style["style_mode"] != "selected_author_style":
            raise ValueError("重写剧情需要已选择的作者风格。")
        result_text = self.ai.generate_text(
            project_id=source.project_id, stage="writing", workflow_key=strategy, task_key="writing",
            payload=self._writing_payload(strategy, source.text, analysis["target_outline"], style),
            output_contract="只返回完整小说正文，不要添加标题说明、分析、JSON或代码围栏。",
        )
        if not result_text:
            raise ValueError("Writing did not return text.")
        created_chapter_id = None
        if strategy == "expansion":
            created_chapter_id = self._save_expansion_chapter(source, result_text, "", existing)
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO chapter_writings(chapter_id,strategy,result_text,
                   created_chapter_id,source_hash,status) VALUES(?,?,?,?,?,'draft')
                   ON CONFLICT(chapter_id) DO UPDATE SET strategy=excluded.strategy,
                   result_text=excluded.result_text,created_chapter_id=excluded.created_chapter_id,
                   source_hash=excluded.source_hash,
                   status='draft',updated_at=CURRENT_TIMESTAMP""",
                (chapter_id, strategy, result_text, created_chapter_id, source.content_hash),
            )
            self._set_stage(connection, chapter_id, "writing")
        return self.get_writing(chapter_id) or {}

    def get_writing(self, chapter_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM chapter_writings WHERE chapter_id=?", (chapter_id,)).fetchone()
        return self._writing_out(row)

    def save_writing(self, chapter_id: int, result_text: str) -> dict[str, Any]:
        """Save the human-edited draft shown beside the source during manual review."""
        source = self._require_current_source(chapter_id)
        writing = self.get_writing(chapter_id)
        text = result_text.strip()
        if writing is None:
            raise ValueError("Generate a writing result before manual review.")
        if not text:
            raise ValueError("The reviewed draft cannot be empty.")
        source_kind = "manual" if text != writing["result_text"] else "ai"
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE chapter_writings SET result_text=?,status='reviewed',updated_at=CURRENT_TIMESTAMP WHERE chapter_id=?",
                (text, chapter_id),
            )
            target_chapter_id = (
                int(writing["created_chapter_id"])
                if writing["strategy"] == "expansion" and writing["created_chapter_id"] is not None
                else chapter_id
            )
            target_source = source if target_chapter_id == chapter_id else self.versions.resolve_chapter_source(
                target_chapter_id, connection=connection
            )
            saved_version = None
            if target_source.text != text:
                saved_version = self.versions.append_chapter_rewrite_version(
                    connection,
                    chapter_id=target_source.chapter_id,
                    rewritten_text=text,
                    source_base_kind=target_source.source_kind,
                    source_base_version_id=target_source.source_version_id,
                    source_hash=target_source.content_hash,
                    expected_head_version_id=target_source.expected_head_version_id,
                    source_kind=source_kind,
                )
            if target_chapter_id == chapter_id and saved_version is not None:
                connection.execute(
                    """UPDATE chapter_workflow_state
                       SET source_base_kind='rewrite_version',source_base_version_id=?,
                           source_hash=?,updated_at=CURRENT_TIMESTAMP
                       WHERE chapter_id=?""",
                    (int(saved_version["id"]), str(saved_version["content_hash"]), chapter_id),
                )
            self._set_stage(connection, chapter_id, "review")
        return self.get_writing(chapter_id) or {}

    def confirm_chapter(self, chapter_id: int) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        confirmed_kind = source.source_kind
        confirmed_version_id = source.source_version_id
        confirmed_hash = source.content_hash
        writing = self.get_writing(chapter_id)
        if writing is None:
            raise ValueError("Writing is required before confirmation.")
        if writing["strategy"] in {"plot_adjust", "plot_rewrite"}:
            if source.source_kind == "rewrite_version" and source.text == writing["result_text"].strip():
                confirmed_kind = source.source_kind
                confirmed_version_id = source.source_version_id
                confirmed_hash = source.content_hash
            else:
                with session(self.database_path) as connection:
                    version = self.versions.append_chapter_rewrite_version(
                        connection, chapter_id=chapter_id, rewritten_text=writing["result_text"],
                        source_base_kind=source.source_kind,
                        source_base_version_id=source.source_version_id, source_hash=source.content_hash,
                        expected_head_version_id=source.expected_head_version_id, source_kind="ai",
                    )
                    confirmed_kind = "rewrite_version"
                    confirmed_version_id = int(version["id"])
                    confirmed_hash = str(version["content_hash"])
        with session(self.database_path) as connection:
            connection.execute("UPDATE chapter_writings SET status='confirmed',updated_at=CURRENT_TIMESTAMP WHERE chapter_id=?", (chapter_id,))
            connection.execute(
                """UPDATE chapter_workflow_state SET current_stage='confirmed',source_base_kind=?,
                          source_base_version_id=?,source_hash=?,updated_at=CURRENT_TIMESTAMP
                   WHERE chapter_id=?""",
                (confirmed_kind, confirmed_version_id, confirmed_hash, chapter_id),
            )
        return self.get_chapter_workflow(chapter_id)

    def _save_expansion_chapter(self, source: Any, text: str, title: str, existing: dict[str, Any] | None) -> int:
        if existing and existing.get("created_chapter_id"):
            created_id = int(existing["created_chapter_id"])
            with session(self.database_path) as connection:
                if title.strip():
                    connection.execute(
                        "UPDATE chapters SET title=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (title.strip(), created_id),
                    )
                created_source = self.versions.resolve_chapter_source(created_id, connection=connection)
                self.versions.append_chapter_rewrite_version(
                    connection,
                    chapter_id=created_id,
                    rewritten_text=text,
                    source_base_kind=created_source.source_kind,
                    source_base_version_id=created_source.source_version_id,
                    source_hash=created_source.content_hash,
                    expected_head_version_id=created_source.expected_head_version_id,
                    source_kind="ai",
                )
            return created_id
        with session(self.database_path) as connection:
            row = connection.execute("SELECT project_id,chapter_index FROM chapters WHERE id=?", (source.chapter_id,)).fetchone()
            if row is None:
                raise FileNotFoundError(f"Chapter not found: {source.chapter_id}")
            project_id, chapter_index = int(row["project_id"]), int(row["chapter_index"])
            connection.execute("UPDATE chapters SET chapter_index=-chapter_index WHERE project_id=? AND chapter_index>?", (project_id, chapter_index))
            connection.execute("UPDATE chapters SET chapter_index=-chapter_index+1 WHERE project_id=? AND chapter_index<0", (project_id,))
            cursor = connection.execute(
                "INSERT INTO chapters(project_id,chapter_index,title,original_text,word_count,origin_kind,status) VALUES(?,?,?,?,?,'expansion','imported')",
                (project_id, chapter_index + 1, title.strip() or f"第{chapter_index + 1}章", text, count_text_units(text)),
            )
            created_id = int(cursor.lastrowid)
            connection.execute("INSERT INTO chapter_workflow_state(chapter_id) VALUES(?)", (created_id,))
        return created_id

    def _require_current_source(self, chapter_id: int) -> Any:
        source = self.versions.resolve_chapter_source(chapter_id)
        with session(self.database_path) as connection:
            self._ensure_state(connection, source)
            row = connection.execute("SELECT * FROM chapter_workflow_state WHERE chapter_id=?", (chapter_id,)).fetchone()
            writing = connection.execute("SELECT * FROM chapter_writings WHERE chapter_id=?", (chapter_id,)).fetchone()
            if self._is_confirmed_output(row, writing, source):
                self._adopt_source(connection, source)
                return source
        if row and row["source_hash"] and str(row["source_hash"]) != source.content_hash:
            raise WorkflowSourceConflict("当前章节已变化，需要重新确认或重新分析受影响阶段。")
        return source

    @staticmethod
    def _is_confirmed_output(state: Any, writing: Any, source: Any) -> bool:
        return bool(
            state and writing and state["current_stage"] == "confirmed"
            and state["source_hash"] != source.content_hash
            and hash_text(str(writing["result_text"]).strip()) == source.content_hash
        )

    @staticmethod
    def _adopt_source(connection: Any, source: Any) -> None:
        connection.execute(
            """UPDATE chapter_workflow_state SET source_base_kind=?,source_base_version_id=?,
                      source_hash=?,updated_at=CURRENT_TIMESTAMP WHERE chapter_id=?""",
            (source.source_kind, source.source_version_id, source.content_hash, source.chapter_id),
        )

    @staticmethod
    def _ensure_state(connection: Any, source: Any) -> None:
        connection.execute("INSERT OR IGNORE INTO chapter_workflow_state(chapter_id) VALUES(?)", (source.chapter_id,))

    def _reset_for_source(self, connection: Any, source: Any) -> None:
        self._ensure_state(connection, source)
        for table in ("chapter_writings", "chapter_style_contexts", "chapter_special_analyses",
                      "chapter_creative_intents", "chapter_workflow_summaries"):
            connection.execute(f"DELETE FROM {table} WHERE chapter_id=?", (source.chapter_id,))
        connection.execute(
            """UPDATE chapter_workflow_state SET current_stage='not_started',source_base_kind=?,
               source_base_version_id=?,source_hash=?,updated_at=CURRENT_TIMESTAMP WHERE chapter_id=?""",
            (source.source_kind, source.source_version_id, source.content_hash, source.chapter_id),
        )

    @staticmethod
    def _set_stage(connection: Any, chapter_id: int, stage: str) -> None:
        if stage not in STAGES:
            raise ValueError(f"Unsupported chapter workflow stage: {stage}")
        connection.execute("UPDATE chapter_workflow_state SET current_stage=?,updated_at=CURRENT_TIMESTAMP WHERE chapter_id=?", (stage, chapter_id))

    def _document_text(self, source: Any) -> str:
        with session(self.database_path) as connection:
            project = connection.execute(
                "SELECT source_path FROM projects WHERE id=?", (source.project_id,)
            ).fetchone()
            chapters = connection.execute(
                "SELECT title,original_text FROM chapters WHERE project_id=? ORDER BY chapter_index,id",
                (source.project_id,),
            ).fetchall()
        path = Path(str(project["source_path"])) if project and project["source_path"] else None
        if path and path.is_file() and path.suffix.lower() == ".txt":
            try:
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except (OSError, UnicodeError):
                pass
        return "\n\n".join(
            f"## {str(row['title'] or '未命名章节')}\n{str(row['original_text'] or '')}"
            for row in chapters
            if str(row["original_text"] or "").strip()
        )

    @staticmethod
    def _style_guidance(snapshot: object) -> str:
        profile = normalize_style_profile(snapshot)
        sections: list[str] = []
        overall_style = str(profile["overall_style"] or "").strip()
        if overall_style:
            sections.extend(["整体风格", overall_style])
        work = str(profile["work"] or "").strip()
        if work:
            sections.append(f"参考作品：{work}")
        for dimension in profile["dimensions"]:
            name = str(dimension["name"] or "").strip()
            analysis = str(dimension["analysis"] or "").strip()
            features = [str(item).strip() for item in dimension["features"] if str(item).strip()]
            examples = [str(item).strip() for item in dimension["examples"] if str(item).strip()]
            if not name or not analysis and not features and not examples:
                continue
            if sections:
                sections.append("")
            sections.append(name)
            if analysis:
                sections.extend(["分析：", analysis])
            if features:
                sections.append("主要特征：")
                sections.extend(f"- {item}" for item in features)
            if examples:
                sections.append("参考表现：")
                sections.extend(f"- {item}" for item in examples)
        return "\n".join(sections).strip() or "请遵循当前已确定的写作风格。"

    @staticmethod
    def _strategy(value: str) -> str:
        if value not in STRATEGIES:
            raise ValueError("strategy must be plot_adjust, expansion, or plot_rewrite.")
        return value

    @staticmethod
    def _writing_payload(
        strategy: str, source_text: str, target_outline: str, style: dict[str, Any],
    ) -> dict[str, Any]:
        guidance = str(style.get("generated_guidance") or "").strip()
        if guidance.startswith(("{", "[")):
            try:
                legacy_snapshot = json.loads(guidance)
            except json.JSONDecodeError:
                guidance = ""
            else:
                guidance = CreativeWorkflowService._style_guidance(legacy_snapshot) if isinstance(legacy_snapshot, dict) else ""
        if not guidance:
            guidance = CreativeWorkflowService._style_guidance(style.get("style_snapshot", {}))
        payload: dict[str, Any] = {
            "target_outline": target_outline,
            "author_style": guidance,
        }
        if strategy == "plot_adjust":
            payload = {"source_text": source_text, **payload}
        return payload

    @staticmethod
    def _normalize_summary(value: dict[str, Any]) -> dict[str, Any]:
        return {
            "plot_summary": str(value.get("plot_summary") or ""),
            "main_characters": str(value.get("main_characters") or ""),
            "key_events": str(value.get("key_events") or ""),
        }

    def _write_summary(self, connection: Any, chapter_id: int, source_hash: str, value: dict[str, Any]) -> None:
        connection.execute(
            """INSERT INTO chapter_workflow_summaries(
                   chapter_id,plot_summary,main_characters,key_events,source_hash
               ) VALUES(?,?,?,?,?)""",
            (chapter_id, value["plot_summary"], value["main_characters"], value["key_events"], source_hash),
        )

    def _summary_out(self, row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"chapter_id": int(row["chapter_id"]), "plot_summary": str(row["plot_summary"]),
                "main_characters": str(row["main_characters"]), "key_events": str(row["key_events"]),
                "source_hash": str(row["source_hash"]),
                "updated_at": str(row["updated_at"])}

    @staticmethod
    def _intent_out(row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"chapter_id": int(row["chapter_id"]), "strategy": str(row["strategy"]),
                "user_instruction": str(row["user_instruction"]), "updated_at": str(row["updated_at"])}

    def _analysis_out(self, row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"chapter_id": int(row["chapter_id"]), "strategy": str(row["strategy"]),
                "source_outline": str(row["source_outline"]),
                "target_outline": str(row["target_outline"]), "source_hash": str(row["source_hash"]),
                "updated_at": str(row["updated_at"])}

    @staticmethod
    def _parse_sections(text: str, labels: tuple[str, ...]) -> dict[str, str]:
        pattern = "|".join(re.escape(label) for label in labels)
        matches = list(re.finditer(rf"【({pattern})】", text))
        found: dict[str, str] = {}
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            found[match.group(1)] = text[match.end():end].strip()
        missing = [label for label in labels if not found.get(label)]
        if missing:
            raise ValueError("AI response is missing required plain-text sections: " + ", ".join(missing))
        return found

    def _style_out(self, row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"chapter_id": int(row["chapter_id"]), "strategy": str(row["strategy"]), "style_mode": str(row["style_mode"]),
                "author_style_material_id": row["author_style_material_id"],
                "style_snapshot": self._load(row["style_snapshot_json"], {}),
                "extraction_settings_snapshot": self._load(row["extraction_settings_snapshot_json"], {}),
                "generated_guidance": str(row["generated_guidance"]), "source_hash": str(row["source_hash"]),
                "created_at": str(row["created_at"])}

    def _writing_out(self, row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"id": int(row["id"]), "chapter_id": int(row["chapter_id"]), "strategy": str(row["strategy"]),
                "result_text": str(row["result_text"]),
                "created_chapter_id": row["created_chapter_id"], "source_hash": str(row["source_hash"]),
                "status": str(row["status"]), "updated_at": str(row["updated_at"])}

    @staticmethod
    def _dump(value: Any) -> str: return json.dumps(value, ensure_ascii=False)
    @staticmethod
    def _load(value: Any, default: Any) -> Any:
        try: return json.loads(str(value))
        except (TypeError, ValueError): return default
