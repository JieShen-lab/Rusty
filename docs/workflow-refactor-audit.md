# 工程类型与小说工作流重构审计

> **HISTORICAL:** 这是 PR #8 实施期间的仓库审计记录。当前代码归属与不变量请以 `docs/architecture.md` 和 `docs/current-implementation.md` 为准。

审计日期：2026-07-29

## 1. 基线与仓库状态

- 当前数据库版本为 `23`，以 `src/rusty/db/schema.py` 的
  `CURRENT_SCHEMA_VERSION` 为准。迁移由 `schema_migrations` 记录，
  `initialize_database()` 按版本顺序执行 `MIGRATIONS`。
- 后端测试使用 pytest；仓库没有独立的 pytest 配置，README 中的裸
  `python -m pytest -q` 会误收集仓库根目录遗留的临时目录，可靠命令应显式指定
  `tests/`。
- `desktop/package.json` 没有前端单元测试命令。生产构建
  `npm run build` 同时执行 React TypeScript 检查、Vite 构建和 Electron
  TypeScript 构建。现有端到端框架为 Playwright，命令为
  `npm run test:e2e`。
- 工作树在本任务开始前已有用户改动：
  `desktop/e2e/phase2.spec.ts`、`CharacterLibraryPage.tsx`、
  `MaterialLibraryPage.tsx`、`PromptManagePage.tsx` 和
  `desktop/src/styles/index.css`。重构必须保留这些改动。

阶段 0 基线：

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `python -m pytest tests -q -o cache_dir=D:\Code\Rusty\tmp\pytest-stage0-cache` | 159 passed | 使用工作区内 `RUSTY_DATABASE_PATH`、`TEMP` 和 `TMP`；Windows 沙箱阻止测试临时目录访问，需在允许创建/清理临时目录的执行环境运行 |
| `npm run build` | passed | TypeScript、Vite 生产构建和 Electron TypeScript 构建均通过 |
| `npm run test:e2e` | 27 passed | Chromium，单 worker |

## 2. 当前工程类型行为

- `projects` 表没有工程类型字段。工程用途被错误地保存在
  `project_settings.processing_mode`。
- `backend/schemas.py::CreateProjectRequest.purpose` 接受
  `rewrite`、`extract` 和历史别名 `summary`。
- `backend/api.py` 将 `summary` 改写成 `extract` 后写入
  `processing_mode`；运行项目时又依据 `processing_mode == "summary"`
  选择 `run_summary_project()`，存在新旧术语并存。
- `ProjectService.create_project()` 直接将 `processing_mode` 写入
  `project_settings`。项目列表和 `ProjectSummary` 不返回独立工程类型。
- `ProjectService.refresh_project_progress()` 仍以
  `processing_mode == "summary"` 判断项目用途。
- `NewProjectPage.tsx` 显示“改写工程 / 提取工程”，并发送
  `purpose: rewrite | extract`。
- `ProjectWorkspacePage.tsx` 通过
  `project.settings.processing_mode === "extract"` 推断工作区类型，并维护两套页面阶段。

目标行为：

- `projects.project_kind` 是唯一权威来源，约束为
  `rewrite | branch | legacy_extract`。
- 新建 API 仅接受 `rewrite | branch`；旧提取项目只读兼容为
  `legacy_extract`。
- `processing_mode` 仅表示 `manual | semi_auto | automatic` 等执行方式，
  不再参与工程用途判断。

## 3. 当前分析与生成行为

- `PipelineService.run_summary_project()` 是旧分析工程的主入口，但其内部的章节摘要、
  场景识别和分析能力可复用。
- 旧分析结果分散在 `chapter_summaries.plot_summary`、
  `chapter_style_analyses`、`project_style_syntheses` 和
  `chapter_scene_analysis`。
- v15 已加入可复用的长篇工作流基础设施：
  `scenes`、`scene_paragraphs`、`scene_fact_ledgers`、
  `character_story_states`、`story_skeletons`、
  `story_skeleton_versions`、`rewrite_plans`、检索与提示词编译快照、
  `scene_generation_stages`、`scene_rewrite_versions`、
  `targeted_repairs` 和一致性问题表。
- 原始场景和章节已有不可变保护与独立改写版本，适合作为分支基线安全机制的基础。
- `StorySkeletonService`/`RewriteWorkflowService` 已支持 AI 骨架提取、版本新增、
  确认以及计划确认，但骨架版本核心仍是 `nodes_json`，尚未覆盖完整的模块化细纲字段。
