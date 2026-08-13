# Rusty code necessity audit

> 审计日期：2026-08-13。原则：只删除能够用调用关系、信任边界、failure mode 与 deletion test 证明为无效的复杂度；大文件、短 helper、单一调用者都不是删除理由。

## 1. Baseline

| 项目 | 结果 |
| --- | --- |
| 起始分支 / HEAD | `codex/production-shell-ui-unification` / `18c0f98c35813e726216a42dfaf18849595c5269` |
| `origin/main` | `df1edf9cfbf3dd77f7e820190a012abcbb5963dd` |
| 审计分支 | `codex/code-necessity-audit`，从 `18c0f98` 创建 |
| schema | `CURRENT_SCHEMA_VERSION = 52` |
| 2026-08-12 UI 分支 | 已找到；当前基线比 main 多 5 个提交，涉及 workspace、文档/角色/素材页面、导航、样式和 Electron production load |
| 起始工作区 | `git status --short` 无内容差异；若干旧 pytest 临时目录因 ACL 不可读并产生 warning |
| Python baseline | `281 passed, 21 subtests passed in 113.10s`；数据库与 TEMP 均隔离在仓库临时目录 |
| frontend build | 通过；1609 modules，Vite 8.70s，Electron TypeScript 通过 |
| mock E2E | `47 passed`，27.0s |
| real backend E2E | `8 passed`，21.7s |
| Electron E2E | `5 passed`，8.3s |
| production E2E | `1 passed`，4.4s |
| baseline failure | 无产品失败。沙箱内首次 pytest/构建分别因 SQLite 路径、TemporaryDirectory ACL、`spawn EPERM` 失败；隔离并授权本地子进程后全部通过 |

## 2. Repository complexity map

`git ls-files` 共 199 个文件。本轮静态审计覆盖 113 个 Python 与 48 个 TS/TSX 文件，共 161 个代码文件。Python 共 49,328 LOC（非测试/示例主生产区约 37,252 LOC），TS/TSX 共 15,602 LOC（非 E2E 约 13,494 LOC）。计数使用 Python AST 与轻量 TS 词法扫描，不引入 runtime dependency。

### 2.1 Python Top 30（按 LOC）

| 文件 | LOC | 函数 | 类 | import | 分支近似 | 主要职责/覆盖 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `src/rusty/db/schema.py` | 4755 | 72 | 0 | 9 | 121 | schema/migration/repair；`test_schema.py`、`test_chapter_workflow_schema.py` |
| `backend/api.py` | 3341 | 300 | 1 | 47 | 125 | HTTP 边界、鉴权、DTO/错误翻译；API/E2E |
| `src/rusty/services/document_library_service.py` | 2475 | 70 | 16 | 15 | 203 | 文档文件、revision/draft/offset；文档 service/API/E2E |
| `src/rusty/ui/main_window.py` | 2183 | 99 | 2 | 31 | 169 | 旧 Qt UI；间接/人工覆盖 |
| `src/rusty/services/anchor_service.py` | 1944 | 66 | 6 | 11 | 161 | 角色、标签、封面、旧 anchor；anchor tests |
| `src/rusty/services/material_service.py` | 1686 | 62 | 7 | 9 | 163 | 素材、分类、来源兼容；material tests |
| `src/rusty/services/creative_workflow_service.py` | 1624 | 78 | 1 | 10 | 238 | 场景创作状态与阶段数据；creative/E2E |
| `src/rusty/services/pipeline_service.py` | 1452 | 66 | 3 | 17 | 172 | legacy pipeline、prompt/model 与版本写入；pipeline tests |
| `backend/schemas.py` | 1370 | 2 | 154 | 4 | 2 | Pydantic API contract；API tests |
| `src/rusty/services/anchor_extraction_service.py` | 1354 | 33 | 8 | 17 | 113 | Preview/Apply、AI 输出校验；preview/apply tests |
| `src/rusty/services/context_service.py` | 1343 | 29 | 6 | 17 | retrieval、budget、版本感知上下文；context tests |
| `src/rusty/services/project_service.py` | 1231 | 36 | 1 | 11 | 工程/章节/legacy migration/export；project tests |
| `src/rusty/services/branch_service.py` | 1154 | 28 | 1 | 8 | branch、anchor、commit/rollback；branch tests |
| `src/rusty/services/rewrite_version_map_service.py` | 1095 | 31 | 4 | 11 | semantic map/hash/provenance/offset；semantic map tests |
| `src/rusty/services/rewrite_workflow_service.py` | 1050 | 31 | 2 | 12 | skeleton/plan/version/consistency persistence；rewrite tests |
| `tests/test_schema.py` | 904 | 16 | 1 | 11 | migration/invariant regression |
| `src/rusty/services/scene_rewrite_orchestrator.py` | 884 | 26 | 1 | 13 | scene rewrite orchestration、AI、transaction stages |
| `src/rusty/services/plot_generation_orchestrator.py` | 841 | 20 | 1 | 15 | branch plot generation、provenance、commit |
| `tests/test_backend_api.py` | 805 | 15 | 2 | 10 | HTTP contracts |
| `tests/test_pipeline_service.py` | 767 | 20 | 3 | 11 | pipeline failure/normal paths |
| `src/rusty/services/scene_service.py` | 684 | 28 | 2 | 11 | scene/source/facts/dynamic state |
| `tests/test_preview_apply_contract_v23.py` | 667 | 23 | 2 | 19 | token single-use、atomic Apply、retry |
| `tests/test_creative_phase_two.py` | 597 | 34 | 6 | 14 | phase-two domain contracts |
| `tests/test_phase2_contract_regressions.py` | 576 | 19 | 2 | 26 | cross-service/E2E-like regressions |
| `tests/test_anchor_service.py` | 544 | 17 | 2 | 10 | anchor/cover/extraction |
| `tests/test_branch_service.py` | 544 | 17 | 1 | 15 | branch/provenance |
| `src/rusty/services/chapter_version_service.py` | 539 | 13 | 3 | 11 | immutable chapter versions/source hash |
| `tests/test_creative_workspace.py` | 494 | 13 | 2 | 15 | creative state/reload |
| `src/rusty/services/prompt_service.py` | 487 | 23 | 3 | 7 | legacy prompt package compatibility |
| `tests/test_document_library_service.py` | 472 | 15 | 1 | 11 | document file/revision/draft |

### 2.2 TS/TSX hotspots

| 文件 | LOC | 函数近似 | 分支近似 | 职责 |
| --- | ---: | ---: | ---: | --- |
| `DocumentLibraryPage.tsx` | 2139 | 82 | 253 | library、workspace editor、autosave、split/merge、dialogs |
| `MaterialLibraryPage.tsx` | 1617 | 36 | 126 | material filtering/editor/Preview→Apply |
| `api/client.ts` | 1506 | 238 | 68 | Electron/fetch transport 与 endpoint wrappers |
| `api/types.ts` | 1421 | 0 | 0 | wire contracts |
| `CreativeWorkspacePage.tsx` | 1290 | 91 | 215 | scene workflow、dirty flush、stage UI |
| `CharacterLibraryPage.tsx` | 1135 | 40 | 113 | character library/editor/extraction |
| `ProjectWorkspacePage.tsx` | 869 | 60 | 179 | project router 与 legacy workspace |
| `NewProjectPage.tsx` | 491 | 20 | 66 | project creation |
| `WorkflowRefactorPanels.tsx` | 444 | 13 | 89 | workflow panels/legacy notice |
| `CharacterCreationDialogs.tsx` | 431 | 10 | 40 | extraction candidate editor |

### 2.3 Frontend state map

根组件计数与分类结论：

| 根组件 | useState | useEffect | SOURCE / SERVER MIRROR | UI EPHEMERAL / 表单草稿 | 结论 |
| --- | ---: | ---: | --- | --- | --- |
| `CreativeWorkspacePage` | 40 | 7 | chapter/state/scene/context payload 与各阶段草稿 | busy/error/settings、`viewStage`、dirty flags | `viewStage` 可回看已解锁阶段，不等同 server stage；dirty flags 驱动 autosave，KEEP |
| `DocumentLibraryPage` | 36 | 3（文件内含 editor effects 共 11） | documents/tags/categories/revisions/draft/content | filter/selection/modal/metadata edit | editor text/title 是未提交草稿，不能从 server mirror 推导；KEEP |
| `MaterialLibraryPage` | 18 | 2（文件内共 3） | materials/categories/tags | selection/query/dialog/editor drafts | `selectedId` 与 `editing` 分别是选择和可变草稿；KEEP |
| `ProjectWorkspacePage` | 2 | 1；legacy 子页 25/5 | project/chapters/detail/prompts | panel widths、selection、legacy stage | legacy page 仍由 `project_kind=legacy_extract` 到达；KEEP LEGACY |
| `CharacterLibraryPage` | 23 | 3（文件内共 4） | cards/tags/categories/projects | selection/query/dialog/editor draft | form draft/cover preview 有独立未保存语义；KEEP |

未发现 A→B→C→A 的 effect 循环。最危险的同步链在 Creative workspace（server stage→view stage）和文档 editor（content/draft→local text→autosave），但两者均有用户可见的浏览/未提交语义，不能作为 derived state 删除。

## 3. Core flow maps

以下为真实主路径；括号内是主要不可替代职责。计数是主成功路径近似，不把 DTO 构造器逐个计入。

### Flow A — 数据库初始化

`create_app/service constructor` → `session/connect`（FK/WAL）→ `initialize_database`（transaction）→ `SCHEMA_SQL + seed` → migration ledger → `MIGRATIONS[v]` → version insert → ready。

- 主路径约 6 hops；每次 service 构造都会重新执行幂等 schema/seed，虽不重跑已记账 migration，仍是高优先人工性能/所有权审查项。
- v52：`ensure table` → column validate → create index → seed missing rows → column+index validate。第二次 column check 已被 deletion experiment 证明重复；index check 独立保留。

### Flow B — 工程打开

`ProjectWorkspacePage` → `getProject` → `GET /api/projects/{id}` → `ProjectService.get_project/get_settings` → SQLite → Pydantic output → page 按 `project_kind` 路由 → Creative 或 legacy state。

- 约 8 hops、2–3 DB reads。顶层 page 只保留路由所需 project；子页再次加载完整工作区数据是组件切换后的权威 load，而非同一对象的无意义 copy。

### Flow C — 章节工作流状态

`CreativeWorkspacePage.loadProject/loadChapter` → API → `CreativeWorkflowService.get_chapter_state/list_scene_states` → SQLite → active scene → local editable drafts → debounce `flushLoadedScene` → PUT/save → navigation flush → reload。

- `selectedChapterIdRef`、`loadedSceneId` 与 `loadedDraftRef.sceneId` 防止快速切换把旧草稿写到新 scene；对应 mock E2E 的 dirty switch/popstate tests，KEEP。
- no-op save、authority、autosave 和 v52 repair 均为 2026-08-11/12 回归高风险区。

### Flow D — 创作工作流

API endpoint（HTTP/token）→ `CreativeWorkflowService`（stage invariant + persistence）→ `SceneService/AnchorService/MaterialService`（DB→domain 边界）→ `WorkflowAI`（prompt/model）→ external AI → structured output check → stage row/draft → response。

- service 拥有 workflow state/persistence；`WorkflowAI` 拥有 prompt/model/AI call；资源 services 拥有 entity existence。
- 多个 public stage method 的 `scenes.get_scene` 不是同一调用链内重复，而是各 API 入口的 DB/domain 边界。

### Flow E — AI 上下文编译

scene/project → `ContextService.retrieve`（resources）→ `compile_scene_context` → `PromptBudgeter`（裁剪）→ `PromptCompiler`（system/user/schema）→ `PromptDefinitionService` → `WorkflowAI`/`StructuredModelService`（model + external call）。

- 未发现同一 compiled prompt 在一个请求内组装两次。`WorkflowAI` 和 `StructuredModelService` 是两种调用入口，存在职责重叠但当前调用者不同，REVIEW 而非删除。

### Flow F — rewrite/version/provenance

orchestrator plan → `resolve_chapter_source` → semantic map/skeleton → `map_hash` → persisted expected hash → external AI → normalize observed skeleton IDs → `validate_map_hash` → append immutable rewrite version → restore/anchor resolution。

