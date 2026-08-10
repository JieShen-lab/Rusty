from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from rusty.content_hash import hash_text
from rusty.db import initialize_database, session
from rusty.serialization import json_object
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService


DEFAULT_FACT_LEDGER: dict[str, Any] = {
    "events": [],
    "characters_present": [],
    "character_changes": {},
    "location": "",
    "time_state": {},
    "objects": {},
    "knowledge_states": {},
    "relationship_changes": [],
    "open_threads": [],
    "resolved_threads": [],
    "foreshadowing": [],
    "required_start_state": {},
    "required_end_state": {},
}

DEFAULT_CHARACTER_STATE: dict[str, Any] = {
    "injuries": [],
    "location": "",
    "emotion": "",
    "current_goal": "",
    "known_secrets": [],
    "hidden_secrets": [],
    "possessions": [],
    "relationship_state": {},
    "recent_changes": [],
}

_TRANSITION_RE = re.compile(
    r"^(?:次日|翌日|当晚|夜里|清晨|黄昏|与此同时|片刻后|不久后|数日后|"
    r"另一边|另一处|回到|转眼|话分两头|镜头一转|场景转换|时间来到|地点来到)",
    re.IGNORECASE,
)
_POV_RE = re.compile(r"^(?:[—\-*#\s]*)(?:视角|POV)[:：]", re.IGNORECASE)
_DIALOGUE_RE = re.compile(r"^[“\"『「].*[”\"』」]\s*$")


@dataclass(frozen=True)
class SceneRecord:
    id: int
    project_id: int
    chapter_id: int
    parent_scene_id: int | None
    scene_index: int
    title: str
    original_start_offset: int
    original_end_offset: int
    original_text: str
    source_version: int
    boundary_reasons: tuple[str, ...]
    boundary_status: str
    scene_type: str
    user_confirmed: bool
    confirmed_at: str | None


