# Rusty 当前产品边界

Rusty 当前版本是阶段式 AI 小说创作器：用户选择已有小说中的位置，说明创作方向，确认 AI 规划，再逐场景生成并保存为新版本。程序负责版本和数据安全，创作质量问题以提示交给用户决定。

## KEEP

- 原文基线不可变；改写以 append-only 版本保存，可查看、恢复或从历史稿继续。
- run 启动时冻结 source snapshot/hash/semantic map，最终提交使用 CAS 和单事务。
- Plot 保留规划确认、生成下一场景、生成全部剩余场景、取消和技术失败重试。
- Prose 使用所选正文版本及其结构，生成正文后把结构偏移作为创作提示，不隐藏式自动修文。
- 简单 facts/state continuity 与 version-local scene/event semantic map。
- 普通续写路线、从原文语义节点创建 IF 路线，以及在同一条路线中继续追加章节。
- `legacy_extract` 的只读查看、分析导出和派生新工程。

## SIMPLIFIED

- Plot 新运行路径为 `awaiting_skeleton → ready → generating → completed`，另有 `failed`、`cancelled`；旧状态值仅供历史数据库读取。
- `bounded_insert` 和 `replace_range` 直接把生成正文合成到冻结 source snapshot，不再要求用户理解或逐条审批“接缝”。
- Branch 是相互独立的平面路线；继续创作会追加到当前 Branch，而不是创建 child branch。
- Prose 的 source skeleton 本身就是结构约束，不再要求 AI 复制 target skeleton；关键事件、顺序、锁定节点和起止状态是核心指导，其余结构项是软指导。
- 一致性检查是创作提示；source/CAS/ownership/hash/结构化输出/数据库完整性错误仍硬阻断。
- 正式界面隐藏 run history、原始状态枚举、内部 ID、map offset/hash 和普通置信度。

## REMOVED

- `fork_and_rejoin` 正式产品模式及回接状态规划。
- child-branch topology、父子分支树及“从此分支派生”。
- mandatory seam proposal/review 阶段及新 seam 写入路径。
- Canon Change 用户工作流、HTTP API、前端 patch review 和生产编排器。
- 创作内容的隐藏式自动 repair；仅允许纯技术格式修复。
- Plot/Prose 主界面的历史 run 列表；单个活动 run 仍可从后端恢复。

对应功能测试随正式能力删除；核心不变量继续由 service、API、浏览器真实后端和 Electron 测试覆盖。

## DORMANT SCHEMA

数据库版本保持 v40。历史迁移不改写，因此 `parent_branch_id`、return-anchor、seam、Canon、旧 Plot 状态及相关 run/table/column 仍可能存在。它们用于旧数据库可读性与升级审计，新 UI/API/工作流不再创建这些产品数据。

历史 rewrite version 的 `source_operation=canon_change` 仍可读取；这不表示 Canon Change 仍是可启动的产品能力。

## DEFERRED

大型 RAG、长期知识图谱、自动跨章节事实传播、复杂分支拓扑、自动回接、版本树/diff、semantic repair debugger 和无人干预写作均不在当前版本。未来若重新引入，应按当时产品需求重新设计，不以 dormant schema 或已删除代码作为预设架构。
