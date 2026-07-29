# Rusty 工程类型与小说工作流

## 工程与操作分类

新建工程只有：

- `rewrite`（改写工程）
- `branch`（扩写工程）

旧分析工程在 v24 迁移时映射为 `legacy_extract`。该类型只读，可查看和导出已有结果，
但不能运行已退役的提取工程主流程。`processing_mode` 保留原值用于兼容，新的工程用途
判断只读取 `projects.project_kind`。

业务操作统一为：

- `plot_generation`
- `prose_rewrite`
- `canon_change`

剧情生成模式为：

- `bounded_insert`
- `open_continuation`
- `fork`
- `fork_and_rejoin`

旧场景 API 的 `skeleton_rewrite | expansion` 仍作为短期兼容协议存在，其中旧
`expansion` 只表示原场景内插入，不代表扩写工程。新业务使用上述操作与生成模式。

## 模块化细纲

`story_skeletons` 和 `story_skeleton_versions` 仍是唯一细纲版本体系。v25 在版本记录中
增加完整的结构化细纲和来源引用，同时保留 `nodes_json` 作为旧下游的兼容投影。

结构化细纲包括元数据、事件节点、因果链接、人物/地点/时间/物品/知识/关系变化、
伏笔、开放与已解决线索、必需起止状态、编辑点和来源引用。写入前会校验必填字段、
节点顺序、唯一 ID、置信度和因果引用。旧 `plot_summary` 只以
`legacy_plot_summary` 返回，不会被伪装成结构化事件。

公共分析职责由 `shared_analysis_service.py` 暴露，适用于 rewrite 和 branch：

- `DocumentAnalysisService`
- `SceneAnalysisService`
- `SkeletonExtractionService`
- `StyleAnalysisService`
- `CharacterAnalysisService`
- `FactLedgerService`

## 分支、锚点和接缝

v26 增加：

- `story_branches`
- `story_anchors`
- `branch_seams`
- `branch_scenes`
- `branch_scene_versions`

分支可从原文或父分支建立，支持多级父子关系。锚点支持文档末尾、章节起止、场景起止、
细纲节点和文本偏移。文本偏移用于精确定位，语义 ID 与 `source_hash` 用于完整性校验。

接缝支持 entry/return 和 keep/insert-before/insert-after/replace-range。接缝必须显式
确认，哈希不匹配时拒绝确认。分支内容独立版本化；删除分支不会删除章节或原场景，
有子分支时拒绝删除父分支。

## 三个编排器

`PlotGenerationOrchestrator` 是四种剧情模式的共同核心。它统一保存目标细纲、起止锚点、
上下文、接缝、回接状态问题和结果。branch 上下文不需要
`current_original_scene`，所有必要语义块整块保存。回接状态不满足时状态为 blocked，
并返回结构化字段差异。

`ProseRewriteOrchestrator` 保存源细纲、保真策略、目标细纲、重写计划与结果。它检测
事件新增/遗漏/顺序变化、动机、结果、知识、因果、伏笔和起止状态漂移。结构问题存在时
不写改写版本。

`CanonChangeOrchestrator` 从生效点向后扫描目标路线，按影响类型保存补丁。每个补丁有
范围、哈希、原文、替换、类型、理由和审查状态。只有 accepted/edited 补丁会应用；
rejected/skipped 保留原文；哈希失配会阻止写入。章节结果进入改写版本，分支结果进入
新的分支场景版本。

## 数据库迁移

本次从 v23 依次升级到 v29：

- v24：`projects.project_kind`
- v25：结构化细纲版本字段
- v26：分支、锚点、接缝与分支正文版本
- v27：统一剧情生成运行
- v28：表达重写运行
- v29：设定变更运行与可审查补丁

迁移不删除旧表、旧项目、原文、摘要、场景、事实账本或生成版本。全新数据库按同一迁移
链初始化；历史最小化诊断库若没有 v15 细纲表，v25 不会凭空创建孤立替代表。

## 桌面工作区

- 新建页只显示改写工程和扩写工程。
- 改写工作区提供增加剧情、重写正文和修改设定。
- 扩写工作区提供末尾续写、指定节点分支和分支回接，并显示分支树。
- 默认细纲编辑器按模块与事件节点工作；JSON 仅保留给旧接口和调试。
- 接缝和设定补丁均为显式选择，不会静默批量应用。
- `legacy_extract` 显示只读兼容说明、导出和创建新工程入口。

## 当前交付边界

数据库迁移、领域服务、三个编排器及其 HTTP API 已实现并由自动化测试覆盖。扩写工作区的
分支读取、创建、切换和删除已连接持久化 API。

改写工作区目前完成了三种操作的入口、参数表单、模块化细纲编辑、接缝审查和设定补丁选择
界面，但尚未把 `plot_generation`、`prose_rewrite`、`canon_change` 的完整分步提交与运行状态
接入桌面端。因此，后端能力可以通过 API 使用，桌面端端到端生成闭环仍是后续工作；当前文档
不将整个总任务标记为完全完成。