- hash 跨持久化与外部 AI 边界，防 stale source、map/version 错配和 restore corruption；默认 KEEP。

### Flow G — 文档编辑

open document → directory/revision/content/draft loads → local editor history/text/title → debounced draft save → manual commit → new immutable revision → chapter directory/offset recalculation → authoritative reload。

- save 后读取用于获得 revision number、trigger/default timestamp 与权威 directory，不按“刚写又读”机械删除。

### Flow H — 素材/人物 Preview → Apply

source text/file/selection → extraction endpoint → `AnchorExtractionService.preview_*` → model structured output → token/candidate editable preview → `apply_*` → token single-use validation → transaction → formal rows/files → response。

- Preview 不写正式资源；Apply 的 token、candidate normalization、transaction 与 retry 是独立 failure modes，由 `test_preview_apply_contract_v23.py` 覆盖，KEEP。

## 4. Hash / integrity map

| hash | 输入 / producer | 保存/consumer | 边界与语义 | 结论 / 删除 failure mode |
| --- | --- | --- | --- | --- |
| canonical `hash_text` | UTF-8 text；chapter/scene/version services | source/content hash、parent/source comparison | persisted identity、provenance、stale source | KEEP；删除会允许错误 parent/base version |
| rewrite `map_hash` | version content hash + ordered semantic segments | plot/prose runs、context、restore validation | persisted semantic-map provenance | KEEP；删除会把 map 应用到错误文本版本 |
| document content hash | imported/edited bytes | document/revision rows、dedupe、filename、migration copy verify | file identity、dedupe、post-copy corruption | KEEP；删除会丢失重复识别或文件损坏检测 |
| cover digest | image bytes | content-addressed cover filename | file identity/cache busting | KEEP |
| backend asset signature | path/size/mtime/file bytes | Electron asset response ETag-like signature | file cache invalidation | KEEP |
| model DB fingerprint | resolved DB identity | secret namespace | credentials isolation | KEEP |
| migration v36 direct SHA-256 | legacy source/rewritten text | newly seeded rewrite versions | one-time persisted provenance | KEEP；可未来统一 helper，但 migration 隔离优先 |
| API token `compare_digest` | supplied/current token | request authorization | timing-safe secret boundary | KEEP |

同一 payload 的重复 hash 主要出现在 file copy 前后与 persisted version read-back，均跨文件/数据库边界。没有满足“纯内存、无 persistence/concurrency/cache/identity、结果无消费者”的仪式性 hash。

## 5. Candidate table

