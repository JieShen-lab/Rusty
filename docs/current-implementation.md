# Rusty 当前功能与代码实现说明

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

### 2.4 提示词包与风格模板

- 管理摘要、情节扩写和改写所需的结构化提示词。
- 支持项目级提示词覆盖，并在项目未绑定时回退到全局默认配置。
- 支持提示词包 JSON 导入、导出和旧格式兼容。
- 支持风格模板 CRUD、导入导出、项目绑定、AI 风格抽取和试写。
- 支持章节风格分析、人工复核和项目级风格综合。

主要实现：

- `src/rusty/services/prompt_service.py`
- `src/rusty/services/prompt_compiler.py`
- `src/rusty/services/prompt_package_extraction_service.py`
- `src/rusty/services/style_service.py`
- `src/rusty/services/style_extraction_service.py`
- `src/rusty/services/analysis_service.py`
- `desktop/src/pages/PromptManagePage.tsx`

### 2.5 素材、角色卡与大纲

- 素材是统一的全局资产，不再区分公共素材和工程素材，也不再为工程创建素材副本；`scope` / `project_id` 仅为 legacy 兼容字段。
- 素材类型固定为场景素材 `scene_reference` 和剧情骨架 `plot_skeleton`，创建后不可转换。
- 两类素材分别拥有独立的多对多分类；标签分为 `general` 与 `applicable_scene` 两组，分类和标签是独立命名空间。标签只在右侧详情和管理弹窗显示，但可在当前类型/分类范围内筛选。
- 剧情骨架和场景素材均使用规范化 `schema_version: 1` 内容；编辑器按条目编辑、排序和删除，未知旧字段保存在 `legacy_extra`，正常 UI 不暴露原始 JSON。
- 素材 AI 只提供三项任务：`narrative_to_plot_skeleton`、`plot_text_to_normalized_skeleton`、`source_text_to_scene_material`。每项独立保存模型、细化程度、候选上限、系统提示词、用户提示词、JSON 分析维度、两组标签开关和附加要求；禁止从剧情骨架派生场景素材。
- AI 整理使用 preview/apply：preview 返回过期时间、Prompt 快照、可编辑候选、结构化证据、置信度、警告及两组标签建议，不写素材/标签/分类；apply 在单一事务中批量创建全部选中候选、标签和分类，任一失败则整批回滚且 Token 保持可重试，全部成功后 Token 单次消费。
- 角色与素材 Preview 保存最多 50,000 字符的完整规范化来源，模型采样最多 16,000 字符；最终 `raw_text` 始终保存完整来源，来源元数据明确记录完整长度、模型样本长度及是否为模型截断。
- 来源可只保存为 `analysis_status='unanalyzed'` 的待整理素材并显示在“最近导入”；修改原始来源会重新标记为未分析。
- 工程通过每种素材独立的标签筛选（任一/全部）和手动固定素材 ID 使用统一资产。上下文检索优先级为：手动指定 → 工程标签筛选 → 时间线/适用场景 → 关键词 → 相似度；未分析素材不参与自动检索。
- 支持大纲模板 CRUD、AI 抽取和项目绑定。
- 角色卡以角色名、身份、年龄、设定为固定字段，其他信息使用有序自定义字段。
- 角色卡支持公共/工程作用域、多标签、分析状态、独立副本和稳定默认封面。标签只在详情区显示和管理，并始终限定在当前工程或公共分类范围内筛选。
- 公共角色支持独立的多对多分类；一个公共角色可属于多个分类，工程角色不能关联公共分类，角色分类与角色标签是独立命名空间。
- 工程角色的权威集合是 `project_character_bindings.is_active = 1`；角色库和改写上下文均从有效绑定读取，不再把 `character_cards.project_id` 当作唯一关系。
- 公共角色复制到工程会原子创建独立副本，复制稳定字段、标签和封面，保留来源卡 ID/版本并自动建立有效工程绑定；公共分类不会复制。
- 公共角色复制到工程时还会在工程副本的 `source_metadata.public_baseline` 保存复制当时的完整稳定字段快照，用于后续字段级差异判断；重复添加会先提示打开已有有效副本或明确创建新副本。
- 工程角色可“保存为公共角色”，该操作始终创建新的公共角色，仅导出用户勾选的稳定字段，不复制工程绑定、事实账本、场景人物状态或其他项目运行时状态，也不会自动加入公共分类。
- “新建角色”统一提供“手动创建”和“从文本提取”两个模式。手动创建不调用 AI、默认 `analysis_status='unanalyzed'`；AI 提取使用 preview/apply 两阶段流程，确认创建后默认标记为已分析。
- AI preview 只返回可编辑候选和 0～8 个短标签建议，不写角色、标签或分类；apply 在单一事务中创建全部确认候选、标签、分类和工程绑定，任一失败整批回滚并允许修正后重试，全部成功后 Preview Token 单次消费。
- 角色提取设置持久化在数据库中，可配置模型、细化程度、候选上限、生成维度、附加要求和高级系统提示词，并支持恢复安全默认值与查看不含 API key 的 Prompt 预览。
- 支持角色卡 CRUD、复制、JSON 导入、AI 抽取和项目绑定；改写时只注入与当前章节相关的人物。

主要实现：

- `src/rusty/services/material_service.py`
- `src/rusty/services/anchor_service.py`
- `src/rusty/services/anchor_extraction_service.py`
- `desktop/src/pages/MaterialLibraryPage.tsx`
- `desktop/src/pages/CharacterLibraryPage.tsx`

