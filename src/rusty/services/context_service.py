from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from rusty.db import session
from rusty.services.anchor_service import AnchorService
from rusty.services.material_service import MaterialService
from rusty.db import default_database_path
from rusty.services.prompt_service import PromptService
from rusty.services.scene_service import SceneRecord, SceneService
from rusty.services.style_service import StyleTemplateService
from rusty.services.branch_service import BranchService
from rusty.services.rewrite_version_map_service import RewriteVersionMapService
from rusty.services.chapter_version_service import ChapterVersionService


DEFAULT_PRIORITIES = {
    "system_rules": 1,
    "user_instruction": 2,
    "current_original_scene": 3,
    "must_preserve_events": 4,
    "required_end_state": 5,
    "story_state": 6,
    "previous_rewritten_tail": 7,
    "next_original_preview": 8,
    "foreshadowing": 9,
    "author_style_context": 12,
    "scene_style_rules": 12,
    "style_examples": 13,
    "chapter_summary": 14,
    "global_summary": 15,
}

STAGE_BLOCK_PRIORITIES = {
    "stage_task": 3,
    "scene_analysis": 4,
    "confirmed_skeleton": 4,
    "rewrite_plan": 4,
    "material_mappings": 5,
    "author_style_context": 5,
    "candidate_rewrite_text": 3,
    "consistency_result": 4,
    "repair_source_text": 3,
    "repair_targets": 4,
}

STAGE_REQUIRED_BLOCKS = {
    "skeleton": {"scene_analysis"},
    "planning": {"confirmed_skeleton", "material_mappings"},
    "rewrite": {"confirmed_skeleton", "rewrite_plan"},
    "consistency_check": {"rewrite_plan", "candidate_rewrite_text"},
    "targeted_repair": {"consistency_result", "repair_source_text", "repair_targets"},
}


class PromptBudgetError(ValueError):
    pass


class SceneTooLongError(PromptBudgetError):
    pass


@dataclass(frozen=True)
class PromptBlock:
    key: str
    content: str
    priority: int
    required: bool = False
    token_count: int = 0
    source_type: str = ""
    source_id: str = ""
    included: bool = True
    decision: str = "included"

    def counted(self) -> "PromptBlock":
        return replace(self, token_count=estimate_tokens(self.content))


@dataclass(frozen=True)
class CompiledContext:
    blocks: tuple[PromptBlock, ...]
    max_input_tokens: int
    reserved_output_tokens: int
    used_input_tokens: int

    def included_blocks(self) -> list[PromptBlock]:
        return [block for block in self.blocks if block.included]

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_input_tokens": self.max_input_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "used_input_tokens": self.used_input_tokens,
            "blocks": [block.__dict__ for block in self.blocks],
        }


class PromptBudgeter:
    """Budget complete semantic blocks; required content is never truncated."""

    def compile(
        self,
        blocks: Iterable[PromptBlock],
        *,
        model_context_tokens: int,
        reserved_output_tokens: int,
    ) -> CompiledContext:
        if reserved_output_tokens <= 0:
            raise PromptBudgetError("reserved_output_tokens must be greater than zero.")
        max_input = model_context_tokens - reserved_output_tokens
        if max_input <= 0:
            raise PromptBudgetError("The reserved output budget consumes the model context.")
        counted = [block.counted() for block in blocks if block.content.strip()]
        required_tokens = sum(block.token_count for block in counted if block.required)
        current_scene = next((block for block in counted if block.key == "current_original_scene"), None)
        if current_scene and current_scene.token_count > max_input:
            raise SceneTooLongError(
                "The current scene cannot fit without truncation; split it into confirmed subscenes first."
            )
        if required_tokens > max_input:
            raise PromptBudgetError(
                f"Required prompt blocks need {required_tokens} tokens but only {max_input} are available."
            )

        selected_ids = {index for index, block in enumerate(counted) if block.required}
        used = required_tokens
        optional = sorted(
            ((index, block) for index, block in enumerate(counted) if not block.required),
            key=lambda pair: (pair[1].priority, pair[0]),
        )
        for index, block in optional:
            if used + block.token_count <= max_input:
                selected_ids.add(index)
                used += block.token_count

        compiled: list[PromptBlock] = []
        for index, block in enumerate(counted):
            if index in selected_ids:
                compiled.append(block)
            else:
                compiled.append(replace(block, included=False, decision="dropped_over_budget"))
        return CompiledContext(tuple(compiled), max_input, reserved_output_tokens, used)


