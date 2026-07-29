from __future__ import annotations

import json
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import default_database_path
from rusty.services.style_service import DETAIL_LEVELS


MAIN_CHARACTER_PRIORITY = 80

CHARACTER_RELATION_COLUMNS = """
    COALESCE((
        SELECT GROUP_CONCAT(name, char(31))
        FROM (
            SELECT DISTINCT t.name AS name
            FROM character_tag_links link
            JOIN character_tags t ON t.id = link.tag_id
            WHERE link.character_card_id = c.id AND t.deleted_at IS NULL
            ORDER BY t.sort_order, t.name
        )
    ), '') AS tag_names,
    COALESCE((
        SELECT GROUP_CONCAT(id, char(31))
        FROM (
            SELECT DISTINCT category.id AS id
            FROM character_category_links link
            JOIN character_categories category ON category.id = link.category_id
            WHERE link.character_card_id = c.id AND category.deleted_at IS NULL
            ORDER BY category.sort_order, category.name
        )
    ), '') AS category_ids_text,
    COALESCE((
        SELECT GROUP_CONCAT(name, char(31))
        FROM (
            SELECT DISTINCT category.name AS name
            FROM character_category_links link
            JOIN character_categories category ON category.id = link.category_id
            WHERE link.character_card_id = c.id AND category.deleted_at IS NULL
            ORDER BY category.sort_order, category.name
        )
    ), '') AS category_names
"""


@dataclass(frozen=True)
class OutlineTemplate:
    id: int
    name: str
    description: str
    detail_level: str
    outline_json: str
    anchor_prompt: str
    source_metadata_json: str
    import_metadata_json: str
    version: int


@dataclass(frozen=True)
class CharacterCard:
    id: int
    name: str
    aliases_json: str
    description: str
    priority: int
    is_main: bool
    relationship_notes: str
    personality: str
    speech_style: str
    action_constraints: str
    anti_ooc_rules: str
    profile_json: str
    source_metadata_json: str
    import_metadata_json: str
    version: int
    scope: str = "public"
    project_id: int | None = None
    source_character_card_id: int | None = None
    source_version: int | None = None
    sort_order: int = 0
    identity: str = ""
    age: str = ""
    setting_text: str = ""
    custom_fields_json: str = "[]"
    raw_text: str = ""
    analysis_status: str = "analyzed"
    cover_path: str | None = None
    cover_updated_at: str | None = None
    tags: tuple[str, ...] = ()
    category_ids: tuple[int, ...] = ()
    categories: tuple[str, ...] = ()
    source_summary: CharacterSourceSummary | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def aliases(self) -> list[str]:
        value = _loads_json(self.aliases_json, [])
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @property
    def profile(self) -> dict[str, Any]:
        value = _loads_json(self.profile_json, {})
        return value if isinstance(value, dict) else {}

    @property
    def source_metadata(self) -> dict[str, Any]:
        value = _loads_json(self.source_metadata_json, {})
        return value if isinstance(value, dict) else {}

    @property
    def import_metadata(self) -> dict[str, Any]:
        value = _loads_json(self.import_metadata_json, {})
        return value if isinstance(value, dict) else {}

    @property
    def custom_fields(self) -> list[dict[str, Any]]:
        value = _loads_json(self.custom_fields_json, [])
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


@dataclass(frozen=True)
class CharacterCategory:
    id: int
    name: str
    normalized_name: str
    sort_order: int
    resource_count: int


@dataclass(frozen=True)
class CharacterSourceSummary:
    kind: str
    label: str
    document_id: int | None = None
    chapter_id: int | None = None
    project_id: int | None = None
    source_card_id: int | None = None


@dataclass(frozen=True)
class CharacterProjectSummary:
    project_id: int
    project_name: str
    character_count: int
    updated_at: str


