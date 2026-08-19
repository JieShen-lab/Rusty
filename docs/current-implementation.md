# Rusty 当前功能与代码实现说明

架构分层、数据权威与代码所有权见 [`architecture.md`](architecture.md)。

> 文档状态：对应当前仓库实现  
> 项目形态：本地小说整理、分析与 AI 辅助改写桌面应用

## 1. 项目概览

Rusty 以本地优先方式管理小说项目。当前主界面采用 Electron + React，Electron 负责桌面窗口、文件选择和后端进程生命周期；FastAPI 提供本地 HTTP API；Python 服务层负责导入、资料管理、AI 调用、改写流水线与导出；SQLite 保存项目数据和生成记录。

仓库仍保留早期 PySide6 桌面端，可用于原有导入、预览和导出流程。当前持续迭代的 Electron 界面位于 `desktop/`。

## 2. 已完成功能

### 2.1 项目与文档导入

- 支持导入 TXT、EPUB、DOCX。
- TXT 支持自动分章、简单标题规则和自定义正则规则，并可在创建项目之前预览分章结果。
- 保存书名、作者、语言、标识符、来源路径、文件指纹和工作目录等元数据。
- 支持项目软删除、项目列表、章节浏览、进度统计和项目级设置。
- 支持把章节加入导出计划，调整顺序、标题和是否导出。

主要实现：

- `src/rusty/importers/`
- `src/rusty/services/chapter_split_service.py`
- `src/rusty/services/project_service.py`
- `desktop/src/pages/NewProjectPage.tsx`
- `desktop/src/pages/ProjectWorkspacePage.tsx`

### 2.2 独立文档库

- 将 TXT、EPUB、DOCX 导入独立文档库，并统一保存为可处理的文本内容。
- 根据内容哈希复用重复文档。
- 分类和标签是独立的多对多实体；同一文档可以同时属于多个分类并绑定多个标签，分类与标签筛选取交集。
- 工程文档由 `project_documents` 关系判定，不依赖特殊标签；全部文档、最近导入和无标签视图只包含非工程文档。
- 工程文档复用文档库的编辑器、revision、文字整理和导出能力，但文档库 revision 不会自动回写项目章节、场景或 AI 结果。
- 支持元数据编辑、章节查看与排序。
- 正文工作区可直接编辑全文或章节，显式保存时创建新的 `manual_edit` revision，旧版本继续保留。
- 正文和章节标题在停止输入 1 秒后自动保存到与当前 revision 绑定的草稿；自动保存不创建 revision，标题栏“保存”才将草稿提交为新的 `manual_edit` revision。
- 章节编辑器将章节标题与正文分开呈现，提交时重建标题、分隔和正文，并平移后续章节的权威 offset。
- TXT 导入严格区分卷标题与章节标题；完全没有章节标题时建立单一“第一章”，卷不会计入章节数。
- 当前 revision 的目录由卷与章节组成：卷可折叠并显示本卷字数，章节继续加载同一正文编辑器；章节的 `volume_id` 可随目录拖动更新。
- 合并文档按所选顺序复制各源 revision 的权威卷/章节范围，不重新解析正文，不修改源文档，也不继承标签或分类。
- AI 与正则识别共用“分章”入口和边界应用服务，确认后分别生成 `split_ai`、`split_regex` revision，不修改旧版本章节记录。
- 支持按“我的分类”树选择并排序合并来源、新增章节、正则分章预览与应用。
- 支持处理模板、文字整理、修订版本和版本恢复。
- “引用范围”仍未实现持久化和下游消费，因此当前工作台不显示该入口。
- 支持迁移文档库存储目录。
- 支持将文档导出为 TXT 或 EPUB。

主要实现：

- `src/rusty/services/document_library_service.py`
- `desktop/src/pages/DocumentLibraryPage.tsx`
- `tests/test_document_library_service.py`
- `tests/test_document_library_api.py`

### 2.3 模型与密钥管理

- 管理 OpenAI 兼容模型的名称、接口地址、模型标识和默认模型。
- 支持连接测试，并区分连接成功、调用失败和密钥缺失。
- API 密钥不写入主 SQLite 数据库；数据库只保存密钥引用，密钥值交由操作系统 keyring 保存。
- 不同数据库使用隔离的密钥引用，避免测试库和正式库互相污染。

主要实现：

- `src/rusty/services/model_service.py`
- `src/rusty/services/ai_client.py`
- `src/rusty/secrets.py`
- `desktop/src/pages/ModelManagePage.tsx`

### 2.4 提示词与风格模板

- 新创作工作流使用三类简单提示词对象：总提示词 `master`、工作流任务提示词 `workflow_task`、公共任务提示词 `common_task`。
- 工程总提示词是工程当前实际使用的文本；从库中选择时复制内容，工程内修改不会与库条目同步，并可再导出为新的库条目。
- 新 AI 调用由 `PromptCompiler` 按“Rusty 内部规则 → 工程总提示词 → 当前任务提示词 → 动态上下文 → 本次要求 → 程序控制的输出契约”组装。JSON Schema 不依赖用户可编辑的 Prompt 正文。
- 新提示词模型不实现版本历史、继承、模板/工程同步或执行快照 UI。
- 旧提示词包继续服务仍可达的历史流水线，不是新创作工作流的核心依赖。

- 管理摘要、情节扩写和改写所需的结构化提示词。
- 支持项目级提示词覆盖，并在项目未绑定时回退到全局默认配置。
- 支持提示词包 JSON 导入、导出和旧格式兼容。
- 支持风格模板 CRUD、导入导出、项目绑定、AI 风格抽取和试写。
- 支持章节风格分析、人工复核和项目级风格综合。

主要实现：

- `src/rusty/services/prompt_service.py`
- `src/rusty/services/prompt_definition_service.py`
- `src/rusty/services/prompt_compiler.py`
- `src/rusty/services/prompt_package_extraction_service.py`
- `src/rusty/services/style_service.py`
- `src/rusty/services/style_extraction_service.py`
- `src/rusty/services/analysis_service.py`
- `desktop/src/pages/PromptManagePage.tsx`

### 2.5 作者风格素材与大纲

- v55 已彻底删除角色卡资产及其分类、标签、封面、提取设置、工程绑定、页面和当前 API。
- 素材库只保留 `author_style`；`plot_skeleton` rows、分类、筛选分支和 `plot_skeleton_extraction` 设置已删除。
- 作者风格继续保存稳定维度 ID、维度名称、提取要求、分析结果、具体特征、原文实例、完整 `raw_text`、来源元数据和素材版本；单维度 preview/apply 与设置 JSON 导入/导出继续可用。
- 大纲模板仍保留 CRUD、AI 抽取和项目绑定，它不是剧情骨架素材。
- Chapter Workflow 的 `source_outline` 与 `target_outline` 是单次运行的中间结果，不进入素材库。
- 人物仍可出现在章节总结、关系、状态和事实账本中；删除的是 Character Card 资产，而不是小说中的人物概念。

主要实现：

- `src/rusty/services/material_service.py`
- `src/rusty/services/anchor_service.py`
- `src/rusty/services/anchor_extraction_service.py`
- `desktop/src/pages/MaterialLibraryPage.tsx`

### 2.6 正文选区快捷保存

- 文档库正文编辑区支持将选中文字作为作者风格来源送入素材页。
- 角色卡与剧情骨架素材入口已删除。
- 入口通过一次性 history state 携带选区正文和文档/工程、revision、卷、章节、offset 及标题来源；用户可仅保存来源，或生成作者风格候选并确认后写库。
- 只保存规范化后的纯文本，前后端均限制单次选区不超过 50,000 字符。
- 来源信息单独保存为元数据，包括文档/工程、章节和字符 offset，不混入正文。
- 素材选区不会直接创建记录；“仅保存来源”才创建未分析素材，AI 候选在 apply 前也不会写库。

### 2.7 可追踪 AI 改写流水线

流水线按章节执行，当前包含：

1. 章节摘要；
2. 场景识别；
3. 可选情节扩写；
4. 基于目标骨架、提示词包、风格和大纲的改写；
5. 人工确认；
6. 按导出计划合并结果。

关键能力：

- 可运行整个项目，也可单独执行章节阶段。
- 可暂停项目、重试失败阶段，并记录阶段状态和错误。
- 改写支持锚点模式与兼容的整章模式。
- 锚点模式要求模型返回结构化结果，并校验锚点是否唯一、目标是否满足；格式错误时可生成修复请求。
- 每次模型调用保存提示词快照、响应、尝试次数、错误信息和用量信息，便于追踪与复现。
- 场景无需改写时保留原文。
- 合并导出时优先使用确认后的改写内容，否则使用原文。

主要实现：

- `src/rusty/services/pipeline_service.py`
- `src/rusty/services/prompt_compiler.py`
- `desktop/src/pages/WorkbenchPage.tsx`
- `tests/test_pipeline_service.py`
- `examples/xianxia/`

### 2.8 章节中心创作工作流

- v56 的 Creative Workflow 只以 `chapter_id` 为创作单元，不读取 scenes、不要求分场或 active scene。历史 scenes、branch、版本和事实表仍由其他模块使用。
- 阶段为“内容总结 → 方向选择与具体要求 → 专项分析 → 风格 → 写作 → 审查”，`confirmed` 只是完成状态。
- 当前策略只有 `plot_adjust`（调整剧情）、`expansion`（增加剧情）、`reimagine`（重新构思）；`faithful` 已从当前 schema、提示词、API 类型和 UI 删除。
- 内容总结读取当前 rewrite head；没有 rewrite 时读取 `original_text`，并保存 source hash。章节正文变化后，下游操作返回 conflict，不静默使用旧分析。
- 三种专项分析统一保存 `source_outline`、`target_outline`、`constraints`、`analysis_notes`。重新构思额外支持 `brief` / `detailed` 粒度并锁定起始条件、核心目的、结束状态和硬约束。
- 调整剧情先形成 preserve/modify/delete/insert 文本计划。preserve span 由程序原样复制，只有 modify/insert 调用模型。
- 增加剧情不修改当前章，而是在其后创建新 chapter；已有后续章节安全后移，不覆盖原下一章。
- 重新构思按锁定边界、目标大纲、用户要求和选定的作者风格快照整章生成。
- 调整剧情与增加剧情默认 `source_auto`：优先从完整 TXT source document 安全采样，无法读取则回退当前章。提取直接复用素材系统 `author_style_extraction` 设置，并把设置、风格档案和 guidance 保存为 workflow 快照，不自动创建素材。
- 重新构思必须选择已分析的 `author_style` material；保存素材 ID、版本和完整快照，之后素材编辑不会改变当前运行。
- 审查按策略保存结构化 issues；修复只替换 issue range，不整章重新生成。
- Phase C 最终 UI 尚未实施。当前 Electron 页面只进行类型/API 适配和基础阶段状态展示，不包含最终六阶段工作台、专项分析双栏和作者风格库视觉重构。

主要实现：

- `src/rusty/services/creative_workflow_service.py`
- `src/rusty/services/prompt_definition_service.py`
- `src/rusty/services/prompt_compiler.py`
- `desktop/src/pages/CreativeWorkspacePage.tsx`
- `desktop/src/pages/PromptManagePage.tsx`
- `tests/test_chapter_creative_workflow.py`
- `tests/test_chapter_workflow_schema.py`
- `tests/test_prompt_definitions.py`

### 2.9 导出

- 项目支持 TXT、EPUB 导出。
- 文档库支持层级 TXT、EPUB 导出：卷是 EPUB 一级 TOC，章节是卷下二级 TOC，无卷章节保持一级。
- 项目导出遵循保存的章节顺序、标题和排除项。
- 导出记录保存在数据库中。

主要实现：

- `src/rusty/exporters/`
- `src/rusty/services/project_service.py`
- `src/rusty/services/document_library_service.py`

## 3. 系统架构

```text
Electron 主进程
  ├─ 创建桌面窗口与系统文件对话框
  ├─ 启动/监控/重启 Python 后端
  └─ 通过受限 IPC 代理 /api/* 请求
          │
React 渲染进程
  ├─ 项目工作台
  ├─ 新建项目与项目空间
  ├─ 模型、提示词、素材、人物和文档库
  └─ API 类型与客户端
          │
FastAPI 本地接口
  ├─ Pydantic 请求/响应模型
  ├─ X-Rusty-Token 写操作校验
  └─ 领域服务编排与错误转换
          │
Python 服务层
  ├─ 导入、分章、项目、文档库与导出
  ├─ 模型、提示词、风格、素材与锚点
  └─ AI 分析、生成、校验、重试和追踪
          │
SQLite + OS keyring + 本地文件
```

## 4. 代码目录

| 路径 | 职责 |
| --- | --- |
| `desktop/electron/` | Electron 主进程、预加载脚本、文件对话框和后端生命周期 |
| `desktop/src/` | React 页面、组件、主题、API 客户端和类型 |
| `backend/api.py` | FastAPI 路由、依赖注入、输入校验和响应转换 |
| `backend/schemas.py` | API 请求与响应模型 |
| `src/rusty/services/` | 项目领域逻辑与 AI 流水线 |
| `src/rusty/db/` | SQLite 连接、建表和版本迁移 |
| `src/rusty/importers/` | TXT、EPUB、DOCX 解析 |
| `src/rusty/exporters/` | TXT、EPUB 输出 |
| `src/rusty/ui/` | 保留的 PySide6 旧版界面 |
| `tests/` | 服务、API、数据库、导入导出和 UI 自动化测试 |
| `examples/xianxia/` | 世界观、人物、风格和改写链路示例 |

## 5. 数据实现

数据库当前架构版本为 51。主要数据域包括：

- 项目、书籍元数据、导入来源、分章规则和章节；
- AI 模型、提示词模板、项目提示词和项目设置；
- 风格模板、分析模板、章节分析和项目综合结果；
- 大纲、角色卡、素材、三类独立标签及项目绑定；
- 流水线阶段状态、摘要、场景分析、情节扩写、改写结果、生成尝试和错误；
- 导出计划和导出记录；
- 文档库文档、分类、标签、处理模板、修订版本、卷、章节、草稿和存储设置。
- 剧情运行状态、草稿生成进度、独立分支路线和不可变章节/场景版本快照。
- 章节/场景创作阶段、预分析、创作方向、strategy 专项分析、SceneTarget、WritingPlan/blocks、Current Draft 和 ReviewMark。

v14 曾将旧 `snippet` 映射为当时的场景素材，将 `outline` 映射为 `plot_skeleton` 并保留旧类型元数据。v19 新增文档卷层级；v20 新增角色分类；v21 新增角色提取设置；v22 新增素材分类、标签组、工程素材筛选和当时的三任务设置；v53 统一角色稳定字段与提取维度。v54 将历史场景素材、同类型分类和工程过滤原地迁移为 `author_style`，保留 ID、关联、来源、时间戳与旧 content，并把当前素材 AI 设置收敛为两套。

兼容性：旧的 `POST /api/characters/extract`、`POST /api/characters/extract/apply`、copy-to-project、project-copy、publish-to-public、角色分析和封面 API 暂时只作为后端 deprecated legacy 接口保留；新角色页不调用它们。素材的单阶段提取、复制与分析接口同样仅为 legacy；新素材页只调用 Preview/Apply。文档选区提取角色统一进入必须填写目标人物名的 AI Preview 流程。

SQLite 连接默认启用外键、WAL、`synchronous=NORMAL` 和 5 秒忙等待。迁移由 `schema_migrations` 记录，初始化时按版本顺序执行。

### 5.1 工作流生命周期与版本一致性

Plot Generation 的新正式路径为 `awaiting_skeleton → ready → generating → completed`，另有
`failed` 和 `cancelled`。旧状态值仍可读取，以兼容 v40 历史数据，但新工作流不再进入
`planning_blocked`、`awaiting_seams` 或 `repair_required`。活动运行可取消，技术失败可显式重试；
创作一致性问题保存为提示，不替用户阻止正式版本。

`generate-next` 推进一个计划场景，`execute` 复用相同核心推进所有剩余场景。生成中的正文
只保存在 `plot_generation_runs.generated_progress_json`；通过最终一致性检查后才原子提交正式
改写正文或分支章节。

正式产品中的分支是从原文创建的独立平面路线；在分支内继续创作会向同一分支追加章节，
不再创建子分支。v36 的 `branch_chapter_version_scenes` 使每个章节版本同时
固定 facts、场景顺序和每个场景的正文版本；v37 增加运行进度、场景游标、生成尝试次数及
正式状态约束。旧数据回填优先选择不晚于章节版本创建时间的最近场景版本，并保持当前正文
与 facts 不丢失。

v38 新增 `chapter_rewrite_versions`。原始章节正文保持不可变，所有 Plot、Prose Rewrite、
人工编辑、迁移和恢复结果都追加为新版本；`chapter_rewrites.current_version_id`
是 current head，`chapters.rewritten_text` 是兼容投影。版本号在章节内单调递增，
`parent_version_id` 指向真实来源，因此允许从历史版本形成分叉而不改写历史。

v39 为 Plot/Prose run 保存来源正文快照、来源版本/hash 和独立的
`expected_source_head_version_id`。最终提交先用状态守卫获取 SQLite 写锁，再执行 source-head
CAS；正文版本、current projection、全部分支章节/场景及 run 终态在单一事务中提交。运行期间
正文 head 改变时，旧运行进入结构化 source conflict，不会覆盖新版本。

章节 effective source 统一由 `ChapterVersionService` 解析。默认继续当前版本，也可显式选择
原始基线或历史 rewrite version；恢复历史正文会创建新的 `restore` 版本。桌面工作区提供轻量
版本列表、历史正文查看和“基于此版本创建新操作”。

分支章节快照的 `facts_after` 取最后一个场景版本。修改非末场景但未重算下游时，
`fact_chain_status=needs_recompute`；当前产品不提供自动跨章节设定传播。

v40 增加 `chapter_rewrite_version_segments` 与 rewrite-version skeleton 关联。每个 rewrite
version 现在同时固定正文、章节边界 facts、场景/event-node 的 version-local span、局部状态、
映射方法和置信度。`ContextService` 不再用 `find(original_scene_text)` 或 original skeleton
offset 解析 rewrite 锚点；任意 text offset 也只使用相邻 segment state。Plot/Prose run 冻结
semantic-map hash 与 resolved anchor snapshot，最终 CAS 同时验证正文版本和 map 归属。
SQLite trigger 禁止业务 UPDATE/DELETE rewrite version 及其 semantic map。锚点预览 API 和
`StoryAnchorPicker` 会展示实际 rewrite excerpt、局部状态与低置信度提示。

v41 增加 `chapter_workflow_state`；v42 增加 `scene_preanalyses` 和 `creative_intents`；v43 增加
`prompt_definitions` 和 `project_master_prompts`；v44 增加
`character_modification_analyses`；v45 增加 `scene_workflow_state`；v46 增加 `scene_targets`；v47 增加
`writing_plans`、`writing_plan_blocks` 和 `scene_current_drafts`；v48 增加 `review_marks`；v49 增加
`strategy_scene_analyses` 与 plot_adjust tasks；v50/v51 分别增加 expansion/reimagine tasks。迁移按现有版本链顺序追加，不删除旧表或旧数据。

