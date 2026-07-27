from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import default_database_path
from rusty.services.style_service import DETAIL_LEVELS


MAIN_CHARACTER_PRIORITY = 80


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
                self._ensure_project_exists(project_id)
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
                self._ensure_project_exists(project_id)
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
        with session(self.database_path) as connection:
            tag_ids = [
                int(row["tag_id"])
                for row in connection.execute(
                    "SELECT tag_id FROM character_tag_links WHERE character_card_id = ?",
                    (source.id,),
                ).fetchall()
            ]
            self._replace_character_tags(connection, copied_id, tag_ids)
        return copied_id

    def delete_character_card(self, card_id: int) -> None:
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

    def list_character_cards(
        self,
        scope: str | None = None,
        project_id: int | None = None,
        tag_id: int | None = None,
        analysis_status: str | None = None,
        untagged: bool = False,
    ) -> list[CharacterCard]:
        clauses = ["c.deleted_at IS NULL"]
        parameters: list[object] = []
        if scope is not None:
            _validate_character_scope(scope, project_id if scope == "project" else None)
            clauses.append("c.scope = ?")
            parameters.append(scope)
        if project_id is not None:
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
        if untagged:
            clauses.append("NOT EXISTS (SELECT 1 FROM character_tag_links tl WHERE tl.character_card_id = c.id)")
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, 0 AS sort_order,
                       COALESCE(GROUP_CONCAT(t.name, char(31)), '') AS tag_names
                FROM character_cards c
                LEFT JOIN character_tag_links link ON link.character_card_id = c.id
                LEFT JOIN character_tags t ON t.id = link.tag_id AND t.deleted_at IS NULL
                WHERE {' AND '.join(clauses)}
                GROUP BY c.id
                ORDER BY c.updated_at DESC, c.id DESC
                """,
                parameters,
            ).fetchall()
        return [self._character_from_row(row) for row in rows]

    def get_character_card(self, card_id: int) -> CharacterCard | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT c.*, 0 AS sort_order,
                       COALESCE(GROUP_CONCAT(t.name, char(31)), '') AS tag_names
                FROM character_cards c
                LEFT JOIN character_tag_links link ON link.character_card_id = c.id
                LEFT JOIN character_tags t ON t.id = link.tag_id AND t.deleted_at IS NULL
                WHERE c.id = ? AND c.deleted_at IS NULL
                GROUP BY c.id
                """,
                (card_id,),
            ).fetchone()
        return self._character_from_row(row) if row is not None else None

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
                """
                SELECT c.*, b.sort_order,
                       COALESCE(GROUP_CONCAT(t.name, char(31)), '') AS tag_names
                FROM project_character_bindings b
                JOIN character_cards c ON c.id = b.character_card_id
                LEFT JOIN character_tag_links link ON link.character_card_id = c.id
                LEFT JOIN character_tags t ON t.id = link.tag_id AND t.deleted_at IS NULL
                WHERE b.project_id = ?
                  AND b.is_active = 1
                  AND c.deleted_at IS NULL
                GROUP BY c.id, b.sort_order
                ORDER BY b.sort_order, c.priority DESC, c.id
                """,
                (project_id,),
            ).fetchall()
        return [self._character_from_row(row) for row in rows]

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

    def analyze_character_card(
        self,
        card_id: int,
        *,
        identity: str,
        age: str,
        setting_text: str,
        custom_fields: list[dict[str, Any]],
        model_id: int | None = None,
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
    def _character_from_row(row) -> CharacterCard:
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
        )


def _card_is_relevant(card: CharacterCard, chapter_text: str) -> bool:
    if card.is_main or card.priority >= MAIN_CHARACTER_PRIORITY:
        return True
    lowered_text = chapter_text.lower()
    names = [card.name, *card.aliases]
    return any(name and name.lower() in lowered_text for name in names)


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


def _normalize_tag_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _normalize_custom_fields(fields: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, field in enumerate(fields or []):
        label = str(field.get("label") or "").strip()
        if not label:
            continue
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


def _loads_json(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback
