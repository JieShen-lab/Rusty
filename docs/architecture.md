# Rusty Architecture Overview

## Runtime layers

```text
Electron main/preload + React UI
              ↓
       desktop API client
              ↓
         FastAPI routes
              ↓
  services and workflow orchestrators
              ↓
 version, branch, content and library services
              ↓
             SQLite
```

Electron owns the desktop process, preload bridge, backend lifecycle and native file boundaries. React owns editing, review and presentation state. It does not decide workflow validity or write SQLite directly.

FastAPI is the transport boundary. `backend/api.py` creates services and registers routers. Domain routers validate HTTP payloads, invoke services and map errors; they do not own SQL, workflow transitions or fact merging. Plot/Prose/Branch/version routes live in `backend/routes/workflows.py`. Their strict contracts live in `backend/workflow_schemas.py` and remain re-exported from `backend.schemas` for compatibility.

## Core content model

### Project, chapter and scene

A project has `project_kind` `rewrite`, `branch` or the read-only compatibility kind `legacy_extract`. Chapters and original scenes describe the imported baseline. `processing_mode` is retained for execution and legacy data, not as the project-purpose authority.

The product-facing ordinary-project entry is now unified: both `rewrite` and historical `branch` projects enter `CreativeWorkspacePage`. `project_kind` remains a compatibility/storage field; `legacy_extract` retains its dedicated read-only route.

`scene_workflow_state` is the authority for each scene's reached stage. `chapter_workflow_state` is the chapter-navigation projection: it remembers the active scene and mirrors that scene's stage for the chapter rail. Source remains a permanent immutable layer on `scenes`; `scene_preanalyses`, intents, strategy analyses, targets, writing plans, current drafts and review marks are separate downstream models that reference the same scene identity and Source offsets.

`scene_targets.design_json` is strategy-shaped: faithful stores a ChangeSet, plot adjustment stores a TargetSkeleton, expansion stores an InsertionBlock, and reimagination stores BoundaryConditions plus a TargetSkeleton. `writing_plan_blocks` is the common prose-operation layer. Preserve copies Source without AI; Transform/Rewrite/Insert call task prompts; Delete omits a span. `scene_current_drafts` is the authoritative editable prose and is never deleted by upstream stale propagation. Review is local traditional diff plus user notes, not an AI review system.

Original chapter text and `chapter_source_versions` are immutable source history. Compatibility columns such as `chapters.rewritten_text` are current projections, not version authority.

### Rewrite versions

`ChapterVersionService` owns the append-only `chapter_rewrite_versions` chain and current head. Plot, Prose, manual edits, restore and the legacy pipeline append through this service. A historical derivation points to the version it actually used.

Each rewrite version freezes its text/hash, parent/source, source operation, chapter facts, fact-chain status, structure provenance and version-local semantic map. `RewriteVersionMapService` maps stable scene/event identities to spans and local states in one version. Semantic anchors resolve against that map; they do not search original text or reuse original offsets.

### Skeleton and facts

Story skeletons are structured and versioned. Original analysis structures and rewrite-version structures coexist; choosing a text version also chooses its matching structure/map snapshot.

Facts have explicit levels: chapter start/end, local semantic segment, scene ledger and branch scene/chapter snapshot. Callers must not substitute chapter-end facts for a middle anchor or combine facts from one version with text from another.

## Branch model

`BranchService` owns independent branch routes, source anchors and versioned branch persistence.

- A root branch starts from an original semantic anchor.
- Continuing a route appends new versioned chapters to that same branch.
- Branch chapters and scenes have immutable versions.
- `branch_chapter_version_scenes` freezes the scene-version order of a chapter snapshot.
- Branch writes never overwrite the original baseline.

## Workflow ownership

`CreativeWorkflowService` owns chapter-stage restoration, lightweight preanalysis, scene intent, the faithful character-modification analysis slice, confirmation and upstream invalidation. Viewing an earlier stage is read-only; edits are the operations that stale downstream artifacts. Target design is an interface boundary in phase one, not a generation implementation.

