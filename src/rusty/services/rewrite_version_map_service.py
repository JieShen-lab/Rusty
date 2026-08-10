from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from rusty.db import session
from rusty.services.project_service import default_database_path


@dataclass(frozen=True)
class VersionSpan:
    id: int
    rewrite_version_id: int
    segment_kind: str
    source_scene_id: int | None
    skeleton_version_id: int | None
    node_id: str | None
    segment_index: int
    start_offset: int
    end_offset: int
    mapping_method: str
    confidence: float
    needs_remap: bool
    state_method: str
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    facts_before: dict[str, Any]
    facts_after: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnchorUnmapped(ValueError):
    pass


class StateUnresolved(ValueError):
    pass


class RewriteVersionMapService:
    """Immutable, queryable semantic positions for one rewrite version."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = (
            Path(database_path) if database_path is not None else default_database_path()
        )

    def create_structural_map(
        self,
        connection: sqlite3.Connection,
        *,
        rewrite_version_id: int,
        chapter_id: int,
        rewritten_text: str,
        source_base_version_id: int | None,
        source_skeleton: dict[str, Any] | None = None,
        observed_skeleton: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_version_text(
            connection, rewrite_version_id=rewrite_version_id, text=rewritten_text
        )
        base_scenes = self._base_scene_segments(
            connection, chapter_id, source_base_version_id
        )
        paragraphs = _paragraph_spans(rewritten_text)
        scene_spans: dict[int, tuple[int, int]] = {}
        if len(paragraphs) == len(base_scenes):
            for base, paragraph in zip(base_scenes, paragraphs, strict=True):
                scene_spans[int(base["source_scene_id"])] = paragraph

        source_skeleton_version_id = self._find_source_skeleton_version(
            connection, chapter_id=chapter_id, skeleton=source_skeleton
        )
        observed_nodes = {
            str(node.get("id")): node
            for node in (observed_skeleton or {}).get("event_nodes", [])
            if isinstance(node, dict)
        }
        source_nodes = [
            node
            for node in (source_skeleton or {}).get("event_nodes", [])
            if isinstance(node, dict)
        ]
        event_rows: list[dict[str, Any]] = []
        for index, source_node in enumerate(source_nodes):
            observed = observed_nodes.get(str(source_node.get("id")))
            if observed is None and index < len(observed_nodes):
                observed = list(observed_nodes.values())[index]
            span = _valid_span(
                observed.get("source_span") if isinstance(observed, dict) else None,
                len(rewritten_text),
            )
            if span is None:
                continue
            source_scene_id = self._scene_for_original_node(
                base_scenes, source_node
            )
            state_before, state_after = self._states_for_scene(
                base_scenes, source_scene_id
            )
            event_rows.append(
                {
                    "segment_kind": "event_node",
                    "source_scene_id": source_scene_id,
                    "skeleton_version_id": source_skeleton_version_id,
                    "node_id": str(source_node.get("id")),
                    "segment_index": index,
                    "start_offset": span[0],
                    "end_offset": span[1],
                    "mapping_method": "semantic",
                    "confidence": float(observed.get("confidence", 0.8)),
                    "state_method": "scene_chain",
                    "state_before": state_before,
                    "state_after": state_after,
                    "facts_before": state_before,
                    "facts_after": state_after,
                }
            )
            if source_scene_id is not None:
                current = scene_spans.get(source_scene_id)
                scene_spans[source_scene_id] = (
                    min(current[0], span[0]) if current else span[0],
                    max(current[1], span[1]) if current else span[1],
                )

        scene_rows: list[dict[str, Any]] = []
        for index, base in enumerate(base_scenes):
            scene_id = int(base["source_scene_id"])
            mapped = scene_spans.get(scene_id)
            if mapped is None:
                continue
            scene_rows.append(
                {
                    "segment_kind": "scene",
                    "source_scene_id": scene_id,
                    "skeleton_version_id": None,
                    "node_id": None,
                    "segment_index": index,
                    "start_offset": mapped[0],
                    "end_offset": mapped[1],
                    "mapping_method": (
                        "structural" if len(paragraphs) == len(base_scenes) else "semantic"
                    ),
                    "confidence": 0.9 if len(paragraphs) == len(base_scenes) else 0.75,
                    "state_method": "inherited_scene_chain",
                    "state_before": base["state_before"],
                    "state_after": base["state_after"],
                    "facts_before": base["facts_before"],
                    "facts_after": base["facts_after"],
                }
            )
        observed_version_id = None
        if observed_skeleton is not None:
            observed_version_id = self._persist_rewrite_skeleton(
                connection,
                rewrite_version_id=rewrite_version_id,
                chapter_id=chapter_id,
                skeleton=observed_skeleton,
            )
            for index, row in enumerate(list(event_rows), start=len(event_rows)):
                event_rows.append(
                    {
                        **row,
                        "skeleton_version_id": observed_version_id,
                        "segment_index": index,
                    }
                )
        self._insert_segments(connection, rewrite_version_id, scene_rows + event_rows)
        return {
            "map_hash": self.map_hash(rewrite_version_id, connection=connection),
            "skeleton_version_id": observed_version_id,
            "segments": self.list_segments(rewrite_version_id, connection=connection),
        }

    def create_transformed_map(
        self,
        connection: sqlite3.Connection,
        *,
        rewrite_version_id: int,
        chapter_id: int,
        rewritten_text: str,
        source_base_version_id: int | None,
        changes: list[dict[str, Any]],
        generated_segment: dict[str, Any] | None = None,
        source_skeleton: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_version_text(
            connection, rewrite_version_id=rewrite_version_id, text=rewritten_text
        )
        base = self._base_segments(connection, chapter_id, source_base_version_id)
        rows: list[dict[str, Any]] = []
        counters: dict[str, int] = {}
        for item in base:
            start = int(item["start_offset"])
            end = int(item["end_offset"])
            method = "identity"
            needs_remap = False
            confidence = float(item.get("confidence", 1.0))
            for change in changes:
                start, end, changed, overlap = _transform_span(
                    start,
                    end,
                    int(change["start"]),
                    int(change["end"]),
                    int(change["replacement_length"]),
                )
                if overlap:
                    if bool(change.get("preserve_semantic_identity")):
                        method = "shifted"
                    else:
                        method = "semantic"
                        needs_remap = True
                        confidence = min(confidence, 0.5)
                elif changed and method != "semantic":
                    method = "shifted"
            if end > len(rewritten_text):
                raise ValueError("Transformed semantic span exceeds rewrite text.")
            kind = str(item["segment_kind"])
            index = counters.get(kind, 0)
            counters[kind] = index + 1
            rows.append(
                {
                    **item,
                    "segment_index": index,
                    "start_offset": start,
                    "end_offset": end,
                    "mapping_method": method,
                    "confidence": confidence,
                    "needs_remap": needs_remap,
                }
            )
        if generated_segment is not None:
            rows.append(
                {
                    "segment_kind": "generated_event",
                    "source_scene_id": None,
                    "skeleton_version_id": None,
                    "node_id": str(generated_segment.get("node_id") or "generated"),
                    "segment_index": counters.get("generated_event", 0),
                    "start_offset": int(generated_segment["start_offset"]),
                    "end_offset": int(generated_segment["end_offset"]),
                    "mapping_method": "identity",
                    "confidence": 1.0,
                    "state_method": "generated_ledger",
                    "state_before": dict(generated_segment.get("state_before") or {}),
                    "state_after": dict(generated_segment.get("state_after") or {}),
                    "facts_before": dict(generated_segment.get("state_before") or {}),
                    "facts_after": dict(generated_segment.get("state_after") or {}),
                }
            )
        self._insert_segments(connection, rewrite_version_id, rows)
        skeleton_version_id = None
        if source_skeleton is not None:
            skeleton_version_id = self._persist_rewrite_skeleton(
                connection,
                rewrite_version_id=rewrite_version_id,
                chapter_id=chapter_id,
                skeleton=source_skeleton,
            )
        return {
            "map_hash": self.map_hash(rewrite_version_id, connection=connection),
            "skeleton_version_id": skeleton_version_id,
            "segments": self.list_segments(rewrite_version_id, connection=connection),
        }

    def resolve_scene_span(
        self, rewrite_version_id: int, scene_id: int
    ) -> VersionSpan:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM chapter_rewrite_version_segments
                WHERE rewrite_version_id = ? AND segment_kind = 'scene'
                  AND source_scene_id = ? AND needs_remap = 0
                ORDER BY confidence DESC, id DESC LIMIT 1
                """,
                (rewrite_version_id, scene_id),
            ).fetchone()
        if row is None:
            raise AnchorUnmapped("anchor_unmapped: scene has no mapping in this rewrite version")
        return _span(row)

    def resolve_node_span(
        self, rewrite_version_id: int, skeleton_version_id: int, node_id: str
    ) -> VersionSpan:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM chapter_rewrite_version_segments
                WHERE rewrite_version_id = ? AND segment_kind = 'event_node'
                  AND skeleton_version_id = ? AND node_id = ? AND needs_remap = 0
                ORDER BY confidence DESC, id DESC LIMIT 1
                """,
                (rewrite_version_id, skeleton_version_id, node_id),
            ).fetchone()
        if row is None:
            raise AnchorUnmapped("anchor_unmapped: event node has no mapping in this rewrite version")
        return _span(row)

    def resolve_state_at_offset(
        self, rewrite_version_id: int, offset: int, side: str
    ) -> dict[str, Any]:
        with session(self.database_path) as connection:
            version = connection.execute(
                "SELECT length(rewritten_text) AS size FROM chapter_rewrite_versions WHERE id = ?",
                (rewrite_version_id,),
            ).fetchone()
            if version is None:
                raise FileNotFoundError(f"Rewrite version not found: {rewrite_version_id}")
            if offset < 0 or offset > int(version["size"]):
                raise ValueError("Anchor text_offset is outside the rewrite version.")
            rows = connection.execute(
                """
                SELECT * FROM chapter_rewrite_version_segments
                WHERE rewrite_version_id = ? AND needs_remap = 0
                ORDER BY start_offset, end_offset, segment_index
                """,
                (rewrite_version_id,),
            ).fetchall()
        containing = [row for row in rows if row["start_offset"] <= offset <= row["end_offset"]]
        if containing:
            row = sorted(
                containing,
                key=lambda item: (
                    0 if item["segment_kind"] == "event_node" else 1,
                    item["end_offset"] - item["start_offset"],
                ),
            )[0]
            return _json_object(
                row["state_before_json"] if side == "before" else row["state_after_json"]
            )
        previous = [row for row in rows if row["end_offset"] <= offset]
        if previous:
            return _json_object(previous[-1]["state_after_json"])
        raise StateUnresolved("state_unresolved: no local state segment covers this offset")

    def list_segments(
        self,
        rewrite_version_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        if connection is None:
            with session(self.database_path) as owned:
                return self.list_segments(rewrite_version_id, connection=owned)
        rows = connection.execute(
            """
            SELECT * FROM chapter_rewrite_version_segments
            WHERE rewrite_version_id = ?
            ORDER BY segment_kind, segment_index, id
            """,
            (rewrite_version_id,),
        ).fetchall()
        return [_span(row).to_dict() for row in rows]

    def map_hash(
        self,
        rewrite_version_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> str:
        if connection is None:
            with session(self.database_path) as owned:
                return self.map_hash(rewrite_version_id, connection=owned)
        version = connection.execute(
            "SELECT content_hash FROM chapter_rewrite_versions WHERE id = ?",
            (rewrite_version_id,),
        ).fetchone()
        if version is None:
            raise FileNotFoundError(f"Rewrite version not found: {rewrite_version_id}")
        segments = self.list_segments(rewrite_version_id, connection=connection)
        payload = json.dumps(
            {"content_hash": version["content_hash"], "segments": segments},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def validate_map_hash(self, rewrite_version_id: int, expected_hash: str) -> None:
        if self.map_hash(rewrite_version_id) != expected_hash:
            raise ValueError("Rewrite semantic map hash does not match the frozen run source.")

    def resolve_structure(
        self,
        connection: sqlite3.Connection,
        *,
        chapter_id: int,
        rewrite_version_id: int | None,
    ) -> dict[str, Any] | None:
        if rewrite_version_id is not None:
            row = connection.execute(
                """
                SELECT v.skeleton_json FROM rewrite_version_skeletons r
                JOIN story_skeleton_versions v ON v.id = r.skeleton_version_id
                WHERE r.rewrite_version_id = ? ORDER BY v.id DESC LIMIT 1
                """,
                (rewrite_version_id,),
            ).fetchone()
            if row is not None:
                value = _json_object(row["skeleton_json"])
                if value:
                    return value
        row = connection.execute(
            """
            SELECT v.skeleton_json FROM story_skeletons s
            JOIN story_skeleton_versions v
              ON v.skeleton_id = s.id AND v.version = s.current_version
            WHERE s.chapter_id = ? AND s.source_kind <> 'rewrite_version'
            ORDER BY s.id DESC LIMIT 1
            """,
            (chapter_id,),
        ).fetchone()
        value = _json_object(row["skeleton_json"]) if row is not None else {}
        return value or None

    def _base_segments(
        self,
        connection: sqlite3.Connection,
        chapter_id: int,
        source_base_version_id: int | None,
    ) -> list[dict[str, Any]]:
        if source_base_version_id is not None:
            return self.list_segments(source_base_version_id, connection=connection)
        return self._original_segments(connection, chapter_id)

    def _base_scene_segments(
        self,
        connection: sqlite3.Connection,
        chapter_id: int,
        source_base_version_id: int | None,
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in self._base_segments(connection, chapter_id, source_base_version_id)
            if row["segment_kind"] == "scene"
        ]

    def _original_segments(
        self, connection: sqlite3.Connection, chapter_id: int
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT s.*, l.facts_json FROM scenes s
            LEFT JOIN scene_fact_ledgers l ON l.id = (
                SELECT l2.id FROM scene_fact_ledgers l2 WHERE l2.scene_id = s.id
                ORDER BY l2.ledger_version DESC LIMIT 1
            )
            WHERE s.chapter_id = ? AND s.deleted_at IS NULL
            ORDER BY s.scene_index, s.id
            """,
            (chapter_id,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        previous: dict[str, Any] = {}
        for index, row in enumerate(rows):
            facts = _json_object(row["facts_json"])
            start_state = previous or (
                facts.get("required_start_state")
                if isinstance(facts.get("required_start_state"), dict)
                else {}
            )
            result.append(
                {
                    "segment_kind": "scene",
                    "source_scene_id": int(row["id"]),
                    "skeleton_version_id": None,
                    "node_id": None,
                    "segment_index": index,
                    "start_offset": int(row["original_start_offset"]),
                    "end_offset": int(row["original_end_offset"]),
                    "mapping_method": "identity",
                    "confidence": 1.0,
                    "needs_remap": False,
                    "state_method": "scene_ledger",
                    "state_before": dict(start_state),
                    "state_after": dict(facts),
                    "facts_before": dict(start_state),
                    "facts_after": dict(facts),
                }
            )
            previous = facts
        return result

    @staticmethod
    def _states_for_scene(
        scenes: list[dict[str, Any]], scene_id: int | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        match = next(
            (row for row in scenes if row.get("source_scene_id") == scene_id), None
        )
        return (
            dict(match.get("state_before") or {}) if match else {},
            dict(match.get("state_after") or {}) if match else {},
        )

    @staticmethod
    def _scene_for_original_node(
        scenes: list[dict[str, Any]], node: dict[str, Any]
    ) -> int | None:
        span = _valid_span(node.get("source_span"), 2**31 - 1)
        if span is None:
            return None
        # Scene boundaries may share an offset.  Requiring the whole event
        # span to fit prevents an event that starts at scene N+1's boundary
        # from being attributed to scene N.
        for scene in scenes:
            if (
                int(scene["start_offset"]) <= span[0]
                and span[1] <= int(scene["end_offset"])
            ):
                return int(scene["source_scene_id"])
        return None

    @staticmethod
    def _find_source_skeleton_version(
        connection: sqlite3.Connection,
        *,
        chapter_id: int,
        skeleton: dict[str, Any] | None,
    ) -> int | None:
        if skeleton is None:
            return None
        ids = {str(item.get("id")) for item in skeleton.get("event_nodes", [])}
        rows = connection.execute(
            """
            SELECT v.id, v.skeleton_json FROM story_skeleton_versions v
            JOIN story_skeletons s ON s.id = v.skeleton_id
            WHERE s.chapter_id = ? AND s.source_kind <> 'rewrite_version'
            ORDER BY v.id DESC
            """,
            (chapter_id,),
        ).fetchall()
        for row in rows:
            value = _json_object(row["skeleton_json"])
            if {str(item.get("id")) for item in value.get("event_nodes", [])} == ids:
                return int(row["id"])
        return None

    @staticmethod
    def _persist_rewrite_skeleton(
        connection: sqlite3.Connection,
        *,
        rewrite_version_id: int,
        chapter_id: int,
        skeleton: dict[str, Any],
    ) -> int:
        version = connection.execute(
            "SELECT project_id FROM chapter_rewrite_versions WHERE id = ?",
            (rewrite_version_id,),
        ).fetchone()
        cursor = connection.execute(
            """
            INSERT INTO story_skeletons(
                project_id, chapter_id, scene_id, scope, source_kind, status,
                current_version, source_rewrite_version_id
            ) VALUES (?, ?, NULL, 'chapter', 'rewrite_version', 'confirmed', 1, ?)
            """,
            (version["project_id"], chapter_id, rewrite_version_id),
        )
        skeleton_id = int(cursor.lastrowid)
        legacy_nodes = [
            {
                "id": item.get("id"),
                "order": item.get("order"),
                "summary": item.get("summary", ""),
                "source_span": item.get("source_span"),
            }
            for item in skeleton.get("event_nodes", [])
        ]
        version_cursor = connection.execute(
            """
            INSERT INTO story_skeleton_versions(
                skeleton_id, version, nodes_json, skeleton_json,
                source_references_json, confirmed_at
            ) VALUES (?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                skeleton_id,
                json.dumps(legacy_nodes, ensure_ascii=False),
                json.dumps(skeleton, ensure_ascii=False),
                json.dumps(skeleton.get("source_references", []), ensure_ascii=False),
            ),
        )
        skeleton_version_id = int(version_cursor.lastrowid)
        connection.execute(
            "INSERT INTO rewrite_version_skeletons(rewrite_version_id, skeleton_version_id) VALUES (?, ?)",
            (rewrite_version_id, skeleton_version_id),
        )
        return skeleton_version_id

    @staticmethod
    def _insert_segments(
        connection: sqlite3.Connection,
        rewrite_version_id: int,
        rows: Iterable[dict[str, Any]],
    ) -> None:
        for row in rows:
            connection.execute(
                """
                INSERT INTO chapter_rewrite_version_segments(
                    rewrite_version_id, segment_kind, source_scene_id,
                    skeleton_version_id, node_id, segment_index,
                    start_offset, end_offset, mapping_method, confidence,
                    needs_remap, state_method, state_before_json,
                    state_after_json, facts_before_json, facts_after_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rewrite_version_id,
                    row["segment_kind"],
                    row.get("source_scene_id"),
                    row.get("skeleton_version_id"),
                    row.get("node_id"),
                    row["segment_index"],
                    row["start_offset"],
                    row["end_offset"],
                    row.get("mapping_method", "structural"),
                    row.get("confidence", 1.0),
                    1 if row.get("needs_remap") else 0,
                    row.get("state_method", "explicit"),
                    json.dumps(row.get("state_before") or {}, ensure_ascii=False),
                    json.dumps(row.get("state_after") or {}, ensure_ascii=False),
                    json.dumps(row.get("facts_before") or {}, ensure_ascii=False),
                    json.dumps(row.get("facts_after") or {}, ensure_ascii=False),
                ),
            )

    @staticmethod
    def _validate_version_text(
        connection: sqlite3.Connection, *, rewrite_version_id: int, text: str
    ) -> None:
        row = connection.execute(
            "SELECT content_hash FROM chapter_rewrite_versions WHERE id = ?",
            (rewrite_version_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Rewrite version not found: {rewrite_version_id}")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != row["content_hash"]:
            raise ValueError("Semantic map text does not match rewrite version content hash.")


def _span(row: sqlite3.Row) -> VersionSpan:
    return VersionSpan(
        id=int(row["id"]),
        rewrite_version_id=int(row["rewrite_version_id"]),
        segment_kind=str(row["segment_kind"]),
        source_scene_id=int(row["source_scene_id"]) if row["source_scene_id"] else None,
        skeleton_version_id=(
            int(row["skeleton_version_id"]) if row["skeleton_version_id"] else None
        ),
        node_id=str(row["node_id"]) if row["node_id"] is not None else None,
        segment_index=int(row["segment_index"]),
        start_offset=int(row["start_offset"]),
        end_offset=int(row["end_offset"]),
        mapping_method=str(row["mapping_method"]),
        confidence=float(row["confidence"]),
        needs_remap=bool(row["needs_remap"]),
        state_method=str(row["state_method"]),
        state_before=_json_object(row["state_before_json"]),
        state_after=_json_object(row["state_after_json"]),
        facts_before=_json_object(row["facts_before_json"]),
        facts_after=_json_object(row["facts_after_json"]),
    )


def _json_object(value: Any) -> dict[str, Any]:
    try:
        result = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def _valid_span(value: Any, text_length: int) -> tuple[int, int] | None:
    if not isinstance(value, dict):
        return None
    start = value.get("start", value.get("start_offset"))
    end = value.get("end", value.get("end_offset"))
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return (start, end) if 0 <= start <= end <= text_length else None


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"(?:^|\n\s*\n)([^\n].*?)(?=\n\s*\n|$)", text, re.DOTALL):
        start, end = match.span(1)
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append((start, end))
    return spans or ([(0, len(text))] if text else [])


def _transform_span(
    span_start: int,
    span_end: int,
    change_start: int,
    change_end: int,
    replacement_length: int,
) -> tuple[int, int, bool, bool]:
    delta = replacement_length - (change_end - change_start)
    if change_start == change_end:
        if span_end <= change_start:
            return span_start, span_end, False, False
        if span_start >= change_start:
            return span_start + delta, span_end + delta, True, False
        return span_start, span_end + delta, True, False
    if span_end <= change_start:
        return span_start, span_end, False, False
    if span_start >= change_end:
        return span_start + delta, span_end + delta, True, False
    mapped_start = min(span_start, change_start)
    mapped_end = max(change_start + replacement_length, span_end + delta)
    return mapped_start, mapped_end, True, True
