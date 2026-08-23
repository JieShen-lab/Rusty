# Rusty 当前实现

Rusty 只有一个产品入口：Electron 桌面端。Electron 启动本地 FastAPI 后端，后端通过服务层访问 SQLite 与模型传输。

## AI 边界

`AIRequestExecutor` 是唯一允许创建模型客户端、调用 `chat` 和创建 `system` message 的业务边界。全局 System Prompt 来自 `prompt_slots.global_system`。章节工作流、作者风格提取、文档整理、文档 AI 分章、JSON 校验/修复和模型连接测试都通过该执行器。

`StructuredModelService` 只负责 JSON 解析、业务校验和一次 JSON 修复；不保存模型调用日志。

## 提示词

提示词使用固定六槽表 `prompt_slots`：

- `global_system`
- `chapter_summary`
- `plot_adjust`
- `expansion`
- `plot_rewrite`
- `writing`

没有通用提示词 CRUD、工程级 master 副本或提示词说明字段。

## 作者风格

作者页与章节工作流的自动原作风格提取共用 `AuthorStyleExtractionService`。提取器读取完整样本文本和当前 `material_ai_settings`，返回一个作者风格档案；档案维度使用配置中的稳定 ID 合并。作者页额外提供有时效的 preview/apply 人工确认流程。

## 章节工作流

工作流只以章节为单位。三个方向是 `plot_adjust`、`expansion` 和 `plot_rewrite`。流程数据分别保存在 summary、intent、special analysis、style context 和 writing 表中。原文保存在 `chapters.original_text` 与 `chapter_source_versions`；确认后的修改追加到 `chapter_rewrite_versions`，当前正文只是不可变版本的投影。

## 工程与文档库边界

工程与文档库是两个完全独立的数据域。工程使用 `projects`、`book_metadata`、`story_volumes`、`chapters`、章节原文/改写版本和章节工作流表保存创作数据；创建工程不会自动创建文档库文档，也不会向文档库目录复制工程源文件。工程导出由 `ProjectService` 直接从工程章节生成 TXT/EPUB。

文档库只管理用户主动导入的文档、文档库自己的章节/卷、分类、草稿和 revision，并使用自己的 storage directory。文档库导出由 `DocumentLibraryService` 从文档库 revision 生成 TXT/EPUB。删除工程不会修改文档库，删除文档库文档也不会修改工程。

## 数据库

当前 schema 版本为 v66。新数据库直接创建 canonical schema；升级支持当前发布基线 v63/v64 以及 v65 到 v66。v66 删除 `project_documents`：迁移先读取旧关联，纯工程镜像（没有分类、草稿且 revision 类型只有 `import`/`project_sync`）仅软删除 `library_documents`，不删除物理文件；存在用户编辑证据的关联文档保留为普通文档库文档，并保留其历史 revision。普通工程章节通过 `chapters.origin_kind` 区分 `source` 与 `expansion`，章节 API 同时返回基准字数、当前有效字数和字数变化量。

模型 API key 不保存在 SQLite 正文中；`ai_models` 只保存系统 keyring 引用。