`PromptDefinitionService` owns editable `master`, `workflow_task` and `common_task` definitions and copy-based project master prompts. `PromptCompiler.compile_creative_json` is the sole compiler entry for new creative tasks: internal rules, project master and task instructions are separated from dynamic context, user intent and the program-owned output contract.

`PlotGenerationOrchestrator` owns Plot lifecycle, target skeleton, incremental progress, consistency warnings, retry/cancel and final commit. Its status vocabulary comes from `rusty.domain.plot_workflow`. Source text, map and resolved anchors are frozen at start; source-head CAS prevents stale overwrite.

`ProseRewriteOrchestrator` owns planning, generation, observed-skeleton extraction, drift checks and version finalization. Source text, structure and map belong to the same selected snapshot.

Shared analysis services provide document, scene, skeleton, style, character and fact extraction to both project kinds. `ContextService` resolves sources and compiles context blocks for legacy workflows; new creative tasks use narrowly scoped context builders in `CreativeWorkflowService`.

## Compatibility boundaries

The following are intentional: v1-v44 migrations; `legacy_extract` read/export/derive; rewrite current projections; old summaries, expansion data, prompt packages and document revisions; the legacy pipeline/scene services and panels while compatibility APIs/tests remain reachable; and PySide UI until explicitly retired. Ordinary creative projects no longer use the large scene-rewrite modal as their entry point.

Compatibility code needs an owning test or documented upgrade reason. Lack of a new-workflow import is not evidence that it is dead.

## Code ownership map

| Change | Primary owner |
| --- | --- |
| Project/chapter CRUD, import/export, legacy derive | `ProjectService` |
| Default SQLite location | `rusty.db.paths` |
| Rewrite version/head/projection | `ChapterVersionService` |
| Version-local semantic anchors/states | `RewriteVersionMapService` + `ContextService` |
| Independent branch routes and versions | `BranchService` |
| Plot lifecycle | `PlotGenerationOrchestrator` |
| Prose lifecycle | `ProseRewriteOrchestrator` |
| Shared skeleton/fact analysis | shared analysis/content services |
| Chapter creative stage, preanalysis and faithful character analysis | `CreativeWorkflowService` |
| Master/task prompt definitions and project copies | `PromptDefinitionService` |
| New creative prompt assembly | `PromptCompiler.compile_creative_json` |
| Workflow HTTP routes/contracts | `backend/routes/workflows.py` + `backend/workflow_schemas.py` |
| Phase-one Electron creative UI | `CreativeWorkspacePage` |
| Legacy Plot/Prose Electron UI | `WorkflowRefactorPanels`, `WorkflowPanelShared`, `StoryAnchorPicker` |
| Workflow browser client | `desktop/src/api/workflowClient.ts` |
| Active-run restoration | `usePersistedWorkflowRun` |
| Historical upgrade | `rusty.db.schema` (append only) |

## Invariants and allowed write paths

- Original text and immutable rewrite/branch versions are not updated or deleted by business code.
- Formal chapter output enters through `ChapterVersionService`.
- Formal branch output enters through `BranchService`.
- Routes do not update workflow run status directly.
- A run uses one frozen content/version/map source snapshot.
- Final output and terminal run state share a visible transaction boundary.
- Schema version 51 is append-only. v46 adds SceneTarget, v47 WritingPlan/blocks and Current Draft, v48 ReviewMark, v49 strategy analyses and plot-adjustment tasks, v50 expansion tasks, and v51 reimagination tasks; v41–v45 remain unchanged.
- Source text and scene offsets remain authoritative evidence; preanalysis and special-analysis records never replace Source Layer content.
- Upstream edits stale downstream analysis/design/planning state but never delete generated prose.

## Phase-one boundary

Implemented: preanalysis, creative direction and faithful character-modification analysis. Reserved for the next phase: Target ChangeSet, other strategy-specific analyses, Writing Plan, block generation, Diff review and automated omission validation.
