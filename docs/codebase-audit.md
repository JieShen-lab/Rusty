# Rusty 代码库审计与 Cleanup 清单

## 审计基线

- 基线：`main@3ed2034bdddaf8a0185d6de1308f80cf30390b02`（PR #8 merge commit）。
- 数据库：`DB_VERSION = 40`。本次 cleanup 不修改版本号，也不改写 v1-v40 迁移。
- 合并后基线：后端 `271 passed, 25 subtests passed`；前端生产构建通过；Mock UI E2E `34 passed`。
- 方法：跟踪文件清单、文件行数、Python import 关系、`rg` 引用搜索、TypeScript 构建、现有测试与 CI 配置。

## 模块清单与职责

| 区域 | 跟踪文件数 | 当前职责 | 审计结论 |
| --- | ---: | --- | --- |
| `backend/` | 4 | FastAPI 应用、HTTP schema、服务装配 | `api.py` 含 238 条路由，`schemas.py` 同时覆盖文档库、工程、工作流和资源库；需要按稳定领域有限拆分 |
| `src/rusty/services/` | 34 | 领域服务、AI 编排、版本与兼容逻辑 | 服务职责基本可辨，但平铺、低层 helper 反向依赖 `ProjectService`，状态与锚点常量重复 |
| `src/rusty/db/` | 3 | SQLite connection、schema 与 v1-v40 migration runner | 历史迁移是兼容资产，全部保留；`schema.py` 大但按版本顺序组织，不在 cleanup 中机械拆分 |
| `src/rusty/importers/` | 4 | TXT、DOCX、EPUB 输入解析 | 边界清晰，保留 |
| `desktop/src/` | 32 | React/Electron UI、页面与 API client | 工作流面板和 API/type 单文件过大；适合按领域拆分并保留兼容 barrel export |
| `desktop/src/components/` | 14 | 通用组件与工作流编辑器 | `WorkflowRefactorPanels.tsx` 同时拥有多条独立状态流，职责过载 |
| `desktop/src/pages/` | 8 | 应用页面 | 文档、素材、角色页面均较大，但本轮只处理与 workflow cleanup 直接相关的热点 |
| `desktop/src/api/` | 2 | 全部 HTTP client 与前端 API 类型 | `client.ts`/`types.ts` 已成为聚合文件；工作流部分可独立成模块，避免一次迁移全部 API |
| `desktop/e2e/` | 4 | Mock UI E2E 与真实后端启动器 | 与 `e2e-real/`、`e2e-electron/` 边界不同，必须分别保留 |
| `tests/` | 34 | service、API、migration、UI invariant 测试 | 文件名已基本按领域表达，不为目录美观进行大规模移动 |
| `docs/` | 12 | 当前实现、重构审计、历史实施报告与视觉证据 | 当前文档与历史报告混放，需要建立当前架构入口并给历史报告明确归档标记 |

### 核心 service ownership

- `ProjectService`：工程、章节、导入导出、legacy analysis 派生，以及 rewrite current projection 的兼容入口。
- `ChapterVersionService`：不可变 chapter rewrite version、current head/projection、source snapshot 和 restore。
- `RewriteVersionMapService`：rewrite-version-local semantic map、结构来源、锚点和局部状态解析。
- `ContextService`：场景改写与 Plot/Prose 工作流上下文、预算和素材/人物/风格组装；职责仍偏宽。
- `PlotGenerationOrchestrator`：Plot 九态生命周期、增量生成、接缝、CAS 与正式提交。
- `ProseRewriteOrchestrator`：Prose 计划、生成、结构漂移检查和 version 提交。
- `CanonChangeOrchestrator`：影响扫描、patch review、原子 apply 和事实传播。
- `BranchService`：branch 血缘、anchor/seam persistence、branch chapter/scene version snapshot。
- `SharedAnalysisService` 及其 facade：章节、场景、细纲、风格、人物与事实分析的共享入口。
- `PipelineService` / `SceneRewriteOrchestrator`：PR #8 前已存在、目前仍由 API/UI/测试调用的章节和场景兼容工作流；不是 dead code。

## 依赖清单

