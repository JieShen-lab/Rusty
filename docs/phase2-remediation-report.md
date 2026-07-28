# Rusty 第二阶段整改实施报告

基线：`2d201c67fe5bb83cc80ae77824f960dd80876cc9`  
分支：`codex/phase2-remediation`

## 1. 修改文件

- 数据库与后端：`src/rusty/db/schema.py`、`backend/schemas.py`、`backend/api.py`。
- 新服务：`structured_model_service.py`、`resource_analysis_service.py`、`document_split_ai_service.py`、`scene_rewrite_orchestrator.py`。
- 既有服务：`material_service.py`、`anchor_service.py`、`context_service.py`、`document_library_service.py`、`rewrite_workflow_service.py`。
- 前端：`api/client.ts`、`api/types.ts`、角色/素材/文档/工程工作台四个页面及 `styles/index.css`。
- 测试：`tests/test_phase2_remediation.py`、`desktop/playwright.config.ts`、`desktop/e2e/phase2.spec.ts`、`desktop/package.json`。

## 2. 数据迁移

`schema.py::_migrate_to_v16` 将版本提升到 v16，新增 `model_invocations`、`document_split_proposals`、`scene_workflow_runs`。迁移不删除 v15 表或字段。旧角色的 `description/personality/speech_style/action_constraints/anti_ooc_rules/relationship_notes/profile_json` 非空值追加到 `custom_fields_json`，旧列继续保留。测试 `test_v16_maps_nonempty_legacy_character_fields_to_custom_fields` 验证旧值可读。

## 3. 素材类型修正

`MaterialService` 和 `MaterialLibraryPage` 的正常产品类型仅为 `scene_reference`、`plot_skeleton`。前端删除 outline 筛选、创建项和 `material_kind` 模拟；“小素材”改为“场景素材”；移除时间线切换及主视图。`import_json_items` 将旧 `outline` 映射为 `plot_skeleton`，并在 `import_metadata.legacy_material_type` 保留来源。`MaterialUpdateRequest` 禁止额外字段，更新接口不能提交 `material_type`。

## 4. 角色固定字段迁移

`CharacterLibraryPage::CharacterEditor` 新建和编辑只呈现角色名、身份、年龄、设定四个固定字段；年龄继续使用字符串。其余旧字段由 v16 迁移到有序自定义属性。保存时角色名为空被阻止；身份、年龄或设定为空时显示“返回补充 / 仍然保存”的非阻断确认。

## 5. 封面文件管理

`AnchorService.save_character_cover/remove_character_cover/character_cover_file` 校验 PNG/JPEG/WebP 签名、5 MiB 上限和可读取图片的 4096 像素尺寸上限；文件复制到数据库目录下 `assets/character-covers`，数据库保存受控相对路径。替换和移除仅清理不再引用的受管文件。前端提供上传、替换、移除、预览；无图片时按角色名生成稳定首字封面。

## 6. 标签功能

角色和素材页面支持标签创建、重命名、删除、点击筛选、多选绑定和解除。服务端规范化标签名并拒绝重复；删除标签只删除关联。测试 `test_tag_rename_delete_only_changes_associations` 验证素材不被删除。

## 7. AI 分析调用流程

`StructuredModelService.run` 解析当前工程模型或默认模型，分离 system/user 消息，保存请求、输出 Schema、模型 ID、响应、解析值、验证结果、Token、耗时和错误。首次 JSON/Schema 失败执行一次格式修复；仍失败则抛错，资源服务不会覆盖旧分析。

`ResourceAnalysisService` 分别校验场景素材、剧情骨架和角色卡 Schema。角色分析返回 proposal、保留已有非空字段的 merged 值以及 conflicts，前端确认后才调用保存接口。测试 `test_real_material_analysis_repairs_schema_and_keeps_audit`、`test_character_analysis_preserves_existing_fields_and_reports_conflict` 使用 mock 模型验证。

## 8. JSON 导入

`MaterialLibraryPage::JsonImportDialog` 支持 `.json` 文件或高级输入框、对象或数组、提交前类型/名称/标签预览。`MaterialService.import_json_items` 逐项校验并返回 imported/errors，非法项不回滚合法项。普通文字使用单独“导入原始文字”，保存为 `unanalyzed`，不调用模型。

## 9. 文档分章和手动标记