- `SceneRewriteOrchestrator` 仅支持 `skeleton_rewrite | expansion`，并要求
  `scene_id`；`expansion` 当前表示原场景内插入剧情，不是正式分支工程。
- `ContextService` 已实现必需/可选语义块、预算、滑动窗口、人物状态、事实账本、
  素材、风格和检索结果，可复用于两类工程；当前入口围绕“当前原文场景”组织，
  尚无独立的分支生成上下文。
- `PromptCompiler` 和模型调用审计可复用，AI 测试已有固定响应与 fake client，
  无需接入真实网络模型。

目标行为：

- 分析拆为工程类型无关的文档、场景、细纲、风格、人物和事实账本服务。
- `story_skeletons`/`story_skeleton_versions` 继续作为唯一细纲版本体系，并扩充为
  可校验的模块化细纲；旧 `plot_summary` 只做兼容展示，不伪造结构化节点。
- `plot_generation` 统一服务 `bounded_insert`、`open_continuation`、`fork` 和
  `fork_and_rejoin`。
- `prose_rewrite` 正式接管现有 `skeleton_rewrite` 能力。
- `canon_change` 使用结构化影响扫描与可审查补丁，不做全局替换。

## 4. 需要修改的模块

- 数据与模型：`src/rusty/db/schema.py`、`src/rusty/models.py`、
  `backend/schemas.py`。
- 工程创建、列表、详情和兼容复制：`project_service.py`、`backend/api.py`。
- 公共分析：`pipeline_service.py` 及新增/拆分的分析服务适配层。
- 模块化细纲与版本：`scene_service.py`、`rewrite_workflow_service.py`。
- 生成与上下文：`scene_rewrite_orchestrator.py`、`context_service.py`、
  `prompt_compiler.py`。
- 前端协议：`desktop/src/api/types.ts`、`desktop/src/api/client.ts`。
- 前端入口和工作区：`NewProjectPage.tsx`、`ProjectWorkspacePage.tsx`；
  大型工作区应拆出分支树、细纲编辑器、接缝审查和设定补丁组件。
- 测试：数据库迁移、工程服务/API、共享分析、分支领域模型、三类编排器、
  前端 Playwright 和最终端到端路径。

## 5. 可直接复用的能力

- SQLite 顺序迁移和幂等初始化机制。
- 原文快照、场景边界、不可变原文保护和场景改写版本。
- `story_skeletons` 与 `story_skeleton_versions` 的版本生命周期。
- 场景事实账本、人物动态状态、提示词编译块、检索、风格上下文、
  模型调用审计、生成阶段、一致性检查和定向修复。
- 章节/场景分析、人物与风格提取、全书归纳、人工确认、导出。
- 素材类型隔离规则：只有剧情骨架素材可引入新关键事件，场景/风格参考只指导表达。

## 6. 需要废弃但暂时兼容的能力

- 新建 `extract`/`summary` 工程的 API 和 UI：新流程启用后停止创建。
- `run_summary_project()` 作为独立工程主流程：保留兼容读取所需代码，并把有价值步骤
  委托给公共分析服务。
- `processing_mode` 的工程用途语义：迁移后仅保留执行方式语义和旧数据原值。
- `skeleton_rewrite` 与 `expansion` 旧协议：短期解析为
  `prose_rewrite` 与 `bounded_insert`，内部业务改用新术语。
- `chapter_plot_expansions` 和 `chapter_summaries.plot_summary`：不删除；
  只作为旧数据读取和迁移适配来源。
- 旧提取工程的分析结果、导出和查看能力：必须保留；旧主流程运行按钮必须停用。

## 7. 风险与实施顺序

- v23 的 `SCHEMA_SQL` 会先创建最新结构再补跑迁移；新增 v24 时必须同时验证全新库和
  手工构造的 v23 库，避免“新建结构已有列、迁移再次添加”的冲突。
- `processing_mode` 同时承载 `rewrite/extract/summary/manual/auto` 历史值，迁移只能据
  旧用途映射 `project_kind`，不得覆盖原字段。
- 现有场景外键大多级联删除，正式分支内容不能挂在会导致删除原文的方向上；
  分支删除测试必须覆盖原始章节、场景和分析数据。
- 旧 UI 的 `extract` 字样还大量用于“从文本提取人物/风格/素材”等公共能力；
  术语清理只能删除“提取工程”含义，不能误删这些分析 API。