class ContextService:
    """Build sliding windows, retrieval provenance, dynamic style context, and prompt snapshots."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.scene_service = SceneService(self.database_path)
        self.anchor_service = AnchorService(self.database_path)
        self.material_service = MaterialService(self.database_path)
        self.prompt_service = PromptService(self.database_path)
        self.style_service = StyleTemplateService(self.database_path)
        self.branch_service = BranchService(self.database_path)
        self.rewrite_maps = RewriteVersionMapService(self.database_path)
        self.chapter_versions = ChapterVersionService(self.database_path)
        self.budgeter = PromptBudgeter()

    def build_sliding_window(
        self,
        scene_id: int,
        *,
        previous_tail_chars: int = 1200,
        next_preview_chars: int = 800,
    ) -> dict[str, Any]:
        scene = self._require_scene(scene_id)
        chapter = self.scene_service.project_service.get_chapter(scene.chapter_id)
        if chapter is None:
            raise FileNotFoundError(f"Chapter not found: {scene.chapter_id}")
        siblings = self.scene_service.list_scenes(scene.chapter_id)
        index = next(i for i, item in enumerate(siblings) if item.id == scene.id)
        previous = siblings[index - 1] if index > 0 else None
        following = siblings[index + 1] if index + 1 < len(siblings) else None
        previous_tail = ""
        if previous is not None:
            with session(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT rewritten_text
                    FROM scene_rewrite_versions
                    WHERE scene_id = ?
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (previous.id,),
                ).fetchone()
            source = str(row["rewritten_text"]) if row is not None else previous.original_text
            previous_tail = source[-previous_tail_chars:]
        return {
            "previous_rewritten_tail": previous_tail,
            "current_original_scene": scene.original_text,
            "next_original_preview": following.original_text[:next_preview_chars] if following else "",
        }

    def retrieve(
        self,
        scene_id: int,
        *,
        keywords: Iterable[str] = (),
        character_names: Iterable[str] = (),
        location: str = "",
        time_hint: str = "",
        manual_material_ids: Iterable[int] = (),
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        scene = self._require_scene(scene_id)
        chapter = self.scene_service.project_service.get_chapter(scene.chapter_id)
        if chapter is None:
            raise FileNotFoundError(f"Chapter not found: {scene.chapter_id}")
        manual_materials = {
            item.id: item
            for item in (
                self.material_service.get_material(int(material_id))
                for material_id in manual_material_ids
            )
            if item is not None
        }
        project_materials = self.material_service.list_materials_for_project(
            scene.project_id,
            include_unanalyzed_manual=False,
        )
        project_filters = {
            item.material_type: item
            for item in self.material_service.get_project_material_filters(scene.project_id)
        }
        project_material_ids = {item.id for item in project_materials}
        all_materials = self.material_service.list_materials(analysis_status="analyzed")
        search_terms = _unique_terms(
            [
                *keywords,
                *character_names,
                location,
                time_hint,
                scene.scene_type,
                *_proper_nouns(scene.original_text),
            ]
        )
        query = {
            "scene_id": scene_id,
            "chapter_id": scene.chapter_id,
            "scene_index": scene.scene_index,
            "keywords": search_terms,
            "characters": list(character_names),
            "location": location,
            "time_hint": time_hint,
            "manual_material_ids": list(manual_material_ids),
        }
        results: list[dict[str, Any]] = []
        for material_id, material in manual_materials.items():
            manual_reason = (
                "用户手动指定素材；该素材尚未分析，仅按明确选择纳入。"
                if material.analysis_status == "unanalyzed"
                else "用户手动指定素材，优先于自动检索。"
            )
            results.append(
                _result(
                    "manual",
                    "material",
                    material_id,
                    _material_location(material),
                    _material_context_content(material),
                    manual_reason,
                    1.0,
                )
            )
        for material in project_materials:
            if material.id in manual_materials:
                continue
            results.append(
                _result(
                    "project_filter",
                    "material",
                    material.id,
                    _material_location(material),
                    _material_context_content(material),
                    "由当前工程配置纳入。",
                    0.92,
                )
            )

        for material in all_materials:
            if material.id in manual_materials:
                continue
            if material.id in project_material_ids:
                continue
            content = " ".join(
                [
                    material.name,
                    material.description,
                    material.raw_text,
                    material.content_json,
                ]
            )
            structural = _timeline_matches(
                material.timeline_start_chapter,
                material.timeline_end_chapter,
                chapter.index,
            )
            matched_terms = [
                term
                for term in search_terms
                if project_filters[material.material_type].include_scene_keywords
                and term
                and term.casefold() in content.casefold()
            ]
            if structural:
                results.append(
                    _result(
                        "structure",
                        "material",
                        material.id,
                        _material_location(material),
                        _material_context_content(material),
                        "工程范围和时间线位置与当前场景匹配。",
                        0.88,
                    )
                )
            elif matched_terms:
                results.append(
                    _result(
                        "keyword",
                        "material",
                        material.id,
                        _material_location(material),
                        _material_context_content(material),
                        f"命中关键词：{', '.join(matched_terms[:5])}。",
                        min(0.86, 0.55 + len(matched_terms) * 0.08),
                    )
                )
            else:
                similarity = _jaccard(scene.original_text, content)
                if similarity >= 0.08:
                    results.append(
                        _result(
                            "vector",
                            "material",
                            material.id,
                            _material_location(material),
                            _material_context_content(material),
                            "词项向量相似度补充结果。",
                            min(0.7, similarity + 0.35),
                        )
                    )

        material_types = {
            item.id: item.material_type
            for item in [*manual_materials.values(), *project_materials, *all_materials]
        }
        for result in results:
            if result["source_type"] == "material":
                result["material_type"] = material_types.get(int(result["source_id"]))

        ledger = self.scene_service.get_fact_ledger(scene_id)
        relationship_text = json.dumps(
            {
                "objects": ledger["objects"],
                "knowledge_states": ledger["knowledge_states"],
                "relationship_changes": ledger["relationship_changes"],
                "open_threads": ledger["open_threads"],
                "foreshadowing": ledger["foreshadowing"],
            },
            ensure_ascii=False,
        )
        if relationship_text != '{"objects": {}, "knowledge_states": {}, "relationship_changes": [], "open_threads": [], "foreshadowing": []}':
            results.append(
                _result(
                    "relationship",
                    "scene_fact_ledger",
                    scene_id,
                    f"scene:{scene_id}:facts",
                    relationship_text,
                    "人物—物品—知识—关系—伏笔链与当前场景直接关联。",
                    0.94,
                )
            )

        order = {
            "manual": 0,
            "project_tag_filter": 1,
            "structure": 2,
            "keyword": 3,
            "relationship": 4,
            "vector": 5,
        }
        results.sort(key=lambda item: (order[item["retrieval_type"]], -item["confidence"], item["source_id"]))
        results = results[:limit]
        with session(self.database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO retrieval_runs (project_id, scene_id, query_json) VALUES (?, ?, ?)",
                (scene.project_id, scene_id, json.dumps(query, ensure_ascii=False)),
            )
            run_id = int(cursor.lastrowid)
            for rank, result in enumerate(results, start=1):
                result["retrieval_run_id"] = run_id
                result["rank_order"] = rank
                connection.execute(
                    """
                    INSERT INTO retrieval_results (
                        retrieval_run_id, retrieval_type, source_type, source_id,
                        source_location, content, relevance_reason, confidence,
                        included_in_prompt, token_count, rank_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        run_id,
                        result["retrieval_type"],
                        result["source_type"],
                        result["source_id"],
                        result["source_location"],
                        result["content"],
                        result["relevance_reason"],
                        result["confidence"],
                        result["token_count"],
                        rank,
                    ),
                )
        return results

    def build_style_context(
        self,
        scene_id: int,
        *,
        global_rules: Iterable[str] = (),
        rules_by_scene_type: dict[str, list[str]] | None = None,
        examples: Iterable[str] = (),
        recent_scene_count: int = 4,
    ) -> dict[str, Any]:
        scene = self._require_scene(scene_id)
        resolved_global_rules = list(global_rules)
        resolved_rules = {key: list(value) for key, value in (rules_by_scene_type or {}).items()}
        resolved_examples = list(examples)
        if not resolved_global_rules and not resolved_rules and not resolved_examples:
            settings = self.scene_service.project_service.get_project_settings(scene.project_id)
            style_template = self.style_service.get_project_style_template(scene.project_id)
            prompt_template = (
                self.prompt_service.get_template(settings.prompt_template_id)
                if settings is not None and settings.prompt_template_id is not None
                else None
            )
            if style_template is not None:
                resolved_global_rules.extend(
                    text
                    for text in (
                        style_template.global_prompt,
                        style_template.generated_prompt or style_template.rewrite_prompt,
                    )
                    if text.strip()
                )
                resolved_examples.extend(_style_examples(style_template.style_profile_json))
            if prompt_template is not None:
                resolved_global_rules.extend(
                    text for text in (prompt_template.global_rules, prompt_template.rewrite_rules) if text.strip()
                )
                for rule in prompt_template.scene_rules:
                    if rule.rewrite_prompt.strip():
                        resolved_rules.setdefault(rule.scene_key, []).append(rule.rewrite_prompt)
        scene_rules = [
            rule
            for scene_key in _scene_rule_keys(scene.scene_type)
            for rule in resolved_rules.get(scene_key, [])
        ]
        limited_examples = sorted(
            (example for example in resolved_examples if example.strip()),
            key=lambda text: _jaccard(scene.original_text, text),
            reverse=True,
        )[:3]
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT recent_techniques_json
                FROM scene_style_contexts c
                JOIN scenes s ON s.id = c.scene_id
                WHERE s.chapter_id = ? AND s.scene_index < ?
                ORDER BY s.scene_index DESC
                LIMIT ?
                """,
                (scene.chapter_id, scene.scene_index, recent_scene_count),
            ).fetchall()
        recent_values = [
            technique
            for row in rows
            for technique in _json_list(row["recent_techniques_json"])
        ]
        recent = _unique_terms(recent_values)
        forbidden = _repeated_techniques(recent_values)
        context = {
            "scene_type": scene.scene_type,
            "global_rules": _unique_terms(resolved_global_rules),
            "scene_rules": list(scene_rules),
            "examples": limited_examples,
            "recent_techniques": recent,
            "forbidden_repetitions": forbidden,
        }
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO scene_style_contexts (
                    scene_id, scene_type, global_rules_json, scene_rules_json,
                    examples_json, recent_techniques_json, forbidden_repetitions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id,
                    scene.scene_type,
                    json.dumps(context["global_rules"], ensure_ascii=False),
                    json.dumps(context["scene_rules"], ensure_ascii=False),
                    json.dumps(context["examples"], ensure_ascii=False),
                    json.dumps(context["recent_techniques"], ensure_ascii=False),
                    json.dumps(context["forbidden_repetitions"], ensure_ascii=False),
                ),
            )
        return context

    def compile_plot_generation_context(
        self,
        *,
        project_id: int,
        start_anchor: dict[str, Any],
        return_anchor: dict[str, Any] | None,
        branch_id: int | None,
        user_direction: str,
        selected_material_ids: Iterable[int] = (),
        style_profile_id: int | None = None,
        rewrite_source_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start = self._resolve_generation_anchor(
            project_id,
            start_anchor,
            branch_id=branch_id,
            rewrite_source_snapshot=rewrite_source_snapshot,
        )
        returned = (
            self._resolve_generation_anchor(
                project_id,
                return_anchor,
                branch_id=branch_id,
                rewrite_source_snapshot=rewrite_source_snapshot,
            )
            if return_anchor is not None
            else None
        )
        materials = []
        for material_id in selected_material_ids:
            material = self.material_service.get_material(int(material_id))
            if material is not None:
                materials.append(material.__dict__)
        author_styles = [item for item in materials if item.get("material_type") == "author_style"]
        style = (
            self.style_service.get_template(style_profile_id).__dict__
            if style_profile_id is not None
            and self.style_service.get_template(style_profile_id) is not None
            else {}
        )
        facts = start["fact_ledger"]
        return {
            "start_anchor_context": start,
            "previous_text_tail": start["previous_text_tail"],
            "start_state": start["state"],
            "character_states": start["character_states"],
            "fact_ledger": facts,
            "open_threads": facts.get("open_threads", []),
            "foreshadowing": facts.get("foreshadowing", []),
            "global_skeleton": start.get("global_skeleton", {}),
            "user_direction": user_direction,
            "author_style_context": author_styles,
            "style_profile": style,
            "previous_generated_scene": start.get("previous_generated_scene", ""),
            "return_state_constraints": (
                (
                    returned["fact_ledger"].get(
                        "required_start_state", returned["state"]
                    )
                )
                if returned is not None
                else {}
            ),
            "return_anchor_context": returned,
        }

    def resolve_generation_anchor_source(
        self,
        project_id: int,
        anchor: dict[str, Any],
        *,
        branch_id: int | None = None,
        rewrite_source_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve the authoritative current text unit bound to a generation anchor."""
        resolved = self._resolve_generation_anchor(
            project_id,
            anchor,
            branch_id=branch_id,
            rewrite_source_snapshot=rewrite_source_snapshot,
        )
        source_text = str(resolved.get("source_text", resolved["text"]))
        return {
            "text": source_text,
            "source_hash": self.branch_service.source_hash(source_text),
            "source_version_id": resolved.get("source_version_id"),
            "source_range": dict(
                resolved.get("source_range")
                or {"start": 0, "end": len(source_text)}
            ),
            "offset": int(resolved.get("local_offset", resolved.get("offset", 0))),
        }

    def preview_story_anchor(
        self,
        *,
        project_id: int,
        anchor: dict[str, Any],
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if anchor.get("anchor_type") in {"branch_chapter", "branch_scene"}:
            raise ValueError("Branch anchor preview requires branch workspace context.")
        chapter_id = self.chapter_versions.resolve_anchor_chapter_id(
            project_id, anchor
        )
        snapshot = self.chapter_versions.resolve_chapter_source(
            chapter_id, source
        ).to_dict()
        resolved = self._resolve_generation_anchor(
            project_id,
            anchor,
            branch_id=None,
            rewrite_source_snapshot=(
                snapshot if snapshot["source_kind"] == "rewrite_version" else None
            ),
        )
        start = int(
            (resolved.get("resolved_span") or {}).get(
                "start", resolved.get("offset", 0)
            )
        )
        end = int(
            (resolved.get("resolved_span") or {}).get(
                "end", resolved.get("offset", 0)
            )
        )
        excerpt_start = max(0, start - 80)
        excerpt_end = min(len(snapshot["text"]), max(end, start) + 80)
        return {
            "resolved_version_id": snapshot.get("source_version_id"),
            "resolved_start": start,
            "resolved_end": end,
            "text_excerpt": str(snapshot["text"])[excerpt_start:excerpt_end],
            "state_before": dict(resolved.get("state_before") or {}),
            "state_after": dict(resolved.get("state_after") or {}),
            "mapping_method": resolved.get("mapping_method", "identity"),
            "state_method": resolved.get("state_method", "scene_ledger"),
            "confidence": float(resolved.get("confidence", 1.0)),
            "semantic_map_hash": resolved.get("semantic_map_hash"),
        }

    def _resolve_generation_anchor(
        self,
        project_id: int,
        anchor: dict[str, Any],
        *,
        branch_id: int | None,
        rewrite_source_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        anchor_type = str(anchor["anchor_type"])
        if anchor_type in {"branch_chapter", "branch_scene"}:
            if branch_id is None:
                raise ValueError("Branch content anchors require branch_id.")
            chapters = self.branch_service.list_chapters(branch_id)
            selected_chapter = next((chapter for chapter in chapters if (
                int(chapter["id"]) == int(anchor.get("branch_chapter_id") or -1)
                or any(int(scene["id"]) == int(anchor.get("branch_scene_id") or -1) for scene in chapter["scenes"])
            )), None)
            if selected_chapter is None:
                raise ValueError("Branch anchor could not be resolved.")
            selected_scene = None
            if anchor_type == "branch_scene":
                selected_scene = self.branch_service.get_scene(
                    int(anchor["branch_scene_id"]),
                    version_id=(int(anchor["source_version_id"]) if anchor.get("source_version_id") else None),
                )
                text = selected_scene["generated_text"]
                facts = selected_scene["facts_after"]
                source_version_id = int(selected_scene["version_id"])
            else:
                selected_chapter = self.branch_service.get_chapter(
                    int(anchor["branch_chapter_id"]),
                    version_id=(int(anchor["source_version_id"]) if anchor.get("source_version_id") else None),
                )
                text = "\n\n".join(
                    str(scene["generated_text"])
                    for scene in selected_chapter["scenes"]
                )
                facts = selected_chapter["facts_after"]
                source_version_id = int(selected_chapter["version_id"])
            history: list[str] = []
            for chapter in chapters:
                for scene in chapter["scenes"]:
                    history.append(str(scene["generated_text"]))
                    if selected_scene is not None and int(scene["id"]) == int(selected_scene["id"]):
                        break
                if selected_scene is not None and any(int(scene["id"]) == int(selected_scene["id"]) for scene in chapter["scenes"]):
                    break
                if selected_scene is None and int(chapter["id"]) == int(selected_chapter["id"]):
                    break
            history_text = "\n\n".join(history)
            local_offset = 0 if anchor.get("side") == "before" else len(text)
            return {
                "source_kind": "branch",
                "text": text,
                "source_text": text,
                "offset": local_offset,
                "local_offset": local_offset,
                "source_version_id": source_version_id,
                "source_hash": self.branch_service.source_hash(text),
                "source_range": {"start": 0, "end": len(text)},
                "previous_text_tail": history_text[: len(history_text) - len(text) + local_offset][-1200:],
                "state": facts,
                "fact_ledger": facts,
                "character_states": facts.get("character_states", []),
                "previous_generated_scene": text,
                "generated_history": history,
            }

        chapters = self.scene_service.project_service.list_chapters(project_id)
        if not chapters:
            raise ValueError("Project has no source chapters.")
        chapter = chapters[-1]
        scene = None
        if anchor.get("chapter_id") is not None:
            chapter = next(
                (item for item in chapters if item.id == int(anchor["chapter_id"])),
                None,
            )
            if chapter is None:
                raise ValueError("Anchor chapter does not belong to project.")
        if anchor.get("scene_id") is not None:
            scene = self.scene_service.get_scene(int(anchor["scene_id"]))
            if scene is None or scene.project_id != project_id:
                raise ValueError("Anchor scene does not belong to project.")
            chapter = self.scene_service.project_service.get_chapter(scene.chapter_id)
        effective_text = (
            str(rewrite_source_snapshot["text"])
            if rewrite_source_snapshot is not None
            and int(rewrite_source_snapshot["chapter_id"]) == int(chapter.id)
            else chapter.original_text
        )
        rewrite_version_id = (
            int(rewrite_source_snapshot["source_version_id"])
            if rewrite_source_snapshot is not None
            and rewrite_source_snapshot.get("source_version_id") is not None
            else None
        )
        if rewrite_version_id is not None and anchor.get("source_version_id") not in (
            None,
            rewrite_version_id,
        ):
            raise ValueError("Anchor source version does not match the frozen rewrite source.")
        offset = len(effective_text)
        mapped_span = None
        mapped_state_before: dict[str, Any] | None = None
        mapped_state_after: dict[str, Any] | None = None
        mapping_method = "identity"
        confidence = 1.0
        state_method = "scene_ledger"
        if scene is not None and rewrite_version_id is not None:
            mapped_span = self.rewrite_maps.resolve_scene_span(
                rewrite_version_id, scene.id
            )
            mapped_state_before = mapped_span.state_before
            mapped_state_after = mapped_span.state_after
            mapping_method = mapped_span.mapping_method
            confidence = mapped_span.confidence
            state_method = mapped_span.state_method
        if anchor_type in {"chapter_start", "scene_start"}:
            offset = (
                mapped_span.start_offset
                if mapped_span is not None
                else (scene.original_start_offset if scene is not None else 0)
            )
        elif anchor_type in {"scene_end"} and scene is not None:
            offset = (
                mapped_span.end_offset
                if mapped_span is not None
                else scene.original_end_offset
            )
        elif anchor_type == "text_offset":
            offset = int(anchor["text_offset"])
        elif anchor_type == "skeleton_node":
            with session(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT s.chapter_id, s.scene_id, v.skeleton_json
                    FROM story_skeleton_versions v
                    JOIN story_skeletons s ON s.id = v.skeleton_id
                    WHERE v.id = ? AND s.project_id = ?
                    """,
                    (anchor["skeleton_version_id"], project_id),
                ).fetchone()
            if row is None:
                raise ValueError("Skeleton anchor does not belong to project.")
            chapter = self.scene_service.project_service.get_chapter(int(row["chapter_id"]))
            if chapter is None:
                raise ValueError("Skeleton anchor chapter is missing.")
            if row["scene_id"] is not None:
                scene = self.scene_service.get_scene(int(row["scene_id"]))
            structured = json.loads(row["skeleton_json"] or "{}")
            node = next((item for item in structured.get("event_nodes", []) if str(item.get("id")) == str(anchor["node_id"])), None)
            if node is None:
                raise ValueError("Skeleton node could not be resolved.")
            if rewrite_version_id is not None:
                mapped_span = self.rewrite_maps.resolve_node_span(
                    rewrite_version_id,
                    int(anchor["skeleton_version_id"]),
                    str(anchor["node_id"]),
                )
                offset = int(
                    mapped_span.start_offset
                    if anchor.get("side") == "before"
                    else mapped_span.end_offset
                )
                mapped_state_before = mapped_span.state_before
                mapped_state_after = mapped_span.state_after
                mapping_method = mapped_span.mapping_method
                confidence = mapped_span.confidence
                state_method = mapped_span.state_method
            else:
                span = node.get("source_span") if isinstance(node.get("source_span"), dict) else {}
                start_value = span.get("start", span.get("start_offset"))
                end_value = span.get("end", span.get("end_offset"))
                if start_value is not None and end_value is not None:
                    offset = int(start_value if anchor.get("side") == "before" else end_value)
                elif scene is not None:
                    offset = scene.original_start_offset if anchor.get("side") == "before" else scene.original_end_offset
                else:
                    offset = 0 if anchor.get("side") == "before" else len(effective_text)
        if offset < 0 or offset > len(effective_text):
            raise ValueError("Anchor text_offset is outside the chapter text.")
        if rewrite_source_snapshot is None and scene is not None and anchor.get("text_offset") is not None and not (
            scene.original_start_offset <= offset <= scene.original_end_offset
        ):
            raise ValueError("Anchor text_offset is outside the selected scene.")
        chapter_text = effective_text
        source_scene = scene if rewrite_source_snapshot is None else None
        siblings = self.scene_service.list_scenes(chapter.id)
        if scene is None and siblings:
            eligible = [
                item for item in siblings if item.original_end_offset <= offset
            ]
            scene = eligible[-1] if eligible else siblings[0]
        if rewrite_version_id is not None:
            if anchor_type == "chapter_start":
                mapped_state_before = dict(
                    rewrite_source_snapshot.get("facts_before") or {}
                )
                mapped_state_after = mapped_state_before
                state_method = "chapter_boundary"
            elif anchor_type in {"chapter_end", "document_end"}:
                mapped_state_before = dict(
                    rewrite_source_snapshot.get("facts_after") or {}
                )
                mapped_state_after = mapped_state_before
                state_method = "chapter_boundary"
            elif anchor_type == "text_offset":
                if offset == 0:
                    local = dict(rewrite_source_snapshot.get("facts_before") or {})
                    state_method = "chapter_boundary"
                elif offset == len(effective_text):
                    local = dict(rewrite_source_snapshot.get("facts_after") or {})
                    state_method = "chapter_boundary"
                else:
                    local = self.rewrite_maps.resolve_state_at_offset(
                        rewrite_version_id, offset, str(anchor.get("side") or "after")
                    )
                    state_method = "nearest_segment"
                mapped_state_before = local
                mapped_state_after = local
                mapping_method = "semantic"
                confidence = 1.0
            facts = dict(
                mapped_state_before
                if anchor_type in {"scene_start"} or anchor.get("side") == "before"
                else mapped_state_after
                or {}
            )
        else:
            facts = self.scene_service.get_fact_ledger(scene.id) if scene is not None else {}
        states = self.scene_service.list_character_states(scene.id) if scene is not None else []
        at_start = anchor_type in {"chapter_start", "scene_start"} or anchor.get("side") == "before"
        if rewrite_version_id is not None:
            state = dict(mapped_state_before or {}) if at_start else dict(mapped_state_after or {})
        else:
            state = facts.get("required_start_state", facts) if at_start else facts.get("required_end_state", facts)
        source_text = source_scene.original_text if source_scene is not None else chapter_text
        local_offset = (
            max(0, min(len(source_text), offset - source_scene.original_start_offset))
            if source_scene is not None
            else offset
        )
        return {
            "source_kind": (
                str(rewrite_source_snapshot["source_kind"])
                if rewrite_source_snapshot is not None
                else "original"
            ),
            "chapter_id": chapter.id,
            "scene_id": scene.id if scene is not None else None,
            "text": chapter_text,
            "source_text": source_text,
            "offset": offset,
            "local_offset": local_offset,
            "source_hash": self.branch_service.source_hash(source_text),
            "source_version_id": (
                rewrite_source_snapshot.get("source_version_id")
                if rewrite_source_snapshot is not None
                else None
            ),
            "source_range": {"start": 0, "end": len(source_text)},
            "previous_text_tail": chapter_text[:offset][-1200:],
            "state": state,
            "state_before": dict(mapped_state_before or state),
            "state_after": dict(mapped_state_after or state),
            "fact_ledger": facts,
            "character_states": states,
            "mapping_method": mapping_method,
            "confidence": confidence,
            "state_method": state_method,
            "semantic_map_hash": (
                self.rewrite_maps.map_hash(rewrite_version_id)
                if rewrite_version_id is not None
                else None
            ),
            "resolved_span": (
                {
                    "start": mapped_span.start_offset,
                    "end": mapped_span.end_offset,
                }
                if mapped_span is not None
                else {"start": offset, "end": offset}
            ),
        }

    def compile_scene_context(
        self,
        scene_id: int,
        *,
        stage: str,
        system_rules: str,
        user_instruction: str,
        task: dict[str, Any],
        model_context_tokens: int,
        reserved_output_tokens: int,
        retrieval_results: Iterable[dict[str, Any]] = (),
        style_context: dict[str, Any] | None = None,
        model_id: int | None = None,
    ) -> dict[str, Any]:
        scene = self._require_scene(scene_id)
        user_instruction = user_instruction.strip() or "按已确认的计划执行，不添加额外用户偏好。"
        window = self.build_sliding_window(scene_id)
        facts = self.scene_service.get_fact_ledger(scene_id)
        character_states = self.scene_service.list_character_states(scene_id)
        retrieval = list(retrieval_results)
        material_context = [item for item in retrieval if item["source_type"] == "material"]
        author_style_context = [
            item for item in material_context if item.get("material_type") == "author_style"
        ]
        stage_values = {
            "stage_task": task,
            "scene_analysis": task.get("scene_analysis", task.get("analysis")),
            "confirmed_skeleton": task.get("confirmed_skeleton"),
            "rewrite_plan": task.get("rewrite_plan"),
            "material_mappings": task.get("material_mappings"),
            "author_style_context": task.get("author_style_context"),
            "candidate_rewrite_text": task.get("candidate_rewrite_text"),
            "consistency_result": task.get("consistency_result", task.get("consistency")),
            "repair_source_text": task.get("repair_source_text"),
            "repair_targets": task.get("repair_targets"),
        }
        required_stage_keys = STAGE_REQUIRED_BLOCKS.get(stage, set())
        stage_blocks = [
            PromptBlock(
                key,
                _stage_text(value) if not isinstance(value, str) else value,
                STAGE_BLOCK_PRIORITIES[key],
                key in required_stage_keys,
                source_type="scene_workflow",
                source_id=f"{scene_id}:{stage}:{key}",
            )
            for key, value in stage_values.items()
            if key in required_stage_keys or value not in (None, "", [], {})
        ]
        blocks = [
            PromptBlock("system_rules", system_rules, 1, True, source_type="system"),
            PromptBlock("user_instruction", user_instruction, 2, True, source_type="user"),
            PromptBlock(
                "current_original_scene",
                window["current_original_scene"],
                3,
                True,
                source_type="scene_original",
                source_id=str(scene_id),
            ),
            *stage_blocks,
            PromptBlock("must_preserve_events", _json_text(task.get("must_preserve_events", [])), 4, True),
            PromptBlock("required_end_state", _json_text(task.get("required_end_state", {})), 5, True),
            PromptBlock("story_state", _json_text({"facts": facts, "characters": character_states}), 6),
            PromptBlock("previous_rewritten_tail", window["previous_rewritten_tail"], 7),
            PromptBlock("next_original_preview", window["next_original_preview"], 8),
            PromptBlock("foreshadowing", _json_text(facts["foreshadowing"]), 9),
            PromptBlock("author_style_context", _json_text(author_style_context), 12),
            PromptBlock("global_style_rules", _json_text((style_context or {}).get("global_rules", [])), 12),
            PromptBlock("scene_style_rules", _json_text((style_context or {}).get("scene_rules", [])), 12),
            PromptBlock("style_examples", _json_text((style_context or {}).get("examples", [])), 13),
            PromptBlock(
                "recent_style_techniques",
                _json_text((style_context or {}).get("recent_techniques", [])),
                13,
            ),
            PromptBlock(
                "forbidden_style_repetitions",
                _json_text((style_context or {}).get("forbidden_repetitions", [])),
                12,
            ),
            PromptBlock("chapter_summary", str(task.get("chapter_summary") or ""), 14),
            PromptBlock("global_summary", str(task.get("global_summary") or ""), 15),
        ]
        compiled = self.budgeter.compile(
            blocks,
            model_context_tokens=model_context_tokens,
            reserved_output_tokens=reserved_output_tokens,
        )
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO prompt_compilations (
                    project_id, chapter_id, scene_id, stage, model_id,
                    max_input_tokens, reserved_output_tokens, used_input_tokens,
                    snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene.project_id,
                    scene.chapter_id,
                    scene.id,
                    stage,
                    model_id,
                    compiled.max_input_tokens,
                    compiled.reserved_output_tokens,
                    compiled.used_input_tokens,
                    json.dumps(compiled.snapshot(), ensure_ascii=False),
                ),
            )
            compilation_id = int(cursor.lastrowid)
            for order, block in enumerate(compiled.blocks):
                connection.execute(
                    """
                    INSERT INTO prompt_compilation_blocks (
                        compilation_id, block_key, content, priority, required,
                        token_count, source_type, source_id, included, decision, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        compilation_id,
                        block.key,
                        block.content,
                        block.priority,
                        1 if block.required else 0,
                        block.token_count,
                        block.source_type,
                        block.source_id,
                        1 if block.included else 0,
                        block.decision,
                        order,
                    ),
                )
            included_keys = {block.key for block in compiled.included_blocks()}
            for result in retrieval:
                context_key = "author_style_context" if result["source_type"] == "material" else "story_state"
                if context_key in included_keys:
                    connection.execute(
                        """
                        UPDATE retrieval_results
                        SET included_in_prompt = 1
                        WHERE retrieval_run_id = ? AND source_type = ? AND source_id = ?
                        """,
                        (
                            result["retrieval_run_id"],
                            result["source_type"],
                            str(result["source_id"]),
                        ),
                    )
        return {
            "id": compilation_id,
            "stage": stage,
            "context": {
                "system_rules": system_rules,
                "task": task,
                "global_context": {},
                "local_context": window,
                "story_state": facts,
                "character_states": character_states,
                "author_style_context": author_style_context,
                "style_context": style_context or {},
                "user_instruction": user_instruction,
            },
            **compiled.snapshot(),
        }

    def _require_scene(self, scene_id: int) -> SceneRecord:
        scene = self.scene_service.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        return scene


def estimate_tokens(text: str) -> int:
    """Deterministic conservative estimate for mixed CJK/Latin prompt budgeting."""
    if not text:
        return 0
    cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    non_cjk = re.sub(r"[\u3400-\u9fff\uf900-\ufaff]", " ", text)
    latin_units = len(re.findall(r"\w+|[^\w\s]", non_cjk, re.UNICODE))
    return cjk + math.ceil(latin_units * 1.25)


def _result(
    retrieval_type: str,
    source_type: str,
    source_id: int | str,
    source_location: str,
    content: str,
    reason: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "retrieval_type": retrieval_type,
        "source_type": source_type,
        "source_id": str(source_id),
        "source_location": source_location,
        "content": content,
        "relevance_reason": reason,
        "confidence": round(float(confidence), 4),
        "included_in_prompt": False,
        "token_count": estimate_tokens(content),
    }


def _material_location(material) -> str:
    timeline = (
        f":chapters:{material.timeline_start_chapter or '*'}-{material.timeline_end_chapter or '*'}"
    )
    return f"material:{material.id}@v{material.version}{timeline}"


def _material_context_content(material) -> str:
    """Keep writing style guidance separate from source text and story facts."""
    if material.material_type == "author_style":
        try:
            content = json.loads(material.content_json)
        except (TypeError, ValueError):
            content = {}
        return json.dumps(
            {
                "summary": str(content.get("summary") or material.description or ""),
                "dimensions": content.get("dimensions") if isinstance(content.get("dimensions"), list) else [],
            },
            ensure_ascii=False,
        )
    return material.description or material.content_json or material.raw_text


def _character_content(card) -> str:
    return json.dumps(
        {
            "name": card.name,
            "aliases": card.aliases,
            "identity": card.identity,
            "description": card.description,
            "personality": card.personality,
            "motivation": card.profile.get("core_motivation", ""),
            "appearance": card.profile.get("appearance", ""),
            "speech_style": card.speech_style,
            "abilities": card.profile.get("abilities", []),
            "limitations": card.action_constraints,
            "background": card.profile.get("background", ""),
            "immutable_rules": card.anti_ooc_rules,
            "setting": card.setting_text,
            "custom_fields": card.custom_fields,
        },
        ensure_ascii=False,
    )


def _proper_nouns(text: str) -> list[str]:
    latin = re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", text)
    quoted = re.findall(r"[《「『“]([^》」』”]{2,12})[》」』”]", text)
    return _unique_terms([*latin, *quoted])


def _timeline_matches(start: int | None, end: int | None, position: int) -> bool:
    if start is None and end is None:
        return False
    return (start is None or position >= start) and (end is None or position <= end)


def _jaccard(left: str, right: str) -> float:
    left_terms = set(_token_terms(left))
    right_terms = set(_token_terms(right))
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def _token_terms(text: str) -> list[str]:
    latin = re.findall(r"[A-Za-z0-9_]{2,}", text.casefold())
    cjk = re.findall(r"[\u3400-\u9fff]{2,4}", text)
    return [*latin, *cjk]


def _unique_terms(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _json_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, indent=2)


def _stage_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _scene_rule_keys(scene_type: str) -> tuple[str, ...]:
    aliases = {
        "action": ("action", "combat", "combat_scene", "action_scene"),
        "dialogue": ("dialogue", "dialogue_scene"),
        "flashback": ("flashback", "memory", "memory_scene"),
        "general": ("general", "default"),
    }
    return aliases.get(scene_type, (scene_type,))


def _style_examples(raw_profile: str) -> list[str]:
    try:
        parsed = json.loads(raw_profile or "{}")
    except (TypeError, json.JSONDecodeError):
        parsed = {}
    profile = parsed if isinstance(parsed, dict) else {}
    values: list[str] = []
    for key in ("examples", "style_examples", "excerpts", "samples"):
        raw = profile.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if str(item).strip())
        elif isinstance(raw, str) and raw.strip():
            values.append(raw)
    return values


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value or "[]"))
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _repeated_techniques(values: Iterable[str]) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        key = value.strip().casefold()
        if key:
            counts[key] = counts.get(key, 0) + 1
    return [key for key, count in counts.items() if count >= 2]
