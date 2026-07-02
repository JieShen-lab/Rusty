# Plan Review Log: Rusty structured style templates, anchors, and export sequencing
Act 1 (grill) complete - plan locked with the user. MAX_ROUNDS=5.

## Round 1 - Codex
Verdict: REVISE

Findings accepted:
- Existing DB initialization needed a real migration plan instead of insert-only schema version recording.
- Project binding was ambiguous against the current strongly typed settings/API/client contract.
- Rewrite outputs needed provenance snapshots once style/outline/character anchors affect generation.
- Manual and AI rewrites needed an explicit source field before export sequencing could label them reliably.
- Export sequencing needed a service-level effective export DTO instead of changing exporters ad hoc.
- Legacy category prompt handling needed either explicit scene-label selection or informational-only behavior.
- Extraction/import endpoints needed centralized file validation and size/token protections.

Claude response:
- Added phase 0 migration runner requirement, schema version bump, and v1 upgrade tests.
- Chose dedicated project binding tables for styles/outlines/characters instead of overloading `project_settings`.
- Listed required contracts across dataclasses, services, Pydantic schemas, API routes, client types, and UI refresh.
- Added rewrite provenance requirements: source, selected ids, version hashes/snapshots, and final prompt snapshot.
- Added `get_effective_export_chapters(project_id)` as the sole TXT/EPUB export sequencing service entry point.
- Made legacy `categoryPrompts` informational by default unless explicit scene-label selection is implemented and tested.
- Required extraction endpoints to reuse centralized path/format/size/token validation.

## Round 2 - Codex
Verdict: REVISE

Findings accepted:
- Verification needed to include the Electron/React TypeScript build because the plan changes backend schemas/routes and desktop client types.
- New style/binding/extraction/trial-writing endpoints needed explicit local API token policy.
- Binding tables needed cardinality, uniqueness, ordering, and delete behavior before implementation.

Claude response:
- Added `npm --prefix desktop run build` to verification whenever backend schemas/routes, desktop client types, or Electron/React UI code changes.
- Required every create/update/delete/import/bind/extract/trial-writing endpoint to use the local API token, with read-only routes classified before implementation.
- Defined binding constraints: one active style, one active outline, many unique character cards per project, optional sort order, no new binding to soft-deleted rows, inactive/ignored stale bindings, and guarded hard deletes when rewrite provenance exists.

## Round 3 - Codex
Verdict: APPROVED

Codex conclusion:
- Round 2 blockers are addressed at the plan level.
- The plan now includes Electron/React build verification, explicit token policy for mutating/template/extraction endpoints, and concrete binding cardinality/delete rules.
- No remaining material implementation risk blocks starting Phase 0, assuming implementation follows and tests the added constraints.
