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
    sort_order: int = 0

    @property
    def aliases(self) -> list[str]:
        value = _loads_json(self.aliases_json, [])
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


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
    ) -> int:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO character_cards (
                    name, aliases_json, description, priority, is_main, relationship_notes,
                    personality, speech_style, action_constraints, anti_ooc_rules,
                    profile_json, source_metadata_json, import_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            return int(cursor.lastrowid)

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
    ) -> None:
        with session(self.database_path) as connection:
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
                    card_id,
                ),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Character card not found: {card_id}")

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

    def list_character_cards(self) -> list[CharacterCard]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, name, aliases_json, description, priority, is_main, relationship_notes,
                       personality, speech_style, action_constraints, anti_ooc_rules, profile_json,
                       source_metadata_json, import_metadata_json, version, 0 AS sort_order
                FROM character_cards
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._character_from_row(row) for row in rows]

    def get_character_card(self, card_id: int) -> CharacterCard | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT id, name, aliases_json, description, priority, is_main, relationship_notes,
                       personality, speech_style, action_constraints, anti_ooc_rules, profile_json,
                       source_metadata_json, import_metadata_json, version, 0 AS sort_order
                FROM character_cards
                WHERE id = ? AND deleted_at IS NULL
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
                SELECT c.id, c.name, c.aliases_json, c.description, c.priority, c.is_main,
                       c.relationship_notes, c.personality, c.speech_style, c.action_constraints,
                       c.anti_ooc_rules, c.profile_json, c.source_metadata_json,
                       c.import_metadata_json, c.version, b.sort_order
                FROM project_character_bindings b
                JOIN character_cards c ON c.id = b.character_card_id
                WHERE b.project_id = ?
                  AND b.is_active = 1
                  AND c.deleted_at IS NULL
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

    def _ensure_project_exists(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Project not found: {project_id}")

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
            sort_order=row["sort_order"],
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


def _loads_json(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback
