# Rusty

Rusty 是本地优先的小说文档管理与章节级 AI 创作桌面应用。当前主应用由 Electron + React、FastAPI、Python 服务层和 SQLite 组成。

当前功能：

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

当前实现与数据结构见 [docs/current-implementation.md](docs/current-implementation.md)。