| ID | 文件/对象 | 类型/边界 | evidence 与 deletion test | 风险 | 初始结论 |
| --- | --- | --- | --- | --- | --- |
| RED-001 | `schema.py` v52 final column validation | duplicate validation；同 transaction/DB state | 原始 5/5；暂删第二次 column call 后 5/5，损坏列仍在 ensure 处失败且不推进 v52 | HIGH | REMOVE column repeat；KEEP index validation |
| RED-002 | `anchor_extraction_service._priority` | dead private helper | 全 161 代码文件与 tests 仅定义 1 次，无动态注册 | LOW | REMOVE |
| RED-003 | `ui.components.create_empty_state` | dead internal UI helper | 全仓仅定义，无 import/caller | LOW | REMOVE |
| RED-004 | `client.ts` style/project-style wrappers | old frontend wrapper | 12 exports在 src + E2E 中均仅定义；backend endpoints 保持 | LOW | REMOVE wrappers；KEEP backend API |
| RED-005 | `client.ts` unused document tag/draft wrappers | old frontend wrapper | rename/delete tag、get chapters、discard draft、direct save content 无消费者 | LOW | REMOVE |
| RED-006 | `client.ts` unused creative/project getters | old frontend wrapper | singular workflow/scene getter与 project-chapter wrapper 无消费者；plural/current replacements在用 | LOW | REMOVE |
| RED-007 | `client.ts` unused prompt CRUD/extract wrappers | old frontend wrapper | create/update/delete old prompt与 analysis prompt、import/extract 无 UI/E2E consumer；read/export legacy UI仍用 | LOW | REMOVE only unconsumed exports |
| RED-008 | `client.ts` unused style imports after RED-004 | duplicate import surface | types only support removed wrappers | LOW | REMOVE |
| RED-009 | `workflowClient.ts` singular version/create branch wrappers | old frontend wrapper | 2 exports仅定义；list/restore/delete/start flows仍用 | LOW | REMOVE |
| RED-010 | `shared_analysis_service` five exported facade classes | wrapper/legacy | repo consumers只有 `SkeletonExtractionService`；其余仅 `services.__init__` export | MEDIUM | KEEP API this round / FUTURE CLEANUP |
| RED-011 | `PromptPackageExtractionService` | explicit pre-v7 compatibility wrapper | 无 repo consumer，但公开 export 且 docstring 明示 compatibility | MEDIUM | KEEP LEGACY |
| RED-012 | tag normalization helpers in schema/anchor/material | duplicate helper | 同实现，但分别处于 migration 与两个 domain service；合并会新增跨层 dependency | LOW | KEEP；抽象收益为负 |
| RED-013 | service constructors repeatedly call `initialize_database` | repeated DB/schema access | nested orchestrators构造 4–8 services，每个幂等 initialize | HIGH | REVIEW ownership/perf，不在本轮改 |
| RED-014 | scene rewrite materials loaded in validation and context assembly | duplicate DB load | generate/execute 先验证 material，后续 `_call_stage`/context可再读 | MEDIUM | MERGE candidate；需并发/authoritative-state deletion test |
| RED-015 | Creative stage methods repeated `get_scene` | validation | 每个 public method 是独立 API entry；DB→domain trust boundary | MEDIUM | KEEP DEFENSIVE |
| RED-016 | API one-line endpoint/output wrappers | wrapper | HTTP route、auth、response model/error translation 是独立 contract | LOW | KEEP boundary |
| RED-017 | structured skeleton → legacy nodes | serialization/legacy | DB 同时维护新结构与旧 nodes；旧 rows/tests/restore仍消费 | HIGH | KEEP LEGACY |
| RED-018 | document save→reload | repeated DB read | revision IDs/timestamps/directory/offset来自 authoritative DB | HIGH | KEEP DEFENSIVE |
| RED-019 | document migration hashes source+temporary | repeated hash | 跨 filesystem copy boundary，检测 partial/corrupt copy | HIGH | KEEP DEFENSIVE |
| RED-020 | `CreativeWorkspacePage.viewStage` | derived-state suspicion | 用户可回看已解锁早期阶段；不等同 authoritative reached stage | MEDIUM | KEEP UI EPHEMERAL |
| RED-021 | document editor text/title/save status | server mirror suspicion | local uncommitted draft、undo/redo、autosave/error状态 | HIGH | KEEP |
| RED-022 | ProjectWorkspace legacy page | legacy UI | `legacy_extract` 路由、export与派生工程 E2E仍到达 | MEDIUM | KEEP LEGACY |
| RED-023 | material `legacy_extra`/source metadata fallback | legacy data | v14/v22 migrations与旧项目仍可能存在；新 UI不生成不代表旧 DB消失 | HIGH | KEEP LEGACY |
| RED-024 | prompt legacy package normalization | legacy serialization | import contract与历史 JSON字段仍由 API消费 | MEDIUM | KEEP LEGACY |
| RED-025 | `WorkflowAI` vs `StructuredModelService` model lookup | duplicate responsibility | 两套调用入口均有真实 callers；尚无单请求双重 lookup 证据 | MEDIUM | REVIEW |

## 6. Removed / merged

初版报告提交 `7889af2` 时生产代码未修改。之后只实施了以下有完整证据的删除：

