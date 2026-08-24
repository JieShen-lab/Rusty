# Rusty

> [!IMPORTANT]
> **项目已停止开发。** Rusty 是一个个人练手项目，完成了从想法、设计、开发到封装成桌面软件的完整实践。经过实际使用后，我确认它没有很好地解决小说创作中的真实需求，现有版本也仍有较多问题，因此不再继续维护或更新。

Rusty 原本是一个本地优先的小说文档管理与章节级 AI 创作桌面应用，主应用由 Electron + React、FastAPI、Python 服务层和 SQLite 组成。

## 项目说明

这个项目最终做出了一款可以安装和运行的软件，也让我完整经历了一次软件项目的开发过程。作为个人练手，它已经完成了自己的目的。

但从成品的实际使用效果来看，它并没有真正帮助我更好地进行作品创作：智能新章节存在覆盖原章节的问题，文章生成结果难以达到预期，格式修改也不能准确遵循要求。与其继续投入时间重复实现已有工具能够提供的能力，我决定在这里结束这个项目。

仓库将作为这次完整练习的记录保留。以下内容仅用于说明项目停止开发前已经实现的功能，不代表它们已经成熟、稳定或适合实际创作使用。

停止开发前的功能：

- 导入 TXT、EPUB、DOCX 并建立章节工程。
- 独立文档库：只管理用户主动导入的文件及其分类、修订、合并、章节/卷编辑、AI 整理、AI 分章与 TXT/EPUB 导出。
- 作者风格档案：完整样本提取、人工确认、编辑，以及提取设置导入/导出。
- 章节工作流：内容总结、调整剧情、增加剧情、重写剧情、风格确定、正文生成和人工确认。
- 六个固定提示词槽，以及统一注入到每次 AI 请求的全局 System Prompt。
- OpenAI-compatible 模型配置与系统 keyring 密钥存储。

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
Set-Location desktop
npm install
npm run electron:dev
```

默认数据库位置：`%USERPROFILE%\AppData\Local\Rusty\rusty.db`。

工程与文档库是两个完全独立的数据域。创建工程不会自动创建文档库文档；工程章节、创作工作流和工程导出由工程系统维护，工程导出由 `ProjectService` 直接生成 TXT/EPUB。文档库只管理用户主动导入的文档和自身版本，文档库导出由 `DocumentLibraryService` 从文档库版本生成 TXT/EPUB。

应用只创建和使用当前数据库结构，不再包含旧数据库升级与数据兼容逻辑。升级后应从空数据库开始使用。

## Windows 封装

封装环境需要 Windows x64、Node.js 与 Python 3.11 以上版本；成品用户不需要安装 Node.js 或 Python。

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
Set-Location desktop
npm install
npm run package:win
```

最终交付文件为 `desktop\release\Rusty-Setup-0.1.0.exe`。安装器按当前用户安装，卸载时保留 `%LOCALAPPDATA%\Rusty` 中的数据库和文档。

当前实现与数据结构见 [docs/current-implementation.md](docs/current-implementation.md)。