## 8. PR #8 修正前基线（2026-07-29）

已完成：

- 工程类型和旧项目兼容迁移
- 结构化细纲基础模型
- 分支、锚点、接缝和运行记录基础模型
- 三类工作流的持久化与校验原型
- 分支基础 CRUD 与部分 UI

尚未完成：

- 真实 AI 规划和生成
- 通用语义设定传播
- 接缝实际应用
- 分支章节模型
- 事实账本同步
- Electron 分步闭环
- 真实后端 E2E

复核发现当前新工作流 HTTP API 仍接收无约束字典；锚点只校验字段存在而未完整校验项目
归属；分支正文缺少章节层；剧情、表达重写和设定变更服务依赖调用者提供生成结果或固定
短语规则；Electron 的细纲、接缝和补丁内容仍是组件内样板状态。后续阶段必须在现有
v24–v29 和基础表之上迭代，不能把这些原型描述为完整闭环。

## 9. 后续修正完成状态（2026-07-30）

在上述基线上完成：

- 新工作流 HTTP API 全部改用拒绝未知字段的正式 Pydantic 模型。
- 锚点验证资源与项目、父分支和版本归属。
- v30–v33 增加分支章节、真实 AI 运行阶段、正式接缝和语义补丁元数据。
- 剧情生成、表达重写和设定传播均由后端调用 AI，前端不再提交生成结果。
- 接缝参与实际文本合成；设定补丁通过单事务原子应用并同步事实账本。
- 旧分析工程具备专用导出和独立派生工程 API。
- Electron 三类操作读取真实运行记录并形成逐步确认闭环。
- 八条浏览器路径使用真实 FastAPI、临时 SQLite 和 FakeLLM 验证。

仍保留的兼容层包括旧 `plot_summary`、旧场景 `expansion` 解析、旧项目读取和分析导出；
这些兼容入口不会创建新的 `legacy_extract` 工程，也不会使用 `processing_mode`
判断工程用途。

## 10. 最终阻断项修正（2026-08-04）

- `bounded_insert` 默认使用 `insert_between`，只在实际插入点加入进入接缝、新剧情和回接
  接缝；只有用户显式选择 `replace_range` 才删除选定范围，原始章节始终不变。
- 统一锚点选择器读取真实章节、场景、细纲节点和父分支章节/场景；子分支上下文从所选
  父分支版本继承正文、`facts_after` 和生成历史，不回退到原文章节末尾。
- v34 保存范围操作；v35 为每条接缝保存独立的来源锚点和版本。服务端按 `seam_id`
  重新解析当前来源并校验哈希，前端不提交权威源正文。
- 模块化细纲的事件、因果、人物/地点/时间/物品/知识/关系变化、伏笔、线索、起止状态、
  编辑点均可通过表单修订，并以新版本保存和确认；来源引用保持只读。
- 测试分为三层：Mock 浏览器 UI、React 浏览器 UI + FastAPI + 临时 SQLite + FakeLLM、
  实际 Electron 主进程 + preload + FastAPI + 临时 SQLite + FakeLLM。浏览器真实后端测试
  仍承担八条完整业务路径，Electron 测试承担桌面启动、原生桥接和最小工作流闭环。

边界校验同时覆盖文本偏移、锚点先后顺序、服务端生成/验证 `source_hash`、活动运行期间
禁止删除分支、软删除后隐藏分支内容且不影响原文。数据库当前版本为 v35。

## 合并前最终数据语义收口（v40）

- rewrite version 的 Scene / skeleton-node anchor 已改由可查询的 version-local semantic map 解析，不再依赖原文字符串匹配或 original source span。
- segment 同时保存局部前后状态；章节 facts 保持章节边界语义，Plot 插入状态单独保存在 generated-event segment。
- Prose observed skeleton、Plot target structure 与 Canon 继承结构均关联到结果 rewrite version；运行冻结 resolved anchor 与 semantic-map hash。
- v40 对 legacy migration 空 facts 做保守回填，并以 `needs_recompute` 表达无法证明的起始状态。
- rewrite versions 与 semantic segments 已有数据库不可变触发器；manual clear 追加 restore version。
- Canon patch 仅可在 reviewing / ready_to_apply 阶段修改，applied 与 cancelled 均为不可审查终态。
- 浏览器真实后端测试覆盖 Plot → Prose → Plot(scene anchor) → Canon；Electron 测试覆盖当前 Prose version 的 scene-anchor 预览与生成。
