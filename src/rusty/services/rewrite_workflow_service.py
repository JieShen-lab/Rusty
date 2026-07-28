from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from rusty.db import initialize_database, session
from rusty.services.context_service import ContextService
from rusty.services.material_service import MaterialService
from rusty.services.project_service import default_database_path
from rusty.services.scene_service import SceneService


SCENE_ANALYSIS_KEYS = {
    "must_preserve_events",
    "expandable_points",
    "characters_present",
    "required_start_state",
    "required_end_state",
    "material_insertion_points",
    "relevant_style_rules",
    "risks",
}
CONSISTENCY_KEYS = {
    "missing_events",
    "altered_facts",
    "unsupported_additions",
    "character_conflicts",
    "knowledge_conflicts",
    "timeline_conflicts",
    "transition_issues",
    "style_repetition",
    "revision_required",
}


@dataclass(frozen=True)
class SkeletonVersion:
    skeleton_id: int
    version_id: int
    version: int
    status: str
    nodes: tuple[dict[str, Any], ...]


class RewriteWorkflowService:
    """Persist the two explicit rewrite modes and their multi-stage outputs."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.scene_service = SceneService(self.database_path)
        self.context_service = ContextService(self.database_path)
        self.material_service = MaterialService(self.database_path)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def create_skeleton(
        self,
        *,
        project_id: int,
        chapter_id: int,
        scene_id: int | None,
        nodes: Iterable[dict[str, Any]],
        scope: str = "scene",
        source_kind: str = "original_analysis",
    ) -> SkeletonVersion:
        normalized = _normalize_skeleton_nodes(nodes)
        if not normalized:
            raise ValueError("A story skeleton requires at least one event node.")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO story_skeletons (
                    project_id, chapter_id, scene_id, scope, source_kind, status, current_version
                ) VALUES (?, ?, ?, ?, ?, 'draft', 1)
                """,
                (project_id, chapter_id, scene_id, scope, source_kind),
            )
            skeleton_id = int(cursor.lastrowid)
            version_cursor = connection.execute(
                """
                INSERT INTO story_skeleton_versions (skeleton_id, version, nodes_json)
                VALUES (?, 1, ?)
                """,
                (skeleton_id, json.dumps(normalized, ensure_ascii=False)),
            )
        return SkeletonVersion(skeleton_id, int(version_cursor.lastrowid), 1, "draft", tuple(normalized))

    def revise_skeleton(
        self,
        skeleton_id: int,
        nodes: Iterable[dict[str, Any]],
        *,
        change_note: str = "",
    ) -> SkeletonVersion:
        normalized = _normalize_skeleton_nodes(nodes)
        if not normalized:
            raise ValueError("A story skeleton requires at least one event node.")
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT current_version FROM story_skeletons WHERE id = ?",
                (skeleton_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Story skeleton not found: {skeleton_id}")
            version = int(row["current_version"]) + 1
            cursor = connection.execute(
                """
                INSERT INTO story_skeleton_versions (
                    skeleton_id, version, nodes_json, change_note
                ) VALUES (?, ?, ?, ?)
                """,
                (skeleton_id, version, json.dumps(normalized, ensure_ascii=False), change_note),
            )
            connection.execute(
                """
                UPDATE story_skeletons
                SET current_version = ?, status = 'draft', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (version, skeleton_id),
            )
        return SkeletonVersion(skeleton_id, int(cursor.lastrowid), version, "draft", tuple(normalized))

    def confirm_skeleton(self, skeleton_id: int, version: int | None = None) -> SkeletonVersion:
        with session(self.database_path) as connection:
            skeleton = connection.execute(
                "SELECT current_version FROM story_skeletons WHERE id = ?",
                (skeleton_id,),
            ).fetchone()
            if skeleton is None:
                raise FileNotFoundError(f"Story skeleton not found: {skeleton_id}")
            selected_version = int(version or skeleton["current_version"])
            row = connection.execute(
                """
                SELECT id, nodes_json
                FROM story_skeleton_versions
                WHERE skeleton_id = ? AND version = ?
                """,
                (skeleton_id, selected_version),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Skeleton version not found: {skeleton_id}@{selected_version}")
            connection.execute(
                """
                UPDATE story_skeleton_versions
                SET confirmed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (int(row["id"]),),
            )
            connection.execute(
                """
                UPDATE story_skeletons
                SET current_version = ?, status = 'confirmed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (selected_version, skeleton_id),
            )
        return SkeletonVersion(
            skeleton_id,
            int(row["id"]),
            selected_version,
            "confirmed",
            tuple(_json_list_of_objects(row["nodes_json"])),
        )

    def create_skeleton_rewrite_plan(
        self,
        *,
        project_id: int,
        chapter_id: int,
        scene_id: int,
        skeleton_version_id: int,
        plan: dict[str, Any],
    ) -> int:
        self._require_confirmed_skeleton_version(skeleton_version_id)
        normalized = _normalize_plan(plan)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO rewrite_plans (
                    project_id, chapter_id, scene_id, mode,
                    skeleton_version_id, plan_json, status
                ) VALUES (?, ?, ?, 'skeleton_rewrite', ?, ?, 'draft')
                """,
                (
                    project_id,
                    chapter_id,
                    scene_id,
                    skeleton_version_id,
                    json.dumps(normalized, ensure_ascii=False),
                ),
            )
        return int(cursor.lastrowid)

    def create_expansion_plan(
        self,
        *,
        project_id: int,
        chapter_id: int,
        scene_id: int,
        skeleton_version_id: int,
        plan: dict[str, Any],
        material_mappings: Iterable[dict[str, Any]],
    ) -> int:
        self._require_confirmed_skeleton_version(skeleton_version_id)
        normalized_plan = _normalize_plan(plan)
        mappings = list(material_mappings)
        if not mappings:
            raise ValueError("Expansion mode requires at least one structured material mapping.")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO rewrite_plans (
                    project_id, chapter_id, scene_id, mode,
                    skeleton_version_id, plan_json, status
                ) VALUES (?, ?, ?, 'expansion', ?, ?, 'draft')
                """,
                (
                    project_id,
                    chapter_id,
                    scene_id,
                    skeleton_version_id,
                    json.dumps(normalized_plan, ensure_ascii=False),
                ),
            )
            plan_id = int(cursor.lastrowid)
            for mapping in mappings:
                material_id = int(mapping["material_id"])
                material = self.material_service.get_material(material_id)
                if material is None:
                    raise FileNotFoundError(f"Material not found: {material_id}")
                event_nodes = _normalize_skeleton_nodes(mapping.get("event_nodes", []))
                if not event_nodes:
                    raise ValueError("Materials must be converted to event nodes before planning.")
                usage_mode = str(mapping.get("usage_mode") or "reference")
                if usage_mode not in {"required", "reference"}:
                    raise ValueError("Material usage_mode must be required or reference.")
                impact = _json_object(mapping.get("impact"))
                if not any(key in impact for key in ("characters", "events", "states")):
                    raise ValueError("Material mapping must describe affected characters, events, or states.")
                connection.execute(
                    """
                    INSERT INTO rewrite_plan_materials (
                        plan_id, material_id, insertion_after_node,
                        insertion_before_node, insertion_scene_offset,
                        usage_mode, event_nodes_json, impact_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan_id,
                        material_id,
                        mapping.get("insertion_after_node"),
                        mapping.get("insertion_before_node"),
                        mapping.get("insertion_scene_offset"),
                        usage_mode,
                        json.dumps(event_nodes, ensure_ascii=False),
                        json.dumps(impact, ensure_ascii=False),
                    ),
                )
        return plan_id

    def confirm_plan(self, plan_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM rewrite_plans WHERE id = ?", (plan_id,)).fetchone()
            if row is None:
                raise FileNotFoundError(f"Rewrite plan not found: {plan_id}")
            connection.execute(
                """
                UPDATE rewrite_plans
                SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (plan_id,),
            )
        return self.get_plan(plan_id)

    def get_plan(self, plan_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM rewrite_plans WHERE id = ?", (plan_id,)).fetchone()
            mappings = connection.execute(
                "SELECT * FROM rewrite_plan_materials WHERE plan_id = ? ORDER BY material_id",
                (plan_id,),
            ).fetchall()
        if row is None:
            raise FileNotFoundError(f"Rewrite plan not found: {plan_id}")
        return {
            **dict(row),
            "plan": _json_object(row["plan_json"]),
            "materials": [
                {
                    **dict(mapping),
                    "event_nodes": _json_list_of_objects(mapping["event_nodes_json"]),
                    "impact": _json_object(mapping["impact_json"]),
                }
                for mapping in mappings
            ],
        }

    def save_stage_output(
        self,
        scene_id: int,
        stage: str,
        output: dict[str, Any],
        *,
        plan_id: int | None = None,
        prompt_compilation_id: int | None = None,
        status: str = "completed",
    ) -> int:
        if stage == "analysis":
            _require_keys(output, SCENE_ANALYSIS_KEYS, stage)
        elif stage == "consistency_check":
            _require_keys(output, CONSISTENCY_KEYS, stage)
        elif stage == "planning":
            _normalize_plan(output)
        elif stage not in {"rewrite", "targeted_repair"}:
            raise ValueError(f"Unsupported generation stage: {stage}")
        if stage in {"rewrite", "targeted_repair"} and not str(output.get("text") or "").strip():
            raise ValueError(f"{stage} output requires non-empty text.")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO scene_generation_stages (
                    scene_id, plan_id, stage, status, output_json, prompt_compilation_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id,
                    plan_id,
                    stage,
                    status,
                    json.dumps(output, ensure_ascii=False),
                    prompt_compilation_id,
                ),
            )
        return int(cursor.lastrowid)

    def save_rewrite_version(
        self,
        scene_id: int,
        rewritten_text: str,
        *,
        plan_id: int,
        skeleton_version_id: int,
        prompt_compilation_id: int | None = None,
        facts_after: dict[str, Any] | None = None,
        revision_kind: str = "generation",
        parent_version_id: int | None = None,
    ) -> int:
        text = rewritten_text.strip()
        if not text:
            raise ValueError("Rewritten scene text cannot be empty.")
        plan = self.get_plan(plan_id)
        allowed_statuses = {"confirmed"} if revision_kind == "generation" else {"confirmed", "executed"}
        if plan["status"] not in allowed_statuses:
            raise ValueError("The rewrite plan must be confirmed before generation is saved.")
        if int(plan["skeleton_version_id"]) != skeleton_version_id:
            raise ValueError("Rewrite plan and generation must reference the same skeleton version.")
        with session(self.database_path) as connection:
            version = int(
                connection.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM scene_rewrite_versions WHERE scene_id = ?",
                    (scene_id,),
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO scene_rewrite_versions (
                    scene_id, plan_id, skeleton_version_id, version,
                    rewritten_text, revision_kind, parent_version_id,
                    prompt_compilation_id, facts_after_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id,
                    plan_id,
                    skeleton_version_id,
                    version,
                    text,
                    revision_kind,
                    parent_version_id,
                    prompt_compilation_id,
                    json.dumps(facts_after or {}, ensure_ascii=False),
                ),
            )
            connection.execute(
                """
                UPDATE rewrite_plans
                SET status = 'executed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (plan_id,),
            )
        return int(cursor.lastrowid)

    def save_consistency_check(
        self,
        *,
        project_id: int,
        result: dict[str, Any],
        check_scope: str,
        chapter_id: int | None = None,
        scene_id: int | None = None,
    ) -> int:
        _require_keys(result, CONSISTENCY_KEYS, "consistency_check")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO consistency_checks (
                    project_id, chapter_id, scene_id, check_scope,
                    result_json, revision_required
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    chapter_id,
                    scene_id,
                    check_scope,
                    json.dumps(result, ensure_ascii=False),
                    1 if result["revision_required"] else 0,
                ),
            )
        return int(cursor.lastrowid)

    def targeted_repair(
        self,
        *,
        scene_id: int,
        source_version_id: int,
        paragraph_start: int,
        paragraph_end: int,
        issues: Iterable[dict[str, Any] | str],
        replacement_text: str,
        affected_facts: dict[str, Any],
    ) -> int:
        with session(self.database_path) as connection:
            source = connection.execute(
                """
                SELECT r.*, p.skeleton_version_id, p.id AS plan_id
                FROM scene_rewrite_versions r
                LEFT JOIN rewrite_plans p ON p.id = r.plan_id
                WHERE r.id = ? AND r.scene_id = ?
                """,
                (source_version_id, scene_id),
            ).fetchone()
        if source is None:
            raise FileNotFoundError(f"Scene rewrite version not found: {source_version_id}")
        paragraphs = _paragraphs(str(source["rewritten_text"]))
        if paragraph_start < 0 or paragraph_end < paragraph_start or paragraph_end >= len(paragraphs):
            raise ValueError("Targeted repair paragraph range is outside the rewritten scene.")
        before_text = "\n\n".join(paragraphs[paragraph_start : paragraph_end + 1])
        replacement = replacement_text.strip()
        if not replacement:
            raise ValueError("Targeted repair replacement cannot be empty.")
        updated_paragraphs = [
            *paragraphs[:paragraph_start],
            replacement,
            *paragraphs[paragraph_end + 1 :],
        ]
        updated_text = "\n\n".join(updated_paragraphs)
        result_version_id = self.save_rewrite_version(
            scene_id,
            updated_text,
            plan_id=int(source["plan_id"]),
            skeleton_version_id=int(source["skeleton_version_id"]),
            facts_after=affected_facts,
            revision_kind="targeted_repair",
            parent_version_id=source_version_id,
        )
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO targeted_repairs (
                    scene_id, source_version_id, result_version_id,
                    paragraph_start, paragraph_end, issues_json,
                    before_text, after_text, affected_facts_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id,
                    source_version_id,
                    result_version_id,
                    paragraph_start,
                    paragraph_end,
                    json.dumps(list(issues), ensure_ascii=False),
                    before_text,
                    replacement,
                    json.dumps(affected_facts, ensure_ascii=False),
                ),
            )
        return int(cursor.lastrowid)

    def build_chapter_check(self, chapter_id: int) -> dict[str, Any]:
        scenes = self.scene_service.list_scenes(chapter_id)
        issues: dict[str, list[dict[str, Any]]] = {
            "state_transitions": [],
            "locations": [],
            "injuries_and_objects": [],
            "naming_and_viewpoint": [],
            "repetition": [],
            "scene_jumps": [],
            "pacing": [],
        }
        previous = None
        for scene in scenes:
            ledger = self.scene_service.get_fact_ledger(scene.id)
            if previous is not None:
                if previous["required_end_state"] != ledger["required_start_state"]:
                    issues["state_transitions"].append(
                        {
                            "previous_scene_id": previous["scene_id"],
                            "scene_id": scene.id,
                            "previous_end": previous["required_end_state"],
                            "current_start": ledger["required_start_state"],
                        }
                    )
                if previous["location"] and ledger["location"] and previous["location"] != ledger["location"]:
                    issues["locations"].append(
                        {
                            "previous_scene_id": previous["scene_id"],
                            "scene_id": scene.id,
                            "from": previous["location"],
                            "to": ledger["location"],
                        }
                    )
            previous = ledger
        return {"chapter_id": chapter_id, **issues}

    def build_book_check(self, project_id: int) -> dict[str, Any]:
        """Read structured ledgers first; callers can load source scenes only for returned risks."""
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT s.id AS scene_id, s.chapter_id, s.scene_index, l.facts_json
                FROM scenes s
                JOIN scene_fact_ledgers l ON l.scene_id = s.id
                WHERE s.project_id = ?
                  AND s.deleted_at IS NULL
                  AND l.ledger_version = (
                      SELECT MAX(latest.ledger_version)
                      FROM scene_fact_ledgers latest
                      WHERE latest.scene_id = s.id
                  )
                ORDER BY s.chapter_id, s.scene_index
                """,
                (project_id,),
            ).fetchall()
        ledgers = [
            {"scene_id": int(row["scene_id"]), "chapter_id": int(row["chapter_id"]), **_json_object(row["facts_json"])}
            for row in rows
        ]
        open_threads: dict[str, int] = {}
        resolved: set[str] = set()
        knowledge_by_character: dict[str, set[str]] = {}
        object_holders: dict[str, set[str]] = {}
        for ledger in ledgers:
            for thread in ledger.get("open_threads", []):
                open_threads.setdefault(str(thread), int(ledger["scene_id"]))
            resolved.update(str(thread) for thread in ledger.get("resolved_threads", []))
            for character, knowledge in _json_object(ledger.get("knowledge_states")).items():
                knowledge_by_character.setdefault(str(character), set()).update(
                    str(item) for item in (knowledge if isinstance(knowledge, list) else [knowledge])
                )
            for name, state in _json_object(ledger.get("objects")).items():
                holder = _json_object(state).get("holder") if isinstance(state, dict) else state
                if holder:
                    object_holders.setdefault(str(name), set()).add(str(holder))
        return {
            "project_id": project_id,
            "character_growth": [],
            "unresolved_foreshadowing": [
                {"thread": thread, "opened_scene_id": scene_id}
                for thread, scene_id in open_threads.items()
                if thread not in resolved
            ],
            "timeline_risks": [],
            "ability_system_risks": [],
            "relationship_trajectory_risks": [],
            "knowledge_states": {key: sorted(value) for key, value in knowledge_by_character.items()},
            "object_state_risks": [
                {"object": name, "holders": sorted(holders)}
                for name, holders in object_holders.items()
                if len(holders) > 1
            ],
            "style_template_risks": [],
            "source_scene_ids_to_review": [],
        }

    def _require_confirmed_skeleton_version(self, version_id: int) -> None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT v.id, v.confirmed_at, s.status
                FROM story_skeleton_versions v
                JOIN story_skeletons s ON s.id = v.skeleton_id
                WHERE v.id = ?
                """,
                (version_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Skeleton version not found: {version_id}")
        if row["confirmed_at"] is None or row["status"] != "confirmed":
            raise ValueError("Skeleton version must be confirmed before planning.")


def _normalize_skeleton_nodes(nodes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(nodes):
        if not isinstance(raw, dict):
            raise ValueError("Skeleton nodes must be objects.")
        node_id = str(raw.get("id") or f"node_{index + 1}").strip()
        event = str(raw.get("event") or raw.get("summary") or "").strip()
        if not node_id or node_id in seen or not event:
            raise ValueError("Skeleton nodes require unique IDs and non-empty event text.")
        seen.add(node_id)
        normalized.append(
            {
                "id": node_id,
                "event": event,
                "required": bool(raw.get("required", True)),
                "characters": [str(item) for item in raw.get("characters", [])],
                "causes": [str(item) for item in raw.get("causes", [])],
                "results": [str(item) for item in raw.get("results", [])],
                "editable": bool(raw.get("editable", True)),
                "sort_order": index,
            }
        )
    return normalized


def _normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    normalized = _json_object(plan)
    required = {
        "sequence",
        "preserve",
        "modify",
        "add",
        "material_insertions",
        "character_changes",
        "expected_end_state",
    }
    missing = sorted(key for key in required if key not in normalized)
    if missing:
        raise ValueError(f"Rewrite plan is missing fields: {', '.join(missing)}")
    if not isinstance(normalized["sequence"], list) or not normalized["sequence"]:
        raise ValueError("Rewrite plan sequence must be a non-empty list.")
    return normalized


def _require_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(key for key in required if key not in value)
    if missing:
        raise ValueError(f"{label} output is missing fields: {', '.join(missing)}")


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list_of_objects(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value or "[]"))
        except (json.JSONDecodeError, TypeError):
            return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
