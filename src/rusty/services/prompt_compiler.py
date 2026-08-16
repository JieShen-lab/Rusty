from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable


RUSTY_RULESET_ID = "rusty.native.rewrite.v1"
RUSTY_SUMMARY_RULESET_ID = "rusty.native.summary.v1"
RUSTY_SCENE_RULESET_ID = "rusty.native.scene_detection.v1"
RUSTY_PLOT_RULESET_ID = "rusty.native.plot_expansion.v1"


@dataclass(frozen=True)
class CompiledRequest:
    """The exact, versioned request Rusty intends to send to a model."""

    stage: str
    messages: tuple[dict[str, str], ...]
    expected_output: str
    provenance: dict[str, Any]
    ruleset_id: str = RUSTY_RULESET_ID

    def message_list(self) -> list[dict[str, str]]:
        return [dict(message) for message in self.messages]

    def snapshot(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ruleset_id": self.ruleset_id,
            "expected_output": self.expected_output,
            "messages": self.message_list(),
            "provenance": self.provenance,
        }

    def repair(self, previous_response: str, error_code: str, error_message: str) -> "CompiledRequest":
        repair_message = (
            "Rusty could not apply the previous response. Correct only the output format; "
            "keep the requested story transformation unchanged.\n\n"
            f"Validation code: {error_code}\n"
            f"Validation detail: {error_message}\n"
            f"Required output: {self.expected_output}\n"
            "Return the corrected result only."
        )
        return CompiledRequest(
            stage=self.stage,
            messages=(
                *self.messages,
                {"role": "assistant", "content": previous_response},
                {"role": "user", "content": repair_message},
            ),
            expected_output=self.expected_output,
            provenance={**self.provenance, "repair_for": error_code},
            ruleset_id=self.ruleset_id,
        )