class AnchorService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def create_outline_template(
        self,
        name: str,
        description: str = "",
        detail_level: str = "standard",
        outline: dict[str, Any] | None = None,
        anchor_prompt: str = "",
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
    ) -> int:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO outline_templates (
                    name,
                    description,
                    detail_level,
                    outline_json,
                    anchor_prompt,
                    source_metadata_json,
                    import_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _required_name(name, "Outline template name is required."),
                    description,
                    _validate_detail_level(detail_level),
                    json.dumps(outline or {}, ensure_ascii=False),
                    anchor_prompt,
                    json.dumps(source_metadata or {}, ensure_ascii=False),
                    json.dumps(import_metadata or {}, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def update_outline_template(
        self,
        template_id: int,
        name: str,
        description: str = "",
        detail_level: str = "standard",
        outline: dict[str, Any] | None = None,
        anchor_prompt: str = "",
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
    ) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE outline_templates
                SET
                    name = ?,
                    description = ?,
                    detail_level = ?,
                    outline_json = ?,
                    anchor_prompt = ?,
                    source_metadata_json = ?,
                    import_metadata_json = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    _required_name(name, "Outline template name is required."),
                    description,
                    _validate_detail_level(detail_level),
                    json.dumps(outline or {}, ensure_ascii=False),
                    anchor_prompt,
                    json.dumps(source_metadata or {}, ensure_ascii=False),
                    json.dumps(import_metadata or {}, ensure_ascii=False),
                    template_id,
                ),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Outline template not found: {template_id}")

    def delete_outline_template(self, template_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE outline_templates
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (template_id,),
            )
            connection.execute(
                """
                UPDATE project_outline_bindings
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE outline_template_id = ?
                """,
                (template_id,),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Outline template not found: {template_id}")

    def list_outline_templates(self) -> list[OutlineTemplate]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, name, description, detail_level, outline_json, anchor_prompt,
                       source_metadata_json, import_metadata_json, version
                FROM outline_templates
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._outline_from_row(row) for row in rows]

    def get_outline_template(self, template_id: int) -> OutlineTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT id, name, description, detail_level, outline_json, anchor_prompt,
                       source_metadata_json, import_metadata_json, version
                FROM outline_templates
                WHERE id = ? AND deleted_at IS NULL
                """,
                (template_id,),
            ).fetchone()
        return self._outline_from_row(row) if row is not None else None

    def bind_project_outline(self, project_id: int, template_id: int) -> None:
        if self.get_outline_template(template_id) is None:
            raise ValueError(f"Outline template not found: {template_id}")
        self._ensure_project_exists(project_id)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO project_outline_bindings (project_id, outline_template_id, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(project_id)
                DO UPDATE SET
                    outline_template_id = excluded.outline_template_id,
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, template_id),
            )

    def unbind_project_outline(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE project_outline_bindings
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ?
                """,
                (project_id,),
            )

    def get_project_outline_template(self, project_id: int) -> OutlineTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT o.id, o.name, o.description, o.detail_level, o.outline_json, o.anchor_prompt,
                       o.source_metadata_json, o.import_metadata_json, o.version
                FROM project_outline_bindings b
                JOIN outline_templates o ON o.id = b.outline_template_id
                WHERE b.project_id = ?
                  AND b.is_active = 1
                  AND o.deleted_at IS NULL
                """,
                (project_id,),
            ).fetchone()
        return self._outline_from_row(row) if row is not None else None

    def create_character_card(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str = "",
        priority: int = 50,
        is_main: bool = False,
        relationship_notes: str = "",
        personality: str = "",
        speech_style: str = "",
        action_constraints: str = "",
        anti_ooc_rules: str = "",
        profile: dict[str, Any] | None = None,
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
        scope: str = "public",
        project_id: int | None = None,
        source_character_card_id: int | None = None,
        source_version: int | None = None,
        identity: str = "",
        age: str = "",
        setting_text: str = "",
        custom_fields: list[dict[str, Any]] | None = None,
        raw_text: str = "",
        analysis_status: str = "analyzed",
        tag_ids: list[int] | None = None,
    ) -> int:
        _validate_character_scope(scope, project_id)
        analysis_status = _validate_analysis_status(analysis_status)
        custom_fields_json = json.dumps(_normalize_custom_fields(custom_fields), ensure_ascii=False)
        with session(self.database_path) as connection:
            if project_id is not None:
                if connection.execute(
                    "SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL",
                    (project_id,),
                ).fetchone() is None:
                    raise ValueError(f"Project not found: {project_id}")
            cursor = connection.execute(
                """
                INSERT INTO character_cards (
                    name, aliases_json, description, priority, is_main, relationship_notes,
                    personality, speech_style, action_constraints, anti_ooc_rules,
                    profile_json, source_metadata_json, import_metadata_json,
                    scope, project_id, source_character_card_id, source_version,
                    identity, age, setting_text, custom_fields_json, raw_text, analysis_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _required_name(name, "Character card name is required."),
                    json.dumps(_clean_aliases(aliases), ensure_ascii=False),
                    description,
                    _clamp_priority(priority),
                    1 if is_main else 0,
                    relationship_notes,
                    personality,
                    speech_style,
                    action_constraints,
                    anti_ooc_rules,
                    json.dumps(profile or {}, ensure_ascii=False),
                    json.dumps(source_metadata or {}, ensure_ascii=False),
                    json.dumps(import_metadata or {}, ensure_ascii=False),
                    scope,
                    project_id,
                    source_character_card_id,
                    source_version,
                    identity.strip(),
                    age.strip(),
                    setting_text,
                    custom_fields_json,
                    raw_text,
                    analysis_status,
                ),
            )
            card_id = int(cursor.lastrowid)
            self._replace_character_tags(connection, card_id, tag_ids or [])
            if scope == "project":
                connection.execute(
                    """
                    INSERT INTO project_character_bindings (
                        project_id, character_card_id, sort_order, is_active
                    ) VALUES (?, ?, 0, 1)
                    """,
                    (project_id, card_id),
                )
            return card_id

    def update_character_card(
        self,
        card_id: int,
        name: str,
        aliases: list[str] | None = None,
        description: str = "",
        priority: int = 50,
        is_main: bool = False,
        relationship_notes: str = "",
        personality: str = "",
        speech_style: str = "",
        action_constraints: str = "",
        anti_ooc_rules: str = "",
        profile: dict[str, Any] | None = None,
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
        scope: str = "public",
        project_id: int | None = None,
        identity: str = "",
        age: str = "",
        setting_text: str = "",
        custom_fields: list[dict[str, Any]] | None = None,
        raw_text: str | None = None,
        analysis_status: str | None = None,
        tag_ids: list[int] | None = None,
    ) -> None:
        _validate_character_scope(scope, project_id)
        status = _validate_analysis_status(analysis_status) if analysis_status is not None else None
        custom_fields_json = json.dumps(_normalize_custom_fields(custom_fields), ensure_ascii=False)
        with session(self.database_path) as connection:
            if project_id is not None:
                if connection.execute(
                    "SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL",
                    (project_id,),
                ).fetchone() is None:
                    raise ValueError(f"Project not found: {project_id}")
            cursor = connection.execute(
                """
                UPDATE character_cards
                SET
                    name = ?,
                    aliases_json = ?,
                    description = ?,
                    priority = ?,
                    is_main = ?,
                    relationship_notes = ?,
                    personality = ?,
                    speech_style = ?,
                    action_constraints = ?,
                    anti_ooc_rules = ?,
                    profile_json = ?,
                    source_metadata_json = ?,
                    import_metadata_json = ?,
                    scope = ?,
                    project_id = ?,
                    identity = ?,
                    age = ?,
                    setting_text = ?,
                    custom_fields_json = ?,
                    raw_text = COALESCE(?, raw_text),
                    analysis_status = COALESCE(?, analysis_status),
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    _required_name(name, "Character card name is required."),
                    json.dumps(_clean_aliases(aliases), ensure_ascii=False),
                    description,
                    _clamp_priority(priority),
                    1 if is_main else 0,
                    relationship_notes,
                    personality,
                    speech_style,
                    action_constraints,
                    anti_ooc_rules,
                    json.dumps(profile or {}, ensure_ascii=False),
                    json.dumps(source_metadata or {}, ensure_ascii=False),
                    json.dumps(import_metadata or {}, ensure_ascii=False),
                    scope,
                    project_id,
                    identity.strip(),
                    age.strip(),
                    setting_text,
                    custom_fields_json,
                    raw_text,
                    status,
                    card_id,
                ),
            )
            if tag_ids is not None:
                self._replace_character_tags(connection, card_id, tag_ids)
            if scope == "project":
                connection.execute(
                    """
                    INSERT INTO project_character_bindings (
                        project_id, character_card_id, sort_order, is_active
                    ) VALUES (?, ?, 0, 1)
                    ON CONFLICT(project_id, character_card_id)
                    DO UPDATE SET is_active = 1, updated_at = CURRENT_TIMESTAMP
                    """,
                    (project_id, card_id),
                )
                connection.execute(
                    """
                    UPDATE project_character_bindings
                    SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE character_card_id = ? AND project_id <> ?
                    """,
                    (card_id, project_id),
                )
                connection.execute(
                    "DELETE FROM character_category_links WHERE character_card_id = ?",
                    (card_id,),
                )
            else:
                connection.execute(
                    """
                    UPDATE project_character_bindings
                    SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE character_card_id = ?
                    """,
                    (card_id,),
                )
        if cursor.rowcount == 0:
            raise ValueError(f"Character card not found: {card_id}")

    def copy_character_card(
        self,
        card_id: int,
        *,
        target_scope: str,
        target_project_id: int | None = None,
    ) -> int:
        source = self.get_character_card(card_id)
        if source is None:
            raise ValueError(f"Character card not found: {card_id}")
        _validate_character_scope(target_scope, target_project_id)
        copied_id = self.create_character_card(
            name=source.name,
            aliases=source.aliases,
            description=source.description,
            priority=source.priority,
            is_main=source.is_main,
            relationship_notes=source.relationship_notes,
            personality=source.personality,
            speech_style=source.speech_style,
            action_constraints=source.action_constraints,
            anti_ooc_rules=source.anti_ooc_rules,
            profile=source.profile,
            source_metadata={
                **source.source_metadata,
                "copied_from_scope": source.scope,
                "copied_from_project_id": source.project_id,
            },
            import_metadata={
                **source.import_metadata,
                "created_by": "character_card_copy",
            },
            scope=target_scope,
            project_id=target_project_id,
            source_character_card_id=source.id,
            source_version=source.version,
            identity=source.identity,
            age=source.age,
            setting_text=source.setting_text,
            custom_fields=source.custom_fields,
            raw_text=source.raw_text,
            analysis_status=source.analysis_status,
        )
        try:
            with session(self.database_path) as connection:
                tag_ids = [
                    int(row["tag_id"])
                    for row in connection.execute(
                        "SELECT tag_id FROM character_tag_links WHERE character_card_id = ?",
                        (source.id,),
                    ).fetchall()
                ]
                self._replace_character_tags(connection, copied_id, tag_ids)
            source_cover = self.character_cover_file(source.id)
            if source.cover_path and source_cover is None:
                raise ValueError("Source character cover is missing or outside the managed directory.")
            if source_cover is not None:
                self.save_character_cover(copied_id, source_cover.read_bytes())
        except Exception:
            copied = self.get_character_card(copied_id)
            copied_cover = copied.cover_path if copied is not None else None
            with session(self.database_path) as connection:
                connection.execute(
                    "DELETE FROM project_character_bindings WHERE character_card_id = ?",
                    (copied_id,),
                )
                connection.execute("DELETE FROM character_cards WHERE id = ?", (copied_id,))
            self._remove_managed_cover(copied_cover)
            raise
        return copied_id

    def copy_public_character_to_project(
        self,
        source_card_id: int,
        target_project_id: int,
    ) -> int:
        source = self.get_character_card(source_card_id)
        if source is None:
            raise ValueError(f"Character card not found: {source_card_id}")
        if source.scope != "public":
            raise ValueError("Only public character cards can be copied to a project.")

        cover_data: bytes | None = None
        if source.cover_path:
            source_cover = self.character_cover_file(source.id)
            if source_cover is None:
                raise ValueError("Source character cover is missing or outside the managed directory.")
            cover_data = source_cover.read_bytes()

        created_cover: Path | None = None
        try:
            with session(self.database_path) as connection:
                if connection.execute(
                    "SELECT 1 FROM projects WHERE id = ? AND deleted_at IS NULL",
                    (target_project_id,),
                ).fetchone() is None:
                    raise ValueError(f"Project not found: {target_project_id}")
                cursor = connection.execute(
                    """
                    INSERT INTO character_cards (
                        name, aliases_json, description, priority, is_main, relationship_notes,
                        personality, speech_style, action_constraints, anti_ooc_rules,
                        profile_json, source_metadata_json, import_metadata_json,
                        scope, project_id, source_character_card_id, source_version,
                        identity, age, setting_text, custom_fields_json, raw_text, analysis_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'project', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source.name,
                        source.aliases_json,
                        source.description,
                        source.priority,
                        1 if source.is_main else 0,
                        source.relationship_notes,
                        source.personality,
                        source.speech_style,
                        source.action_constraints,
                        source.anti_ooc_rules,
                        source.profile_json,
                        json.dumps(
                            {
                                **source.source_metadata,
                                "copied_from_scope": "public",
                                "source_character_card_id": source.id,
                                "public_baseline": {
                                    "source_card_id": source.id,
                                    "source_version": source.version,
                                    "stable_fields": _stable_character_fields(source),
                                },
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {**source.import_metadata, "created_by": "character_public_copy"},
                            ensure_ascii=False,
                        ),
                        target_project_id,
                        source.id,
                        source.version,
                        source.identity,
                        source.age,
                        source.setting_text,
                        source.custom_fields_json,
                        source.raw_text,
                        source.analysis_status,
                    ),
                )
                copied_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO character_tag_links (character_card_id, tag_id)
                    SELECT ?, tag_id
                    FROM character_tag_links
                    WHERE character_card_id = ?
                    """,
                    (copied_id, source.id),
                )
                connection.execute(
                    """
                    INSERT INTO project_character_bindings (
                        project_id, character_card_id, sort_order, is_active
                    ) VALUES (?, ?, 0, 1)
                    """,
                    (target_project_id, copied_id),
                )
                if cover_data is not None:
                    extension, width, height = _inspect_cover(cover_data)
                    if len(cover_data) > 5 * 1024 * 1024:
                        raise ValueError("Character cover must be 5 MB or smaller.")
                    if width is not None and height is not None and (width > 4096 or height > 4096):
                        raise ValueError("Character cover dimensions must not exceed 4096×4096.")
                    cover_dir = self.database_path.parent / "assets" / "character-covers"
                    cover_dir.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256(cover_data).hexdigest()
                    created_cover = cover_dir / f"{copied_id}-{digest[:20]}.{extension}"
                    created_cover.write_bytes(cover_data)
                    relative = created_cover.relative_to(self.database_path.parent).as_posix()
                    connection.execute(
                        """
                        UPDATE character_cards
                        SET cover_path = ?, cover_updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (relative, copied_id),
                    )
            return copied_id
        except Exception:
            if created_cover is not None and created_cover.is_file():
                created_cover.unlink()
            raise

    def find_active_project_copy(
        self,
        source_card_id: int,
        target_project_id: int,
    ) -> CharacterCard | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                f"""
                SELECT c.*, binding.sort_order,
                       {CHARACTER_RELATION_COLUMNS}
                FROM project_character_bindings binding
                JOIN character_cards c ON c.id = binding.character_card_id
                WHERE binding.project_id = ?
                  AND binding.is_active = 1
                  AND c.deleted_at IS NULL
                  AND c.scope = 'project'
                  AND c.source_character_card_id = ?
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT 1
                """,
                (target_project_id, source_card_id),
            ).fetchone()
            return (
                self._character_from_row(
                    row,
                    source_summary=self._character_source_summary(connection, row),
                )
                if row is not None
                else None
            )

    def publish_project_character_to_public(
        self,
        source_card_id: int,
        selected_fields: list[str],
    ) -> int:
        source = self.get_character_card(source_card_id)
        if source is None:
            raise ValueError(f"Character card not found: {source_card_id}")
        if source.scope != "project" or source.project_id is None:
            raise ValueError("Only project characters can be saved as public characters.")
        selected = set(selected_fields)
        if "name" not in selected:
            raise ValueError("Publishing a project character requires the name field.")
        stable = _stable_character_fields(source)
        tag_ids: list[int] = []
        if "tags" in selected:
            with session(self.database_path) as connection:
                tag_ids = [
                    int(row["tag_id"])
                    for row in connection.execute(
                        "SELECT tag_id FROM character_tag_links WHERE character_card_id = ?",
                        (source.id,),
                    ).fetchall()
                ]
        published_id = self.create_character_card(
            name=str(stable["name"]),
            aliases=list(stable["aliases"]) if "aliases" in selected else [],
            description=str(stable["description"]) if "description" in selected else "",
            relationship_notes=(
                str(stable["relationship_notes"])
                if "relationship_notes" in selected
                else ""
            ),
            personality=str(stable["personality"]) if "personality" in selected else "",
            speech_style=str(stable["speech_style"]) if "speech_style" in selected else "",
            action_constraints=(
                str(stable["action_constraints"])
                if "action_constraints" in selected
                else ""
            ),
            anti_ooc_rules=(
                str(stable["anti_ooc_rules"])
                if "anti_ooc_rules" in selected
                else ""
            ),
            profile=dict(stable["profile"]) if "profile" in selected else {},
            source_metadata={
                "source_kind": "project_copy",
                "source_project_character_id": source.id,
                "source_project_id": source.project_id,
            },
            import_metadata={"created_by": "project_character_publish"},
            scope="public",
            project_id=None,
            identity=str(stable["identity"]) if "identity" in selected else "",
            age=str(stable["age"]) if "age" in selected else "",
            setting_text=str(stable["setting_text"]) if "setting_text" in selected else "",
            custom_fields=(
                list(stable["custom_fields"])
                if "custom_fields" in selected
                else []
            ),
            raw_text="",
            analysis_status=source.analysis_status,
            tag_ids=tag_ids,
        )
        if "cover" in selected and source.cover_path:
            cover = self.character_cover_file(source.id)
            if cover is None:
                raise ValueError("Source character cover is missing or outside the managed directory.")
            try:
                self.save_character_cover(published_id, cover.read_bytes())
            except Exception:
                with session(self.database_path) as connection:
                    connection.execute(
                        "DELETE FROM character_cards WHERE id = ?",
                        (published_id,),
                    )
                raise
        return published_id

    def delete_character_card(self, card_id: int) -> None:
        card = self.get_character_card(card_id)
        if card is None:
            raise ValueError(f"Character card not found: {card_id}")
        cover_path = card.cover_path
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE character_cards
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (card_id,),
            )
            connection.execute(
                """
                UPDATE project_character_bindings
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE character_card_id = ?
                """,
                (card_id,),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Character card not found: {card_id}")
        self._remove_managed_cover(cover_path)

    def list_character_cards(
        self,
        scope: str | None = None,
        project_id: int | None = None,
        tag_id: int | None = None,
        category_id: int | None = None,
        analysis_status: str | None = None,
        untagged: bool = False,
    ) -> list[CharacterCard]:
        clauses = ["c.deleted_at IS NULL"]
        parameters: list[object] = []
        from_clause = "character_cards c"
        sort_order = "0"
        order_by = "c.updated_at DESC, c.id DESC"
        if scope is not None:
            _validate_character_scope(scope, project_id if scope == "project" else None)
            clauses.append("c.scope = ?")
            parameters.append(scope)
        if scope == "project" and project_id is not None:
            from_clause = (
                "project_character_bindings binding "
                "JOIN character_cards c ON c.id = binding.character_card_id"
            )
            clauses.extend(["binding.project_id = ?", "binding.is_active = 1"])
            parameters.append(project_id)
            sort_order = "binding.sort_order"
            order_by = "binding.sort_order, c.updated_at DESC, c.id DESC"
        elif project_id is not None:
            clauses.append("c.project_id = ?")
            parameters.append(project_id)
        if analysis_status is not None:
            clauses.append("c.analysis_status = ?")
            parameters.append(_validate_analysis_status(analysis_status))
        if tag_id is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM character_tag_links filter_link "
                "WHERE filter_link.character_card_id = c.id AND filter_link.tag_id = ?)"
            )
            parameters.append(tag_id)
        if category_id is not None:
            clauses.extend(
                [
                    "c.scope = 'public'",
                    (
                        "EXISTS (SELECT 1 FROM character_category_links category_filter "
                        "WHERE category_filter.character_card_id = c.id "
                        "AND category_filter.category_id = ?)"
                    ),
                ]
            )
            parameters.append(category_id)
        if untagged:
            clauses.append("NOT EXISTS (SELECT 1 FROM character_tag_links tl WHERE tl.character_card_id = c.id)")
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, {sort_order} AS sort_order,
                       {CHARACTER_RELATION_COLUMNS}
                FROM {from_clause}
                WHERE {' AND '.join(clauses)}
                ORDER BY {order_by}
                """,
                parameters,
            ).fetchall()
            return [
                self._character_from_row(
                    row,
                    source_summary=self._character_source_summary(connection, row),
                )
                for row in rows
            ]

    def get_character_card(self, card_id: int) -> CharacterCard | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                f"""
                SELECT c.*, 0 AS sort_order,
                       {CHARACTER_RELATION_COLUMNS}
                FROM character_cards c
                WHERE c.id = ? AND c.deleted_at IS NULL
                """,
                (card_id,),
            ).fetchone()
            return (
                self._character_from_row(
                    row,
                    source_summary=self._character_source_summary(connection, row),
                )
                if row is not None
                else None
            )

    def bind_project_character(self, project_id: int, card_id: int, sort_order: int = 0) -> None:
        if self.get_character_card(card_id) is None:
            raise ValueError(f"Character card not found: {card_id}")
        self._ensure_project_exists(project_id)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO project_character_bindings (project_id, character_card_id, sort_order, is_active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(project_id, character_card_id)
                DO UPDATE SET
                    sort_order = excluded.sort_order,
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, card_id, sort_order),
            )

    def unbind_project_character(self, project_id: int, card_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE project_character_bindings
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ? AND character_card_id = ?
                """,
                (project_id, card_id),
            )

    def list_project_character_cards(self, project_id: int) -> list[CharacterCard]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, b.sort_order,
                       {CHARACTER_RELATION_COLUMNS}
                FROM project_character_bindings b
                JOIN character_cards c ON c.id = b.character_card_id
                WHERE b.project_id = ?
                  AND b.is_active = 1
                  AND c.deleted_at IS NULL
                ORDER BY b.sort_order, c.priority DESC, c.id
                """,
                (project_id,),
            ).fetchall()
            return [
                self._character_from_row(
                    row,
                    source_summary=self._character_source_summary(connection, row),
                )
                for row in rows
            ]

    def list_relevant_project_character_cards(self, project_id: int, chapter_text: str) -> list[CharacterCard]:
        return [
            card
            for card in self.list_project_character_cards(project_id)
            if _card_is_relevant(card, chapter_text)
        ]

    def list_character_tags(self) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT t.*, COUNT(c.id) AS resource_count
                FROM character_tags t
                LEFT JOIN character_tag_links link ON link.tag_id = t.id
                LEFT JOIN character_cards c ON c.id = link.character_card_id AND c.deleted_at IS NULL
                WHERE t.deleted_at IS NULL
                GROUP BY t.id
                ORDER BY t.sort_order, t.name
                """
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "normalized_name": str(row["normalized_name"]),
                "sort_order": int(row["sort_order"]),
                "resource_count": int(row["resource_count"]),
            }
            for row in rows
        ]

    def create_character_tag(self, name: str) -> dict[str, Any]:
        normalized = _required_tag_name(name)
        key = _normalize_tag_name(normalized)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO character_tags (name, normalized_name)
                VALUES (?, ?)
                ON CONFLICT(normalized_name) WHERE deleted_at IS NULL
                DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """,
                (normalized, key),
            )
        return next(item for item in self.list_character_tags() if item["normalized_name"] == key)

    def rename_character_tag(self, tag_id: int, name: str) -> dict[str, Any]:
        normalized = _required_tag_name(name)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE character_tags
                SET name = ?, normalized_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (normalized, _normalize_tag_name(normalized), tag_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Character tag not found: {tag_id}")
        return next(item for item in self.list_character_tags() if item["id"] == tag_id)

    def delete_character_tag(self, tag_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute("DELETE FROM character_tag_links WHERE tag_id = ?", (tag_id,))
            cursor = connection.execute(
                "UPDATE character_tags SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                (tag_id,),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Character tag not found: {tag_id}")

    def set_character_tag(self, card_id: int, tag_id: int, selected: bool) -> CharacterCard:
        with session(self.database_path) as connection:
            if connection.execute(
                "SELECT 1 FROM character_cards WHERE id = ? AND deleted_at IS NULL", (card_id,)
            ).fetchone() is None:
                raise ValueError(f"Character card not found: {card_id}")
            if connection.execute(
                "SELECT 1 FROM character_tags WHERE id = ? AND deleted_at IS NULL", (tag_id,)
            ).fetchone() is None:
                raise ValueError(f"Character tag not found: {tag_id}")
            if selected:
                connection.execute(
                    "INSERT OR IGNORE INTO character_tag_links (character_card_id, tag_id) VALUES (?, ?)",
                    (card_id, tag_id),
                )
            else:
                connection.execute(
                    "DELETE FROM character_tag_links WHERE character_card_id = ? AND tag_id = ?",
                    (card_id, tag_id),
                )
        card = self.get_character_card(card_id)
        if card is None:
            raise ValueError(f"Character card not found: {card_id}")
        return card

    def list_character_categories(self) -> list[CharacterCategory]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT category.id, category.name, category.normalized_name,
                       category.sort_order,
                       COUNT(DISTINCT CASE
                           WHEN card.scope = 'public' AND card.deleted_at IS NULL
                           THEN link.character_card_id
                       END) AS resource_count
                FROM character_categories category
                LEFT JOIN character_category_links link
                    ON link.category_id = category.id
                LEFT JOIN character_cards card
                    ON card.id = link.character_card_id
                WHERE category.deleted_at IS NULL
                GROUP BY category.id
                ORDER BY category.sort_order, category.name
                """
            ).fetchall()
        return [
            CharacterCategory(
                id=int(row["id"]),
                name=str(row["name"]),
                normalized_name=str(row["normalized_name"]),
                sort_order=int(row["sort_order"]),
                resource_count=int(row["resource_count"]),
            )
            for row in rows
        ]

    def create_character_category(self, name: str) -> CharacterCategory:
        category_name = _required_category_name(name)
        normalized_name = _normalize_tag_name(category_name)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO character_categories (name, normalized_name, sort_order)
                VALUES (
                    ?,
                    ?,
                    COALESCE((SELECT MAX(sort_order) + 1 FROM character_categories), 0)
                )
                ON CONFLICT(normalized_name) WHERE deleted_at IS NULL
                DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """,
                (category_name, normalized_name),
            )
        return next(
            category
            for category in self.list_character_categories()
            if category.normalized_name == normalized_name
        )

    def rename_character_category(self, category_id: int, name: str) -> CharacterCategory:
        category_name = _required_category_name(name)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE character_categories
                SET name = ?, normalized_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (category_name, _normalize_tag_name(category_name), category_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Character category not found: {category_id}")
        return next(
            category
            for category in self.list_character_categories()
            if category.id == category_id
        )

    def delete_character_category(self, category_id: int) -> None:
        with session(self.database_path) as connection:
            if connection.execute(
                "SELECT 1 FROM character_categories WHERE id = ? AND deleted_at IS NULL",
                (category_id,),
            ).fetchone() is None:
                raise ValueError(f"Character category not found: {category_id}")
            connection.execute(
                "DELETE FROM character_category_links WHERE category_id = ?",
                (category_id,),
            )
            connection.execute(
                """
                UPDATE character_categories
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (category_id,),
            )

    def set_character_category(
        self,
        card_id: int,
        category_id: int,
        selected: bool,
    ) -> CharacterCard:
        with session(self.database_path) as connection:
            if connection.execute(
                "SELECT 1 FROM character_categories WHERE id = ? AND deleted_at IS NULL",
                (category_id,),
            ).fetchone() is None:
                raise ValueError(f"Character category not found: {category_id}")
            card = connection.execute(
                "SELECT scope FROM character_cards WHERE id = ? AND deleted_at IS NULL",
                (card_id,),
            ).fetchone()
            if card is None:
                raise ValueError(f"Character card not found: {card_id}")
            if str(card["scope"]) != "public":
                raise ValueError("Only public character cards can belong to character categories.")
            if selected:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO character_category_links (
                        character_card_id, category_id
                    ) VALUES (?, ?)
                    """,
                    (card_id, category_id),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM character_category_links
                    WHERE character_card_id = ? AND category_id = ?
                    """,
                    (card_id, category_id),
                )
        updated = self.get_character_card(card_id)
        if updated is None:
            raise ValueError(f"Character card not found: {card_id}")
        return updated

    def list_character_project_summaries(self) -> list[CharacterProjectSummary]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT p.id AS project_id,
                       p.name AS project_name,
                       COUNT(DISTINCT CASE
                           WHEN binding.is_active = 1 AND card.deleted_at IS NULL
                           THEN binding.character_card_id
                       END) AS character_count,
                       p.updated_at
                FROM projects p
                LEFT JOIN project_character_bindings binding
                    ON binding.project_id = p.id
                LEFT JOIN character_cards card
                    ON card.id = binding.character_card_id
                WHERE p.deleted_at IS NULL
                GROUP BY p.id
                ORDER BY p.updated_at DESC, p.id DESC
                """
            ).fetchall()
        return [
            CharacterProjectSummary(
                project_id=int(row["project_id"]),
                project_name=str(row["project_name"]),
                character_count=int(row["character_count"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def analyze_character_card(
        self,
        card_id: int,
        *,
        identity: str,
        age: str,
        setting_text: str,
        custom_fields: list[dict[str, Any]],
        model_id: int | None = None,
        invocation_id: int | None = None,
    ) -> None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT import_metadata_json FROM character_cards WHERE id = ? AND deleted_at IS NULL",
                (card_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Character card not found: {card_id}")
            metadata = _loads_json(str(row["import_metadata_json"] or "{}"), {})
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["last_analyzed_model_id"] = model_id
            metadata["last_analysis_invocation_id"] = invocation_id
            connection.execute(
                """
                UPDATE character_cards
                SET identity = ?, age = ?, setting_text = ?, custom_fields_json = ?,
                    analysis_status = 'analyzed', import_metadata_json = ?,
                    version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    identity.strip(),
                    age.strip(),
                    setting_text,
                    json.dumps(_normalize_custom_fields(custom_fields), ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    card_id,
                ),
            )

    def save_character_cover(self, card_id: int, data: bytes) -> CharacterCard:
        current = self.get_character_card(card_id)
        if current is None:
            raise ValueError(f"Character card not found: {card_id}")
        extension, width, height = _inspect_cover(data)
        if len(data) > 5 * 1024 * 1024:
            raise ValueError("Character cover must be 5 MB or smaller.")
        if width is not None and height is not None and (width > 4096 or height > 4096):
            raise ValueError("Character cover dimensions must not exceed 4096×4096.")
        cover_dir = self.database_path.parent / "assets" / "character-covers"
        cover_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()
        target = cover_dir / f"{card_id}-{digest[:20]}.{extension}"
        target.write_bytes(data)
        relative = target.relative_to(self.database_path.parent).as_posix()
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE character_cards
                SET cover_path = ?, cover_updated_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (relative, card_id),
            )
        self._remove_managed_cover(current.cover_path, excluding=relative)
        updated = self.get_character_card(card_id)
        if updated is None:
            raise RuntimeError("Character card disappeared after cover update.")
        return updated

    def remove_character_cover(self, card_id: int) -> CharacterCard:
        current = self.get_character_card(card_id)
        if current is None:
            raise ValueError(f"Character card not found: {card_id}")
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE character_cards
                SET cover_path = NULL, cover_updated_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (card_id,),
            )
        self._remove_managed_cover(current.cover_path)
        updated = self.get_character_card(card_id)
        if updated is None:
            raise RuntimeError("Character card disappeared after cover removal.")
        return updated

    def character_cover_file(self, card_id: int) -> Path | None:
        card = self.get_character_card(card_id)
        if card is None or not card.cover_path:
            return None
        path = (self.database_path.parent / card.cover_path).resolve()
        root = (self.database_path.parent / "assets" / "character-covers").resolve()
        if root not in path.parents or not path.is_file():
            return None
        return path

    def _remove_managed_cover(self, value: str | None, *, excluding: str | None = None) -> None:
        if not value or value == excluding:
            return
        with session(self.database_path) as connection:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM character_cards WHERE cover_path = ? AND deleted_at IS NULL",
                    (value,),
                ).fetchone()[0]
            )
        if count:
            return
        path = (self.database_path.parent / value).resolve()
        root = (self.database_path.parent / "assets" / "character-covers").resolve()
        if root in path.parents and path.is_file():
            path.unlink()

    def _ensure_project_exists(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Project not found: {project_id}")

    @staticmethod
    def _replace_character_tags(connection, card_id: int, tag_ids: list[int]) -> None:
        connection.execute("DELETE FROM character_tag_links WHERE character_card_id = ?", (card_id,))
        for tag_id in dict.fromkeys(tag_ids):
            tag = connection.execute(
                "SELECT id FROM character_tags WHERE id = ? AND deleted_at IS NULL",
                (int(tag_id),),
            ).fetchone()
            if tag is None:
                raise ValueError(f"Character tag not found: {tag_id}")
            connection.execute(
                "INSERT INTO character_tag_links (character_card_id, tag_id) VALUES (?, ?)",
                (card_id, int(tag_id)),
            )

    @staticmethod
    def _outline_from_row(row) -> OutlineTemplate:
        return OutlineTemplate(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            detail_level=row["detail_level"],
            outline_json=row["outline_json"],
            anchor_prompt=row["anchor_prompt"],
            source_metadata_json=row["source_metadata_json"],
            import_metadata_json=row["import_metadata_json"],
            version=row["version"],
        )

    @staticmethod
    def _character_source_summary(connection, row) -> CharacterSourceSummary:
        source_metadata = _loads_json(str(row["source_metadata_json"] or "{}"), {})
        import_metadata = _loads_json(str(row["import_metadata_json"] or "{}"), {})
        source_metadata = source_metadata if isinstance(source_metadata, dict) else {}
        import_metadata = import_metadata if isinstance(import_metadata, dict) else {}
        created_by = str(import_metadata.get("created_by") or "")
        source_card_id = row["source_character_card_id"]

        if source_card_id is not None:
            source = connection.execute(
                "SELECT name, scope FROM character_cards WHERE id = ?",
                (source_card_id,),
            ).fetchone()
            source_name = str(source["name"]) if source is not None else f"#{source_card_id}"
            source_scope = str(source["scope"]) if source is not None else ""
            if str(row["scope"]) == "project" and source_scope == "public":
                return CharacterSourceSummary(
                    kind="public_copy",
                    label=f"公共角色“{source_name}”",
                    project_id=row["project_id"],
                    source_card_id=int(source_card_id),
                )
            return CharacterSourceSummary(
                kind="project_copy",
                label=f"工程角色“{source_name}”",
                project_id=row["project_id"],
                source_card_id=int(source_card_id),
            )

        source_kind = str(source_metadata.get("source_kind") or "")
        document_id = _optional_int(source_metadata.get("document_id"))
        chapter_id = _optional_int(source_metadata.get("chapter_id"))
        project_id = _optional_int(source_metadata.get("project_id"))
        if source_kind == "project_copy":
            source_project_character_id = _optional_int(
                source_metadata.get("source_project_character_id")
            )
            source_name = (
                connection.execute(
                    "SELECT name FROM character_cards WHERE id = ?",
                    (source_project_character_id,),
                ).fetchone()
                if source_project_character_id is not None
                else None
            )
            label_name = (
                str(source_name["name"])
                if source_name is not None
                else f"#{source_project_character_id}"
            )
            return CharacterSourceSummary(
                kind="project_copy",
                label=f"工程角色“{label_name}”",
                project_id=_optional_int(source_metadata.get("source_project_id")),
                source_card_id=source_project_character_id,
            )
        if source_kind == "document" and document_id is not None:
            document = connection.execute(
                "SELECT title FROM library_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            chapter = (
                connection.execute(
                    "SELECT title FROM library_document_chapters WHERE id = ?",
                    (chapter_id,),
                ).fetchone()
                if chapter_id is not None
                else None
            )
            title = str(document["title"]) if document is not None else f"文档 #{document_id}"
            label = f"《{title}》"
            if chapter is not None and str(chapter["title"]).strip():
                label += f" · {str(chapter['title']).strip()}"
            return CharacterSourceSummary(
                kind="document_selection",
                label=label,
                document_id=document_id,
                chapter_id=chapter_id,
            )
        if source_kind == "project" and project_id is not None:
            project = connection.execute(
                "SELECT name FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            project_name = str(project["name"]) if project is not None else f"#{project_id}"
            return CharacterSourceSummary(
                kind="project_selection",
                label=f"工程“{project_name}”",
                chapter_id=chapter_id,
                project_id=project_id,
            )
        if created_by.startswith("ai_"):
            return CharacterSourceSummary(
                kind="ai_extraction",
                label="AI 文本提取",
                document_id=document_id,
                chapter_id=chapter_id,
                project_id=project_id,
            )
        source_file_name = str(source_metadata.get("source_file_name") or "").strip()
        if source_file_name:
            return CharacterSourceSummary(
                kind="file_import",
                label=f"文件 {source_file_name}",
                project_id=project_id,
            )
        if not source_metadata and not import_metadata:
            return CharacterSourceSummary(kind="manual", label="手动创建")
        return CharacterSourceSummary(kind="manual", label="本地创建")

    @staticmethod
    def _character_from_row(
        row,
        *,
        source_summary: CharacterSourceSummary | None = None,
    ) -> CharacterCard:
        keys = set(row.keys())
        return CharacterCard(
            id=row["id"],
            name=row["name"],
            aliases_json=row["aliases_json"],
            description=row["description"],
            priority=row["priority"],
            is_main=bool(row["is_main"]),
            relationship_notes=row["relationship_notes"],
            personality=row["personality"],
            speech_style=row["speech_style"],
            action_constraints=row["action_constraints"],
            anti_ooc_rules=row["anti_ooc_rules"],
            profile_json=row["profile_json"],
            source_metadata_json=row["source_metadata_json"],
            import_metadata_json=row["import_metadata_json"],
            version=row["version"],
            scope=row["scope"],
            project_id=row["project_id"],
            source_character_card_id=row["source_character_card_id"],
            source_version=row["source_version"],
            sort_order=row["sort_order"],
            identity=row["identity"],
            age=row["age"],
            setting_text=row["setting_text"],
            custom_fields_json=row["custom_fields_json"],
            raw_text=row["raw_text"],
            analysis_status=row["analysis_status"],
            cover_path=row["cover_path"],
            cover_updated_at=row["cover_updated_at"],
            tags=tuple(item for item in str(row["tag_names"] or "").split(chr(31)) if item),
            category_ids=(
                tuple(
                    int(item)
                    for item in str(row["category_ids_text"] or "").split(chr(31))
                    if item
                )
                if "category_ids_text" in keys
                else ()
            ),
            categories=(
                tuple(
                    item
                    for item in str(row["category_names"] or "").split(chr(31))
                    if item
                )
                if "category_names" in keys
                else ()
            ),
            source_summary=source_summary,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _card_is_relevant(card: CharacterCard, chapter_text: str) -> bool:
    if card.is_main or card.priority >= MAIN_CHARACTER_PRIORITY:
        return True
    lowered_text = chapter_text.lower()
    names = [card.name, *card.aliases]
    return any(name and name.lower() in lowered_text for name in names)


def _stable_character_fields(card: CharacterCard) -> dict[str, Any]:
    return {
        "name": card.name,
        "aliases": card.aliases,
        "description": card.description,
        "identity": card.identity,
        "age": card.age,
        "setting_text": card.setting_text,
        "relationship_notes": card.relationship_notes,
        "personality": card.personality,
        "speech_style": card.speech_style,
        "action_constraints": card.action_constraints,
        "anti_ooc_rules": card.anti_ooc_rules,
        "profile": card.profile,
        "custom_fields": card.custom_fields,
        "tags": list(card.tags),
        "cover": card.cover_path,
    }


def _required_name(value: str, message: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError(message)
    return name


def _validate_detail_level(value: str) -> str:
    level = value.strip().lower()
    if level not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail level: {value}")
    return level


def _clean_aliases(aliases: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for alias in aliases or []:
        text = str(alias).strip()
        key = text.lower()
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
    return cleaned


def _clamp_priority(priority: int) -> int:
    return max(0, min(100, int(priority)))


def _validate_character_scope(scope: str, project_id: int | None) -> None:
    if scope not in {"public", "project"}:
        raise ValueError(f"Unsupported character scope: {scope}")
    if scope == "project" and project_id is None:
        raise ValueError("Project character cards require a project.")
    if scope == "public" and project_id is not None:
        raise ValueError("Public character cards cannot belong to a project.")


def _validate_analysis_status(value: str) -> str:
    if value not in {"unanalyzed", "analyzed"}:
        raise ValueError(f"Unsupported analysis status: {value}")
    return value


def _required_tag_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Tag name is required.")
    if len(normalized) > 40:
        raise ValueError("Tag name must be 40 characters or fewer.")
    return normalized


def _required_category_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Character category name is required.")
    if len(normalized) > 40:
        raise ValueError("Character category name must be 40 characters or fewer.")
    return normalized


def _normalize_tag_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_custom_fields(fields: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, field in enumerate(fields or []):
        label = " ".join(str(field.get("label") or "").strip().split())
        if not label:
            raise ValueError(f"Custom field {index + 1} requires a label.")
        key = label.casefold()
        if key in seen:
            raise ValueError(f"Duplicate custom field label: {label}")
        seen.add(key)
        normalized.append(
            {
                "id": str(field.get("id") or f"field_{index}"),
                "label": label,
                "value": str(field.get("value") or ""),
                "sort_order": len(normalized),
            }
        )
    return normalized


def _inspect_cover(data: bytes) -> tuple[str, int | None, int | None]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(data):
                break
            length = int.from_bytes(data[index : index + 2], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB}:
                if index + 7 > len(data):
                    break
                height = int.from_bytes(data[index + 3 : index + 5], "big")
                width = int.from_bytes(data[index + 5 : index + 7], "big")
                return "jpg", width, height
            index += max(length, 2)
        return "jpg", None, None
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", None, None
    raise ValueError("Character cover must be a PNG, JPEG, or WebP image.")


def _loads_json(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback
