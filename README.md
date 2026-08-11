# Rusty

Rusty 是本地优先的小说资料管理、文档整理与 AI 辅助改写桌面应用。

当前主应用由 Electron + React、FastAPI、Python 服务层和 SQLite 组成，支持项目工作台、素材库、角色卡库、文档库、可追踪 AI 改写与 TXT/EPUB 导出。完整功能、架构和数据说明见 [当前功能与代码实现说明](docs/current-implementation.md)。

## 主要能力

- 导入 TXT、EPUB、DOCX，预览并调整分章结果。
- 管理统一的全局素材资产、公共/工程角色卡和独立文档库；素材不再创建公共/工程副本。
- 使用独立标签和类型专属分类组织素材；素材标签分为通用标签与适用场景标签，公共角色另有独立的多对多分类。
- 编辑文档正文，保存 revision，合并文档、新增章节、正则分章和文字整理。
- 从文档正文选区进入角色 AI 提取候选流程；Preview 不写数据，Apply 在同一事务中创建角色、标签、分类和工程绑定，成功后 Token 单次消费，失败时整批回滚并允许重试。
- 文档或工程选区可进入素材“来源 → preview → 人工确认 → apply”流程，也可只保存为待整理来源；Preview 不写素材、标签或分类，Apply 整批原子提交。完整来源最多 50,000 字符，模型采样最多 16,000 字符且不会覆盖最终 `raw_text`。
- 工程通过剧情骨架/场景素材各自的标签筛选和手动固定 ID 使用统一素材，自动检索不会纳入未分析素材。
- “新建角色”提供互不依赖的手动创建和 AI 文本提取模式；AI 提取采用 preview/apply 两阶段接口。
- 公共角色添加到工程时创建带公共基线快照的独立副本并自动绑定；工程角色可只导出勾选的稳定字段为新的公共角色，项目动态状态仍留在事实账本和场景人物状态中。
- 配置 OpenAI 兼容模型，执行可追踪的章节分析、情节扩展和改写流程。
- 普通小说工程使用统一的章节中心三栏工作台，完成预分析、四种 strategy 的专项分析与目标设计、block 写作规划、Current Draft 生成/编辑，以及 Source ↔ Current Draft 传统 Diff 审查。

## Development

Create an environment and install the project:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
```

安装桌面端依赖并运行：

```powershell
Set-Location desktop
npm install
npm run electron:dev
```

Electron 会自动启动本地 FastAPI 后端。默认数据库位置：

```text
%USERPROFILE%\AppData\Local\Rusty\rusty.db
```

Model API keys are not stored in the main SQLite database. Rusty stores a
keyring reference in `ai_models.api_key_secret_ref` and writes the secret value
to the operating system keyring through the `keyring` package.

The AI pipeline uses OpenAI-compatible `/chat/completions` APIs through `httpx`.
Current stages include chapter summary, scene detection, chapter rewrite,
error recording, retry entry points, project pause status, and merged text
output. Project-level AI settings can bind a model and prompt template, and the
pipeline falls back to global defaults when a project has no explicit binding.

运行后端测试：

```powershell
python -m pytest -q
```

Initialize a SQLite database from source:

```powershell
$env:PYTHONPATH = "src"
python -m rusty.db.schema rusty.db
```

## Current Structure

- `desktop/`: Electron + React 桌面端
- `backend/`: FastAPI 本地接口与 Pydantic 类型
- `src/rusty/importers/`: TXT / EPUB / DOCX parsing
- `src/rusty/exporters/`: TXT / EPUB export
- `src/rusty/services/project_service.py`: project persistence and import/export workflow
- `src/rusty/services/material_service.py`: unified material library, type-specific categories, tag groups, project filters, structured content, and AI settings
- `src/rusty/services/anchor_service.py`: character cards, public-only categories, tags, atomic project copies, and project bindings
- `src/rusty/services/document_library_service.py`: document categories, tags, project relations, revisions, editing, merge, chapter operations, and export
- `src/rusty/services/model_service.py`: model CRUD and keyring-backed API key references
- `src/rusty/services/prompt_service.py`: legacy prompt package CRUD and project-level overrides
- `src/rusty/services/prompt_definition_service.py`: master/workflow/common prompt CRUD and project master copies
- `src/rusty/services/creative_workflow_service.py`: scene-authoritative creative target, planning, draft generation and review workflow
- `src/rusty/services/pipeline_service.py`: AI summary, scene detection, rewrite, retry, pause, and merge workflow
- `src/rusty/db/connection.py`: SQLite connection defaults
- `src/rusty/db/schema.py`: v51 schema, migrations, indexes, and seed data
- `tests/`: database, service, API, pipeline, importer/exporter, and UI tests

旧版 PySide6 入口仍可通过 `.\.venv\Scripts\rusty` 启动，但新增功能以 Electron 桌面端为准。
