from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rusty.db import default_database_path, session
from rusty.models import count_text_units
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.material_service import MaterialService, compile_material_ai_prompt
from rusty.services.workflow_ai import WorkflowAI


STRATEGIES = {"plot_adjust", "expansion", "reimagine"}
STAGES = {"not_started", "summary", "direction", "special_analysis", "style", "writing", "review", "confirmed"}
class WorkflowSourceConflict(ValueError):
    """The current chapter text no longer matches the workflow source."""


class CreativeWorkflowService:
    """Chapter-only creative workflow. Legacy scene data is deliberately ignored."""

    def __init__(self, database_path: str | Path | None = None, *, ai_client: Any | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client)
        self.versions = ChapterVersionService(self.database_path)
        self.materials = MaterialService(self.database_path)

    def list_chapter_states(self, project_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id FROM chapters WHERE project_id=? ORDER BY chapter_index,id", (project_id,)
            ).fetchall()
        return [self.get_chapter_workflow(int(row["id"])) for row in rows]

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

    def get_chapter_state(self, chapter_id: int) -> dict[str, Any]:
        return self.get_chapter_workflow(chapter_id)

    def run_chapter_summary(self, chapter_id: int) -> dict[str, Any]:
        source = self.versions.resolve_chapter_source(chapter_id)
        value = self.ai.generate_json(
            project_id=source.project_id, stage="chapter_summary", workflow_key=None,
            task_key="chapter_summary", payload={"chapter_id": chapter_id, "source_text": source.text},
            output_contract=("JSON object: plot_summary string; main_characters, key_events, relationships, "
                             "important_facts, open_threads arrays; start_state and end_state objects."),
        )
        summary = self._normalize_summary(value)
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

    def run_special_analysis(self, chapter_id: int, *, outline_detail_level: str | None = None) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        summary = self.get_chapter_summary(chapter_id)
        intent = self.get_chapter_direction(chapter_id)
        if summary is None or intent is None:
            raise ValueError("Summary and direction are required before special analysis.")
        detail = None
        if intent["strategy"] == "reimagine":
            detail = outline_detail_level or "detailed"
            if detail not in {"brief", "detailed"}:
                raise ValueError("outline_detail_level must be brief or detailed.")
        value = self.ai.generate_json(
            project_id=source.project_id, stage="special_analysis", workflow_key=intent["strategy"],
            task_key="special_analysis", user_instruction=intent["user_instruction"],
            payload={"source_text": source.text, "summary": summary, "strategy": intent["strategy"],
                     "outline_detail_level": detail},
            output_contract=("JSON object: source_outline array, target_outline array, constraints object, "
                             "analysis_notes array. Nodes have stable ids; plot_adjust targets have "
                             "operation preserve|modify|delete|insert and source_ids."),
        )
        return self.save_special_analysis(chapter_id, {**value, "strategy": intent["strategy"], "outline_detail_level": detail})

    def save_special_analysis(self, chapter_id: int, value: dict[str, Any]) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        intent = self.get_chapter_direction(chapter_id)
        if intent is None:
            raise ValueError("Direction is required before special analysis.")
        strategy = self._strategy(str(value.get("strategy") or intent["strategy"]))
        if strategy != intent["strategy"]:
            raise ValueError("Special analysis strategy must match the direction.")
        detail = value.get("outline_detail_level")
        if strategy == "reimagine":
            detail = str(detail or "detailed")
            if detail not in {"brief", "detailed"}:
                raise ValueError("outline_detail_level must be brief or detailed.")
        else:
            detail = None
        source_outline = self._object_list(value.get("source_outline"), "source_outline")
        target_outline = self._object_list(value.get("target_outline"), "target_outline")
        constraints = value.get("constraints") if isinstance(value.get("constraints"), dict) else {}
        notes = value.get("analysis_notes") if isinstance(value.get("analysis_notes"), list) else []
        if not source_outline or not target_outline:
            raise ValueError("Special analysis requires source_outline and target_outline.")
        if strategy == "plot_adjust" and any(str(node.get("operation")) not in {"preserve", "modify", "delete", "insert"} for node in target_outline):
            raise ValueError("plot_adjust target nodes require a valid operation.")
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO chapter_special_analyses(chapter_id,strategy,outline_detail_level,
                   source_outline_json,target_outline_json,constraints_json,analysis_notes_json,source_hash)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(chapter_id) DO UPDATE SET
                   strategy=excluded.strategy,outline_detail_level=excluded.outline_detail_level,
                   source_outline_json=excluded.source_outline_json,target_outline_json=excluded.target_outline_json,
                   constraints_json=excluded.constraints_json,analysis_notes_json=excluded.analysis_notes_json,
                   source_hash=excluded.source_hash,updated_at=CURRENT_TIMESTAMP""",
                (chapter_id, strategy, detail, self._dump(source_outline), self._dump(target_outline),
                 self._dump(constraints), self._dump(notes), source.content_hash),
            )
            connection.execute("DELETE FROM chapter_style_contexts WHERE chapter_id=?", (chapter_id,))
            connection.execute("DELETE FROM chapter_writings WHERE chapter_id=?", (chapter_id,))
            self._set_stage(connection, chapter_id, "special_analysis")
        return self.get_special_analysis(chapter_id) or {}

    def get_special_analysis(self, chapter_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM chapter_special_analyses WHERE chapter_id=?", (chapter_id,)).fetchone()
        return self._analysis_out(row)

    def resolve_style(self, chapter_id: int, *, source_scope: str = "document", author_style_material_id: int | None = None) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        intent = self.get_chapter_direction(chapter_id)
        analysis = self.get_special_analysis(chapter_id)
        if intent is None or analysis is None:
            raise ValueError("Special analysis is required before resolving style.")
        strategy = intent["strategy"]
        if strategy == "reimagine":
            if author_style_material_id is None:
                raise ValueError("reimagine requires a selected author_style material.")
            material = self.materials.get_material(author_style_material_id)
            if material is None or material.material_type != "author_style":
                raise ValueError("Selected author style material does not exist.")
            if material.analysis_status != "analyzed":
                raise ValueError("Selected author style material is not analyzed.")
            mode, scope = "selected_author_style", "chapter"
            snapshot = {"name": material.name, "description": material.description, "raw_text": material.raw_text,
                        "profile": self._load(material.content_json, {})}
            settings_snapshot: dict[str, Any] = {}
            guidance = self._style_guidance(snapshot)
            material_version = material.version
        else:
            if author_style_material_id is not None:
                raise ValueError("plot_adjust and expansion use source_auto style.")
            if source_scope not in {"document", "chapter"}:
                raise ValueError("source_scope must be document or chapter.")
            style_text, scope = self._style_source(source, source_scope)
            settings = self.materials.get_ai_settings("author_style_extraction")
            settings_snapshot = asdict(settings)
            extracted = self.ai.generate_json(
                project_id=source.project_id, stage="author_style_extraction",
                payload={"sample_text": self._sample_style_source(style_text),
                         "extraction_prompt": compile_material_ai_prompt(settings),
                         "dimensions": [dict(item) for item in settings.dimensions],
                         "local_chapter_reference": source.text},
                output_contract="JSON object containing style_snapshot object and generated_guidance string.",
            )
            snapshot = extracted.get("style_snapshot") if isinstance(extracted.get("style_snapshot"), dict) else extracted
            guidance = str(extracted.get("generated_guidance") or self._style_guidance(snapshot))
            mode, author_style_material_id, material_version = "source_auto", None, None
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO chapter_style_contexts(chapter_id,strategy,style_mode,source_scope,
                   author_style_material_id,author_style_material_version,style_snapshot_json,
                   extraction_settings_snapshot_json,generated_guidance,source_hash) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(chapter_id) DO UPDATE SET strategy=excluded.strategy,style_mode=excluded.style_mode,
                   source_scope=excluded.source_scope,author_style_material_id=excluded.author_style_material_id,
                   author_style_material_version=excluded.author_style_material_version,
                   style_snapshot_json=excluded.style_snapshot_json,
                   extraction_settings_snapshot_json=excluded.extraction_settings_snapshot_json,
                   generated_guidance=excluded.generated_guidance,source_hash=excluded.source_hash,
                   created_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP""",
                (chapter_id, strategy, mode, scope, author_style_material_id, material_version,
                 self._dump(snapshot), self._dump(settings_snapshot), guidance, source.content_hash),
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
        if strategy == "reimagine" and style["style_mode"] != "selected_author_style":
            raise ValueError("reimagine requires a selected author_style snapshot.")
        if strategy == "plot_adjust":
            plan = self._create_patch_plan(source, intent, analysis)
            result_text, plan = self._execute_patch(source, intent, analysis, style, plan)
            created_chapter_id = None
        else:
            value = self.ai.generate_json(
                project_id=source.project_id, stage="writing", workflow_key=strategy, task_key="writing",
                payload={"source_text": source.text, "summary": self.get_chapter_summary(chapter_id),
                         "special_analysis": analysis, "style_snapshot": style["style_snapshot"],
                         "style_guidance": style["generated_guidance"]},
                user_instruction=intent["user_instruction"],
                output_contract="JSON object with non-empty text string and optional title string.",
            )
            result_text = str(value.get("text") or "").strip()
            if not result_text:
                raise ValueError("Writing did not return text.")
            plan, created_chapter_id = [], None
            if strategy == "expansion":
                created_chapter_id = self._save_expansion_chapter(source, result_text, str(value.get("title") or ""), existing)
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO chapter_writings(chapter_id,strategy,writing_plan_json,result_text,
                   created_chapter_id,source_hash,status) VALUES(?,?,?,?,?,?,'draft')
                   ON CONFLICT(chapter_id) DO UPDATE SET strategy=excluded.strategy,
                   writing_plan_json=excluded.writing_plan_json,result_text=excluded.result_text,
                   created_chapter_id=excluded.created_chapter_id,source_hash=excluded.source_hash,
                   status='draft',updated_at=CURRENT_TIMESTAMP""",
                (chapter_id, strategy, self._dump(plan), result_text, created_chapter_id, source.content_hash),
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
            if writing["strategy"] == "expansion" and writing["created_chapter_id"] is not None:
                created_source = self.versions.resolve_chapter_source(
                    int(writing["created_chapter_id"]), connection=connection
                )
                self.versions.append_chapter_rewrite_version(
                    connection,
                    chapter_id=created_source.chapter_id,
                    rewritten_text=text,
                    source_operation="manual",
                    source_run_id=writing["id"],
                    source_base_kind=created_source.source_kind,
                    source_base_version_id=created_source.source_version_id,
                    source_hash=created_source.content_hash,
                    facts_before=created_source.facts_before,
                    facts_after=created_source.facts_after,
                    expected_head_version_id=created_source.expected_head_version_id,
                    source_kind=source_kind,
                    fact_chain_status="needs_recompute",
                    mapping_strategy="structural",
                )
            self._set_stage(connection, chapter_id, "review")
        return self.get_writing(chapter_id) or {}

    def confirm_chapter(self, chapter_id: int) -> dict[str, Any]:
        source = self._require_current_source(chapter_id)
        writing = self.get_writing(chapter_id)
        if writing is None:
            raise ValueError("Writing is required before confirmation.")
        if writing["strategy"] in {"plot_adjust", "reimagine"}:
            with session(self.database_path) as connection:
                self.versions.append_chapter_rewrite_version(
                    connection, chapter_id=chapter_id, rewritten_text=writing["result_text"],
                    source_operation="manual", source_run_id=writing["id"], source_base_kind=source.source_kind,
                    source_base_version_id=source.source_version_id, source_hash=source.content_hash,
                    facts_before=source.facts_before, facts_after=source.facts_after,
                    expected_head_version_id=source.expected_head_version_id, source_kind="ai",
                    fact_chain_status="needs_recompute", mapping_strategy="structural",
                )
        with session(self.database_path) as connection:
            connection.execute("UPDATE chapter_writings SET status='confirmed',updated_at=CURRENT_TIMESTAMP WHERE chapter_id=?", (chapter_id,))
            self._set_stage(connection, chapter_id, "confirmed")
        return self.get_chapter_workflow(chapter_id)

    def _create_patch_plan(self, source: Any, intent: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
        value = self.ai.generate_json(
            project_id=source.project_id, stage="writing_plan", workflow_key="plot_adjust", task_key="writing",
            payload={"source_text": source.text, "special_analysis": analysis}, user_instruction=intent["user_instruction"],
            output_contract=("JSON object with blocks array. Each has operation preserve|modify|delete|insert, "
                             "start_offset, end_offset, instruction and order."),
        )
        return self._object_list(value.get("blocks"), "blocks")

    def _execute_patch(self, source: Any, intent: dict[str, Any], analysis: dict[str, Any],
                       style: dict[str, Any], plan: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        text, cursor, output, executed = source.text, 0, [], []
        for order, block in enumerate(plan):
            operation = str(block.get("operation") or "")
            if operation not in {"preserve", "modify", "delete", "insert"}:
                raise ValueError("Writing plan contains an unsupported operation.")
            start = int(block.get("start_offset", cursor))
            end = int(block.get("end_offset", start if operation == "insert" else cursor))
            if start < cursor or end < start or end > len(text):
                raise ValueError("Writing plan contains overlapping or invalid source spans.")
            if start > cursor:
                output.append(text[cursor:start])
            generated = ""
            if operation == "preserve":
                generated = text[start:end]
            elif operation in {"modify", "insert"}:
                value = self.ai.generate_json(
                    project_id=source.project_id, stage="writing", workflow_key="plot_adjust", task_key="writing",
                    payload={"operation": operation, "source_text": text[start:end],
                             "instruction": str(block.get("instruction") or ""),
                             "context_before": text[max(0, start - 500):start], "context_after": text[end:end + 500],
                             "special_analysis": analysis, "style_snapshot": style["style_snapshot"]},
                    user_instruction=intent["user_instruction"],
                    output_contract="JSON object with text string for only this block.",
                )
                generated = str(value.get("text") or "")
                if not generated:
                    raise ValueError("A modify/insert block returned empty text.")
            output.append(generated)
            executed.append({**block, "order": order, "start_offset": start, "end_offset": end,
                             "source_text": text[start:end], "result_text": generated})
            if operation != "insert":
                cursor = end
        output.append(text[cursor:])
        return "".join(output), executed

    def _save_expansion_chapter(self, source: Any, text: str, title: str, existing: dict[str, Any] | None) -> int:
        if existing and existing.get("created_chapter_id"):
            created_id = int(existing["created_chapter_id"])
            with session(self.database_path) as connection:
                connection.execute(
                    "UPDATE chapters SET title=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (title.strip() or "新增章节", created_id),
                )
                created_source = self.versions.resolve_chapter_source(created_id, connection=connection)
                self.versions.append_chapter_rewrite_version(
                    connection,
                    chapter_id=created_id,
                    rewritten_text=text,
                    source_operation="manual",
                    source_run_id=int(existing["id"]),
                    source_base_kind=created_source.source_kind,
                    source_base_version_id=created_source.source_version_id,
                    source_hash=created_source.content_hash,
                    facts_before=created_source.facts_before,
                    facts_after=created_source.facts_after,
                    expected_head_version_id=created_source.expected_head_version_id,
                    source_kind="ai",
                    fact_chain_status="needs_recompute",
                    mapping_strategy="structural",
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
                "INSERT INTO chapters(project_id,chapter_index,title,original_text,word_count,status) VALUES(?,?,?,?,?,'imported')",
                (project_id, chapter_index + 1, title.strip() or f"第{chapter_index + 1}章", text, count_text_units(text)),
            )
            created_id = int(cursor.lastrowid)
            connection.execute("INSERT INTO chapter_workflow_state(chapter_id) VALUES(?)", (created_id,))
        return created_id

    def _require_current_source(self, chapter_id: int) -> Any:
        source = self.versions.resolve_chapter_source(chapter_id)
        with session(self.database_path) as connection:
            self._ensure_state(connection, source)
            row = connection.execute("SELECT source_hash FROM chapter_workflow_state WHERE chapter_id=?", (chapter_id,)).fetchone()
        if row and row["source_hash"] and str(row["source_hash"]) != source.content_hash:
            raise WorkflowSourceConflict("当前章节已变化，需要重新确认或重新分析受影响阶段。")
        return source

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

    def _style_source(self, source: Any, requested_scope: str) -> tuple[str, str]:
        if requested_scope == "document":
            with session(self.database_path) as connection:
                row = connection.execute("SELECT source_path FROM projects WHERE id=?", (source.project_id,)).fetchone()
            path = Path(str(row["source_path"])) if row and row["source_path"] else None
            if path and path.is_file() and path.suffix.lower() == ".txt":
                try:
                    value = path.read_text(encoding="utf-8").strip()
                    if value:
                        return value, "document"
                except (OSError, UnicodeError):
                    pass
        return source.text, "chapter"

    @staticmethod
    def _sample_style_source(text: str, limit: int = 24000) -> str:
        if len(text) <= limit:
            return text
        part, middle = limit // 3, max(0, len(text) // 2 - limit // 6)
        return text[:part] + "\n\n[中段采样]\n\n" + text[middle:middle + part] + "\n\n[末段采样]\n\n" + text[-part:]

    @staticmethod
    def _style_guidance(snapshot: dict[str, Any]) -> str:
        return json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _strategy(value: str) -> str:
        if value not in STRATEGIES:
            raise ValueError("strategy must be plot_adjust, expansion, or reimagine.")
        return value

    @staticmethod
    def _normalize_summary(value: dict[str, Any]) -> dict[str, Any]:
        return {
            "plot_summary": str(value.get("plot_summary") or ""),
            "main_characters": value.get("main_characters") if isinstance(value.get("main_characters"), list) else [],
            "key_events": value.get("key_events") if isinstance(value.get("key_events"), list) else [],
            "relationships": value.get("relationships") if isinstance(value.get("relationships"), list) else [],
            "start_state": value.get("start_state") if isinstance(value.get("start_state"), dict) else {},
            "end_state": value.get("end_state") if isinstance(value.get("end_state"), dict) else {},
            "important_facts": value.get("important_facts") if isinstance(value.get("important_facts"), list) else [],
            "open_threads": value.get("open_threads") if isinstance(value.get("open_threads"), list) else [],
        }

    def _write_summary(self, connection: Any, chapter_id: int, source_hash: str, value: dict[str, Any]) -> None:
        connection.execute(
            """INSERT INTO chapter_workflow_summaries(chapter_id,plot_summary,main_characters_json,
               key_events_json,relationships_json,start_state_json,end_state_json,important_facts_json,
               open_threads_json,source_hash) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (chapter_id, value["plot_summary"], self._dump(value["main_characters"]), self._dump(value["key_events"]),
             self._dump(value["relationships"]), self._dump(value["start_state"]), self._dump(value["end_state"]),
             self._dump(value["important_facts"]), self._dump(value["open_threads"]), source_hash),
        )

    def _summary_out(self, row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"chapter_id": int(row["chapter_id"]), "plot_summary": str(row["plot_summary"]),
                "main_characters": self._load(row["main_characters_json"], []), "key_events": self._load(row["key_events_json"], []),
                "relationships": self._load(row["relationships_json"], []), "start_state": self._load(row["start_state_json"], {}),
                "end_state": self._load(row["end_state_json"], {}), "important_facts": self._load(row["important_facts_json"], []),
                "open_threads": self._load(row["open_threads_json"], []), "source_hash": str(row["source_hash"]),
                "updated_at": str(row["updated_at"])}

    @staticmethod
    def _intent_out(row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"chapter_id": int(row["chapter_id"]), "strategy": str(row["strategy"]),
                "user_instruction": str(row["user_instruction"]), "updated_at": str(row["updated_at"])}

    def _analysis_out(self, row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"chapter_id": int(row["chapter_id"]), "strategy": str(row["strategy"]),
                "outline_detail_level": row["outline_detail_level"], "source_outline": self._load(row["source_outline_json"], []),
                "target_outline": self._load(row["target_outline_json"], []), "constraints": self._load(row["constraints_json"], {}),
                "analysis_notes": self._load(row["analysis_notes_json"], []), "source_hash": str(row["source_hash"]),
                "updated_at": str(row["updated_at"])}

    def _style_out(self, row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"chapter_id": int(row["chapter_id"]), "strategy": str(row["strategy"]), "style_mode": str(row["style_mode"]),
                "source_scope": str(row["source_scope"]), "author_style_material_id": row["author_style_material_id"],
                "author_style_material_version": row["author_style_material_version"],
                "style_snapshot": self._load(row["style_snapshot_json"], {}),
                "extraction_settings_snapshot": self._load(row["extraction_settings_snapshot_json"], {}),
                "generated_guidance": str(row["generated_guidance"]), "source_hash": str(row["source_hash"]),
                "created_at": str(row["created_at"])}

    def _writing_out(self, row: Any) -> dict[str, Any] | None:
        if row is None: return None
        return {"id": int(row["id"]), "chapter_id": int(row["chapter_id"]), "strategy": str(row["strategy"]),
                "writing_plan": self._load(row["writing_plan_json"], []), "result_text": str(row["result_text"]),
                "created_chapter_id": row["created_chapter_id"], "source_hash": str(row["source_hash"]),
                "status": str(row["status"]), "updated_at": str(row["updated_at"])}

    @staticmethod
    def _object_list(value: Any, label: str) -> list[dict[str, Any]]:
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError(f"{label} must be an array of objects.")
        return [dict(item) for item in value]

    @staticmethod
    def _dump(value: Any) -> str: return json.dumps(value, ensure_ascii=False)
    @staticmethod
    def _load(value: Any, default: Any) -> Any:
        try: return json.loads(str(value))
        except (TypeError, ValueError): return default
