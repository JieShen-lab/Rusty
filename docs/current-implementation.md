# Rusty 当前功能与代码实现说明

> 文档状态：对应当前仓库实现  
> 项目形态：本地小说整理、分析与 AI 辅助改写桌面应用

## 1. 项目概览

Rusty 以本地优先方式管理小说项目。当前主界面采用 Electron + React，Electron 负责桌面窗口、文件选择和后端进程生命周期；FastAPI 提供本地 HTTP API；Python 服务层负责导入、资料管理、AI 调用、改写流水线与导出；SQLite 保存项目数据和生成记录。

仓库仍保留早期 PySide6 桌面端，可用于原有导入、预览和导出流程。当前持续迭代的 R2 界面位于 `desktop/`。

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
- 支持文档分类、元数据编辑、章节查看与排序。
- 支持处理模板、文本清理、修订版本和版本恢复。
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

### 2.5 素材、世界观、人物与大纲

- 素材支持公共库和项目时间线两种作用域。
- 支持世界观、地理、势力、功法、物品、事件等分类，并支持自定义分类。
- 公共素材可复制到项目中，复制结果与原素材独立。
- 支持基于文本或文件调用 AI 抽取指定类型素材。
- 支持大纲模板 CRUD、AI 抽取和项目绑定。
- 支持人物卡 CRUD、复制、导入、AI 抽取和项目绑定。
- 人物卡保存别名、人物资料、来源信息和导入元数据；改写时只注入与当前章节相关的人物。

主要实现：

- `src/rusty/services/material_service.py`
- `src/rusty/services/anchor_service.py`
- `src/rusty/services/anchor_extraction_service.py`
- `desktop/src/pages/MaterialLibraryPage.tsx`
- `desktop/src/pages/CharacterLibraryPage.tsx`
- `desktop/src/pages/AnchorManagePage.tsx`

### 2.6 可追踪 AI 改写流水线

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

### 2.7 导出

- 项目支持 TXT、EPUB 导出。
- 文档库支持 TXT、EPUB 导出。
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
| `design-system/` | R2 视觉规范、页面设计说明和概念图 |

## 5. 数据实现

数据库当前架构版本为 13。主要数据域包括：

- 项目、书籍元数据、导入来源、分章规则和章节；
- AI 模型、提示词模板、项目提示词和项目设置；
- 风格模板、分析模板、章节分析和项目综合结果；
- 大纲、人物卡、素材、分类及项目绑定；
- 流水线阶段状态、摘要、场景分析、情节扩写、改写结果、生成尝试和错误；
- 导出计划和导出记录；
- 文档库文档、分类、处理模板、修订版本、章节和存储设置。

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
python -m unittest discover -s tests
```

桌面端类型检查与生产构建：

```powershell
Set-Location desktop
npm run build
```

测试覆盖数据库迁移、导入导出、项目与文档库、模型密钥隔离、提示词兼容、素材与锚点、API 权限、流水线成功/失败/重试、结构化改写校验，以及 PySide6 基础 UI。

## 9. 当前边界

- 应用定位为单机本地工具，没有多用户、云同步和远程服务端部署。
- AI 能力依赖用户配置可用的 OpenAI 兼容模型和 API 密钥。
- 生成内容仍需要人工审阅；确认与导出流程保留了人工控制点。
- PySide6 旧界面与 Electron R2 同时存在，新增功能主要集中在 Electron R2。
- 当前仓库没有桌面安装包构建与签名脚本，开发运行以源码环境为主。