## 6. 桌面端与安全边界

- 后端默认只监听 `127.0.0.1:8765`。
- Electron 启动时生成临时 API token，并在所有代理请求中注入 `X-Rusty-Token`。
- 会修改数据的 API 需要 token；健康检查和必要的只读接口可直接访问。
- 渲染进程启用 `contextIsolation` 和沙箱，禁用 Node 集成。
- IPC 后端代理仅允许 `/api/` 路径。
- 外部链接交由系统浏览器打开，并阻止窗口导航到非允许来源。
- 模型 API 密钥使用操作系统 keyring，不通过 API 返回。

## 7. 本地开发

要求 Python 3.11+ 和 Node.js。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev,ui-r2]"

Set-Location desktop
npm install
npm run electron:dev
```

`electron:dev` 会启动 Vite、编译 Electron 主进程，并由 Electron 自动启动 FastAPI 后端。也可以分别运行：

```powershell
python -m backend.server

Set-Location desktop
npm run dev
```

旧版 PySide6 界面仍可通过以下命令启动：

```powershell
.\.venv\Scripts\rusty
```

默认数据库位置：

```text
%USERPROFILE%\AppData\Local\Rusty\rusty.db
```

## 8. 验证方式

Python 测试：

```powershell
python -m pytest -q
```

桌面端类型检查与生产构建：

```powershell
Set-Location desktop
npm run build
```

桌面自动化分为三类，不能互相替代：

```powershell
npm run test:e2e          # Mock 浏览器 UI
npm run test:e2e:real     # React 浏览器 UI + FastAPI + SQLite + FakeLLM
npm run test:e2e:electron # 实际 Electron + preload + FastAPI + SQLite + FakeLLM
```

完整后端测试覆盖数据库迁移、导入导出、项目与文档库、卷章层级、草稿与 revision、模型密钥隔离、提示词兼容、素材与锚点、API 权限、流水线成功/失败/重试、结构化改写校验，以及 PySide6 基础 UI。

## 9. 当前边界

- 四种方向已复用 SceneTarget → WritingPlan → Current Draft → traditional Diff 主链；strategy 差异集中在专项分析、Target 结构和 reimagine 的 full-scene generation 决策。
- 当前不提供 AI 自动审查、人物漏改 validator、fidelity score、ReviewMark severity/type、复杂版本树、Prompt snapshot UI、拖拽节点图或保留度 slider。
- 旧 `SceneRewritePanel`、`RewriteOperationPanel`、提示词包 API 和历史 Plot/Prose 服务仍为兼容代码；普通创作主路径不再通过大型 Scene Rewrite modal 进入。

- 应用定位为单机本地工具，没有多用户、云同步和远程服务端部署。
- AI 能力依赖用户配置可用的 OpenAI 兼容模型和 API 密钥。
- 生成内容仍需要人工审阅；确认与导出流程保留了人工控制点。
- PySide6 旧界面与 Electron 同时存在，新增功能主要集中在 Electron。
- 角色编辑器支持 PNG/JPEG/WebP 自定义封面（最大 5 MB）和创建前本地预览；若角色创建成功后封面上传失败，角色记录会保留并提示重新上传。
- “引用范围”仍未持久化或接入下游消费，因此 Electron 工作台暂不显示该入口。
- 当前仓库没有桌面安装包构建与签名脚本，开发运行以源码环境为主。

> 2026-08-04：工程类型、任意语义锚点与父分支锚点、模块化细纲和三类写作工作流已接入
> Electron。`bounded_insert` 默认保留原文并执行插入；接缝按各自来源独立校验哈希。
> 自动化明确区分浏览器真实后端集成测试与实际 Electron E2E。
> 最新模型与迁移说明见 [workflow-refactor.md](workflow-refactor.md)，审计基线见
> [workflow-refactor-audit.md](workflow-refactor-audit.md)。