### 2.6 正文选区快捷保存

- 文档库正文编辑区、工程原文和工程改写稿支持选中文字后打开右键菜单。
- 菜单并列提供“添加为剧情骨架来源”“添加为场景素材来源”“提取角色卡”。
- 两个素材入口通过一次性 history state 将选区正文和文档/工程、revision、卷、章节、offset 及标题来源带到素材页；用户可仅保存来源，或生成候选并确认后写库。
- “提取角色卡”通过 history state 将选区正文与文档、revision、章节、偏移及标题来源传到角色页，读取一次后立即清除；长文本不进入 URL 或 localStorage，确认候选前不创建角色。
- 只保存规范化后的纯文本，前后端均限制单次选区不超过 50,000 字符。
- 来源信息单独保存为元数据，包括文档/工程、章节和字符 offset，不混入正文。
- 素材选区不会直接创建记录；“仅保存来源”才创建未分析素材，AI 候选在 apply 前也不会写库。

### 2.7 可追踪 AI 改写流水线

流水线按章节执行，当前包含：

1. 章节摘要；
2. 场景识别；
3. 可选情节扩写；
4. 基于目标骨架、提示词包、风格、大纲和相关人物卡的改写；
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

### 2.8 导出

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

数据库当前架构版本为 20。主要数据域包括：

- 项目、书籍元数据、导入来源、分章规则和章节；
- AI 模型、提示词模板、项目提示词和项目设置；
- 风格模板、分析模板、章节分析和项目综合结果；
- 大纲、角色卡、素材、三类独立标签及项目绑定；
- 流水线阶段状态、摘要、场景分析、情节扩写、改写结果、生成尝试和错误；
- 导出计划和导出记录；
- 文档库文档、分类、标签、处理模板、修订版本、卷、章节、草稿和存储设置。

v14 将旧素材类型 `snippet` 映射为 `scene_reference`，将 `outline` 映射为 `plot_skeleton` 并保留旧类型元数据；旧素材分类和文档分类迁移为标签。角色卡旧固定字段迁移为身份、年龄、设定及有序自定义字段。v19 新增文档卷层级；v20 新增仅适用于公共角色的 `character_categories` / `character_category_links`，并幂等补齐历史工程角色的有效 `project_character_bindings`；v21 新增单例 `character_extraction_settings`；v22 新增素材分类、标签组、工程素材筛选和三任务 `material_ai_settings`。v22 会原地保留历史工程素材 ID，把 `scope` 统一为 `public`、清空 `project_id`，并在来源元数据记录 `legacy_scope` / `legacy_project_id` / `migrated_to_unified_library`；已有标签会转为对应工程的素材筛选，未打标签的旧素材不会生成伪标签。v23 为三个素材 AI 任务分别增加用户提示词模板、JSON 分析维度、通用标签开关和适用场景标签开关；v22 的 `generate_tags` 会迁移到两个新开关。迁移和关系写入均可幂等重放。

兼容性：旧的 `POST /api/characters/extract`、`POST /api/characters/{card_id}/analyze` 和 `POST /api/characters/{card_id}/analyze/confirm` 暂时仅作为后端 legacy 接口保留；对应前端调用已清理，新角色页不再调用这些单阶段接口。素材的 `POST /api/material-extractions`、`POST /api/materials/{id}/copy`、`POST /api/materials/{id}/analyze` 与分析 apply 接口也仅作为后端 legacy 接口保留；对应前端调用与废弃的旧素材管理页已清理，新的素材页只调用 `/api/material-extractions/preview` 与 `/api/material-extractions/apply`。旧的选区直接创建素材接口已删除，文档和工程选区必须进入候选确认流程。

SQLite 连接默认启用外键、WAL、`synchronous=NORMAL` 和 5 秒忙等待。迁移由 `schema_migrations` 记录，初始化时按版本顺序执行。

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

完整后端测试覆盖数据库迁移、导入导出、项目与文档库、卷章层级、草稿与 revision、模型密钥隔离、提示词兼容、素材与锚点、API 权限、流水线成功/失败/重试、结构化改写校验，以及 PySide6 基础 UI。

## 9. 当前边界

- 应用定位为单机本地工具，没有多用户、云同步和远程服务端部署。
- AI 能力依赖用户配置可用的 OpenAI 兼容模型和 API 密钥。
- 生成内容仍需要人工审阅；确认与导出流程保留了人工控制点。
- PySide6 旧界面与 Electron 同时存在，新增功能主要集中在 Electron。
- 角色编辑器支持 PNG/JPEG/WebP 自定义封面（最大 5 MB）和创建前本地预览；若角色创建成功后封面上传失败，角色记录会保留并提示重新上传。
- “引用范围”仍未持久化或接入下游消费，因此 Electron 工作台暂不显示该入口。
- 当前仓库没有桌面安装包构建与签名脚本，开发运行以源码环境为主。

> 2026-07-29：工程类型、分支、模块化细纲和三类写作工作流的数据库、领域服务与 API
> 已完成重构；Electron 已接入分支持久化，但三类写作工作流的桌面端完整提交闭环仍待接入。
> 最新模型与迁移说明见 [workflow-refactor.md](workflow-refactor.md)，审计基线见
> [workflow-refactor-audit.md](workflow-refactor-audit.md)。
