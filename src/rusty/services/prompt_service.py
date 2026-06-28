from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rusty.db import initialize_database, session
from rusty.services.project_service import default_database_path


@dataclass(frozen=True)
class PromptTemplate:
    id: int
    name: str
    global_rules: str
    summary_rules: str
    scene_detection_rules: str
    rewrite_rules: str
    version: int
    is_default: bool


class PromptService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def create_template(
        self,
        name: str,
        global_rules: str = "",
        summary_rules: str = "",
        scene_detection_rules: str = "",
        rewrite_rules: str = "",
        is_default: bool = False,
    ) -> int:
        with session(self.database_path) as connection:
            if is_default:
                connection.execute("UPDATE prompt_templates SET is_default = 0 WHERE deleted_at IS NULL")
            cursor = connection.execute(
                """
                INSERT INTO prompt_templates (
                    name,
                    global_rules,
                    summary_rules,
                    scene_detection_rules,
                    rewrite_rules,
                    is_default
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, global_rules, summary_rules, scene_detection_rules, rewrite_rules, 1 if is_default else 0),
            )
            return int(cursor.lastrowid)

    def update_template(
        self,
        template_id: int,
        name: str,
        global_rules: str,
        summary_rules: str,
        scene_detection_rules: str,
        rewrite_rules: str,
        is_default: bool = False,
    ) -> None:
        with session(self.database_path) as connection:
            if is_default:
                connection.execute("UPDATE prompt_templates SET is_default = 0 WHERE deleted_at IS NULL")
            connection.execute(
                """
                UPDATE prompt_templates
                SET
                    name = ?,
                    global_rules = ?,
                    summary_rules = ?,
                    scene_detection_rules = ?,
                    rewrite_rules = ?,
                    version = version + 1,
                    is_default = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    name,
                    global_rules,
                    summary_rules,
                    scene_detection_rules,
                    rewrite_rules,
                    1 if is_default else 0,
                    template_id,
                ),
            )

    def delete_template(self, template_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE prompt_templates SET deleted_at = CURRENT_TIMESTAMP, is_default = 0 WHERE id = ?",
                (template_id,),
            )

    def list_templates(self) -> list[PromptTemplate]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    global_rules,
                    summary_rules,
                    scene_detection_rules,
                    rewrite_rules,
                    version,
                    is_default
                FROM prompt_templates
                WHERE deleted_at IS NULL
                ORDER BY is_default DESC, updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_template(self, template_id: int) -> PromptTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    global_rules,
                    summary_rules,
                    scene_detection_rules,
                    rewrite_rules,
                    version,
                    is_default
                FROM prompt_templates
                WHERE id = ? AND deleted_at IS NULL
                """,
                (template_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def get_default_template(self) -> PromptTemplate | None:
        templates = self.list_templates()
        return templates[0] if templates else None

    def save_project_prompt(self, project_id: int, prompt_key: str, prompt_text: str) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO project_custom_prompts (project_id, prompt_key, prompt_text)
                VALUES (?, ?, ?)
                ON CONFLICT(project_id, prompt_key)
                DO UPDATE SET prompt_text = excluded.prompt_text, updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, prompt_key, prompt_text),
            )

    def list_project_prompts(self, project_id: int) -> dict[str, str]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT prompt_key, prompt_text
                FROM project_custom_prompts
                WHERE project_id = ?
                ORDER BY prompt_key
                """,
                (project_id,),
            ).fetchall()
        return {row["prompt_key"]: row["prompt_text"] for row in rows}

    @staticmethod
    def _from_row(row) -> PromptTemplate:
        return PromptTemplate(
            id=row["id"],
            name=row["name"],
            global_rules=row["global_rules"],
            summary_rules=row["summary_rules"],
            scene_detection_rules=row["scene_detection_rules"],
            rewrite_rules=row["rewrite_rules"],
            version=row["version"],
            is_default=bool(row["is_default"]),
        )
