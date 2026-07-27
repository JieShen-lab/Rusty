# Rusty

Rusty 是本地优先的小说资料管理、文档整理与 AI 辅助改写桌面应用。

当前主应用由 Electron + React、FastAPI、Python 服务层和 SQLite 组成，支持项目工作台、素材库、角色卡库、文档库、可追踪 AI 改写与 TXT/EPUB 导出。完整功能、架构和数据说明见 [当前功能与代码实现说明](docs/current-implementation.md)。

## 主要能力

- 导入 TXT、EPUB、DOCX，预览并调整分章结果。
- 管理公共/工程素材、公共/工程角色卡和独立文档库。
- 使用独立标签组织素材、角色卡与文档。
- 编辑文档正文，保存 revision，合并文档、新增章节、正则分章和文字整理。
- 从文档正文、工程原文和改写稿选区快捷保存场景素材、剧情骨架或公共角色卡。
- 配置 OpenAI 兼容模型，执行可追踪的章节分析、情节扩展和改写流程。

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
- `src/rusty/services/material_service.py`: material library, tags, scopes, copies, and analysis state
- `src/rusty/services/anchor_service.py`: character cards, tags, copies, and project bindings
- `src/rusty/services/document_library_service.py`: document tags, revisions, editing, merge, chapter operations, and export
- `src/rusty/services/model_service.py`: model CRUD and keyring-backed API key references
- `src/rusty/services/prompt_service.py`: prompt template CRUD and project-level prompt overrides
- `src/rusty/services/pipeline_service.py`: AI summary, scene detection, rewrite, retry, pause, and merge workflow
- `src/rusty/db/connection.py`: SQLite connection defaults
- `src/rusty/db/schema.py`: v14 schema, migrations, indexes, and seed data
- `tests/`: database, service, API, pipeline, importer/exporter, and UI tests

旧版 PySide6 入口仍可通过 `.\.venv\Scripts\rusty` 启动，但新增功能以 Electron 桌面端为准。
