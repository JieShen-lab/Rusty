# Plan: Rusty structured style templates, anchors, and export sequencing
_Locked via grill by Codex + user_

## Goal
Extend Rusty from a local novel import/rewrite/export MVP into a structured fanfic/expansion workflow where users can create and reuse style templates, optionally extract those templates from sample prose, bind style/outline/character anchors to a project, inject them into the rewrite stage without affecting summary or scene detection, and arrange chapter export order before TXT/EPUB output. DOCX remains import-only and is explicitly out of scope for export.

## 2026-07-14 unified prompt-package decision (supersedes the separate-resource UI)
- The user-facing domain is one project-named prompt package, not separate style, outline, and character libraries.
- The canonical versioned JSON contains system rules, summary rules, scene-recognition categories, general rewrite rules, scene-specific rewrite rules, story-development anchors, character anchors, and metadata.
- "Style" is represented by the general and scene-specific rewrite rules. Story and character anchors live in the same package because they all serve prompt assembly.
- Analysis projects run: source -> chapter summaries -> AI prompt-package extraction -> review/export. Extraction persists and binds the resulting package to the source project.
- Rewrite projects bind one prompt package and run: source -> chapter summary -> scene recognition -> optional AI plot expansion -> AI rewrite -> export.
- Plot expansion may revise or add mainline/key nodes, but must remain inside the package's story and character constraints. Its result is stored separately and injected into the subsequent rewrite.
- Scene recognition returns configured category keys; rewrite injects only the specific rules matching those keys, plus the package's general rewrite rules and relevant character anchors.
- Legacy `style_templates`, outline templates, character cards, and their bindings remain readable for compatibility, but they are no longer separate primary navigation concepts.
- Reference screenshots determine information architecture only. Rusty never generates or enables jailbreak, policy-bypass, "breakthrough", or privileged hidden instructions.

## Approach
0. Add a schema migration foundation before any feature tables.
   - Bump `CURRENT_SCHEMA_VERSION` from 1 and replace insert-only version recording with an idempotent migration runner.
   - Keep `CREATE TABLE IF NOT EXISTS` for fresh installs, but make existing databases upgrade through explicit versioned migrations.
   - Add tests that create a v1-style database, run initialization, and assert new tables/columns/indexes exist with preserved data.
   - Treat migration support as phase 0; do not add UI/API work until this is in place.

1. Add a first-class `style_templates` domain object.
   - Store structured style data separately from existing `prompt_templates`.
   - Include fields for name, description, detail level, global/rewrite additions, style profile JSON, generated prompt text, source metadata, compatibility/import metadata, timestamps, and soft delete.
   - Use explicit project binding tables instead of overloading `project_settings`: `project_style_bindings`, `project_outline_bindings`, and `project_character_bindings`.
   - Keep `project_settings` focused on model/prompt/target controls, avoiding a fragile dataclass/API contract expansion for every anchor type.
   - Binding constraints: one active style template per project, one active outline per project, many character cards per project with unique `(project_id, character_card_id)`, optional character sort order, and priority/main flags stored on the card or binding.
   - Soft-deleted templates/cards cannot be newly bound; existing bindings should become inactive or ignored rather than breaking project loads.
   - Hard deletes must be guarded by foreign keys or converted to soft deletes when a template/card has rewrite provenance.
   - Inject selected style templates only into the rewrite stage.

2. Implement style template manual management.
   - Add service CRUD for style templates.
   - Add backend schemas/routes and client/service adapters for CRUD and project binding instead of relying on generic settings updates.
   - Required contracts: Python models/dataclasses, service methods, Pydantic request/response models, FastAPI routes, frontend/backend client types, and UI state refresh.
   - Every create/update/delete/import/bind/extract/trial-writing endpoint must require the local API token; read-only list/get endpoints should be explicitly classified as public local reads or token-protected reads before implementation.
   - Add UI for listing, creating, editing, deleting, and selecting style templates.
   - Keep the first UI pass functional and Chinese-localized, consistent with the requested Apple-like direction.

3. Implement style template import/export.
   - Define Rusty's versioned JSON schema as the canonical exchange format.
   - Allow `.json` files and `.txt` files whose content is JSON.
   - On import, detect canonical Rusty schema first.
   - Add compatibility mapping for legacy fields: `name`, `rewriteTemplate`, `identifyTemplate`, and `breakthroughTemplate`.
   - Map `rewriteTemplate.commonPrompt` to common rewrite style/rules and `rewriteTemplate.categoryPrompts` to scene-specific rewrite rule metadata where possible.
   - Map `identifyTemplate.categories` to informational scene metadata only unless phase 1 explicitly implements scene-specific rewrite selection.
   - If scene-specific rewrite selection is implemented, use `chapter_scene_analysis.scene_labels_json` at rewrite time and add tests proving selected category rules enter rewrite prompts only for matching scenes.
   - Store `breakthroughTemplate` only as a normal imported text field for compatibility; do not generate it, analyze it, enable it by default, or treat it as special privileged behavior.
   - Fail loudly on malformed JSON or unrecoverable encoding/format errors.