class PromptCompiler:
    """Compile Rusty-native rules and user-owned assets without hiding either."""

    def compile_workflow_json(
        self,
        *,
        stage: str,
        payload: dict[str, Any],
        output_contract: str,
    ) -> CompiledRequest:
        system = (
            "You are Rusty's structured novel-workflow component. Use only the supplied "
            "story state and user direction. Return valid JSON only. Author style context "
            "guides expression and must never introduce unconfirmed story facts."
        )
        user = (
            f"WORKFLOW STAGE: {stage}\n\n"
            f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            f"OUTPUT CONTRACT:\n{output_contract}"
        )
        return CompiledRequest(
            stage=stage,
            messages=(
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ),
            expected_output=output_contract,
            provenance={"workflow_stage": stage},
            ruleset_id="rusty.native.workflow.v1",
        )

    def compile_creative_json(
        self,
        *,
        stage: str,
        master_prompt: str,
        task_prompt: str,
        payload: dict[str, Any],
        user_instruction: str,
        output_contract: str,
        prompt_definition_id: int | None = None,
    ) -> CompiledRequest:
        """Compile new creative tasks while keeping the output contract program-owned."""
        internal_rules = (
            "You are Rusty's structured creative-workflow component. Treat Source text as "
            "immutable evidence, distinguish facts from inference, and never invent facts "
            "outside the supplied context. Return valid JSON only."
        )
        system = (
            f"[RUSTY INTERNAL SYSTEM RULES]\n{internal_rules}\n\n"
            f"[PROJECT MASTER PROMPT]\n{master_prompt.strip() or 'None'}\n\n"
            f"[CURRENT TASK PROMPT]\n{task_prompt.strip() or 'None'}"
        )
        user = (
            "[DYNAMIC CONTEXT]\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "[THIS REQUEST'S USER INSTRUCTION]\n"
            f"{user_instruction.strip() or 'None'}\n\n"
            "[PROGRAM-CONTROLLED OUTPUT CONTRACT]\n"
            f"{output_contract}"
        )
        return CompiledRequest(
            stage=stage,
            messages=(
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ),
            expected_output=output_contract,
            provenance={
                "compiler": "rusty-creative-task",
                "workflow_stage": stage,
                "prompt_definition_id": prompt_definition_id,
            },
            ruleset_id="rusty.native.creative.v1",
        )

    def compile_summary(self, chapter, template) -> CompiledRequest:
        system = _system_message(
            RUSTY_SUMMARY_RULESET_ID,
            "You are Rusty's chapter-analysis component. Extract story facts for later "
            "editing. Do not rewrite the prose. Return only valid JSON.",
            template.global_rules,
        )
        user = (
            _section("USER SUMMARY RULES", template.summary_rules)
            + "\n\nReturn an object with plot_skeleton:string, "
            "characters:[{name:string, role_in_chapter:string}], and key_events:string[]. "
            "Character entries describe project facts and must not be promoted into a reusable style template."
            + _chapter_section(chapter.title, chapter.original_text)
        )
        return self._compiled(
            "summary",
            system,
            user,
            "JSON object: plot_skeleton:string, characters:[{name,role_in_chapter}], key_events:string[]",
            template,
            ruleset_id=RUSTY_SUMMARY_RULESET_ID,
        )

    def compile_scene_detection(self, chapter, template) -> CompiledRequest:
        categories = "\n\n".join(
            (
                f"- id: {rule.scene_key}\n"
                f"  name: {rule.display_name}\n"
                f"  description: {rule.description}\n"
                f"  detection rule: {rule.detection_prompt}"
            )
            for rule in template.scene_rules
        )
        system = _system_message(
            RUSTY_SCENE_RULESET_ID,
            "You are Rusty's scene-identification component. Classify only against the "
            "provided category IDs, cite compact evidence, and return only valid JSON.",
            template.global_rules,
        )
        user = (
            _section("AVAILABLE CATEGORIES", categories or "No categories are configured.")
            + "\n\nReturn exactly this shape:\n"
            '{"analysis":{"has_target_content":true,"categories":["id"],'
            '"markers":[{"category_id":"id","category_name":"name",'
            '"expand_description":"who did what in this scene",'
            '"evidence":"short exact excerpt"}],"reasoning":"brief reason"}}'
            + "\nIf no category matches, use false and empty arrays."
            + _chapter_section(chapter.title, chapter.original_text)
        )
        return self._compiled(
            "scene_detection",
            system,
            user,
            "JSON object with analysis.has_target_content, categories, markers, and reasoning",
            template,
            ruleset_id=RUSTY_SCENE_RULESET_ID,
        )

    def compile_plot_expansion(
        self,
        chapter,
        template,
        *,
        plot_summary: str,
        characters_json: str,
        labels: Iterable[str],
        reasoning: str,
    ) -> CompiledRequest:
        system = _system_message(
            RUSTY_PLOT_RULESET_ID,
            "You are Rusty's plot-planning component. Propose a target skeleton without "
            "rewriting the chapter prose.",
            template.global_rules,
        )
        user = (
            "Preserve established facts, chronology, and character constraints. Return only a planning draft."
            + _section("ORIGINAL PLOT SKELETON", plot_summary or "Not extracted")
            + _section("CHAPTER CHARACTERS", characters_json or "[]")
            + _section("SCENE LABELS", ", ".join(labels) or "None")
            + _section("IDENTIFICATION REASONING", reasoning or "None")
            + _chapter_section(chapter.title, chapter.original_text)
        )
        return self._compiled(
            "plot_expansion",
            system,
            user,
            "plain-text target plot skeleton",
            template,
            ruleset_id=RUSTY_PLOT_RULESET_ID,
        )

    def compile_rewrite(
        self,
        chapter,
        template,
        *,
        rewrite_mode: str,
        target_text: str,
        package_sections: str,
        style_system_rules: str,
        style_section: str,
        outline_section: str,
        character_section: str,
        marker_section: str,
    ) -> CompiledRequest:
        if rewrite_mode not in {"anchor_expand", "full_rewrite"}:
            raise ValueError(f"Unsupported rewrite mode: {rewrite_mode}")

        native_rule = (
            "You are Rusty's novel-rewrite component. Preserve established facts and "
            "character constraints. User-owned rules describe the desired prose; Rusty's "
            "output contract controls only how the result is applied."
        )
        if rewrite_mode == "anchor_expand":
            native_rule += (
                " Work on one exact source fragment. Text outside that fragment is frozen "
                "and will be retained by Rusty."
            )
            contract = (
                'JSON object only: {"anchor":"an exact non-empty substring copied from the original chapter",'
                '"expanded":"the complete replacement for that substring"}'
            )
        else:
            contract = "complete rewritten chapter as plain text, with no commentary"

        system = _system_message(
            RUSTY_RULESET_ID,
            native_rule,
            _join_nonempty(template.global_rules, style_system_rules),
        )
        user = (
            _section("USER REWRITE RULES", template.rewrite_rules)
            + target_text
            + package_sections
            + style_section
            + outline_section
            + character_section
            + marker_section
            + _section("RUSTY OUTPUT CONTRACT", contract)
            + _chapter_section(chapter.title, chapter.original_text)
        )
        return self._compiled(rewrite_mode, system, user, contract, template, stage="rewrite")

    def compile_scene_stage(
        self,
        *,
        stage: str,
        compilation: dict[str, Any],
        output_protocol: str,
        provenance: dict[str, Any] | None = None,
    ) -> CompiledRequest:
        """Compile a budgeted scene snapshot without rejoining and truncating it."""
        blocks = compilation.get("blocks")
        if not isinstance(blocks, list):
            raise ValueError("Scene prompt compilation requires budgeted blocks.")
        included = [
            block
            for block in blocks
            if isinstance(block, dict) and bool(block.get("included", True))
        ]
        system_blocks = [block for block in included if block.get("key") == "system_rules"]
        user_blocks = [block for block in included if block.get("key") != "system_rules"]
        if not system_blocks:
            raise ValueError("Budgeted scene prompt is missing required system rules.")
        if not any(block.get("key") == "current_original_scene" for block in user_blocks):
            raise ValueError("Budgeted scene prompt is missing the complete current scene.")
        if not any(block.get("key") == "user_instruction" for block in user_blocks):
            raise ValueError("Budgeted scene prompt is missing the user instruction block.")
        required_by_stage = {
            "skeleton": {"scene_analysis"},
            "planning": {"confirmed_skeleton", "material_mappings"},
            "rewrite": {"confirmed_skeleton", "rewrite_plan"},
            "consistency_check": {"rewrite_plan", "candidate_rewrite_text"},
            "targeted_repair": {"consistency_result", "repair_source_text", "repair_targets"},
        }
        included_keys = {str(block.get("key")) for block in user_blocks}
        missing_stage_blocks = sorted(required_by_stage.get(stage, set()) - included_keys)
        if missing_stage_blocks:
            raise ValueError(
                "Budgeted scene prompt is missing required stage blocks: "
                + ", ".join(missing_stage_blocks)
            )
        system = "\n\n".join(
            f"## {str(block.get('key')).upper()}\n{str(block.get('content') or '')}"
            for block in system_blocks
        )
        user = "\n\n".join(
            f"## {str(block.get('key')).upper()}\n{str(block.get('content') or '')}"
            for block in user_blocks
        )
        user += f"\n\n## OUTPUT PROTOCOL\n{output_protocol}"
        return CompiledRequest(
            stage=stage,
            messages=(
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ),
            expected_output=output_protocol,
            provenance={
                "compiler": "rusty-scene-budgeted",
                "prompt_compilation_id": compilation.get("id"),
                "used_input_tokens": compilation.get("used_input_tokens"),
                "reserved_output_tokens": compilation.get("reserved_output_tokens"),
                **(provenance or {}),
            },
            ruleset_id=f"rusty.native.scene.{stage}.v1",
        )

    @staticmethod
    def _compiled(
        label: str,
        system: str,
        user: str,
        expected_output: str,
        template,
        *,
        stage: str | None = None,
        ruleset_id: str = RUSTY_RULESET_ID,
    ) -> CompiledRequest:
        return CompiledRequest(
            stage=stage or label,
            messages=(
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ),
            expected_output=expected_output,
            provenance={
                "compiler": "rusty-native",
                "template_id": template.id,
                "template_name": template.name,
                "template_version": template.version,
                "mode": label,
            },
            ruleset_id=ruleset_id,
        )


def _system_message(ruleset_id: str, native_rules: str, user_rules: str) -> str:
    return (
        f"[RUSTY NATIVE RULES: {ruleset_id}]\n{native_rules.strip()}\n\n"
        "[USER-OWNED SYSTEM RULES]\n"
        f"{user_rules.strip() or 'None'}"
    )


def _section(title: str, content: str) -> str:
    return f"\n\n## {title}\n{content.strip() or 'None'}"


def _chapter_section(title: str, text: str) -> str:
    return f"\n\n--- ORIGINAL CHAPTER: {title} ---\n{text}\n--- END ORIGINAL CHAPTER ---"


def _join_nonempty(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())