期望方向：

```text
React/Electron UI
  -> desktop API client
  -> FastAPI transport
  -> services/orchestrators
  -> version/branch/content services
  -> SQLite
```

实际发现：

1. `default_database_path()` 定义在 `ProjectService`，导致几乎所有 service 为取得路径而 import `project_service`。
2. 当前存在结构循环：`ProjectService -> ChapterVersionService -> RewriteVersionMapService -> ProjectService`。`ChapterVersionService` 通过函数内 import 暂时规避模块加载循环。
3. `ModelService -> AIClient -> ModelService` 也通过函数内 import 规避；该循环包含真实构造职责，本轮先记录，不贸然引入 DI 框架。
4. `ContextService` 直接依赖 anchor、branch、chapter version、rewrite map、scene、material、prompt 和 style 八类服务，是剩余最大的 service dependency hotspot。
5. FastAPI 领域逻辑主要已在 service 中，但 238 条 closure route 共享大量局部 service 实例，使 router 拆分需要显式依赖容器，不能简单剪贴。

优先处理：把数据库默认路径移动到明确的低层 `rusty.db.paths`；把真正共享的 workflow status/anchor vocabulary 移到单一领域模块。暂不增加 repository、event bus 或 DI 框架。

## 大文件与职责热点

按跟踪源码统计，主要热点包括：

- `src/rusty/db/schema.py`：约 4k 行。原因是不可改写的 v1-v40 migration 历史；KEEP。
- `backend/api.py`：约 3k 行、238 条路由。按 workflow/version 等稳定领域拆 router 是高价值项。
- `backend/schemas.py`：约 1.7k 行。schema 与 route 同步按领域拆分，保留 `backend.schemas` 导入兼容面。
- `src/rusty/services/branch_service.py`：约 1.6k 行。拥有同一份 branch persistence transaction，机械拆分会隐藏事务边界；本轮只抽 vocabulary/小 primitive。
- `src/rusty/services/context_service.py`：约 1.3k 行且依赖面宽；记录为剩余高债务，不在本轮重写上下文策略。
- `desktop/src/api/client.ts`、`types.ts`：分别约 1.5k/1.4k 行；优先抽 workflow/version API。
- `desktop/src/components/WorkflowRefactorPanels.tsx`：约 650 行，包含 Rewrite、Branch、Legacy 及三条 run lifecycle；可按独立状态流拆分。
- `desktop/src/pages/DocumentLibraryPage.tsx`、`MaterialLibraryPage.tsx`、`CharacterLibraryPage.tsx`：均较大，但与本轮 workflow cleanup 无直接关系，避免扩大 diff。

## Dead code 与兼容分类

### DELETE（仍需在删除前逐项补充引用证据）

- 无引用的重复前端局部类型/状态集合；以 TypeScript build 和 `rg` 确认后删除。
- workflow 文件中语义完全一致的局部 hash/JSON object helper；改由具名 `hashing`/`serialization` primitive 替代后删除。
- 已完成方案的失效注释、无意义 debug 输出；CLI 明确需要的初始化/临时 token 输出不属于 debug。

### KEEP

- Plot、Prose、Canon、Branch 各自编排器；业务语义不同，不合并成 generic orchestrator。
- `current_original_scene`：仍属于旧 scene rewrite context 的必需 block；branch generation 已有独立 context，不可仅凭名称删除。
- `skeleton_rewrite` / 旧 `expansion` scene workflow：仍有 API、React UI、数据库表与回归测试可达。
- `chapter_rewrites`、`chapters.rewritten_text`：是 current projection/兼容 cache，权威写入继续由 `ChapterVersionService` 收口。
- 三类 E2E：Mock browser、real-backend browser、Electron 覆盖不同边界。

### COMPATIBILITY

- `legacy_extract` 只读、导出与派生路径。
- `processing_mode` 旧数据读取与执行方式字段；不得再作为工程用途权威。
- `chapter_plot_expansions`、旧 summary/plot summary、prompt package、document revision 等旧数据库读取。
- v1-v40 migration、旧 rewrite projection、旧 branch scene 数据回填。

### UNKNOWN（本轮不删除）

