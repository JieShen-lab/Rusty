from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.extraction_apply_error import CandidateApplyError
from rusty.db import default_database_path
from rusty.services.style_service import DETAIL_LEVELS


MATERIAL_TYPES = {"scene_reference", "plot_skeleton"}
MATERIAL_SCOPES = {"public", "project"}
ANALYSIS_STATUSES = {"unanalyzed", "analyzed"}
MATERIAL_TAG_GROUPS = {"general", "applicable_scene"}
PROJECT_FILTER_MATCH_MODES = {"any", "all"}
MATERIAL_AI_TASK_TYPES = {
    "narrative_to_plot_skeleton",
    "plot_text_to_normalized_skeleton",
    "source_text_to_scene_material",
}
MATERIAL_AI_DEFAULTS: dict[str, dict[str, Any]] = {
    "narrative_to_plot_skeleton": {
        "detail_level": "standard",
        "max_candidates": 6,
        "system_prompt": (
            "Extract a reusable plot skeleton from narrative text. Use only supported facts, "
            "preserve causal order, and leave missing dimensions empty."
        ),
        "user_prompt_template": "Identify the premise, stages, conflicts, turns, climax, resolution, and hooks.",
        "analysis_dimensions": [
            "premise", "stages", "conflicts", "turning_points", "climax", "resolution", "hooks",
        ],
        "generate_general_tags": True,
        "generate_applicable_scene_tags": False,
    },
    "plot_text_to_normalized_skeleton": {
        "detail_level": "standard",
        "max_candidates": 6,
        "system_prompt": (
            "Normalize existing plot text into a structured plot skeleton without adding events "
            "or changing the source order."
        ),
        "user_prompt_template": "Normalize the supplied plot while preserving every supported causal link.",
        "analysis_dimensions": [
            "premise", "stages", "conflicts", "turning_points", "climax", "resolution", "hooks",
        ],
        "generate_general_tags": True,
        "generate_applicable_scene_tags": False,
    },
    "source_text_to_scene_material": {
        "detail_level": "standard",
        "max_candidates": 6,
        "system_prompt": (
            "Extract reusable scene-writing material from source text. Do not generate a plot skeleton "
            "or invent unsupported details."
        ),
        "user_prompt_template": "Extract scene beats, actions, environment, sensory cues, and writing guidance.",
        "analysis_dimensions": [
            "summary", "key_beats", "actions", "environment", "sensory",
            "writing_guidance", "source_cues", "avoidances", "applicable_conditions",
        ],
        "generate_general_tags": True,
        "generate_applicable_scene_tags": True,
    },
}


@dataclass(frozen=True)
class ResourceTag:
    id: int
    name: str
    normalized_name: str
    sort_order: int
    resource_count: int
    tag_group: str = "general"


@dataclass(frozen=True)
class MaterialCategory:
    id: int
    material_type: str
    name: str
    normalized_name: str
    sort_order: int
    resource_count: int


@dataclass(frozen=True)
class MaterialSourceSummary:
    kind: str
    label: str
    document_id: int | None = None
    chapter_id: int | None = None
    project_id: int | None = None


@dataclass(frozen=True)
class ProjectMaterialFilter:
    project_id: int
    material_type: str
    match_mode: str
    tag_ids: tuple[int, ...]
    manual_material_ids: tuple[int, ...]
    include_scene_keywords: bool
    include_applicable_scene_tags: bool


@dataclass(frozen=True)
class MaterialAISettings:
    task_type: str
    model_id: int | None
    detail_level: str
    max_candidates: int
    system_prompt: str
    user_prompt_template: str
    analysis_dimensions: tuple[str, ...]
    generate_general_tags: bool
    generate_applicable_scene_tags: bool
    custom_requirements: str
    updated_at: str

    @property
    def generate_tags(self) -> bool:
        """Legacy read compatibility; new callers use the two independent switches."""
        return self.generate_general_tags and self.generate_applicable_scene_tags


@dataclass(frozen=True)
class Material:
    id: int
    material_type: str
    scope: str
    project_id: int | None
    project_name: str | None
    name: str
    description: str
    detail_level: str
    raw_text: str
    content_json: str
    analysis_status: str
    source_metadata_json: str
    import_metadata_json: str
    source_material_id: int | None
    source_version: int | None
    timeline_start_chapter: int | None
    timeline_end_chapter: int | None
    sort_order: int
    version: int
    created_at: str
    updated_at: str
    tags: tuple[str, ...] = ()
    general_tags: tuple[str, ...] = ()
    applicable_scene_tags: tuple[str, ...] = ()
    category_ids: tuple[int, ...] = ()
    categories: tuple[str, ...] = ()
    source_summary: MaterialSourceSummary | None = None

MaterialTag = ResourceTag


