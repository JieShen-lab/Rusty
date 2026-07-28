from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from rusty.db import initialize_database, session
from rusty.services.anchor_service import AnchorService
from rusty.services.material_service import MaterialService
from rusty.services.project_service import default_database_path
from rusty.services.scene_service import SceneRecord, SceneService


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
    "character_context": 10,
    "material_context": 11,
    "scene_style_rules": 12,
    "style_examples": 13,
    "chapter_summary": 14,
    "global_summary": 15,
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
        self.budgeter = PromptBudgeter()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def build_sliding_window(
        self,
        scene_id: int,
        *,
        previous_tail_chars: int = 1200,
        next_preview_chars: int = 800,
    ) -> dict[str, Any]:
        scene = self._require_scene(scene_id)
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
        manual_character_ids: Iterable[int] = (),
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        scene = self._require_scene(scene_id)
        manual_materials = {
            item.id: item
            for item in (
                self.material_service.get_material(int(material_id))
                for material_id in manual_material_ids
            )
            if item is not None
        }
        all_materials = self.material_service.list_materials(
            scope="project",
            project_id=scene.project_id,
        ) + self.material_service.list_materials(scope="public")
        bound_characters = self.anchor_service.list_project_character_cards(scene.project_id)
        character_by_id = {card.id: card for card in bound_characters}
        search_terms = _unique_terms(
            [*keywords, *character_names, location, time_hint, *_proper_nouns(scene.original_text)]
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
            "manual_character_ids": list(manual_character_ids),
        }
        results: list[dict[str, Any]] = []
        for material_id, material in manual_materials.items():
            results.append(
                _result(
                    "manual",
                    "material",
                    material_id,
                    _material_location(material),
                    material.description or material.raw_text or json.dumps(json.loads(material.content_json), ensure_ascii=False),
                    "用户手动指定素材，优先于自动检索。",
                    1.0,
                )
            )
        for character_id in manual_character_ids:
            card = character_by_id.get(int(character_id)) or self.anchor_service.get_character_card(int(character_id))
            if card is not None:
                results.append(
                    _result(
                        "manual",
                        "character_card",
                        card.id,
                        f"character:{card.name}@v{card.version}",
                        _character_content(card),
                        "用户手动指定角色卡，优先于自动检索。",
                        1.0,
                    )
                )

        for card in bound_characters:
            if card.id in set(int(value) for value in manual_character_ids):
                continue
            names = [card.name, *card.aliases]
            matched = [name for name in names if name and name in scene.original_text]
            if matched:
                results.append(
                    _result(
                        "structure",
                        "character_card",
                        card.id,
                        f"character:{card.name}@v{card.version}",
                        _character_content(card),
                        f"当前场景出现角色名：{', '.join(matched)}。",
                        0.96,
                    )
                )

        for material in all_materials:
            if material.id in manual_materials:
                continue
            content = " ".join(
                [
                    material.name,
                    material.description,
                    material.raw_text,
                    material.content_json,
                    " ".join(material.tags),
                ]
            )
            structural = (
                material.project_id == scene.project_id
                and _timeline_matches(material.timeline_start_chapter, material.timeline_end_chapter, scene.scene_index)
            )
            matched_terms = [term for term in search_terms if term and term.casefold() in content.casefold()]
            if structural:
                results.append(
                    _result(
                        "structure",
                        "material",
                        material.id,
                        _material_location(material),
                        material.description or material.raw_text or material.content_json,
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
                        material.description or material.raw_text or material.content_json,
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
                            material.description or material.raw_text or material.content_json,
                            "词项向量相似度补充结果。",
                            min(0.7, similarity + 0.35),
                        )
                    )

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

        order = {"manual": 0, "structure": 1, "keyword": 2, "relationship": 3, "vector": 4}
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
        scene_rules = (rules_by_scene_type or {}).get(scene.scene_type, [])
        limited_examples = sorted(
            (example for example in examples if example.strip()),
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
        recent = _unique_terms(
            technique
            for row in rows
            for technique in _json_list(row["recent_techniques_json"])
        )
        forbidden = _repeated_techniques(recent)
        context = {
            "scene_type": scene.scene_type,
            "global_rules": list(global_rules),
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
        window = self.build_sliding_window(scene_id)
        facts = self.scene_service.get_fact_ledger(scene_id)
        character_states = self.scene_service.list_character_states(scene_id)
        retrieval = list(retrieval_results)
        material_context = [
            item for item in retrieval if item["source_type"] == "material"
        ]
        character_context = [
            item for item in retrieval if item["source_type"] == "character_card"
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
            PromptBlock("must_preserve_events", _json_text(task.get("must_preserve_events", [])), 4, True),
            PromptBlock("required_end_state", _json_text(task.get("required_end_state", {})), 5, True),
            PromptBlock("story_state", _json_text({"facts": facts, "characters": character_states}), 6),
            PromptBlock("previous_rewritten_tail", window["previous_rewritten_tail"], 7),
            PromptBlock("next_original_preview", window["next_original_preview"], 8),
            PromptBlock("foreshadowing", _json_text(facts["foreshadowing"]), 9),
            PromptBlock("character_context", _json_text(character_context), 10),
            PromptBlock("material_context", _json_text(material_context), 11),
            PromptBlock("scene_style_rules", _json_text((style_context or {}).get("scene_rules", [])), 12),
            PromptBlock("style_examples", _json_text((style_context or {}).get("examples", [])), 13),
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
                context_key = (
                    "material_context"
                    if result["source_type"] == "material"
                    else "character_context"
                    if result["source_type"] == "character_card"
                    else "story_state"
                )
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
                "character_context": character_states,
                "material_context": material_context,
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
    scope = f"project:{material.project_id}" if material.project_id is not None else "public"
    timeline = (
        f":chapters:{material.timeline_start_chapter or '*'}-{material.timeline_end_chapter or '*'}"
    )
    return f"{scope}:material:{material.id}@v{material.version}{timeline}"


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
