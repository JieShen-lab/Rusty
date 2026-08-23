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

## 数据库

当前 schema 版本为 v64。新数据库直接创建 canonical schema；升级只支持当前发布基线 v63 到 v64。迁移保留当前工程、章节、原文、改写版本、章节工作流、作者风格、作者提取设置、模型、文档库、修订、分类和文档分章 proposal，然后删除退出产品的表。

模型 API key 不保存在 SQLite 正文中；`ai_models` 只保存系统 keyring 引用。
