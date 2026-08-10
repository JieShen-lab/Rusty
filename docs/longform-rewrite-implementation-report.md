# 长篇改写与资源库实施报告

> **HISTORICAL:** 本文记录早期实现状态，不是当前架构规范。请参阅 `docs/architecture.md`。

## 实施前审查清单

### 文档库现有结构与规格

- 页面结构：`TopBar` → 顶部反馈区 → `document-library-layout` 三栏主体。
- 三栏：左侧标签导航、中间文档书架、右侧文档详情；默认列宽为 `210px / minmax(480px, 1fr) / 310px`。
- 面板：主体为 `1px` 边框、`12px` 圆角、白色背景；三栏之间用同一条边框分隔。
- 面板标题区：高度 `58px`；左、右标题居中，标题 `16px/700`。
- 左侧导航：导航项高度 `42px`、圆角 `7px`，图标 `16px`，选中态使用 `--accent-soft` 和 `--accent`。
- 中央区：搜索框位于面板头部，高度 `36px`；内容区滚动；书架边距 `18px`，卡片间距 `18px 14px`。
- 卡片：透明外框、`10px` 圆角；悬停显示 `--line` 边框和 `--paper` 背景；选中使用 `--selected-border` 与 `--accent-soft`。
- 空状态：图标、标题、可选主按钮组成完整居中状态；加载和无结果沿用相同区域。
- 详情区：固定 `58px` 标题、独立滚动内容、固定底部操作栏；内容 section 使用 `14px` 内边距和底部分隔线。
- 底部按钮：两列，按钮高度 `40px`、圆角 `8px`、图标约 `15px`。
- 对话框：遮罩从桌面标题栏下方开始，模态框使用 `14px` 圆角、边框、阴影、固定标题/滚动内容/底部操作。

### 角色卡和素材库待替换的旧 UI

- 两页仍使用独立的 `resource-page/resource-layout/resource-sidebar/resource-main/resource-detail` 样式；尺寸、间距、选中态和空状态均未使用文档库规格。
- 左侧是连续普通按钮和 `<hr>`，缺少面板标题、分组语义、统一计数与项目选择器规格。
- 卡片常驻编辑、复制、分析、删除操作；`MoreHorizontal` 点击后直接删除。
- 右侧详情没有固定面板标题和固定底部操作栏；未选择时只有一行文字。
- 素材详情默认直接显示 JSON；角色编辑与素材编辑仍是简化后台表单。
- 加载、成功反馈、异步禁用和错误反馈不完整。

### 长篇改写流程现状与缺口

- 已有：不可与 `rewritten_text` 混淆的章级 `original_text`、章级摘要、章级场景标签、章级目标骨架、章级改写、模型请求快照、角色卡/素材独立复制语义。
- 缺少：原文版本快照与数据库不可变约束、卷/场景/段落实体、场景边界确认状态、子场景、场景事实账本、人物动态状态、结构化骨架版本、扩写规划和素材插入映射。
- 缺少：按字段计算的 Token 预算、必选块保护、滑动窗口、分层检索记录、动态风格规则/示例/近期技法记录。
- 缺少：场景分析 → 规划 → 正文 → 一致性检查 → 定向修复的持久化流程，以及章级/卷级/全书检查结果。
- 当前正文生成仍以整章为单位，并将章级摘要、风格模板、角色卡和原文章节直接拼接；没有场景级追溯和局部修订版本。

### 计划修改文件

- 数据库与模型：`src/rusty/db/schema.py`、`src/rusty/models.py`。
- 改写服务：新增场景/上下文/工作流服务，并调整 `prompt_compiler.py`、`pipeline_service.py`、`project_service.py`、`material_service.py`。
- API：`backend/schemas.py`、`backend/api.py`、`desktop/src/api/types.ts`、`desktop/src/api/client.ts`。
- UI：`CharacterLibraryPage.tsx`、`MaterialLibraryPage.tsx`、`desktop/src/styles/index.css`、必要的资源库公共组件。
- 测试：新增场景、预算、窗口、检索、工作流、迁移和前端构建/交互覆盖。
- 证据：`docs/visual-regression/*` 与本报告。

### 明确禁止修改

- `desktop/src/pages/DocumentLibraryPage.tsx`。
- 文档书架、文档封面、文档详情、文档工作台的 DOM 结构和交互。
- `index.css` 中现有 `.document-*` 规则的值、顺序和选择器语义。
- 文档库按钮位置、三栏比例、间距、颜色和空状态。

## 实施结果

### 1. 修改文件清单