class SceneService:
    """Own immutable source ranges, scene boundaries, facts, and dynamic character state."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.project_service = ProjectService(self.database_path)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def get_source_version(self, chapter_id: int, source_version: int = 1) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, document_id, chapter_id, source_version,
                       original_start_offset, original_end_offset, original_text,
                       content_hash, created_at
                FROM chapter_source_versions
                WHERE chapter_id = ? AND source_version = ?
                """,
                (chapter_id, source_version),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Chapter source version not found: {chapter_id}@{source_version}")
        return dict(row)

    def ensure_source_version(self, chapter_id: int) -> dict[str, Any]:
        chapter = self.project_service.get_chapter(chapter_id)
        if chapter is None:
            raise FileNotFoundError(f"Chapter not found: {chapter_id}")
        with session(self.database_path) as connection:
            existing = connection.execute(
                "SELECT source_version FROM chapter_source_versions WHERE chapter_id = ? ORDER BY source_version LIMIT 1",
                (chapter_id,),
            ).fetchone()
            if existing is None:
                offsets = connection.execute(
                    "SELECT source_start_offset, source_end_offset FROM chapters WHERE id = ?",
                    (chapter_id,),
                ).fetchone()
                start = int(offsets["source_start_offset"] or 0)
                end = int(offsets["source_end_offset"] or (start + len(chapter.original_text)))
                connection.execute(
                    """
                    INSERT INTO chapter_source_versions (
                        project_id, chapter_id, source_version,
                        original_start_offset, original_end_offset,
                        original_text, content_hash
                    ) VALUES (?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        chapter.project_id,
                        chapter_id,
                        start,
                        end,
                        chapter.original_text,
                        hash_text(chapter.original_text),
                    ),
                )
        return self.get_source_version(chapter_id)

    def list_scenes(self, chapter_id: int) -> list[SceneRecord]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM scenes
                WHERE chapter_id = ? AND deleted_at IS NULL
                ORDER BY scene_index
                """,
                (chapter_id,),
            ).fetchall()
        return [self._scene_from_row(row) for row in rows]

    def get_scene(self, scene_id: int) -> SceneRecord | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM scenes WHERE id = ? AND deleted_at IS NULL",
                (scene_id,),
            ).fetchone()
        return self._scene_from_row(row) if row is not None else None

    def split_chapter(
        self,
        chapter_id: int,
        *,
        proposed_boundaries: Iterable[int] | Iterable[dict[str, Any]] | None = None,
        source: str = "heuristic",
        replace_proposed: bool = True,
    ) -> list[SceneRecord]:
        """Create proposed scenes; confirmed user boundaries are never overwritten."""
        source_version = self.ensure_source_version(chapter_id)
        chapter_text = str(source_version["original_text"])
        current = self.list_scenes(chapter_id)
        if any(scene.user_confirmed for scene in current):
            return current
        if current and not replace_proposed:
            return current
        proposed = list(proposed_boundaries) if proposed_boundaries is not None else None
        if proposed and isinstance(proposed[0], dict):
            items = self._validate_range_items(chapter_text, proposed)
        else:
            boundaries = (
                self._validate_boundaries(chapter_text, proposed or [])
                if proposed is not None
                else self._heuristic_boundaries(chapter_text)
            )
            items = self._items_from_ranges(
                self._ranges_from_boundaries(chapter_text, boundaries),
                reasons=[source],
            )
        with session(self.database_path) as connection:
            self._retire_active_scenes(connection, chapter_id)
            self._insert_scene_items(
                connection,
                project_id=int(source_version["project_id"]),
                chapter_id=chapter_id,
                chapter_text=chapter_text,
                items=items,
                source_version=int(source_version["source_version"]),
                status="proposed",
                confirmed=False,
            )
        return self.list_scenes(chapter_id)

    def confirm_boundaries(self, chapter_id: int) -> list[SceneRecord]:
        scenes = self.list_scenes(chapter_id)
        if not scenes:
            scenes = self.split_chapter(chapter_id)
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE scenes
                SET boundary_status = 'confirmed', user_confirmed = 1,
                    confirmed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE chapter_id = ? AND deleted_at IS NULL
                """,
                (chapter_id,),
            )
        return self.list_scenes(chapter_id)

    def adjust_boundaries(
        self,
        chapter_id: int,
        boundaries: Iterable[int] | Iterable[dict[str, Any]],
    ) -> list[SceneRecord]:
        """Replace boundaries only as an explicit user edit and retain superseded rows."""
        source_version = self.ensure_source_version(chapter_id)
        chapter_text = str(source_version["original_text"])
        submitted = list(boundaries)
        if submitted and isinstance(submitted[0], dict):
            items = self._validate_range_items(chapter_text, submitted)
        else:
            validated = self._validate_boundaries(chapter_text, submitted)
            items = self._items_from_ranges(
                self._ranges_from_boundaries(chapter_text, validated),
                reasons=["user_adjustment"],
            )
        with session(self.database_path) as connection:
            self._retire_active_scenes(connection, chapter_id)
            items = [
                {**item, "reasons": _unique_strings([*item["reasons"], "user_adjustment"])}
                for item in items
            ]
            self._insert_scene_items(
                connection,
                project_id=int(source_version["project_id"]),
                chapter_id=chapter_id,
                chapter_text=chapter_text,
                items=items,
                source_version=int(source_version["source_version"]),
                status="adjusted",
                confirmed=True,
            )
        return self.list_scenes(chapter_id)

    def split_scene_into_subscenes(self, scene_id: int, boundaries: Iterable[int]) -> list[SceneRecord]:
        parent = self.get_scene(scene_id)
        if parent is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        local_boundaries = self._validate_boundaries(parent.original_text, boundaries)
        ranges = self._ranges_from_boundaries(parent.original_text, local_boundaries)
        with session(self.database_path) as connection:
            next_index = int(
                connection.execute(
                    "SELECT COALESCE(MAX(scene_index), 0) + 1 FROM scenes WHERE chapter_id = ?",
                    (parent.chapter_id,),
                ).fetchone()[0]
            )
            for local_start, local_end in ranges:
                text = parent.original_text[local_start:local_end]
                cursor = connection.execute(
                    """
                    INSERT INTO scenes (
                        project_id, chapter_id, parent_scene_id, scene_index, title,
                        original_start_offset, original_end_offset, original_text,
                        source_version, boundary_reason_json, boundary_status,
                        scene_type, user_confirmed, confirmed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '["oversized_scene"]',
                              'confirmed', ?, 1, CURRENT_TIMESTAMP)
                    """,
                    (
                        parent.project_id,
                        parent.chapter_id,
                        parent.id,
                        next_index,
                        f"{parent.title} · {next_index}",
                        parent.original_start_offset + local_start,
                        parent.original_start_offset + local_end,
                        text,
                        parent.source_version,
                        self.detect_scene_type(text),
                    ),
                )
                self._replace_paragraphs(connection, int(cursor.lastrowid), text, parent.original_start_offset + local_start)
                next_index += 1
        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM scenes WHERE parent_scene_id = ? AND deleted_at IS NULL ORDER BY scene_index",
                (scene_id,),
            ).fetchall()
        return [self._scene_from_row(row) for row in rows]

    def save_fact_ledger(
        self,
        scene_id: int,
        facts: dict[str, Any],
        *,
        source_kind: str = "analysis",
        model_id: int | None = None,
        prompt_compilation_id: int | None = None,
    ) -> dict[str, Any]:
        self._require_scene(scene_id)
        normalized = {**DEFAULT_FACT_LEDGER, **json_object(facts)}
        with session(self.database_path) as connection:
            version = int(
                connection.execute(
                    "SELECT COALESCE(MAX(ledger_version), 0) + 1 FROM scene_fact_ledgers WHERE scene_id = ?",
                    (scene_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO scene_fact_ledgers (
                    scene_id, ledger_version, facts_json, source_kind,
                    model_id, prompt_compilation_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id,
                    version,
                    json.dumps(normalized, ensure_ascii=False),
                    source_kind,
                    model_id,
                    prompt_compilation_id,
                ),
            )
        return {"scene_id": scene_id, "ledger_version": version, **normalized}

    def get_fact_ledger(self, scene_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT ledger_version, facts_json
                FROM scene_fact_ledgers
                WHERE scene_id = ?
                ORDER BY ledger_version DESC
                LIMIT 1
                """,
                (scene_id,),
            ).fetchone()
        if row is None:
            return {"scene_id": scene_id, "ledger_version": 0, **DEFAULT_FACT_LEDGER}
        return {
            "scene_id": scene_id,
            "ledger_version": int(row["ledger_version"]),
            **{**DEFAULT_FACT_LEDGER, **json_object(row["facts_json"])},
        }

    def save_character_state(
        self,
        scene_id: int,
        character_name: str,
        state: dict[str, Any],
        *,
        character_card_id: int | None = None,
    ) -> dict[str, Any]:
        scene = self._require_scene(scene_id)
        name = character_name.strip()
        if not name:
            raise ValueError("Character name is required.")
        normalized = {**DEFAULT_CHARACTER_STATE, **json_object(state)}
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO character_story_states (
                    project_id, scene_id, character_card_id, character_name, state_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scene_id, character_name)
                DO UPDATE SET
                    character_card_id = excluded.character_card_id,
                    state_json = excluded.state_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    scene.project_id,
                    scene_id,
                    character_card_id,
                    name,
                    json.dumps(normalized, ensure_ascii=False),
                ),
            )
        return {"scene_id": scene_id, "character_name": name, **normalized}

    def list_character_states(self, scene_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT character_card_id, character_name, state_json, updated_at
                FROM character_story_states
                WHERE scene_id = ?
                ORDER BY character_name
                """,
                (scene_id,),
            ).fetchall()
        return [
            {
                "character_card_id": row["character_card_id"],
                "character_name": row["character_name"],
                **{**DEFAULT_CHARACTER_STATE, **json_object(row["state_json"])},
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    @staticmethod
    def detect_scene_type(text: str) -> str:
        dialogue_lines = sum(1 for line in text.splitlines() if _DIALOGUE_RE.match(line.strip()))
        if dialogue_lines >= 3:
            return "dialogue"
        if re.search(r"(?:刀|剑|拳|掌|冲|撞|躲|杀|战|追|逃)", text):
            return "action"
        if re.search(r"(?:回忆|想起|梦见|多年以前)", text):
            return "flashback"
        return "general"

    @staticmethod
    def _heuristic_boundaries(text: str, max_scene_chars: int = 3200) -> list[int]:
        paragraphs = _paragraph_spans(text)
        if len(paragraphs) <= 1:
            return []
        boundaries: list[int] = []
        current_start = 0
        for index, (start, end, paragraph) in enumerate(paragraphs):
            if index == 0:
                continue
            previous = paragraphs[index - 1][2].strip()
            stripped = paragraph.strip()
            semantic_break = bool(_TRANSITION_RE.match(stripped) or _POV_RE.match(stripped))
            oversized = end - current_start > max_scene_chars
            dialogue_chain = _DIALOGUE_RE.match(previous) and _DIALOGUE_RE.match(stripped)
            if (semantic_break or oversized) and not dialogue_chain:
                boundaries.append(start)
                current_start = start
        return boundaries

    @staticmethod
    def _validate_boundaries(text: str, boundaries: Iterable[int]) -> list[int]:
        cleaned = sorted({int(value) for value in boundaries})
        if any(value <= 0 or value >= len(text) for value in cleaned):
            raise ValueError("Scene boundaries must be inside the chapter source range.")
        paragraph_starts = {start for start, _, _ in _paragraph_spans(text)}
        invalid = [value for value in cleaned if value not in paragraph_starts]
        if invalid:
            raise ValueError(f"Scene boundaries must align to paragraph starts: {invalid}")
        return cleaned

    @staticmethod
    def _ranges_from_boundaries(text: str, boundaries: list[int]) -> list[tuple[int, int]]:
        points = [0, *boundaries, len(text)]
        return [(points[index], points[index + 1]) for index in range(len(points) - 1)]

    @staticmethod
    def _validate_range_items(
        text: str,
        boundaries: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        submitted = list(boundaries)
        if not submitted:
            raise ValueError("At least one scene boundary is required.")
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(submitted):
            start = int(raw.get("start_offset", -1))
            end = int(raw.get("end_offset", -1))
            if start < 0 or end <= start or end > len(text):
                raise ValueError(f"Scene boundary {index + 1} is outside the chapter source range.")
            normalized.append(
                {
                    "start_offset": start,
                    "end_offset": end,
                    "title": str(raw.get("title") or f"场景 {index + 1}").strip() or f"场景 {index + 1}",
                    "reasons": _unique_strings(raw.get("reasons") or []),
                }
            )
        starts = [int(item["start_offset"]) for item in normalized]
        if starts != sorted(starts):
            raise ValueError("Scene boundaries must be submitted in source order.")
        expected = 0
        for index, item in enumerate(normalized):
            start = int(item["start_offset"])
            if start != expected:
                relation = "overlap" if start < expected else "gap"
                raise ValueError(f"Scene boundary {index + 1} creates a {relation}.")
            expected = int(item["end_offset"])
        if expected != len(text):
            raise ValueError("Scene boundaries must cover the complete chapter source.")
        return normalized

    @staticmethod
    def _items_from_ranges(
        ranges: list[tuple[int, int]],
        *,
        reasons: list[str],
    ) -> list[dict[str, Any]]:
        return [
            {
                "start_offset": start,
                "end_offset": end,
                "title": f"场景 {index}",
                "reasons": list(reasons),
            }
            for index, (start, end) in enumerate(ranges, start=1)
        ]

    @staticmethod
    def _retire_active_scenes(connection, chapter_id: int) -> None:
        rows = connection.execute(
            "SELECT id FROM scenes WHERE chapter_id = ? AND deleted_at IS NULL ORDER BY scene_index",
            (chapter_id,),
        ).fetchall()
        for offset, row in enumerate(rows, start=1):
            connection.execute(
                """
                UPDATE scenes
                SET scene_index = ?, deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (-1000000 - offset, int(row["id"])),
            )

    @staticmethod
    def _insert_scene_items(
        connection,
        *,
        project_id: int,
        chapter_id: int,
        chapter_text: str,
        items: list[dict[str, Any]],
        source_version: int,
        status: str,
        confirmed: bool,
    ) -> None:
        for index, item in enumerate(items, start=1):
            start = int(item["start_offset"])
            end = int(item["end_offset"])
            text = chapter_text[start:end]
            cursor = connection.execute(
                """
                INSERT INTO scenes (
                    project_id, chapter_id, scene_index, title,
                    original_start_offset, original_end_offset, original_text,
                    source_version, boundary_reason_json, boundary_status,
                    scene_type, user_confirmed, confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
                """,
                (
                    project_id,
                    chapter_id,
                    index,
                    str(item["title"]),
                    start,
                    end,
                    text,
                    source_version,
                    json.dumps(item["reasons"], ensure_ascii=False),
                    status,
                    SceneService.detect_scene_type(text),
                    1 if confirmed else 0,
                    1 if confirmed else 0,
                ),
            )
            SceneService._replace_paragraphs(connection, int(cursor.lastrowid), text, start)

    @staticmethod
    def _insert_scenes(
        connection,
        *,
        project_id: int,
        chapter_id: int,
        chapter_text: str,
        ranges: list[tuple[int, int]],
        source_version: int,
        status: str,
        confirmed: bool,
        reasons: list[str],
    ) -> None:
        for index, (start, end) in enumerate(ranges, start=1):
            text = chapter_text[start:end]
            cursor = connection.execute(
                """
                INSERT INTO scenes (
                    project_id, chapter_id, scene_index, title,
                    original_start_offset, original_end_offset, original_text,
                    source_version, boundary_reason_json, boundary_status,
                    scene_type, user_confirmed, confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
                """,
                (
                    project_id,
                    chapter_id,
                    index,
                    f"场景 {index}",
                    start,
                    end,
                    text,
                    source_version,
                    json.dumps(reasons, ensure_ascii=False),
                    status,
                    SceneService.detect_scene_type(text),
                    1 if confirmed else 0,
                    1 if confirmed else 0,
                ),
            )
            SceneService._replace_paragraphs(connection, int(cursor.lastrowid), text, start)

    @staticmethod
    def _replace_paragraphs(connection, scene_id: int, text: str, base_offset: int) -> None:
        connection.execute("DELETE FROM scene_paragraphs WHERE scene_id = ?", (scene_id,))
        for index, (start, end, paragraph) in enumerate(_paragraph_spans(text)):
            connection.execute(
                """
                INSERT INTO scene_paragraphs (
                    scene_id, paragraph_index, original_start_offset,
                    original_end_offset, original_text
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (scene_id, index, base_offset + start, base_offset + end, paragraph),
            )

    def _require_scene(self, scene_id: int) -> SceneRecord:
        scene = self.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        return scene

    @staticmethod
    def _scene_from_row(row) -> SceneRecord:
        reasons = _json_list(row["boundary_reason_json"])
        return SceneRecord(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            chapter_id=int(row["chapter_id"]),
            parent_scene_id=int(row["parent_scene_id"]) if row["parent_scene_id"] is not None else None,
            scene_index=int(row["scene_index"]),
            title=str(row["title"]),
            original_start_offset=int(row["original_start_offset"]),
            original_end_offset=int(row["original_end_offset"]),
            original_text=str(row["original_text"]),
            source_version=int(row["source_version"]),
            boundary_reasons=tuple(str(item) for item in reasons),
            boundary_status=str(row["boundary_status"]),
            scene_type=str(row["scene_type"]),
            user_confirmed=bool(row["user_confirmed"]),
            confirmed_at=str(row["confirmed_at"]) if row["confirmed_at"] is not None else None,
        )


def _paragraph_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for match in re.finditer(r"(?:\r?\n){2,}", text):
        end = match.start()
        if end > cursor and text[cursor:end].strip():
            spans.append((cursor, end, text[cursor:end]))
        cursor = match.end()
    if cursor < len(text) and text[cursor:].strip():
        spans.append((cursor, len(text), text[cursor:]))
    if not spans and text:
        spans.append((0, len(text), text))
    return spans


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