4. Implement AI style extraction.
   - Support input by pasted text and local `TXT / EPUB / DOCX` files.
   - Reuse existing import/parsing utilities for file input through centralized validation: suffix allowlist, existence checks, file size/sample size limits, API token protection, and clear unsupported-format errors.
   - Extraction endpoints must not accept arbitrary unbounded paths or raw files without validation.
   - Offer detail levels: brief, standard, detailed.
   - Use a single AI call in the first version to produce a structured style template.
   - Persist the extraction source type, source file name, sample character count, detail level, and generated structure.

5. Add style test-writing validation as an enhancement after extraction.
   - Provide a default trial-writing prompt with configurable target length and sample scene.
   - Use the extracted style template to generate a short sample for human review.
   - Store the trial output and optional user notes later as tuning history, but do not require that for the first extraction implementation.

6. Add independent outline templates and character cards.
   - Store outline anchors separately from prompt templates and style templates.
   - Store character cards separately with name, aliases, priority, relationship/personality/speech/action constraints, and anti-OOC rules.
   - Bind one outline and multiple character cards to a project.
   - First version uses pasted text or local `TXT / EPUB / DOCX` sources and detail levels consistent with style extraction.

7. Inject outline and character anchors into rewrite only.
   - Summary stays objective and does not use style/outline/character anchors.
   - Scene detection does not use these anchors by default.
   - Rewrite combines: global/safety rules, project prompt overrides, rewrite rules, selected style template, selected outline, relevant character cards, target length/expansion/output constraints, then current chapter source text.
   - Character cards are filtered per chapter by simple deterministic matching: character name or alias in the source chapter, plus any high-priority/main characters that should always be included.
   - AI-based relevant-character detection is deferred.
   - Persist rewrite provenance for every rewrite: `rewrite_source` (`ai` or `manual`), selected prompt/style/outline/card ids, template/card version hashes or immutable prompt snapshots, and the final assembled prompt snapshot used by the model.
   - Do not depend on mutable current template/card rows to explain prior generated text.

8. Add export chapter sequencing.
   - Do not implement full re-chaptering or text re-splitting.
   - Add a persistent per-project export plan with chapter id, export order, export title, and include/exclude flag.
   - Default export plan mirrors current chapter order.
   - Add `get_effective_export_chapters(project_id)` as the single service entry point for TXT/EPUB export.
   - The effective export DTO must filter excluded chapters, sort by saved export order, carry export titles, include source status, and compute counts only from included chapters.
   - EPUB export must use order-based unique filenames rather than original `chapter_index` filenames after reordering/filtering.
   - TXT/EPUB export should use the saved plan when present, otherwise current chapter order through the same service entry point.
   - Show source status per chapter: original, manual rewrite, AI rewrite, or kept original.

9. Sequence implementation in five phases.
   - Phase 0: schema migration runner, upgrade tests, and rewrite provenance fields needed before later features.
   - Phase 1: style template storage, CRUD, import/export, project binding, rewrite injection.
   - Phase 2: AI style extraction and trial-writing validation.
   - Phase 3: outline templates, character cards, project binding, and rewrite injection with deterministic character filtering.
   - Phase 4: export chapter sequencing and export integration.

10. Verification and release discipline.
   - For each phase, add focused service tests plus UI smoke tests where relevant.
   - Run `python -m unittest discover -s tests`, `python -m compileall src tests`, `git diff --check`, and a PySide offscreen smoke check when UI changes.
   - Run `npm --prefix desktop run build` whenever backend schemas/routes, desktop client types, or Electron/React UI code changes.
   - Commit and push after each verified phase.

## Key decisions & tradeoffs
- Style templates are separate from `prompt_templates`, avoiding a mixed object that cannot be reused independently.
- Style templates only affect rewrite, not summary or scene detection, keeping analysis stages more objective.
- Outline and character anchors outrank style during rewrite because plot and character consistency are more important than imitation of prose surface.
- Character-card selection starts with deterministic name/alias matching plus main-character priority; this is cheaper and more predictable than an extra AI call.
- Project anchor bindings use dedicated tables instead of `project_settings` columns because the current settings contract is strongly typed and should remain narrow.
- Project bindings are deliberately cardinality-limited: one active style, one active outline, many unique character cards.
- Template import/export uses versioned JSON as the canonical format while allowing `.txt` containers that contain JSON for user convenience.
- Legacy `categoryPrompts` are informational by default; executable scene-specific rewrite rules require explicit label-matching implementation and tests.
- Legacy `breakthroughTemplate` is treated only as compatible imported text and is not a privileged or default prompt mechanism.
- Export sequencing is saved per project, but full re-chaptering is out of scope for the first export-plan version.
- Rewrite history must be auditable even after templates, styles, outlines, or character cards are edited or deleted.

## Risks / open questions
- Style/outline/character prompt assembly can grow large; later phases may need truncation, summaries, or token-budget management.
- Imported legacy JSON may be mojibake or partially invalid; the importer needs clear error reporting and should not silently corrupt templates.
- Apple-style Chinese UI work is requested, but broad UI redesign should be staged separately from the first style-template data model changes to keep risk contained.
- Trial-writing validation needs default prompts and storage decisions, but it can follow the first extraction implementation.

## Out of scope
- DOCX export.
- Full re-chaptering or automatic splitting of rewritten full text.
- URL/web article extraction.
- AI-based relevant-character detection in the first character-card version.
- Automatically generating, enabling, or analyzing sensitive legacy breakthrough content.
- Packaging as an executable.
