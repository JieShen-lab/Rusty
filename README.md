# Rusty

Rusty 是本地优先的小说资料管理、文档整理与 AI 辅助改写桌面应用。

当前主应用由 Electron + React、FastAPI、Python 服务层和 SQLite 组成，支持项目工作台、作者风格素材库、文档库、章节级 AI 创作与 TXT/EPUB 导出。完整功能、架构和数据说明见 [当前功能与代码实现说明](docs/current-implementation.md)。

## 主要能力

- 导入 TXT、EPUB、DOCX，预览并调整分章结果。
- 管理作者风格素材与独立文档库。角色卡资产和剧情骨架素材已删除。
- 作者风格保留维度、提取要求、分析结果、具体特征、原文实例、原始来源、单维度提取及 JSON 设置导入/导出。
- 编辑文档正文，保存 revision，合并文档、新增章节、正则分章和文字整理。
- 文档或工程选区可进入作者风格“来源 → preview → 人工确认 → apply”流程，也可只保存为待整理来源。
- Workflow 的 `source_outline` / `target_outline` 是单次运行的中间分析结果，不是可复用素材。
- 作者风格是一份由多个可编辑维度组成的完整档案。每个维度保存名称、提取要求、分析结果、具体特征和原文实例，不保存实例的文档/章节位置；素材保留原始分析文本，便于以后只新增或重新提取一个维度。
- 素材 AI 只保留一套 `author_style_extraction` 当前配置；修改后立即成为新默认。
- 配置 OpenAI 兼容模型，执行可追踪的章节分析、情节扩展和改写流程。
- Creative Workflow 只以章节为创作单元，阶段为内容总结、方向、专项分析、风格、写作、审查。
- 当前策略只有调整剧情、增加剧情、重新构思。调整剧情按文本 patch 执行并由程序原样复制 preserve span；增加剧情在当前章后创建新章节并安全后移原有章节；重新构思按边界和选定作者风格整章生成。
- 调整剧情和增加剧情默认自动分析原作风格；重新构思必须选择作者风格素材。自动分析复用素材库的 `author_style_extraction` 配置并保存运行时快照。
- 最终六阶段工作台和作者风格素材库视觉重构尚未实施，本轮桌面端仅提供基础状态显示。

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
- `src/rusty/services/anchor_service.py`: outline template CRUD and project binding
- `src/rusty/services/document_library_service.py`: document categories, tags, project relations, revisions, editing, merge, chapter operations, and export
- `src/rusty/services/model_service.py`: model CRUD and keyring-backed API key references
- `src/rusty/services/prompt_service.py`: legacy prompt package CRUD and project-level overrides
- `src/rusty/services/prompt_definition_service.py`: master/workflow/common prompt CRUD and project master copies
- `src/rusty/services/creative_workflow_service.py`: chapter summary, strategy analysis, style snapshot, writing and review workflow
- `src/rusty/services/pipeline_service.py`: AI summary, scene detection, rewrite, retry, pause, and merge workflow
- `src/rusty/db/connection.py`: SQLite connection defaults
- `src/rusty/db/schema.py`: v56 schema, migrations, indexes, and seed data
- `tests/`: database, service, API, pipeline, importer/exporter, and UI tests

旧版 PySide6 入口仍可通过 `.\.venv\Scripts\rusty` 启动，但新增功能以 Electron 桌面端为准。