| 项目 | 实际删除 | 为什么安全 | 验证 |
| --- | ---: | --- | --- |
| RED-001 v52 重复 column validation | 1 LOC / 1 schema check | 同 transaction/connection；两次之间只有建 index 与补行，不能改变 columns；第一次仍拒绝损坏布局，最终 index check仍在 | deletion experiment 5/5；最终专项 5/5；全量 281 + 21 subtests |
| RED-002 `_priority` | 8 LOC / 1 function | 全仓静态引用仅定义，无注册/反射路径 | 全量 Python；hash/consumer scan |
| RED-003 `create_empty_state` | 17 LOC / 1 function | 全仓无 import/caller，Qt 页面不消费 | 全量 Python；静态引用 scan |
| RED-004/008 style/project-style frontend wrappers/imports | 55 LOC / 11 wrappers + 5 imports | src、TSX、全部 E2E均零消费者；backend routes与types保留 | build；最终 bundle hash与 baseline 相同；47/8/5/1 E2E |
| RED-009 workflow client wrappers | 12 LOC / 2 wrappers + 1 import | singular get/create exports零消费者；使用中的 list/restore/delete flows未动 | build、相同 bundle hash、全部 E2E |

合计删除 **93 LOC、15 个函数、1 次重复 schema check、6 个随 wrapper 失效的 type imports**。没有为了合并而创建新 abstraction；本轮 **MERGE = 0**。RED-005～007 虽为静态零消费者候选，但为了让单个提交保持高度聚焦，留作下一轮独立 frontend surface cleanup，不夸大为已完成成果。

## 7. Kept defensive code

| 区域 | failure mode | 信任边界 | 证明 |
| --- | --- | --- | --- |
| rewrite content/map hashes | stale/corrupt map恢复到错误版本 | DB/external AI/history→domain | semantic map、snapshot provenance、version-aware workflow tests |
| Preview/Apply token + transaction | replay、partial apply、失败后候选丢失 | editable preview→formal DB/files | preview/apply contract + E2E retry |
| Creative dirty refs/flush queue | 快速 scene/chapter 导航错写草稿 | UI async state→API commit | workflow-refactor E2E dirty switch/popstate |
| document draft/revision/offset | draft覆盖新 revision、章节 offset 错位 | local edit→immutable revision | document service/API/E2E |
| DB migration ledger/transaction | 半迁移却推进版本 | old DB→current schema | schema + v52 repair tests |
| API Pydantic/token/error handlers | 非法 wire input 或未授权写入 | HTTP→service | API contract tests |
| AI structured validators | 非 JSON/缺字段进入 persistence | external model→domain | extraction/creative/model tests |
| file hash/copy checks | 截断或同名文件覆盖 | filesystem→library DB | document library tests |

## 8. Legacy status

- **KEEP LEGACY**：`legacy_extract` project UI/export/create-derived path；production E2E 与 real E2E覆盖。
- **KEEP LEGACY**：structured skeleton 的 legacy node projection、material `legacy_extra`、project material source metadata、prompt/style import normalization；旧 DB/JSON仍可包含。
- **KEEP LEGACY**：backend `/api/styles`、旧 prompt/style/analysis endpoints；本轮只移除无消费者的 desktop wrappers，不改变 HTTP contract。
- **FUTURE CLEANUP**：`PromptPackageExtractionService` 与 shared analysis facades；须先决定 Python package public API 的弃用政策。
- **SAFE TO RETIRE（frontend only）**：候选 RED-004～009 的零消费者 exports；不会删除 backend route、Pydantic schema或 persisted fields。

## 9. Human review priority