class MaterialService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def list_materials(
        self,
        *,
        scope: str | None = None,
        project_id: int | None = None,
        material_type: str | None = None,
        tag_id: int | None = None,
        tag_group: str | None = None,
        category_id: int | None = None,
        analysis_status: str | None = None,
        pending_imports: bool = False,
        untagged: bool = False,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Material]:
        if scope is not None and scope not in MATERIAL_SCOPES:
            raise ValueError(f"Unsupported material scope: {scope}")
        if material_type is not None:
            material_type = _validate_type(material_type)
        if analysis_status is not None:
            analysis_status = _validate_analysis_status(analysis_status)
        if tag_group is not None and tag_group not in MATERIAL_TAG_GROUPS:
            raise ValueError(f"Unsupported material tag group: {tag_group}")
        clauses = ["m.deleted_at IS NULL"]
        parameters: list[object] = []
        if material_type is not None:
            clauses.append("m.material_type = ?")
            parameters.append(material_type)
        if analysis_status is not None:
            clauses.append("m.analysis_status = ?")
            parameters.append(analysis_status)
        if category_id is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM material_category_links category_filter "
                "WHERE category_filter.material_id = m.id AND category_filter.category_id = ?)"
            )
            parameters.append(category_id)
        if tag_id is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM material_tag_links filter_link "
                "JOIN material_tags filter_tag ON filter_tag.id = filter_link.tag_id "
                "WHERE filter_link.material_id = m.id AND filter_link.tag_id = ? "
                "AND filter_tag.deleted_at IS NULL"
                + (" AND filter_tag.tag_group = ?" if tag_group is not None else "")
                + ")"
            )
            parameters.append(tag_id)
            if tag_group is not None:
                parameters.append(tag_group)
        elif tag_group is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM material_tag_links group_link "
                "JOIN material_tags group_tag ON group_tag.id = group_link.tag_id "
                "WHERE group_link.material_id = m.id AND group_tag.deleted_at IS NULL "
                "AND group_tag.tag_group = ?)"
            )
            parameters.append(tag_group)
        if pending_imports:
            clauses.append(
                "(m.analysis_status = 'unanalyzed' AND "
                "json_extract(m.import_metadata_json, '$.created_by') IN "
                "('pending_material_import', 'selection_context_menu', 'json_batch_import'))"
            )
        if untagged:
            clauses.append("NOT EXISTS (SELECT 1 FROM material_tag_links tl WHERE tl.material_id = m.id)")
        if query and query.strip():
            like = f"%{query.strip()}%"
            clauses.append(
                "(m.name LIKE ? OR m.description LIKE ? OR m.raw_text LIKE ? OR "
                "EXISTS (SELECT 1 FROM material_tag_links ql JOIN material_tags qt ON qt.id = ql.tag_id "
                "WHERE ql.material_id = m.id AND qt.deleted_at IS NULL AND qt.name LIKE ?))"
            )
            parameters.extend([like, like, like, like])
        pagination = ""
        if limit is not None:
            if limit < 1 or limit > 500:
                raise ValueError("limit must be between 1 and 500.")
            pagination = " LIMIT ? OFFSET ?"
            parameters.extend([limit, max(0, offset)])
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT m.*, NULL AS project_name,
                       COALESCE((
                           SELECT GROUP_CONCAT(t.name, char(31))
                           FROM material_tag_links link
                           JOIN material_tags t ON t.id = link.tag_id
                           WHERE link.material_id = m.id AND t.deleted_at IS NULL
                       ), '') AS tag_names,
                       COALESCE((
                           SELECT GROUP_CONCAT(t.name, char(31))
                           FROM material_tag_links link
                           JOIN material_tags t ON t.id = link.tag_id
                           WHERE link.material_id = m.id AND t.deleted_at IS NULL
                             AND t.tag_group = 'general'
                       ), '') AS general_tag_names,
                       COALESCE((
                           SELECT GROUP_CONCAT(t.name, char(31))
                           FROM material_tag_links link
                           JOIN material_tags t ON t.id = link.tag_id
                           WHERE link.material_id = m.id AND t.deleted_at IS NULL
                             AND t.tag_group = 'applicable_scene'
                       ), '') AS applicable_scene_tag_names,
                       COALESCE((
                           SELECT GROUP_CONCAT(c.id, char(31))
                           FROM material_category_links link
                           JOIN material_categories c ON c.id = link.category_id
                           WHERE link.material_id = m.id AND c.deleted_at IS NULL
                       ), '') AS category_ids,
                       COALESCE((
                           SELECT GROUP_CONCAT(c.name, char(31))
                           FROM material_category_links link
                           JOIN material_categories c ON c.id = link.category_id
                           WHERE link.material_id = m.id AND c.deleted_at IS NULL
                       ), '') AS category_names
                FROM materials m
                WHERE {' AND '.join(clauses)}
                ORDER BY m.updated_at DESC, m.id DESC
                {pagination}
                """,
                parameters,
            ).fetchall()
        return [self._row_to_material(row) for row in rows]

    def get_material(self, material_id: int) -> Material | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT m.*, NULL AS project_name,
                       COALESCE((
                           SELECT GROUP_CONCAT(t.name, char(31)) FROM material_tag_links link
                           JOIN material_tags t ON t.id = link.tag_id
                           WHERE link.material_id = m.id AND t.deleted_at IS NULL
                       ), '') AS tag_names,
                       COALESCE((
                           SELECT GROUP_CONCAT(t.name, char(31)) FROM material_tag_links link
                           JOIN material_tags t ON t.id = link.tag_id
                           WHERE link.material_id = m.id AND t.deleted_at IS NULL
                             AND t.tag_group = 'general'
                       ), '') AS general_tag_names,
                       COALESCE((
                           SELECT GROUP_CONCAT(t.name, char(31)) FROM material_tag_links link
                           JOIN material_tags t ON t.id = link.tag_id
                           WHERE link.material_id = m.id AND t.deleted_at IS NULL
                             AND t.tag_group = 'applicable_scene'
                       ), '') AS applicable_scene_tag_names,
                       COALESCE((
                           SELECT GROUP_CONCAT(c.id, char(31)) FROM material_category_links link
                           JOIN material_categories c ON c.id = link.category_id
                           WHERE link.material_id = m.id AND c.deleted_at IS NULL
                       ), '') AS category_ids,
                       COALESCE((
                           SELECT GROUP_CONCAT(c.name, char(31)) FROM material_category_links link
                           JOIN material_categories c ON c.id = link.category_id
                           WHERE link.material_id = m.id AND c.deleted_at IS NULL
                       ), '') AS category_names
                FROM materials m
                WHERE m.id = ? AND m.deleted_at IS NULL
                """,
                (material_id,),
            ).fetchone()
        return self._row_to_material(row) if row is not None else None

    def create_material(
        self,
        *,
        material_type: str,
        scope: str,
        name: str,
        project_id: int | None = None,
        description: str = "",
        detail_level: str = "standard",
        raw_text: str = "",
        content: dict[str, Any] | None = None,
        analysis_status: str = "analyzed",
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
        source_material_id: int | None = None,
        source_version: int | None = None,
        timeline_start_chapter: int | None = None,
        timeline_end_chapter: int | None = None,
        sort_order: int = 0,
        tag_ids: list[int] | None = None,
        category_ids: list[int] | None = None,
    ) -> int:
        material_type = _validate_type(material_type)
        requested_scope = _validate_scope(scope, project_id)
        normalized_name = _required_name(name)
        detail_level = _validate_detail_level(detail_level)
        analysis_status = _validate_analysis_status(analysis_status)
        _validate_timeline(timeline_start_chapter, timeline_end_chapter)
        source_metadata_value = dict(source_metadata or {})
        if requested_scope == "project":
            source_metadata_value.setdefault("legacy_scope", "project")
            source_metadata_value.setdefault("legacy_project_id", project_id)
            source_metadata_value.setdefault("migrated_to_unified_library", True)
        with session(self.database_path) as connection:
            if project_id is not None:
                self._require_project(connection, project_id)
            cursor = connection.execute(
                """
                INSERT INTO materials (
                    material_type, scope, project_id, name, description, detail_level,
                    raw_text, content_json, analysis_status, source_metadata_json,
                    import_metadata_json, source_material_id, source_version,
                    timeline_start_chapter, timeline_end_chapter, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_type,
                    "public",
                    None,
                    normalized_name,
                    description,
                    detail_level,
                    raw_text,
                    json.dumps(
                        normalize_material_content(material_type, content or {}),
                        ensure_ascii=False,
                    ),
                    analysis_status,
                    json.dumps(source_metadata_value, ensure_ascii=False),
                    json.dumps(import_metadata or {}, ensure_ascii=False),
                    source_material_id,
                    source_version,
                    timeline_start_chapter,
                    timeline_end_chapter,
                    sort_order,
                ),
            )
            material_id = int(cursor.lastrowid)
            self._replace_tags(connection, material_id, tag_ids or [])
            self._replace_categories(connection, material_id, category_ids or [], material_type)
        return material_id

    def create_extracted_material(
        self,
        *,
        material_type: str,
        name: str,
        description: str,
        detail_level: str,
        raw_text: str,
        content: dict[str, Any],
        source_metadata: dict[str, Any],
        import_metadata: dict[str, Any],
        sort_order: int,
        general_tags: list[str],
        applicable_scene_tags: list[str],
        category_ids: list[int],
    ) -> int:
        """Create one confirmed AI candidate and all accepted links atomically."""
        return self.create_extracted_material_batch(
            material_type=material_type,
            candidates=[
                {
                    "name": name,
                    "description": description,
                    "content": content,
                    "sort_order": sort_order,
                    "general_tags": general_tags,
                    "applicable_scene_tags": applicable_scene_tags,
                    "category_ids": category_ids,
                }
            ],
            detail_level=detail_level,
            raw_text=raw_text,
            source_metadata=source_metadata,
            import_metadata=import_metadata,
        )[0]

    def create_extracted_material_batch(
        self,
        *,
        material_type: str,
        candidates: list[dict[str, Any]],
        detail_level: str,
        raw_text: str,
        source_metadata: dict[str, Any],
        import_metadata: dict[str, Any],
    ) -> list[int]:
        """Create all confirmed AI candidates and accepted relations in one transaction."""
        material_type = _validate_type(material_type)
        detail_level = _validate_detail_level(detail_level)
        if not candidates:
            raise ValueError("At least one material candidate is required.")
        prepared: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id") or "")
            try:
                prepared.append(
                    {
                        **candidate,
                        "candidate_id": candidate_id,
                        "name": _required_name(str(candidate.get("name") or "")),
                        "content": normalize_material_content(
                            material_type, candidate.get("content")
                        ),
                        "general_tags": _normalized_tag_names(candidate.get("general_tags") or []),
                        "applicable_scene_tags": _normalized_tag_names(
                            candidate.get("applicable_scene_tags") or []
                        ),
                        "category_ids": [
                            int(value) for value in candidate.get("category_ids", [])
                        ],
                    }
                )
            except Exception as exc:
                raise CandidateApplyError(
                    candidate_id,
                    f"Material candidate {candidate_id} failed: {exc}",
                ) from exc
        created_ids: list[int] = []
        with session(self.database_path) as connection:
            valid_categories = {
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM material_categories WHERE material_type = ? AND deleted_at IS NULL",
                    (material_type,),
                ).fetchall()
            }
            for candidate in prepared:
                if not set(candidate["category_ids"]).issubset(valid_categories):
                    raise CandidateApplyError(
                        candidate["candidate_id"],
                        (
                            f"Material candidate {candidate['candidate_id']} failed: "
                            "one or more categories do not exist or have the wrong type."
                        ),
                    )
            for candidate in prepared:
                try:
                    cursor = connection.execute(
                        """
                        INSERT INTO materials (
                            material_type, scope, project_id, name, description, detail_level,
                            raw_text, content_json, analysis_status, source_metadata_json,
                            import_metadata_json, sort_order
                        ) VALUES (?, 'public', NULL, ?, ?, ?, ?, ?, 'analyzed', ?, ?, ?)
                        """,
                        (
                            material_type,
                            candidate["name"],
                            str(candidate.get("description") or ""),
                            detail_level,
                            raw_text,
                            json.dumps(candidate["content"], ensure_ascii=False),
                            json.dumps(source_metadata, ensure_ascii=False),
                            json.dumps(import_metadata, ensure_ascii=False),
                            int(candidate.get("sort_order") or 0),
                        ),
                    )
                    material_id = int(cursor.lastrowid)
                    created_ids.append(material_id)
                    for group, names in (
                        ("general", candidate["general_tags"]),
                        ("applicable_scene", candidate["applicable_scene_tags"]),
                    ):
                        for tag_name in names:
                            connection.execute(
                                """
                                INSERT INTO material_tags (name, normalized_name, tag_group)
                                VALUES (?, ?, ?)
                                ON CONFLICT(normalized_name, tag_group) WHERE deleted_at IS NULL
                                DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                                """,
                                (tag_name, _normalize_tag_name(tag_name), group),
                            )
                            tag_id = int(
                                connection.execute(
                                    """
                                    SELECT id FROM material_tags
                                    WHERE normalized_name = ? AND tag_group = ? AND deleted_at IS NULL
                                    """,
                                    (_normalize_tag_name(tag_name), group),
                                ).fetchone()["id"]
                            )
                            connection.execute(
                                "INSERT OR IGNORE INTO material_tag_links (material_id, tag_id) VALUES (?, ?)",
                                (material_id, tag_id),
                            )
                    self._replace_categories(
                        connection,
                        material_id,
                        candidate["category_ids"],
                        material_type,
                    )
                except Exception as exc:
                    raise CandidateApplyError(
                        candidate["candidate_id"],
                        f"Material candidate {candidate['candidate_id']} failed: {exc}",
                    ) from exc
        return created_ids

    def update_material(
        self,
        material_id: int,
        *,
        name: str,
        description: str,
        detail_level: str,
        content: dict[str, Any],
        raw_text: str | None = None,
        analysis_status: str | None = None,
        timeline_start_chapter: int | None = None,
        timeline_end_chapter: int | None = None,
        sort_order: int = 0,
        tag_ids: list[int] | None = None,
        category_ids: list[int] | None = None,
    ) -> None:
        _validate_timeline(timeline_start_chapter, timeline_end_chapter)
        status = _validate_analysis_status(analysis_status) if analysis_status is not None else None
        with session(self.database_path) as connection:
            current = connection.execute(
                "SELECT id FROM materials WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            ).fetchone()
            if current is None:
                raise FileNotFoundError(f"Material not found: {material_id}")
            connection.execute(
                """
                UPDATE materials
                SET name = ?, description = ?, detail_level = ?, content_json = ?,
                    raw_text = COALESCE(?, raw_text),
                    analysis_status = COALESCE(?, analysis_status),
                    timeline_start_chapter = ?, timeline_end_chapter = ?, sort_order = ?,
                    version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    _required_name(name),
                    description,
                    _validate_detail_level(detail_level),
                    json.dumps(
                        normalize_material_content(
                            str(
                                connection.execute(
                                    "SELECT material_type FROM materials WHERE id = ?",
                                    (material_id,),
                                ).fetchone()["material_type"]
                            ),
                            content,
                        ),
                        ensure_ascii=False,
                    ),
                    raw_text,
                    status,
                    timeline_start_chapter,
                    timeline_end_chapter,
                    sort_order,
                    material_id,
                ),
            )
            if tag_ids is not None:
                self._replace_tags(connection, material_id, tag_ids)
            if category_ids is not None:
                row = connection.execute(
                    "SELECT material_type FROM materials WHERE id = ?",
                    (material_id,),
                ).fetchone()
                self._replace_categories(connection, material_id, category_ids, str(row["material_type"]))

    def analyze_material(
        self,
        material_id: int,
        *,
        content: dict[str, Any],
        model_id: int | None = None,
        invocation_id: int | None = None,
    ) -> None:
        if not isinstance(content, dict) or not content:
            raise ValueError("Material analysis result must be a non-empty object.")
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT material_type, import_metadata_json FROM materials WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Material not found: {material_id}")
            metadata = _json_object(str(row["import_metadata_json"]))
            metadata["last_analyzed_model_id"] = model_id
            metadata["last_analysis_invocation_id"] = invocation_id
            connection.execute(
                """
                UPDATE materials
                SET content_json = ?, analysis_status = 'analyzed',
                    import_metadata_json = ?, version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    json.dumps(
                        normalize_material_content(str(row["material_type"]), content),
                        ensure_ascii=False,
                    ),
                    json.dumps(metadata, ensure_ascii=False),
                    material_id,
                ),
            )

    def import_json_items(
        self,
        value: object,
        *,
        default_scope: str = "public",
        default_project_id: int | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        items = value if isinstance(value, list) else [value]
        if not items or not all(isinstance(item, dict) for item in items):
            raise ValueError("Material JSON import requires an object or an array of objects.")
        imported: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, raw_item in enumerate(items):
            item = dict(raw_item)
            try:
                original_type = str(item.get("material_type") or item.get("type") or "").strip()
                material_type = "plot_skeleton" if original_type == "outline" else _validate_type(original_type)
                scope = str(item.get("scope") or default_scope)
                project_id = item.get("project_id", default_project_id)
                if project_id is not None:
                    project_id = int(project_id)
                tag_ids = self._tag_ids_from_names(item.get("tags", []))
                import_metadata = _json_object_value(item.get("import_metadata"))
                if original_type == "outline":
                    import_metadata["legacy_material_type"] = "outline"
                import_metadata["created_by"] = "json_batch_import"
                material_id = self.create_material(
                    material_type=material_type,
                    scope=scope,
                    project_id=project_id,
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    detail_level=str(item.get("detail_level") or "standard"),
                    raw_text=str(item.get("raw_text") or ""),
                    content=_json_object_value(item.get("content")),
                    analysis_status=str(item.get("analysis_status") or "unanalyzed"),
                    source_metadata=_json_object_value(item.get("source_metadata")),
                    import_metadata=import_metadata,
                    tag_ids=tag_ids,
                )
                material = self.get_material(material_id)
                imported.append(
                    {
                        "index": index,
                        "id": material_id,
                        "name": material.name if material else str(item.get("name") or ""),
                        "material_type": material_type,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"index": index, "name": str(item.get("name") or ""), "error": str(exc)})
        return {"imported": imported, "errors": errors}

    def delete_material(self, material_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE materials SET deleted_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Material not found: {material_id}")

    def copy_material(
        self,
        material_id: int,
        *,
        target_scope: str,
        target_project_id: int | None = None,
        tag_ids: list[int] | None = None,
    ) -> int:
        source = self.get_material(material_id)
        if source is None:
            raise FileNotFoundError(f"Material not found: {material_id}")
        copied_id = self.create_material(
            material_type=source.material_type,
            scope=target_scope,
            project_id=target_project_id,
            name=source.name,
            description=source.description,
            detail_level=source.detail_level,
            raw_text=source.raw_text,
            content=_json_object(source.content_json),
            analysis_status=source.analysis_status,
            source_metadata={
                **_json_object(source.source_metadata_json),
                "copied_from_scope": source.scope,
                "copied_from_project_id": source.project_id,
            },
            import_metadata={
                **_json_object(source.import_metadata_json),
                "created_by": "material_copy",
                "source_material_id": source.id,
                "source_version": source.version,
            },
            source_material_id=source.id,
            source_version=source.version,
            timeline_start_chapter=source.timeline_start_chapter,
            timeline_end_chapter=source.timeline_end_chapter,
            sort_order=source.sort_order,
            tag_ids=tag_ids,
        )
        if tag_ids is None:
            with session(self.database_path) as connection:
                source_tags = [
                    int(row["tag_id"])
                    for row in connection.execute(
                        "SELECT tag_id FROM material_tag_links WHERE material_id = ?",
                        (source.id,),
                    ).fetchall()
                ]
                self._replace_tags(connection, copied_id, source_tags)
        return copied_id

    def list_tags(self, tag_group: str | None = None) -> list[MaterialTag]:
        if tag_group is not None and tag_group not in MATERIAL_TAG_GROUPS:
            raise ValueError(f"Unsupported material tag group: {tag_group}")
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT t.*, COUNT(m.id) AS resource_count
                FROM material_tags t
                LEFT JOIN material_tag_links link ON link.tag_id = t.id
                LEFT JOIN materials m ON m.id = link.material_id AND m.deleted_at IS NULL
                WHERE t.deleted_at IS NULL
                  {"AND t.tag_group = ?" if tag_group is not None else ""}
                GROUP BY t.id
                ORDER BY t.sort_order, t.name
                """,
                (tag_group,) if tag_group is not None else (),
            ).fetchall()
        return [self._row_to_tag(row) for row in rows]

    def _tag_ids_from_names(self, value: object, *, tag_group: str = "general") -> list[int]:
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise ValueError("tags must be an array of names.")
        existing = {tag.normalized_name: tag.id for tag in self.list_tags(tag_group)}
        ids: list[int] = []
        for raw_name in value:
            name = str(raw_name).strip()
            if not name:
                continue
            normalized = _normalize_tag_name(name)
            tag_id = existing.get(normalized)
            if tag_id is None:
                tag = self.create_tag(name, tag_group=tag_group)
                tag_id = tag.id
                existing[tag.normalized_name] = tag.id
            if tag_id not in ids:
                ids.append(tag_id)
        return ids

    def create_tag(self, name: str, *, tag_group: str = "general") -> MaterialTag:
        if tag_group not in MATERIAL_TAG_GROUPS:
            raise ValueError(f"Unsupported material tag group: {tag_group}")
        normalized_name = _required_tag_name(name)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO material_tags (name, normalized_name, tag_group)
                VALUES (?, ?, ?)
                ON CONFLICT(normalized_name, tag_group) WHERE deleted_at IS NULL
                DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """,
                (normalized_name, _normalize_tag_name(normalized_name), tag_group),
            )
            tag_id = int(cursor.lastrowid) if cursor.lastrowid else int(
                connection.execute(
                    "SELECT id FROM material_tags WHERE normalized_name = ? AND tag_group = ? AND deleted_at IS NULL",
                    (_normalize_tag_name(normalized_name), tag_group),
                ).fetchone()["id"]
            )
        return next(item for item in self.list_tags() if item.id == tag_id)

    def rename_tag(self, tag_id: int, name: str) -> MaterialTag:
        normalized_name = _required_tag_name(name)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE material_tags
                SET name = ?, normalized_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (normalized_name, _normalize_tag_name(normalized_name), tag_id),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Material tag not found: {tag_id}")
        return next(item for item in self.list_tags() if item.id == tag_id)

    def delete_tag(self, tag_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute("DELETE FROM material_tag_links WHERE tag_id = ?", (tag_id,))
            cursor = connection.execute(
                "UPDATE material_tags SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                (tag_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Material tag not found: {tag_id}")

    def set_material_tag(self, material_id: int, tag_id: int, selected: bool) -> Material:
        with session(self.database_path) as connection:
            self._require_material(connection, material_id)
            self._require_tag(connection, tag_id)
            if selected:
                connection.execute(
                    "INSERT OR IGNORE INTO material_tag_links (material_id, tag_id) VALUES (?, ?)",
                    (material_id, tag_id),
                )
            else:
                connection.execute(
                    "DELETE FROM material_tag_links WHERE material_id = ? AND tag_id = ?",
                    (material_id, tag_id),
                )
        material = self.get_material(material_id)
        if material is None:
            raise FileNotFoundError(f"Material not found: {material_id}")
        return material

    def list_categories(self, material_type: str | None = None) -> list[MaterialCategory]:
        if material_type is not None:
            material_type = _validate_type(material_type)
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, COUNT(m.id) AS resource_count
                FROM material_categories c
                LEFT JOIN material_category_links link ON link.category_id = c.id
                LEFT JOIN materials m ON m.id = link.material_id AND m.deleted_at IS NULL
                WHERE c.deleted_at IS NULL
                  {"AND c.material_type = ?" if material_type is not None else ""}
                GROUP BY c.id
                ORDER BY c.material_type, c.sort_order, c.name
                """,
                (material_type,) if material_type is not None else (),
            ).fetchall()
        return [
            MaterialCategory(
                id=int(row["id"]),
                material_type=str(row["material_type"]),
                name=str(row["name"]),
                normalized_name=str(row["normalized_name"]),
                sort_order=int(row["sort_order"]),
                resource_count=int(row["resource_count"]),
            )
            for row in rows
        ]

    def create_category(self, material_type: str, name: str) -> MaterialCategory:
        material_type = _validate_type(material_type)
        clean_name = _required_category_name(name)
        normalized_name = _normalize_tag_name(clean_name)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO material_categories (material_type, name, normalized_name)
                VALUES (?, ?, ?)
                ON CONFLICT(material_type, normalized_name) WHERE deleted_at IS NULL
                DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """,
                (material_type, clean_name, normalized_name),
            )
            category_id = int(cursor.lastrowid) if cursor.lastrowid else int(
                connection.execute(
                    """
                    SELECT id FROM material_categories
                    WHERE material_type = ? AND normalized_name = ? AND deleted_at IS NULL
                    """,
                    (material_type, normalized_name),
                ).fetchone()["id"]
            )
        return next(item for item in self.list_categories() if item.id == category_id)

    def rename_category(self, category_id: int, name: str) -> MaterialCategory:
        clean_name = _required_category_name(name)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE material_categories
                SET name = ?, normalized_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (clean_name, _normalize_tag_name(clean_name), category_id),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Material category not found: {category_id}")
        return next(item for item in self.list_categories() if item.id == category_id)

    def delete_category(self, category_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute("DELETE FROM material_category_links WHERE category_id = ?", (category_id,))
            cursor = connection.execute(
                """
                UPDATE material_categories
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (category_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Material category not found: {category_id}")

    def set_material_category(self, material_id: int, category_id: int, selected: bool) -> Material:
        with session(self.database_path) as connection:
            material = connection.execute(
                "SELECT material_type FROM materials WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            ).fetchone()
            category = connection.execute(
                "SELECT material_type FROM material_categories WHERE id = ? AND deleted_at IS NULL",
                (category_id,),
            ).fetchone()
            if material is None:
                raise FileNotFoundError(f"Material not found: {material_id}")
            if category is None:
                raise FileNotFoundError(f"Material category not found: {category_id}")
            if str(material["material_type"]) != str(category["material_type"]):
                raise ValueError("Material category type must match the material type.")
            if selected:
                connection.execute(
                    "INSERT OR IGNORE INTO material_category_links (material_id, category_id) VALUES (?, ?)",
                    (material_id, category_id),
                )
            else:
                connection.execute(
                    "DELETE FROM material_category_links WHERE material_id = ? AND category_id = ?",
                    (material_id, category_id),
                )
        updated = self.get_material(material_id)
        if updated is None:
            raise FileNotFoundError(f"Material not found: {material_id}")
        return updated

    def get_project_material_filters(self, project_id: int) -> list[ProjectMaterialFilter]:
        with session(self.database_path) as connection:
            self._require_project(connection, project_id)
            rows = connection.execute(
                """
                SELECT f.*,
                       COALESCE((
                           SELECT GROUP_CONCAT(tag_id, char(31))
                           FROM project_material_filter_tags
                           WHERE filter_id = f.id
                       ), '') AS tag_ids
                FROM project_material_filters f
                WHERE f.project_id = ?
                ORDER BY f.material_type
                """,
                (project_id,),
            ).fetchall()
        by_type = {str(row["material_type"]): self._row_to_project_filter(row) for row in rows}
        return [
            by_type.get(material_type)
            or ProjectMaterialFilter(project_id, material_type, "any", (), (), True, True)
            for material_type in ("plot_skeleton", "scene_reference")
        ]

    def set_project_material_filter(
        self,
        project_id: int,
        material_type: str,
        *,
        match_mode: str = "any",
        tag_ids: list[int] | None = None,
        manual_material_ids: list[int] | None = None,
        include_scene_keywords: bool = True,
        include_applicable_scene_tags: bool = True,
    ) -> ProjectMaterialFilter:
        material_type = _validate_type(material_type)
        if match_mode not in PROJECT_FILTER_MATCH_MODES:
            raise ValueError(f"Unsupported project material match mode: {match_mode}")
        clean_tag_ids = list(dict.fromkeys(int(value) for value in (tag_ids or [])))
        clean_manual_ids = list(dict.fromkeys(int(value) for value in (manual_material_ids or [])))
        with session(self.database_path) as connection:
            self._require_project(connection, project_id)
            for tag_id in clean_tag_ids:
                self._require_tag(connection, tag_id)
            for material_id in clean_manual_ids:
                row = connection.execute(
                    """
                    SELECT id FROM materials
                    WHERE id = ? AND material_type = ? AND deleted_at IS NULL
                    """,
                    (material_id, material_type),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Material {material_id} does not match {material_type}.")
            connection.execute(
                """
                INSERT INTO project_material_filters (
                    project_id, material_type, match_mode, manual_material_ids_json,
                    include_scene_keywords, include_applicable_scene_tags
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, material_type) DO UPDATE SET
                    match_mode = excluded.match_mode,
                    manual_material_ids_json = excluded.manual_material_ids_json,
                    include_scene_keywords = excluded.include_scene_keywords,
                    include_applicable_scene_tags = excluded.include_applicable_scene_tags,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    project_id,
                    material_type,
                    match_mode,
                    json.dumps(clean_manual_ids),
                    int(include_scene_keywords),
                    int(include_applicable_scene_tags),
                ),
            )
            filter_id = int(
                connection.execute(
                    "SELECT id FROM project_material_filters WHERE project_id = ? AND material_type = ?",
                    (project_id, material_type),
                ).fetchone()["id"]
            )
            connection.execute("DELETE FROM project_material_filter_tags WHERE filter_id = ?", (filter_id,))
            for tag_id in clean_tag_ids:
                connection.execute(
                    "INSERT INTO project_material_filter_tags (filter_id, tag_id) VALUES (?, ?)",
                    (filter_id, tag_id),
                )
        return next(
            item for item in self.get_project_material_filters(project_id)
            if item.material_type == material_type
        )

    def list_materials_for_project(
        self,
        project_id: int,
        *,
        material_type: str | None = None,
        include_unanalyzed_manual: bool = True,
    ) -> list[Material]:
        filters = self.get_project_material_filters(project_id)
        selected_filters = [
            item for item in filters
            if material_type is None or item.material_type == _validate_type(material_type)
        ]
        materials = self.list_materials(material_type=material_type)
        tags_by_material: dict[int, set[int]] = {}
        if materials:
            placeholders = ",".join("?" for _ in materials)
            with session(self.database_path) as connection:
                for row in connection.execute(
                    f"""
                    SELECT material_id, tag_id
                    FROM material_tag_links
                    WHERE material_id IN ({placeholders})
                    """,
                    [item.id for item in materials],
                ).fetchall():
                    tags_by_material.setdefault(int(row["material_id"]), set()).add(
                        int(row["tag_id"])
                    )
        selected: list[Material] = []
        for material in materials:
            filter_value = next(
                (item for item in selected_filters if item.material_type == material.material_type),
                None,
            )
            if filter_value is None:
                continue
            is_manual = material.id in filter_value.manual_material_ids
            if material.analysis_status != "analyzed" and not (is_manual and include_unanalyzed_manual):
                continue
            material_tag_ids = tags_by_material.get(material.id, set())
            matches = [tag_id in material_tag_ids for tag_id in filter_value.tag_ids]
            tag_match = bool(matches) and (
                all(matches) if filter_value.match_mode == "all" else any(matches)
            )
            if is_manual or tag_match:
                selected.append(material)
        return selected

    def list_ai_settings(self) -> list[MaterialAISettings]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM material_ai_settings ORDER BY task_type"
            ).fetchall()
        return [self._row_to_ai_settings(row) for row in rows]

    def get_ai_settings(self, task_type: str) -> MaterialAISettings:
        _validate_ai_task_type(task_type)
        return next(item for item in self.list_ai_settings() if item.task_type == task_type)

    def update_ai_settings(
        self,
        task_type: str,
        *,
        model_id: int | None,
        detail_level: str,
        max_candidates: int,
        system_prompt: str,
        custom_requirements: str,
        user_prompt_template: str | None = None,
        analysis_dimensions: list[str] | None = None,
        generate_general_tags: bool | None = None,
        generate_applicable_scene_tags: bool | None = None,
        generate_tags: bool | None = None,
    ) -> MaterialAISettings:
        _validate_ai_task_type(task_type)
        _validate_detail_level(detail_level)
        if max_candidates < 1 or max_candidates > 20:
            raise ValueError("max_candidates must be between 1 and 20.")
        current = self.get_ai_settings(task_type)
        dimensions = _normalized_dimensions(
            list(current.analysis_dimensions) if analysis_dimensions is None else analysis_dimensions
        )
        general_tags = (
            generate_tags if generate_general_tags is None and generate_tags is not None
            else current.generate_general_tags if generate_general_tags is None
            else generate_general_tags
        )
        applicable_tags = (
            generate_tags if generate_applicable_scene_tags is None and generate_tags is not None
            else current.generate_applicable_scene_tags
            if generate_applicable_scene_tags is None
            else generate_applicable_scene_tags
        )
        prompt_template = (
            current.user_prompt_template if user_prompt_template is None else user_prompt_template
        )
        with session(self.database_path) as connection:
            if model_id is not None:
                model = connection.execute(
                    "SELECT id FROM ai_models WHERE id = ? AND deleted_at IS NULL",
                    (model_id,),
                ).fetchone()
                if model is None:
                    raise FileNotFoundError(f"AI model not found: {model_id}")
            connection.execute(
                """
                UPDATE material_ai_settings
                SET model_id = ?, detail_level = ?, max_candidates = ?,
                    system_prompt = ?, user_prompt_template = ?,
                    analysis_dimensions_json = ?,
                    generate_general_tags = ?, generate_applicable_scene_tags = ?,
                    generate_tags = ?, custom_requirements = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_type = ?
                """,
                (
                    model_id,
                    detail_level,
                    max_candidates,
                    system_prompt,
                    prompt_template,
                    json.dumps(dimensions, ensure_ascii=False),
                    int(general_tags),
                    int(applicable_tags),
                    int(general_tags or applicable_tags),
                    custom_requirements,
                    task_type,
                ),
            )
        return self.get_ai_settings(task_type)

    def reset_ai_settings(self, task_type: str) -> MaterialAISettings:
        _validate_ai_task_type(task_type)
        defaults = MATERIAL_AI_DEFAULTS[task_type]
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE material_ai_settings
                SET model_id = NULL, detail_level = 'standard', max_candidates = 6,
                    generate_tags = ?,
                    generate_general_tags = ?, generate_applicable_scene_tags = ?,
                    custom_requirements = '', system_prompt = ?,
                    user_prompt_template = ?, analysis_dimensions_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_type = ?
                """,
                (
                    int(defaults["generate_general_tags"] or defaults["generate_applicable_scene_tags"]),
                    int(defaults["generate_general_tags"]),
                    int(defaults["generate_applicable_scene_tags"]),
                    defaults["system_prompt"],
                    defaults["user_prompt_template"],
                    json.dumps(defaults["analysis_dimensions"], ensure_ascii=False),
                    task_type,
                ),
            )
        return self.get_ai_settings(task_type)

    @staticmethod
    def _require_project(connection, project_id: int) -> None:
        row = connection.execute(
            "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL",
            (project_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Project not found: {project_id}")

    @staticmethod
    def _require_material(connection, material_id: int) -> None:
        row = connection.execute(
            "SELECT id FROM materials WHERE id = ? AND deleted_at IS NULL",
            (material_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Material not found: {material_id}")

    @staticmethod
    def _require_tag(connection, tag_id: int) -> None:
        row = connection.execute(
            "SELECT id FROM material_tags WHERE id = ? AND deleted_at IS NULL",
            (tag_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Material tag not found: {tag_id}")

    @staticmethod
    def _replace_tags(connection, material_id: int, tag_ids: list[int]) -> None:
        connection.execute("DELETE FROM material_tag_links WHERE material_id = ?", (material_id,))
        for tag_id in dict.fromkeys(tag_ids):
            MaterialService._require_tag(connection, int(tag_id))
            connection.execute(
                "INSERT INTO material_tag_links (material_id, tag_id) VALUES (?, ?)",
                (material_id, int(tag_id)),
            )

    @staticmethod
    def _replace_categories(
        connection,
        material_id: int,
        category_ids: list[int],
        material_type: str,
    ) -> None:
        connection.execute("DELETE FROM material_category_links WHERE material_id = ?", (material_id,))
        for category_id in dict.fromkeys(int(value) for value in category_ids):
            row = connection.execute(
                """
                SELECT material_type FROM material_categories
                WHERE id = ? AND deleted_at IS NULL
                """,
                (category_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Material category not found: {category_id}")
            if str(row["material_type"]) != material_type:
                raise ValueError("Material category type must match the material type.")
            connection.execute(
                "INSERT INTO material_category_links (material_id, category_id) VALUES (?, ?)",
                (material_id, category_id),
            )

    @staticmethod
    def _row_to_material(row) -> Material:
        tag_names = str(row["tag_names"] or "")
        general_tag_names = str(row["general_tag_names"] or "")
        applicable_scene_tag_names = str(row["applicable_scene_tag_names"] or "")
        category_ids = str(row["category_ids"] or "")
        category_names = str(row["category_names"] or "")
        source_metadata = _json_object(str(row["source_metadata_json"]))
        import_metadata = _json_object(str(row["import_metadata_json"]))
        return Material(
            id=int(row["id"]),
            material_type=str(row["material_type"]),
            scope=str(row["scope"]),
            project_id=int(row["project_id"]) if row["project_id"] is not None else None,
            project_name=str(row["project_name"]) if row["project_name"] is not None else None,
            name=str(row["name"]),
            description=str(row["description"]),
            detail_level=str(row["detail_level"]),
            raw_text=str(row["raw_text"]),
            content_json=str(row["content_json"]),
            analysis_status=str(row["analysis_status"]),
            source_metadata_json=str(row["source_metadata_json"]),
            import_metadata_json=str(row["import_metadata_json"]),
            source_material_id=int(row["source_material_id"]) if row["source_material_id"] is not None else None,
            source_version=int(row["source_version"]) if row["source_version"] is not None else None,
            timeline_start_chapter=(
                int(row["timeline_start_chapter"]) if row["timeline_start_chapter"] is not None else None
            ),
            timeline_end_chapter=(
                int(row["timeline_end_chapter"]) if row["timeline_end_chapter"] is not None else None
            ),
            sort_order=int(row["sort_order"]),
            version=int(row["version"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            tags=tuple(item for item in tag_names.split(chr(31)) if item),
            general_tags=tuple(item for item in general_tag_names.split(chr(31)) if item),
            applicable_scene_tags=tuple(
                item for item in applicable_scene_tag_names.split(chr(31)) if item
            ),
            category_ids=tuple(int(item) for item in category_ids.split(chr(31)) if item),
            categories=tuple(item for item in category_names.split(chr(31)) if item),
            source_summary=_material_source_summary(source_metadata, import_metadata),
        )

    @staticmethod
    def _row_to_tag(row) -> MaterialTag:
        return MaterialTag(
            id=int(row["id"]),
            name=str(row["name"]),
            normalized_name=str(row["normalized_name"]),
            sort_order=int(row["sort_order"]),
            resource_count=int(row["resource_count"]),
            tag_group=str(row["tag_group"] or "general"),
        )

    @staticmethod
    def _row_to_project_filter(row) -> ProjectMaterialFilter:
        tag_ids = str(row["tag_ids"] or "")
        manual_ids = _json_int_list(row["manual_material_ids_json"])
        return ProjectMaterialFilter(
            project_id=int(row["project_id"]),
            material_type=str(row["material_type"]),
            match_mode=str(row["match_mode"]),
            tag_ids=tuple(int(value) for value in tag_ids.split(chr(31)) if value),
            manual_material_ids=tuple(manual_ids),
            include_scene_keywords=bool(row["include_scene_keywords"]),
            include_applicable_scene_tags=bool(row["include_applicable_scene_tags"]),
        )

    @staticmethod
    def _row_to_ai_settings(row) -> MaterialAISettings:
        return MaterialAISettings(
            task_type=str(row["task_type"]),
            model_id=int(row["model_id"]) if row["model_id"] is not None else None,
            detail_level=str(row["detail_level"]),
            max_candidates=int(row["max_candidates"]),
            system_prompt=str(row["system_prompt"]),
            user_prompt_template=str(row["user_prompt_template"]),
            analysis_dimensions=tuple(_json_string_list(row["analysis_dimensions_json"])),
            generate_general_tags=bool(row["generate_general_tags"]),
            generate_applicable_scene_tags=bool(row["generate_applicable_scene_tags"]),
            custom_requirements=str(row["custom_requirements"]),
            updated_at=str(row["updated_at"]),
        )


def _validate_type(value: str) -> str:
    if value not in MATERIAL_TYPES:
        raise ValueError(f"Unsupported material type: {value}")
    return value


def _validate_scope(value: str, project_id: int | None) -> str:
    if value not in MATERIAL_SCOPES:
        raise ValueError(f"Unsupported material scope: {value}")
    if value == "project" and project_id is None:
        raise ValueError("Project materials require a project_id.")
    if value == "public" and project_id is not None:
        raise ValueError("Public materials cannot belong to a project.")
    return value


def _validate_analysis_status(value: str) -> str:
    if value not in ANALYSIS_STATUSES:
        raise ValueError(f"Unsupported analysis status: {value}")
    return value


def _validate_detail_level(value: str) -> str:
    if value not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail level: {value}")
    return value


def _required_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Material name is required.")
    return normalized


def _required_tag_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Tag name is required.")
    if len(normalized) > 40:
        raise ValueError("Tag name must be 40 characters or fewer.")
    return normalized


def _normalize_tag_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _normalized_tag_names(values: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values[:8]:
        name = _required_tag_name(str(value))
        normalized = _normalize_tag_name(name)
        if normalized not in seen:
            names.append(name)
            seen.add(normalized)
    return names


def _normalized_dimensions(values: list[str]) -> list[str]:
    dimensions: list[str] = []
    seen: set[str] = set()
    for value in values:
        dimension = str(value).strip()
        key = dimension.casefold()
        if dimension and key not in seen:
            dimensions.append(dimension)
            seen.add(key)
    return dimensions


def _validate_timeline(start: int | None, end: int | None) -> None:
    if start is not None and start < 1:
        raise ValueError("timeline_start_chapter must be greater than 0.")
    if end is not None and end < 1:
        raise ValueError("timeline_end_chapter must be greater than 0.")
    if start is not None and end is not None and end < start:
        raise ValueError("timeline_end_chapter cannot be before timeline_start_chapter.")


def _required_category_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Material category name is required.")
    if len(normalized) > 80:
        raise ValueError("Material category name must be 80 characters or fewer.")
    return normalized


def _validate_ai_task_type(value: str) -> str:
    if value not in MATERIAL_AI_TASK_TYPES:
        raise ValueError(f"Unsupported material AI task type: {value}")
    return value


def normalize_material_content(material_type: str, value: object) -> dict[str, Any]:
    if material_type == "plot_skeleton":
        return normalize_plot_skeleton_content(value)
    if material_type == "scene_reference":
        return normalize_scene_reference_content(value)
    raise ValueError(f"Unsupported material type: {material_type}")


def normalize_plot_skeleton_content(value: object) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    known = {
        "schema_version", "premise", "stages", "conflicts", "turning_points",
        "climax", "resolution", "hooks", "legacy_extra",
    }
    legacy_extra = _json_object_value(source.get("legacy_extra")) if isinstance(source.get("legacy_extra"), dict) else {}
    legacy_extra.update({key: item for key, item in source.items() if key not in known})
    return {
        "schema_version": 1,
        "premise": str(source.get("premise") or source.get("summary") or "").strip(),
        "stages": _normalize_structured_items(source.get("stages"), "stage"),
        "conflicts": _normalize_structured_items(source.get("conflicts"), "conflict"),
        "turning_points": _normalize_structured_items(source.get("turning_points"), "turning-point"),
        "climax": _normalize_structured_object(source.get("climax"), "climax"),
        "resolution": _normalize_structured_object(source.get("resolution"), "resolution"),
        "hooks": _normalize_structured_items(source.get("hooks"), "hook"),
        "legacy_extra": legacy_extra,
    }


def normalize_scene_reference_content(value: object) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    known = {
        "schema_version", "summary", "key_beats", "actions", "environment",
        "sensory", "writing_guidance", "source_cues", "avoidances",
        "applicable_conditions", "legacy_extra",
    }
    legacy_extra = _json_object_value(source.get("legacy_extra")) if isinstance(source.get("legacy_extra"), dict) else {}
    legacy_extra.update({key: item for key, item in source.items() if key not in known})
    return {
        "schema_version": 1,
        "summary": str(source.get("summary") or "").strip(),
        "key_beats": _normalize_structured_items(source.get("key_beats"), "beat"),
        "actions": _normalize_structured_items(source.get("actions"), "action"),
        "environment": _normalize_structured_items(source.get("environment"), "environment"),
        "sensory": _normalize_structured_items(source.get("sensory"), "sensory"),
        "writing_guidance": _normalize_structured_items(source.get("writing_guidance"), "guidance"),
        "source_cues": _normalize_structured_items(source.get("source_cues"), "source-cue"),
        "avoidances": _normalize_structured_items(source.get("avoidances"), "avoidance"),
        "applicable_conditions": _normalize_structured_items(
            source.get("applicable_conditions"), "condition"
        ),
        "legacy_extra": legacy_extra,
    }


def _normalize_structured_items(value: object, prefix: str) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if isinstance(item, dict):
            entry = dict(item)
            entry["id"] = str(entry.get("id") or f"{prefix}-{index + 1}")
            if "summary" not in entry:
                entry["summary"] = str(
                    entry.get("text") or entry.get("title") or entry.get("event") or ""
                ).strip()
        else:
            entry = {"id": f"{prefix}-{index + 1}", "summary": str(item).strip()}
        if str(entry.get("summary") or "").strip() or len(entry) > 2:
            normalized.append(entry)
    return normalized


def _normalize_structured_object(value: object, prefix: str) -> dict[str, Any]:
    if isinstance(value, dict):
        result = dict(value)
        result["id"] = str(result.get("id") or prefix)
        if "summary" not in result:
            result["summary"] = str(result.get("text") or result.get("event") or "").strip()
        return result
    return {"id": prefix, "summary": str(value or "").strip()}


def _material_source_summary(
    source_metadata: dict[str, Any],
    import_metadata: dict[str, Any],
) -> MaterialSourceSummary:
    source_kind = str(
        source_metadata.get("source_kind")
        or source_metadata.get("source_type")
        or import_metadata.get("created_by")
        or ""
    )
    document_id = _optional_int(source_metadata.get("document_id"))
    chapter_id = _optional_int(source_metadata.get("chapter_id"))
    project_id = _optional_int(
        source_metadata.get("project_id") or source_metadata.get("legacy_project_id")
    )
    document_title = str(source_metadata.get("document_title") or "").strip()
    chapter_title = str(source_metadata.get("chapter_title") or "").strip()
    file_name = str(
        source_metadata.get("file_name")
        or source_metadata.get("source_file_name")
        or source_metadata.get("source_path")
        or ""
    ).strip()
    if source_metadata.get("migrated_to_unified_library") or source_kind == "legacy_project_material":
        return MaterialSourceSummary(
            "legacy_project_material",
            f"历史工程素材 · {source_metadata.get('project_name') or project_id or '未知工程'}",
            project_id=project_id,
        )
    if source_kind in {"document", "document_selection", "selection_context_menu"} or document_id:
        label = f"《{document_title}》" if document_title else "文档选区"
        if chapter_title:
            label += f" · {chapter_title}"
        return MaterialSourceSummary("document_selection", label, document_id, chapter_id, project_id)
    if source_kind in {"project", "project_selection"}:
        project_name = str(
            source_metadata.get("project_name")
            or source_metadata.get("source_project_name")
            or ""
        ).strip()
        return MaterialSourceSummary(
            "project_selection",
            f"工程“{project_name}”选区" if project_name else "工程选区",
            project_id=project_id,
            chapter_id=chapter_id,
        )
    if source_kind in {"file", "file_import", "manual_import", "json_import", "json_batch_import"}:
        return MaterialSourceSummary(
            "file_import",
            f"文件 {Path(file_name).name}" if file_name else "文件导入",
        )
    if source_kind in {"paste", "pasted_text"}:
        return MaterialSourceSummary("pasted_text", "粘贴文本")
    if source_kind.startswith("ai_") or "extraction" in source_kind:
        return MaterialSourceSummary("ai_extraction", "AI 提取", document_id, chapter_id, project_id)
    if source_kind in {"material_copy", "legacy_copy"}:
        return MaterialSourceSummary("legacy_copy", "历史素材副本", project_id=project_id)
    return MaterialSourceSummary("manual", "本地创建", document_id, chapter_id, project_id)


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _json_int_list(value: object) -> list[int]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    result: list[int] = []
    for item in parsed:
        parsed_item = _optional_int(item)
        if parsed_item is not None and parsed_item not in result:
            result.append(parsed_item)
    return result


def _json_string_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed if str(item).strip()] if isinstance(parsed, list) else []


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_object_value(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return dict(value)
