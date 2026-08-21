from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import default_database_path, session


PROMPT_KINDS = {"master", "workflow_task", "common_task"}
WORKFLOW_KEYS = {"plot_adjust", "expansion", "plot_rewrite"}


@dataclass(frozen=True)
class PromptDefinition:
    id: int
    name: str
    description: str
    kind: str
    workflow_key: str | None
    task_key: str | None
    content: str
    input_description: str
    is_default: bool
    created_at: str
    updated_at: str


class PromptDefinitionService:
    """Simple editable prompts with no versions, inheritance, or synchronization."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()

    def list_definitions(self) -> list[PromptDefinition]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM prompt_definitions WHERE deleted_at IS NULL
                ORDER BY CASE kind WHEN 'master' THEN 0 WHEN 'workflow_task' THEN 1 ELSE 2 END,
                         workflow_key, task_key, is_default DESC, updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_definition(self, definition_id: int) -> PromptDefinition | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM prompt_definitions WHERE id = ? AND deleted_at IS NULL",
                (definition_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def find_task(self, *, workflow_key: str | None, task_key: str) -> PromptDefinition | None:
        kind = "workflow_task" if workflow_key else "common_task"
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM prompt_definitions
                WHERE kind = ? AND COALESCE(workflow_key, '') = COALESCE(?, '')
                  AND task_key = ? AND deleted_at IS NULL
                ORDER BY is_default DESC, updated_at DESC, id DESC LIMIT 1
                """,
                (kind, workflow_key, task_key),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def get_system_prompt(self) -> PromptDefinition | None:
        """Return the single active system prompt used by every chapter-workflow AI call."""
        with session(self.database_path) as connection:
            row = connection.execute(
                """SELECT * FROM prompt_definitions
                   WHERE kind='master' AND is_default=1 AND deleted_at IS NULL
                   ORDER BY updated_at DESC,id DESC LIMIT 1"""
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def create_definition(self, **value: Any) -> PromptDefinition:
        normalized = self._normalize(value)
        with session(self.database_path) as connection:
            self._clear_default(connection, normalized)
            cursor = connection.execute(
                """
                INSERT INTO prompt_definitions (
                    name, description, kind, workflow_key, task_key, content,
                    input_description, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._write_tuple(normalized),
            )
        return self.get_definition(int(cursor.lastrowid))  # type: ignore[return-value]

    def update_definition(self, definition_id: int, **value: Any) -> PromptDefinition:
        if self.get_definition(definition_id) is None:
            raise FileNotFoundError(f"Prompt definition not found: {definition_id}")
        normalized = self._normalize(value)
        with session(self.database_path) as connection:
            self._clear_default(connection, normalized, exclude_id=definition_id)
            connection.execute(
                """
                UPDATE prompt_definitions
                SET name = ?, description = ?, kind = ?, workflow_key = ?, task_key = ?,
                    content = ?, input_description = ?, is_default = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (*self._write_tuple(normalized), definition_id),
            )
        return self.get_definition(definition_id)  # type: ignore[return-value]

    def duplicate_definition(self, definition_id: int) -> PromptDefinition:
        source = self.get_definition(definition_id)
        if source is None:
            raise FileNotFoundError(f"Prompt definition not found: {definition_id}")
        return self.create_definition(
            name=f"{source.name}（副本）",
            description=source.description,
            kind=source.kind,
            workflow_key=source.workflow_key,
            task_key=source.task_key,
            content=source.content,
            input_description=source.input_description,
            is_default=False,
        )

    def delete_definition(self, definition_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE prompt_definitions
                SET deleted_at = CURRENT_TIMESTAMP, is_default = 0
                WHERE id = ? AND deleted_at IS NULL
                """,
                (definition_id,),
            )
        if cursor.rowcount == 0:
            raise FileNotFoundError(f"Prompt definition not found: {definition_id}")

    def initialize_project_master(self, project_id: int, definition_id: int | None = None) -> dict[str, Any]:
        definition = self.get_definition(definition_id) if definition_id is not None else None
        if definition_id is not None and (definition is None or definition.kind != "master"):
            raise ValueError("Selected project master prompt must be a master prompt definition.")
        if definition is None:
            definition = next((item for item in self.list_definitions() if item.kind == "master" and item.is_default), None)
        content = definition.content if definition else ""
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO project_master_prompts (
                    project_id, content, source_prompt_definition_id
                ) VALUES (?, ?, ?)
                """,
                (project_id, content, definition.id if definition else None),
            )
        return self.get_project_master(project_id)

    def get_project_master(self, project_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM project_master_prompts WHERE project_id = ?", (project_id,)
            ).fetchone()
        if row is None:
            return self.initialize_project_master(project_id)
        return {
            "project_id": int(row["project_id"]),
            "content": str(row["content"]),
            "source_prompt_definition_id": row["source_prompt_definition_id"],
            "updated_at": str(row["updated_at"]),
        }

    def save_project_master(self, project_id: int, content: str) -> dict[str, Any]:
        with session(self.database_path) as connection:
            exists = connection.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
            if exists is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            connection.execute(
                """
                INSERT INTO project_master_prompts (project_id, content, source_prompt_definition_id)
                VALUES (?, ?, NULL)
                ON CONFLICT(project_id) DO UPDATE SET
                    content = excluded.content,
                    source_prompt_definition_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, content),
            )
        return self.get_project_master(project_id)

    def export_project_master(self, project_id: int, *, name: str, description: str = "") -> PromptDefinition:
        master = self.get_project_master(project_id)
        return self.create_definition(
            name=name,
            description=description,
            kind="master",
            content=master["content"],
            input_description="所有新工作流任务都会携带此文本。",
            is_default=False,
        )

    def export_definition(self, definition_id: int) -> str:
        definition = self.get_definition(definition_id)
        if definition is None:
            raise FileNotFoundError(f"Prompt definition not found: {definition_id}")
        return json.dumps({"schema": "rusty.prompt_definition.v1", **definition.__dict__}, ensure_ascii=False, indent=2)

    def import_definition(self, content: str) -> PromptDefinition:
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Prompt definition is not valid JSON: {exc.msg}") from exc
        if not isinstance(value, dict) or value.get("schema") != "rusty.prompt_definition.v1":
            raise ValueError("Unsupported prompt definition schema.")
        return self.create_definition(**{**value, "is_default": False})

    @staticmethod
    def _normalize(value: dict[str, Any]) -> dict[str, Any]:
        kind = str(value.get("kind") or "")
        if kind not in PROMPT_KINDS:
            raise ValueError(f"Unsupported prompt kind: {kind}")
        workflow_key = str(value.get("workflow_key") or "").strip() or None
        task_key = str(value.get("task_key") or "").strip() or None
        if kind == "master":
            workflow_key = None
            task_key = None
        elif kind == "common_task":
            workflow_key = None
            if task_key is None:
                raise ValueError("Common task prompts require task_key.")
        elif workflow_key is None or task_key is None:
            raise ValueError("Workflow task prompts require workflow_key and task_key.")
        elif workflow_key not in WORKFLOW_KEYS:
            raise ValueError("workflow_key must be plot_adjust, expansion, or plot_rewrite.")
        name = str(value.get("name") or "").strip()
        if not name:
            raise ValueError("Prompt name is required.")
        return {
            "name": name,
            "description": str(value.get("description") or ""),
            "kind": kind,
            "workflow_key": workflow_key,
            "task_key": task_key,
            "content": str(value.get("content") or ""),
            "input_description": str(value.get("input_description") or ""),
            "is_default": bool(value.get("is_default", False)),
        }

    @staticmethod
    def _write_tuple(value: dict[str, Any]) -> tuple[Any, ...]:
        return (
            value["name"], value["description"], value["kind"], value["workflow_key"],
            value["task_key"], value["content"], value["input_description"],
            1 if value["is_default"] else 0,
        )

    @staticmethod
    def _clear_default(connection: Any, value: dict[str, Any], exclude_id: int | None = None) -> None:
        if not value["is_default"]:
            return
        connection.execute(
            """
            UPDATE prompt_definitions SET is_default = 0
            WHERE kind = ? AND COALESCE(workflow_key, '') = COALESCE(?, '')
              AND COALESCE(task_key, '') = COALESCE(?, '')
              AND deleted_at IS NULL AND id <> COALESCE(?, -1)
            """,
            (value["kind"], value["workflow_key"], value["task_key"], exclude_id),
        )

    @staticmethod
    def _from_row(row: Any) -> PromptDefinition:
        return PromptDefinition(
            id=int(row["id"]), name=str(row["name"]), description=str(row["description"]),
            kind=str(row["kind"]), workflow_key=row["workflow_key"], task_key=row["task_key"],
            content=str(row["content"]), input_description=str(row["input_description"]),
            is_default=bool(row["is_default"]), created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