`DocumentSplitAIService.preview` 调用模型生成连续、无重叠、完整覆盖正文的边界并只保存草案；`apply` 再校验用户编辑结果，通过 `DocumentLibraryService.apply_split_boundaries` 创建新 revision，源 revision 不修改。

`DocumentLibraryPage` 用标准对话框替换合并、新增章节、正则分章的 prompt。合并支持多选、顺序调整和新标题；正则预览显示数量、标题、offset、字数和未匹配区间。正文编辑器提供手动开始/结束标记、取消、标题确认、dirty/保存状态、离开与切章提醒、撤销/重做。选区菜单保持三个并列入口并改用轻量名称对话框。

## 10. 场景级模型编排

`SceneRewriteOrchestrator` 执行分析、骨架提取、规划、正文、一致性检查和按需定向修复。每个阶段先调用 `ContextService.compile_scene_context`，再调用 `PromptCompiler.compile_scene_stage`，最后经 `StructuredModelService` 调用模型并记录快照。骨架未确认时不能生成规划；规划未确认时不能生成正文。扩写模式只允许剧情骨架素材产生新增事件，场景素材只进入写法参考。

测试 `test_scene_orchestrator_enforces_confirmation_gates_and_executes_models` 验证五次 mock 模型调用、两道确认门禁、版本保存和历史读取。

## 11. 工作台接入

`ProjectWorkspacePage::SceneRewritePanel` 提供场景列表、原文边界预览、offset 手动调整、边界确认、两种模式、骨架 JSON 编辑、角色卡 ID、两类素材选择、扩写插入位置、规划预览、三段确认、执行状态、一致性结果和版本历史。改写版本独立保存，原文不覆盖；上下文服务继续把上一场景最新改写尾部送入下一场景。

## 12. 已修复逻辑错误

- `ContextService.retrieve` 用 `chapter.chapter_index` 判断素材章节范围，不再用 `scene.scene_index`。
- 空 `user_instruction` 编译为“按已确认的计划执行，不添加额外用户偏好。”必选块。
- `RewriteWorkflowService.build_chapter_check` 检查相邻状态、位置、伤势、物品、知识、视角、重复和节奏。
- `build_book_check` 检查未闭合伏笔、物品多持有人、知识消失、时间倒序、关系突变、能力冲突、技法重复及需回读场景。
- 工程选区创建素材默认进入当前工程；文档选区默认进入公共库；均保存来源版本和选区快照。

## 13. 后端测试结果

命令：`python -m pytest tests -q`  
结果：`103 passed in 13.04s`。专项测试文件包含 9 项，覆盖类型迁移、类型不可修改、模型修复审计、角色迁移、封面、标签、空指令、AI 分章和完整场景编排。

## 14. 前端测试结果

`package.json` 已加入 `test:e2e`、`test:e2e:ui`；`playwright.config.ts` 固定 Chromium、1440×900 和本地 Vite 服务。`phase2.spec.ts` 使用 API mock 覆盖两类素材、JSON 导入预览、AI 分析、角色空字段/自定义属性/封面入口、文档无横向溢出、正文三个右键入口、手动标记/AI 分章入口和场景三段确认。结果：`6 passed (3.7s)`。

Browser 插件在当前环境不可用，按前端测试技能说明使用仓库内 Playwright。

## 15. 构建结果

命令：`npm run build`  
结果：TypeScript、Vite 生产构建和 Electron TypeScript 构建全部通过；Vite 转换 1599 个模块。

## 16. 文档库视觉回归

`docs/visual-regression/document-library-before.png` 与 `document-library-after.png` 均为 1440×900，SHA-256 相同。第二阶段没有修改任何既有 `.document-*` 声明值、三栏宽度、卡片、颜色、间距或详情结构；新增 CSS 使用新的功能类。Playwright 的文档库 1440×900 检查确认无横向溢出。

## 17. 仍未完成或存在风险

- Playwright 使用确定性 API mock 验证前端状态机；真实第三方模型端到端调用仍取决于用户模型密钥、供应商兼容性和网络。
- 文件选择器由 Electron preload 提供，浏览器 E2E 覆盖了 JSON 粘贴路径；原生操作系统文件选择器未自动化。
- 角色/素材“AI 提取”沿用现有先创建候选、再删除未选择项的服务语义；页面支持选择保留，但候选名称和标签的逐项内联修改仍通过保存后编辑完成。
- 全书检查基于结构化账本的确定性规则发现风险；涉及隐喻、复杂时间跳跃或隐性知识的判断仍需要模型或人工复核。
