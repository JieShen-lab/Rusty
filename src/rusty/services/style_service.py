from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import default_database_path

CANONICAL_STYLE_SCHEMA = "rusty.style_template"
CANONICAL_STYLE_VERSION = 1
DETAIL_LEVELS = {"brief", "standard", "detailed"}


@dataclass(frozen=True)
class StyleTemplate:
    id: int
    name: str
    description: str
    detail_level: str
    global_prompt: str
    rewrite_prompt: str
    style_profile_json: str
    generated_prompt: str
    source_metadata_json: str
    import_metadata_json: str
    version: int


class StyleTemplateService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def create_template(
        self,
        name: str,
        description: str = "",
        detail_level: str = "standard",
        global_prompt: str = "",
        rewrite_prompt: str = "",
        style_profile: dict[str, Any] | None = None,
        generated_prompt: str = "",
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
    ) -> int:
        level = _validate_detail_level(detail_level)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO style_templates (
                    name,
                    description,
                    detail_level,
                    global_prompt,
                    rewrite_prompt,
                    style_profile_json,
                    generated_prompt,
                    source_metadata_json,
                    import_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _required_name(name),
                    description,
                    level,
                    global_prompt,
                    rewrite_prompt,
                    json.dumps(style_profile or {}, ensure_ascii=False),
                    generated_prompt,
                    json.dumps(source_metadata or {}, ensure_ascii=False),
                    json.dumps(import_metadata or {}, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def update_template(
        self,
        template_id: int,
        name: str,
        description: str = "",
        detail_level: str = "standard",
        global_prompt: str = "",
        rewrite_prompt: str = "",
        style_profile: dict[str, Any] | None = None,
        generated_prompt: str = "",
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
    ) -> None:
        level = _validate_detail_level(detail_level)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE style_templates
                SET
                    name = ?,
                    description = ?,
                    detail_level = ?,
                    global_prompt = ?,
                    rewrite_prompt = ?,
                    style_profile_json = ?,
                    generated_prompt = ?,
                    source_metadata_json = ?,
                    import_metadata_json = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    _required_name(name),
                    description,
                    level,
                    global_prompt,
                    rewrite_prompt,
                    json.dumps(style_profile or {}, ensure_ascii=False),
                    generated_prompt,
                    json.dumps(source_metadata or {}, ensure_ascii=False),
                    json.dumps(import_metadata or {}, ensure_ascii=False),
                    template_id,
                ),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Style template not found: {template_id}")

    def delete_template(self, template_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE style_templates
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (template_id,),
            )
            connection.execute(
                """
                UPDATE project_style_bindings
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE style_template_id = ?
                """,
                (template_id,),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Style template not found: {template_id}")

    def list_templates(self) -> list[StyleTemplate]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    description,
                    detail_level,
                    global_prompt,
                    rewrite_prompt,
                    style_profile_json,
                    generated_prompt,
                    source_metadata_json,
                    import_metadata_json,
                    version
                FROM style_templates
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_template(self, template_id: int) -> StyleTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    description,
                    detail_level,
                    global_prompt,
                    rewrite_prompt,
                    style_profile_json,
                    generated_prompt,
                    source_metadata_json,
                    import_metadata_json,
                    version
                FROM style_templates
                WHERE id = ? AND deleted_at IS NULL
                """,
                (template_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def bind_project_style(self, project_id: int, template_id: int) -> None:
        if self.get_template(template_id) is None:
            raise ValueError(f"Style template not found: {template_id}")
        with session(self.database_path) as connection:
            project = connection.execute(
                "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if project is None:
                raise ValueError(f"Project not found: {project_id}")
            connection.execute(
                """
                INSERT INTO project_style_bindings (
                    project_id,
                    style_template_id,
                    is_active
                ) VALUES (?, ?, 1)
                ON CONFLICT(project_id)
                DO UPDATE SET
                    style_template_id = excluded.style_template_id,
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, template_id),
            )

    def unbind_project_style(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE project_style_bindings
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ?
                """,
                (project_id,),
            )

    def get_project_style_template(self, project_id: int) -> StyleTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    s.id,
                    s.name,
                    s.description,
                    s.detail_level,
                    s.global_prompt,
                    s.rewrite_prompt,
                    s.style_profile_json,
                    s.generated_prompt,
                    s.source_metadata_json,
                    s.import_metadata_json,
                    s.version
                FROM project_style_bindings b
                JOIN style_templates s ON s.id = b.style_template_id
                WHERE b.project_id = ?
                  AND b.is_active = 1
                  AND s.deleted_at IS NULL
                """,
                (project_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def export_template(self, template_id: int) -> str:
        template = self.get_template(template_id)
        if template is None:
            raise ValueError(f"Style template not found: {template_id}")
        payload = {
            "schema": CANONICAL_STYLE_SCHEMA,
            "version": CANONICAL_STYLE_VERSION,
            "template": self._template_payload(template),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def import_template_text(self, text: str) -> int:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid style template JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Style template JSON must be an object.")
        data = self._payload_to_template_args(payload)
        return self.create_template(**data)

    def import_template_file(self, path: str | Path) -> int:
        template_path = Path(path)
        if template_path.suffix.lower() not in {".json", ".txt"}:
            raise ValueError("Style template import only supports .json or .txt files containing JSON.")
        return self.import_template_text(template_path.read_text(encoding="utf-8-sig"))

    def _payload_to_template_args(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("schema") == CANONICAL_STYLE_SCHEMA:
            template = payload.get("template")
            if not isinstance(template, dict):
                raise ValueError("Canonical style template payload is missing template object.")
            return {
                "name": str(template.get("name") or ""),
                "description": str(template.get("description") or ""),
                "detail_level": str(template.get("detail_level") or "standard"),
                "global_prompt": str(template.get("global_prompt") or ""),
                "rewrite_prompt": str(template.get("rewrite_prompt") or ""),
                "style_profile": _object_or_empty(template.get("style_profile")),
                "generated_prompt": str(template.get("generated_prompt") or ""),
                "source_metadata": _object_or_empty(template.get("source_metadata")),
                "import_metadata": {
                    **_object_or_empty(template.get("import_metadata")),
                    "import_schema": CANONICAL_STYLE_SCHEMA,
                },
            }
        return _legacy_payload_to_template_args(payload)

    def _template_payload(self, template: StyleTemplate) -> dict[str, Any]:
        return {
            "name": template.name,
            "description": template.description,
            "detail_level": template.detail_level,
            "global_prompt": template.global_prompt,
            "rewrite_prompt": template.rewrite_prompt,
            "style_profile": _loads_object(template.style_profile_json),
            "generated_prompt": template.generated_prompt,
            "source_metadata": _loads_object(template.source_metadata_json),
            "import_metadata": _loads_object(template.import_metadata_json),
            "version": template.version,
        }

    @staticmethod
    def _from_row(row) -> StyleTemplate:
        return StyleTemplate(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            detail_level=row["detail_level"],
            global_prompt=row["global_prompt"],
            rewrite_prompt=row["rewrite_prompt"],
            style_profile_json=row["style_profile_json"],
            generated_prompt=row["generated_prompt"],
            source_metadata_json=row["source_metadata_json"],
            import_metadata_json=row["import_metadata_json"],
            version=row["version"],
        )


def _legacy_payload_to_template_args(payload: dict[str, Any]) -> dict[str, Any]:
    rewrite_template = payload.get("rewriteTemplate")
    identify_template = payload.get("identifyTemplate")
    rewrite_prompt = ""
    style_profile: dict[str, Any] = {}
    if isinstance(rewrite_template, dict):
        rewrite_prompt = str(rewrite_template.get("commonPrompt") or rewrite_template.get("prompt") or "")
        category_prompts = rewrite_template.get("categoryPrompts")
        if category_prompts is not None:
            style_profile["legacy_category_prompts"] = category_prompts
    elif rewrite_template is not None:
        rewrite_prompt = str(rewrite_template)

    if isinstance(identify_template, dict) and identify_template.get("categories") is not None:
        style_profile["legacy_identify_categories"] = identify_template.get("categories")

    import_metadata = {
        "import_schema": "legacy",
        "legacy_fields": sorted(str(key) for key in payload.keys()),
    }
    if "breakthroughTemplate" in payload:
        import_metadata["legacy_breakthroughTemplate"] = payload.get("breakthroughTemplate")

    return {
        "name": str(payload.get("name") or "Imported style template"),
        "description": "Imported from legacy style/prompt template JSON.",
        "detail_level": "standard",
        "global_prompt": "",
        "rewrite_prompt": rewrite_prompt,
        "style_profile": style_profile,
        "generated_prompt": rewrite_prompt,
        "source_metadata": {},
        "import_metadata": import_metadata,
    }


def _required_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Style template name is required.")
    return name


def _validate_detail_level(value: str) -> str:
    level = value.strip().lower()
    if level not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported style template detail level: {value}")
    return level


def _object_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _loads_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
