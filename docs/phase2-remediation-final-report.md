# Rusty 第二阶段整改最终报告

基线：`c43e4766debfdd131ae5356c325dce33fcb50557`
分支：`codex/phase2-remediation`

## 1. 修改文件

- 模型上下文：`src/rusty/services/context_service.py`、`prompt_compiler.py`、`scene_rewrite_orchestrator.py`
- 场景边界：`backend/schemas.py`、`backend/api.py`、`scene_service.py`、新增 `scene_boundary_ai_service.py`
- 文档 offset：`document_library_service.py`、`desktop/src/pages/DocumentLibraryPage.tsx`
- 角色封面：`anchor_service.py`
- 素材分析：`resource_analysis_service.py`、`MaterialLibraryPage.tsx`
- 工作台：`ProjectWorkspacePage.tsx`、`desktop/src/api/client.ts`、`types.ts`
- 回归：新增 `tests/test_phase2_contract_regressions.py`，更新 `desktop/e2e/phase2.spec.ts`

## 2. 数据迁移

本轮没有新增数据库列或表，因此没有新增迁移。已有 v15/v16 迁移保持不变；场景历史、模型调用、封面相对路径和旧素材兼容逻辑未删除。

## 3. 场景阶段提示词

`ContextService.compile_scene_context` 新增独立块：`stage_task`、`scene_analysis`、`confirmed_skeleton`、`rewrite_plan`、`material_mappings`、`scene_reference_constraints`、`candidate_rewrite_text`、`consistency_result`、`repair_source_text`、`repair_targets`。每块继续保存 `block_key/source_type/source_id/token_count/included/decision/priority/required`。

`PromptCompiler.compile_scene_stage` 按阶段校验必需块。`SceneRewriteOrchestrator._check_and_repair` 从 `scene_rewrite_versions` 读取真实正文；连续修复以最新结果版本为父版本，复查读取真实修复后正文。

测试：`test_scene_stage_messages_contain_complete_unique_inputs_and_repair_chain`、`test_planning_prompt_contains_material_mapping_and_stable_insertion`；QueueAI messages 断言独特分析、骨架、规划、候选正文、修复正文和段落范围。

## 4. 场景边界协议与 AI 切分

`SceneBoundaryItem` 统一前后端范围对象。`SceneService._validate_range_items` 拒绝空列表、乱序、空洞、重叠、越界和未完整覆盖；保存标题、原因、原文切片及序号，旧活动场景软删除。

`SceneBoundaryAIService.analyze` 通过 `StructuredModelService` 调用绑定/默认模型，发送完整章节并校验严格 Schema。结果仅保存为 proposed；已确认边界不被覆盖。启发式切分仅在 `source=heuristic` 使用。

测试：`test_ai_scene_boundaries_call_model_and_preserve_confirmed_ranges`、`test_fastapi_scene_boundary_object_contract_and_validation`。

## 5. 精确章节 offset

`DocumentLibraryService.get_content/save_content` 优先使用合法 `start_offset/end_offset`，旧数据才回退行号。章节编辑生成新 revision，当前章节更新 end offset，后续章节按 delta 平移，并复制标题和顺序；不再调用 `parse_txt` 丢失人工目录。`mark_chapter` 检查标题、越界、重复/重叠，并按 offset 重排索引。

测试：`test_exact_same_line_chapter_offsets_survive_edit_and_shift_following_chapter`。

## 6. 角色封面复制与清理

`AnchorService.copy_character_card` 读取受控源封面字节并调用 `save_character_cover` 为副本生成独立路径；失败时删除未完成副本。`delete_character_card` 软删除后仅清理没有活动引用且位于受控目录内的文件。

测试：`test_character_cover_copy_is_independent_and_delete_cleans_only_own_file`。

## 7. 资源选择器与版本恢复

`SceneRewritePanel` 用可搜索、多选的角色、剧情骨架和场景素材选择器替代数据库 ID 输入。剧情骨架和场景素材按类型分离；插入位置为 `__start__`、确认骨架 node id 或 `__end__`。后端验证类型、工程可见范围、删除状态和节点存在性。

版本历史显示版本、时间、模式、父版本、修复状态和预览，支持与原文/上一版本对比及二次确认恢复。恢复创建 `revision_kind=restore` 新版本，不覆盖历史。

## 8. 动态风格上下文

`build_style_context` 读取项目绑定 style template、rewrite prompt、场景规则和 style profile 示例；示例按文本相关性取前三。近期技术先从原始序列统计重复，再生成去重展示，修复了“先去重导致 forbidden_repetitions 永远为空”的错误。

测试：`test_bound_style_rules_examples_and_recent_repetition_enter_context`。

## 9. dirty guard

`DocumentLibraryPage.confirmDiscardDirty` 统一保护章节/文档切换、工作台关闭、文字整理、引用范围、恢复版本、正则/AI 分章及会刷新正文的操作。保存按钮等待 API 成功后才清 dirty；失败保留 dirty。

E2E：`未保存正文取消切换后仍保留编辑内容`。

## 10. 重新分析与 AI 提取

角色和素材在已分析状态下重新分析前显示确认。素材分析改为 `propose_material_analysis → 预览 → apply_material_analysis`，用户确认前不覆盖结构化内容。

AI 提取候选在正式保存前可改名称、两类素材类型、摘要和标签；确认时以选定类型新建正式记录并删除临时候选，取消时清理候选。

## 11. 自动化结果

- `python -m pytest tests -q -p no:cacheprovider`：`110 passed in 15.03s`
- `npm run build`：TypeScript、Vite（1599 modules）和 Electron TypeScript 构建通过
- `npm run test:e2e`：`7 passed (4.2s)`
- `npm ci`：前两次因 Electron 二进制下载 `ECONNRESET` 失败；保持 lockfile 不变并设置 `ELECTRON_SKIP_BINARY_DOWNLOAD=1` 后成功安装 263 packages

## 12. 文档库视觉回归

未修改任何既有 `.document-*` CSS 值；`styles/index.css` 仅新增 `.scene-resource-picker` 和 `.scene-diff`。既有 `docs/visual-regression/document-library-before.png` 与 `document-library-after.png` 未变化；Playwright 1440×900 无横向溢出测试通过。

## 13. 风险

- Playwright 使用确定性 API 路由验证前端状态机；真实接口契约由 FastAPI TestClient 覆盖，第三方模型供应商仍依赖用户模型配置、密钥和网络。
- AI 提取沿用现有“先创建临时候选、确认时重建正式记录”的兼容路径；取消和保存会清理临时候选，但进程在清理前异常终止时可能留下可见临时记录。
- 本轮未自动生成新的视觉截图；沿用且未改动已有文档库前后基线图，代码 diff 证明 `.document-*` 值未变化。
