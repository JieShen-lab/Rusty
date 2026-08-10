# Rusty 工程类型与小说工作流

## 分类与兼容

新建工程只接受 `rewrite`（改写工程）和 `branch`（扩写工程）。历史分析工程在 v24
无损映射为 `legacy_extract`，只能查看、导出或派生新工程，不能继续运行旧提取主流程。
`processing_mode` 仅保留为执行方式兼容字段，业务用途统一读取 `projects.project_kind`。

操作类型为 `plot_generation`、`prose_rewrite`、`canon_change`；剧情模式为
`bounded_insert`、`open_continuation`、`fork`、`fork_and_rejoin`。四种剧情模式共享
`PlotGenerationOrchestrator`，没有平行的生成实现。

## 模块化细纲和公共分析

`story_skeletons` 与 `story_skeleton_versions` 是唯一细纲版本体系。结构化细纲保存事件、
因果、人物状态、时空、物品、知识、关系、伏笔、线索、起止状态、编辑点和来源引用；
AI 输出在持久化前统一校验。桌面编辑器调用创建、读取、修订和确认版本 API，旧
`plot_summary` 仍按旧分析结果读取，不伪造结构化节点。

章节、场景、细纲、风格、人物和事实账本能力由共享分析服务暴露，可由两类工程调用。

## 分支、锚点、章节和接缝

分支存储由以下实体组成：

- `story_branches`、`story_anchors`
- `branch_chapters`、`branch_chapter_versions`
- `branch_scenes`、`branch_scene_versions`
- `branch_seams`、`rewrite_seams`

锚点支持原文章节/场景/细纲节点/文本偏移和分支章节/场景。创建时会验证项目归属、
父分支归属、节点存在性和正文版本归属。v30 将旧 `branch_scenes` 自动归入默认章节，
不丢失正文与事实数据。

接缝必须逐条确认、拒绝或编辑。应用前重新校验 `source_hash`；分支接缝只进入分支
视图，`bounded_insert` 的进入和退出接缝进入改写版本，原始基线保持不可变。

## 工作流闭环

剧情生成依次完成上下文分析、AI 目标细纲、人工确认、AI 接缝、人工审查、场景规划、
逐场景生成、事实提取、连续性检查和版本保存。扩写无需 `current_original_scene`；
回接模式在规划前后都校验必要进入状态：规划阶段不满足时进入 `planning_blocked`，
生成完成后不满足时进入 `repair_required`，两者都不能执行普通生成。

表达重写从源细纲和保真策略生成计划与正文，再从正文自动提取 observed skeleton。
遗漏、新增、顺序、知识和起止状态漂移会阻止写入；允许一次结构化局部修复，复查通过
后才保存章节版本。

设定变更先用事实账本、人物状态、细纲、实体和属性做候选召回，再由 AI 返回结构化
语义影响。所有接受补丁在任何写入前完成哈希与重叠检查，并在单一事务中应用；任一
冲突会整体回滚。章节和分支场景的新版本继承未受影响事实并更新变更事实，随后执行
一致性复查。

## 数据库迁移

当前数据库版本为 v40：

- v24：`project_kind`
- v25：结构化细纲字段
- v26–v29：分支、运行和补丁基础表
- v30：分支章节、章节版本及旧分支场景迁移
- v31：AI 剧情运行阶段、选择项、场景计划和事实账本
- v32：正式改写接缝及剧情运行关联
- v33：语义补丁置信度、证据和人工确认元数据
- v34：剧情运行范围操作，区分默认的 `insert_between` 与显式 `replace_range`
- v35：接缝独立来源锚点和来源版本，使进入、回接接缝分别校验当前文本
- v36：`branch_chapter_version_scenes` 固化章节版本所引用的场景版本与顺序
- v37：Plot 正式状态约束，以及运行草稿进度、下一场景游标和重试次数
- v38：`chapter_rewrite_versions`，为章节改写正文建立不可变版本链、真实父版本和来源哈希
- v39：章节改写 current head、Plot/Prose 冻结来源快照与期望 head、分支事实链状态，
  并统一 Prose/Canon 的取消和终态约束
- v40：`chapter_rewrite_version_segments` 保存 rewrite version-local 场景/事件 span、局部状态、映射方法与置信度；补偿回填 legacy rewrite facts，并为 rewrite versions 与 semantic maps 增加数据库级不可变触发器

迁移不删除旧表、项目、原文、摘要、分析、场景、事实账本或历史版本；全新数据库和
v29 历史数据库均走同一迁移链。

## 桌面工作区与旧项目

改写工作区提供三类分步操作；扩写工作区提供末尾续写、中途分支、回接和父子分支树。
localStorage 只保存最近查看的运行 ID，刷新后必须从后端读取实际状态；每类工作流同时
提供数据库历史运行列表。终态运行可以查看结果或清除当前选择后开始新运行，活动运行
必须先显式取消。

旧工程分析导出使用专用 JSON API，包含元数据、章节摘要、人物、风格、全书归纳、
提示词和结构化细纲。派生工程复制原文并可选复制分析结果，新旧项目拥有独立 ID 和
版本，不修改旧工程。

## Plot 运行生命周期与不变量

正式状态机为：

```text
awaiting_skeleton → awaiting_seams → ready → generating → completed
        │                 │            │          └→ repair_required → retry → ready
        └→ planning_blocked ──修订细纲──┘
活动状态 ──cancel──→ cancelled
技术失败 ──→ failed ──retry（可恢复失败）──→ ready
```