- 数据库与导入：`src/rusty/db/schema.py`、`src/rusty/services/project_service.py`。
- 场景与改写服务：`src/rusty/services/scene_service.py`、`src/rusty/services/context_service.py`、`src/rusty/services/rewrite_workflow_service.py`、`src/rusty/services/prompt_compiler.py`、`src/rusty/services/__init__.py`。
- 角色响应：`src/rusty/services/anchor_service.py`。
- API：`backend/schemas.py`、`backend/api.py`、`desktop/src/api/types.ts`、`desktop/src/api/client.ts`。
- UI：`desktop/src/components/LibraryPrimitives.tsx`、`desktop/src/pages/CharacterLibraryPage.tsx`、`desktop/src/pages/MaterialLibraryPage.tsx`、`desktop/src/styles/theme.css`、`desktop/src/styles/index.css`。
- 测试与证据：`tests/test_schema.py`、`tests/test_longform_rewrite_services.py`、`docs/visual-regression/*.png`、本报告。
- `desktop/src/pages/DocumentLibraryPage.tsx` 未修改；没有改写现有 `.document-*` 规则。

### 2. 数据库迁移说明

- Schema 版本从 14 升至 15；迁移函数为 `src/rusty/db/schema.py::_migrate_to_v15`。
- `chapters` 新增 `volume_id`、`source_start_offset`、`source_end_offset`，旧章节会自动关联默认卷并回填连续字符位置。
- 新增不可变原文快照 `chapter_source_versions`。迁移为每个旧章节创建 `source_version=1` 的完整原文记录。
- 新增场景/段落、事实与动态状态、骨架/计划、提示词快照/检索、风格、生成阶段/修复/一致性检查表。
- `prevent_original_chapter_text_update`、`prevent_source_version_update/delete` 和 `prevent_scene_original_update` 触发器阻止原文或场景原文范围被覆盖。
- 新导入项目在 `project_service.py` 中写入 SHA-256 原文快照；旧库迁移保持原数据和软删除语义。
- `tests/test_schema.py::test_v14_database_migrates_to_v15_with_immutable_source_snapshot` 验证 v14 数据迁移、重复执行迁移和原文更新拦截。

### 3. 新增数据对象

- `story_volumes`、`chapter_source_versions`、`scenes`、`scene_paragraphs`：保存文档 → 卷 → 章 → 场景 → 段落层级与原文位置。
- `scene_fact_ledgers`：版本化保存事件、知识、物品、人物关系、伏笔、起止状态等事实。
- `character_story_states`：保存伤势、位置、情绪、目标、秘密、持有物等剧情动态；不会回写角色卡。
- `story_skeletons`、`story_skeleton_versions`：保存可编辑、可确认、可追溯的结构化剧情骨架。
- `rewrite_plans`、`rewrite_plan_materials`：区分骨架重写与扩写，记录插入位置、强制/参考语义、事件节点和状态影响。
- `prompt_compilations`、`prompt_compilation_blocks`：保存实际发送上下文的字段、Token、取舍决定和来源。
- `retrieval_runs`、`retrieval_results`：保存分层检索的来源位置、相关理由、置信度、是否入选和 Token。
- `scene_style_contexts`、`scene_generation_stages`、`scene_rewrite_versions`、`targeted_repairs`、`consistency_checks`：保存动态风格、多阶段结果、改写版本、局部差异和检查结论。

### 4. 两种改写模式的调用流程

- 骨架重写：`POST /api/story-skeletons` 提取/保存节点 → `.../versions` 编辑 → `.../confirm` 确认 → `POST /api/rewrite-plans`（`mode=skeleton_rewrite`）→ `.../confirm` → 按分析、规划、正文、校验阶段保存 → 保存场景改写版本。
- 扩写：确认原文骨架 → 素材先转换成 `event_nodes` → 建立带插入位置、`required/reference` 和 `impact` 的 `mode=expansion` 计划 → 用户确认 → 执行相同多阶段流程。
- 未确认骨架不能建立计划；未确认计划不能保存模型生成版本；生成版本必须引用计划所用的同一骨架版本。
- 旧章级接口为已有工程兼容保留；新增场景级 API 是新工作流的数据边界，避免破坏现有存量功能。

### 5. 提示词编译过程

- `ContextService.compile_scene_context` 依次读取滑动窗口、事实账本、人物动态状态、分层检索和动态风格上下文，构造独立 `PromptBlock`。
- `PromptCompiler.compile_scene_stage` 只编译预算器标记为 included 的块，系统规则和用户要求继续使用不同消息角色。
- 每次编译写入 `prompt_compilations` 和 `prompt_compilation_blocks`；快照包含块 key、内容、优先级、required、Token、来源、是否采用及原因。
- 场景分析和一致性检查分别强制校验规定字段；规划强制校验事件顺序、保留/修改/新增内容、插入点、人物变化和结束状态；Schema 不完整时不入库。