| Priority | 文件/函数 | 为什么值得人工看 | 当前结论 | deletion test | 风险 |
| --- | --- | --- | --- | --- | --- |
| P0 | `schema.py initialize_database` + all service constructors | nested service构造重复 schema/seed，所有权分散 | KEEP pending design | 否 | migration/启动正确性 |
| P0 | `rewrite_version_map_service.map_hash/validate_map_hash` | provenance核心且多处 producer/consumer | KEEP | 否 | 版本错配/恢复损坏 |
| P0 | `chapter_version_service.append/resolve` | source hash与 immutable version authority | KEEP | 否 | 历史不可逆错误 |
| P0 | `document_library_service` commit/draft/offset methods | file+DB双写、revision与offset | KEEP | 否 | 数据丢失 |
| P0 | Creative autosave/scene switch refs | 近期修复的 race/no-op save | KEEP | E2E existing | 错 scene 写入 |
| P0 | Preview/Apply apply methods | token与文件/DB atomicity | KEEP | existing failure tests | replay/partial data |
| P1 | v52 final validator | column重复已证明；index必须保留 | REMOVE one call | 是，5/5 | migration |
| P1 | scene orchestrator material reads | validation与context可能重复 load | MERGE candidate | 否 | concurrent material edit |
| P1 | WorkflowAI/StructuredModelService | model/prompt职责重叠 | REVIEW | 否 | prompt语义改变 |
| P1 | shared analysis facades | 多个零 repo consumer公开 wrapper | FUTURE CLEANUP | 静态 only | public API |
| P1 | prompt legacy normalization | fallback可能掩盖坏数据，但仍需 import兼容 | KEEP LEGACY | 否 | 历史导入 |
| P1 | material legacy source summary | 多层 fallback，旧 DB仍可能包含 | KEEP LEGACY | 否 | 历史项目 |
| P1 | `ContextService._resolve_generation_anchor` | 多 service/read/hash集中 | KEEP/REVIEW | 否 | anchor/offset |
| P1 | plot commit transaction | AI result→branch/version multi-write | KEEP | existing tests | partial commit |
| P1 | document library path migration | hash、temp copy、path map update | KEEP | existing tests | 文件丢失 |
| P2 | `api.py` 300 route/helper functions | 大但大多是明确 HTTP boundary | KEEP boundary | N/A | 可维护性 |
| P2 | 12 zero-consumer style wrappers | 安全的 frontend surface reduction | REMOVE | build/E2E pending | 低 |
| P2 | 其他 zero-consumer client wrappers | 分批删除避免误删动态调用 | REMOVE | build/E2E pending | 低 |
| P2 | duplicate tag normalize helpers | 重复但共享抽象收益低 | KEEP | N/A | 低 |
| P2 | `DocumentLibraryPage` 单文件多组件 | 复杂但拆文件不减少概念 | KEEP this round | N/A | 可维护性 |

## 10. Before / After

| 指标 | Before | After | 说明 |
| --- | ---: | ---: | --- |
| production LOC（Python + frontend TS/TSX） | 50,746 | 50,653 | -93；tests 0 LOC change |
| production Python LOC | 37,252 | 37,226 | -26 |
| frontend production TS/TSX LOC | 13,494 | 13,427 | -67 |
| production functions removed | 0 | 15 | 2 dead Python + 13 frontend wrappers |
| duplicate validation count（已证明项） | 1 | 0 | v52 second column check |
| audited core flows | 8 | 8 | 产品流程未删 |
| Flow A schema checks (v52 repair path) | column×2 + index×1 | column×1 + index×1 | 减少 1 个 function/check hop |
| other core-flow hops/DB reads/serialization/hash | baseline | unchanged | 无足够 deletion proof，不动 |
| key frontend useState | 224 | 224 | 没有把 form/autosave state误删成 derived state |
| Python regression | 281 + 21 subtests | 281 + 21 subtests | final 121.10s |
| build | pass | pass | JS/CSS asset hashes相同 |
| mock / real / Electron / production E2E | 47 / 8 / 5 / 1 | 47 / 8 / 5 / 1 | 全绿 |

最终候选总数 **25**；实际 REMOVE **5 组（16 个可执行项：15 functions + 1 check）**；MERGE **0**；明确 KEEP defensive **8 组**；LEGACY/FUTURE **5 组**；HUMAN REVIEW **20 项**。未实施项保留在 candidate 与 priority 表中，不能把“发现”写成“已清理”。

## 11. Final commits and conclusion

| SHA | 内容 |
| --- | --- |
| `7889af2` | `audit: map code necessity and redundancy`；仅初版报告 |
| `c286542` | `refactor: remove proven low-risk redundancy`；92 LOC dead code/zero-consumer wrapper |
| `bd5c259` | `refactor: remove duplicate workflow schema guard`；1 LOC，完整 deletion proof |

核心结论：Rusty 的大部分 hash、migration、revision、offset、Preview/Apply 与 autosave 防御都跨越真实的不可信、持久化、并发或历史边界，不能因“看起来重复”删除。可证明的无效复杂度集中在零消费者 frontend surface、两个真实 dead helper，以及 v52 同一事务同一 DB state 内的第二次列布局验证。

**这次减少的是经过证明的无效复杂度，而不是为了追求代码短而降低 Rusty 的数据一致性和版本可靠性。**