- PySide `src/rusty/ui/` 与 Electron 双 UI 的长期产品定位。
- 旧 pipeline/scene workflow 何时停止公开 API 支持。
- 部分 API client public method 是否供仓库外脚本使用；无公开弃用策略前不凭组件引用数删除。

## 重复 primitive 审计

- SHA-256 文本 hash 至少在 `ChapterVersionService`、`CanonChangeOrchestrator`、`BranchService`、`RewriteVersionMapService` 与 API 文件出现。只有 UTF-8 文本 hash 语义一致的调用可收口；文件/bytes fingerprint 保持独立。
- JSON object 容错解析在版本、map、API 输出组装中重复。仅合并“dict/JSON object/空值”语义完全一致的实现；严格 schema 校验不改为容错 helper。
- Plot active statuses 同时存在于 `PlotGenerationOrchestrator` 与 `BranchService`；anchor type 集合同时存在于 schema、branch/context 和前端。Python 侧应有单一 vocabulary，Pydantic/TypeScript 保留边界类型但不各自发明另一套业务集合。
- rewrite projection 写入需继续核验 Plot、Prose、Canon、manual、restore 是否全部通过 `ChapterVersionService.append_chapter_rewrite_version()`；任何旁路列为修复项。

## Cleanup 实施边界

拟按可独立验证的提交推进：

1. 本审计与基线清单。
2. 抽取数据库路径、workflow status/anchor vocabulary 和完全等价的小 primitive，消除明确循环依赖。
3. 有限拆分 FastAPI workflow/version routes 与 schemas；保留 `create_app()` 的服务装配和 transport 行为。
4. 拆分 React workflow panels、复用 persisted-run hook，并拆出 workflow/version API；不改 UI 行为。
5. 核验并收口 rewrite/branch persistence 写入旁路，删除有证据的 dead compatibility code。
6. 整理测试 fixture/E2E helper（仅在确有同层重复时）和架构/历史文档。

每个提交先运行定向测试；最终保持测试数量不下降，并运行后端、构建、三类 E2E 与 `git diff --check`。

## 已实施的 Cleanup

- 默认数据库路径移动到 `rusty.db.paths`，服务不再为了路径 helper 反向依赖 `ProjectService`；旧导入继续 re-export。
- Plot 状态、generation mode 和 Story Anchor 集合收口到 `rusty.domain` 的具名模块。
- UTF-8 正文 hash 与 legacy-tolerant JSON object 解码收口到单一职责模块。
- Branch/Plot/Prose/Canon/rewrite-version HTTP 路由移动到 `backend.routes.workflows`；对应 Pydantic 模型移动到 `backend.workflow_schemas`。
- workflow browser client、persisted-run hook 和独立共享 UI 从聚合文件拆出。
- legacy pipeline 的正式 rewrite 不再旁路写 projection，而是通过 `ChapterVersionService` 产生不可变版本。
- 当前架构、所有权、写入不变量与历史文档分类已建立明确入口。

本轮没有删除 migration、legacy API、旧 pipeline/scene workflow、PySide UI 或公开 API client method，因为它们仍有运行路径或缺少正式弃用证据。

## 剩余复杂度热点

### High

- `ContextService` 同时负责检索、上下文语义、预算和多工作流 source resolution；需要未来在不改变 prompt 的专门重构中处理。
- `backend/api.py` 的非 workflow 领域（文档、素材、角色）仍有大量 route，后续应按独立业务边界分批迁移。
- `schema.py` 体积大，但它是 migration audit trail；可导航性与历史不可变性存在合理张力。

### Medium

- `BranchService` 同时拥有 topology、anchor/seam 与 chapter snapshot persistence；事务边界清楚，后续只能按事务所有权谨慎拆分。
- PySide 与 Electron 两套 UI 同时存在，公共产品边界尚未正式说明。
- 事实 ledger JSON schema 仍较动态；本轮禁止重新定义 facts 业务语义。

### Low

- 历史实施报告与当前文档尚未分层。
- 大型页面中的纯展示片段仍可逐步组件化，但当前测试边界完整，收益低于 workflow 热点。