### 6. 上下文裁剪规则

- 先从模型上下文中预留输出 Token，再按 1–15 的既定优先级选择完整块。
- 系统规则、用户明确要求、当前完整原文、必须保留事件和结束状态标记为 required，不允许删除或截断。
- 当前场景单块无法容纳时抛出 `SceneTooLongError`，要求先切为子场景；不会截断拼接后的总字符串。
- 可选块超预算时整块移除并记录 `dropped_over_budget`。
- 滑动窗口固定使用上一场景最新改写结尾、当前场景完整原文和下一场景原文预览。
- 检索顺序为手动指定 → 结构 → 关键词 → 关系 → 向量补充；手动素材/角色优先，编译后回写是否实际进入提示词。

### 7. 角色卡 UI 调整内容

- 页面改为文档库同层级顶部栏、反馈区和 `210px / 自适应 / 310px` 三栏结构。
- 左栏提供公共/工程范围、工程选择器、全部/未分析/无标签、自定义标签和数量。
- 中央卡片仅承担浏览、单击选择和双击编辑；移除常驻操作，统一搜索、Hover、选择、加载和空状态。
- 右栏改为固定“角色详情”标题、滚动稳定设定内容和固定底部编辑/复制/AI/删除操作；删除使用危险样式和原生二次确认。
- 动态剧情状态没有加入角色编辑器；角色详情补充来源、来源版本、范围、分析状态和更新时间。

### 8. 素材库 UI 调整内容

- 页面使用与文档库相同的顶部栏、反馈区和三栏框架；保留导入、AI 提取和新建主操作。
- 左栏按公共/工程、工程选择器、大纲/剧情骨架/小素材、状态和自定义标签分组并显示数量。
- 中央保留文本卡片及工程时间线；两种视图共用边框、圆角、Hover、选择和详情语义。
- 右栏默认把事件节点、条件、剧情维度、影响等递归转换为可读文本；原始 JSON 只在“查看结构数据/高级编辑”次级入口出现。
- 导入、提取和编辑使用统一对话框；AI 提取结果支持逐项选择后保留，未选结果使用既有软删除。

### 9. 文档库未发生视觉变化的验证结果

- `desktop/src/pages/DocumentLibraryPage.tsx` 的 Git diff 为空。
- 在 Chromium、1440×900、相同空数据库状态下生成前后截图。
- `document-library-before.png` 与 `document-library-after.png` 的 SHA-256 均为 `7D98CF0910E908991E8DE235A4AFB81E599E3AC11CE6F3ADDCE790B9C205864C`，PNG 字节完全一致。
- 证据位于 `docs/visual-regression/`：文档库、角色卡、素材库各有 before/after 共六张截图。

### 10. 测试结果

- 后端全量：`python -m pytest tests -q`，最终 94 项通过（13.72 秒）。
- 专项：场景边界与确认、原文不可变、事实/角色动态分离、预算裁剪、必选块保护、滑动窗口、手动优先检索、两种模式确认、Schema 校验与定向修复均有自动化覆盖。
- Playwright Chromium：2 项、1.6 秒通过；覆盖公共/工程切换、未分析筛选、选择与详情、双击编辑、删除确认取消、素材结构可读展示、工程时间线、无搜索结果和 1440px 横向溢出检查。
- UI 构建的 TypeScript 类型检查同时覆盖新增 API 请求/响应类型。

### 11. 构建结果

- `npm run build` 通过：`tsc --noEmit`、Vite production build（1599 modules）和 Electron TypeScript build 全部成功。
- 构建产物主 JS 约 306.68 kB（gzip 90.15 kB），主 CSS 约 117.61 kB（gzip 19.99 kB）。

### 12. 尚未完成或存在风险的部分

- 没有修改现有章级工作台的交互入口，以避免在未设计场景确认 UI 的情况下改变存量工程行为；场景级完整 API 和持久化流程已提供，但工作台仍需在后续产品迭代中接入边界调整、骨架确认和扩写计划确认界面。
- 分层检索的“向量”阶段目前使用本地词项相似度作为无外部向量库时的确定性回退；检索来源和置信度已记录，接入实际 embedding 后可替换该阶段，不影响前三级检索。
- Token 估算采用保守的本地估算器；它遵守不截断 required 块的安全边界，但不同模型的精确 Token 数会有少量偏差。
- AI 提取端到端成功依赖用户已配置且可访问的模型；本次离线回归验证了对话框、选择保存、错误反馈和禁用逻辑，未调用外部付费模型。