- `planning_blocked` 只允许修订目标细纲或取消；`repair_required` 只允许显式重试或取消。
- `completed` 与 `cancelled` 是不可恢复终态，不能再次 execute。
- `generate-next` 每次只推进一个场景；`execute` 生成全部剩余场景，二者共用同一生成核心。
- 草稿场景保存在运行进度中，一致性检查通过前不会写入正式改写正文或分支当前内容。
- 接缝审查必须一次覆盖本运行的全部接缝；重复、缺少、额外、跨运行 ID 或任一 hash
  失效都会使整批事务回滚。

顶级分支只能锚定原文；子分支必须提供 `parent_branch_id` 并锚定该父分支的
`branch_chapter` 或 `branch_scene`。`base_source_version_id` 由服务端从起点版本派生，
客户端兼容值必须与锚点版本完全相同。

每个 `branch_chapter_version` 是不可变的标题、摘要、facts、场景顺序和场景版本联合
快照。场景正文产生新版本时会创建新的章节快照，旧章节版本不再动态读取
`branch_scenes.current_version`。

## 章节改写版本链与原子最终提交

`chapters.original_text` 是不可变基线；`chapter_rewrite_versions` 是改写正文的唯一权威
历史，`chapter_rewrites.current_version_id` 和 `chapters.rewritten_text` 只是当前投影。Plot、
Prose Rewrite 和 Canon Change 都通过 `ChapterVersionService` 解析 effective source：默认读取
当前 head，也可明确选择原始基线或历史版本。恢复历史版本会追加一个 `restore` 版本，不会
删除后来的版本。

每个运行在启动时冻结来源种类、来源版本、正文快照、正文 hash 和启动时 current head。
`parent_version_id` 表示真实派生父版本，`expected_source_head_version_id` 单独用于提交 CAS；
因此从 v1 派生时可以保留 `parent=v1`，同时防止运行期间变化的 v3/v4 被旧运行覆盖。

最终一致性检查通过后，正式提交以运行级单一 SQLite 写事务完成：

- bounded insert 在同一事务中追加 rewrite version、更新 current projection 并将 run 标记完成；
- branch 在同一事务中创建全部章节、场景、场景版本、章节快照映射并完成 run；
- 任一章节/状态更新失败会整体回滚，草稿进度仍留在 run 中用于诊断；
- cancel 和 final commit 都用状态守卫争夺写锁，合法结果只有“completed + 完整正式输出”或
  “cancelled + 无正式输出”。

分支章节 `facts_after` 始终来自该 snapshot 的最后一个场景版本。修改中间场景但未重算
下游事实时，新章节快照标记为 `needs_recompute`；Canon Change 会从生效点向后为所有受
影响场景创建新版本（即使正文不变但 facts 变化），并提交 `consistent` 的完整场景/事实链。

## Rewrite version-local 语义锚点与局部状态

v40 将稳定语义身份与文本位置分开：`scene_id` / `node_id` 继续表示身份，
`chapter_rewrite_version_segments` 记录该身份在特定 rewrite version 中的 span、局部
`state_before` / `state_after`、映射方法和置信度。Scene 与 skeleton-node 锚点只通过该表解析；
缺少映射时返回 `anchor_unmapped`，不再搜索 original scene 文本，也不再复用 original
`source_span`。`text_offset` 使用目标位置最近的 segment state；无法解析时返回
`state_unresolved`，不会回退到章节末尾状态。

Plot insert 与 Canon patch 使用确定性 span transformation；replace overlap 会标记需要重新映射。
Prose 复用 drift check 已提取的 observed skeleton source spans，持久化 rewrite-version structure
和 scene/event map。运行启动时冻结 resolved anchor、source version、source/map hash 和局部状态，
后续阶段不再重新解释锚点。`POST /api/story-anchors/preview` 在启动前返回版本、实际 span、
正文摘录、前后状态、映射方法与置信度；桌面端只展示当前所选版本中可解析的语义锚点。

`chapter_rewrite_versions.facts_before/facts_after` 始终表示章节边界状态，插入剧情的局部
状态保存在 generated-event segment。v40 对 v38 migration 产生的空 facts 做 best-effort
scene-ledger 回填；证据不足时保留空起点并标记 `needs_recompute`。rewrite versions 与对应
semantic segments 由 SQLite trigger 禁止 UPDATE/DELETE；恢复原文会追加 `restore` 版本。

## 验证

自动化覆盖后端单元/迁移测试、前端类型检查和构建、API Mock 浏览器 UI E2E、由真实
FastAPI、临时 SQLite 和 FakeLLM 驱动的八条浏览器集成 E2E，以及启动实际 Electron
主进程并验证 preload、文件路径和应用关闭的 Electron E2E。CI 工作流分别运行
`backend`、`frontend-build`、`mock-ui-e2e`、`real-backend-e2e` 和 `electron-e2e`。

当前已知限制：

- 生产 AI 的质量、成本和延迟取决于用户配置的模型；自动化测试只使用 FakeLLM。
- 角色和素材在工作区当前以 ID 多选输入，后续可改进为搜索式资源选择器。
- 旧场景 API 的 `expansion` 仍作为短期兼容词存在，新业务统一使用 `bounded_insert`。
- 文本位置锚点当前使用数值偏移输入，尚未提供富文本拖选交互。
- 模块化细纲编辑器提供表单与键值编辑，不包含复杂因果关系图谱可视化。
- 正文版本 UI 当前提供线性列表、历史正文查看和“基于此版本创建新操作”，尚未绘制分叉树。
