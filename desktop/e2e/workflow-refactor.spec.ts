import { expect, test, type Page } from '@playwright/test';

const skeleton = {
  metadata: {},
  event_nodes: [{ id: 'event-1', order: 1, event_type: 'conflict', summary: '生成事件', participants: [], location: '', time_state: {}, causes: [], effects: [], locked: false, source_span: null, confidence: 1 }],
  causal_links: [], character_state_changes: [], location_changes: [], time_changes: [],
  object_changes: [], knowledge_changes: [], relationship_changes: [], foreshadowing: [],
  open_threads: [], resolved_threads: [], required_start_state: {}, required_end_state: {},
  editable_points: [], source_references: [],
};

function plotRun(projectKind: 'rewrite' | 'branch' | 'legacy_extract') {
  return {
    id: 31, project_id: 99, branch_id: projectKind === 'branch' ? 21 : null,
    generation_mode: projectKind === 'branch' ? 'open_continuation' : 'bounded_insert',
    output_topology: projectKind === 'branch' ? 'branch' : 'in_place',
    status: 'awaiting_skeleton', stage: 'confirm_target_skeleton',
    start_anchor: { anchor_type: 'chapter_start', chapter_id: 901 },
    return_anchor: projectKind === 'rewrite' ? { anchor_type: 'chapter_end', chapter_id: 901 } : null,
    start_state: {}, required_return_state: {}, target_skeleton: skeleton, context: {},
    seams: [], issues: [], result: {}, scene_plan: {}, fact_ledger: {},
  };
}

async function mockWorkspace(page: Page, projectKind: 'rewrite' | 'branch' | 'legacy_extract') {
  let branches: unknown[] = [];
  let lastPlotPayload: Record<string, unknown> | null = null;
  let storedSkeleton = structuredClone(skeleton);
  let skeletonVersion = 1;
  let skeletonStatus: 'draft' | 'confirmed' = 'confirmed';
  await page.route('http://127.0.0.1:8765/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path === '/api/projects/99') {
      body = {
        project: { id: 99, name: `${projectKind} project`, project_kind: projectKind, status: 'ready', current_stage: 'split', source_format: 'txt', total_chapters: 1, total_words: 20, completed_chapters: 0, book_title: 'Book', author: null, created_at: '', updated_at: '', progress: 0 },
        metadata: {},
        settings: { processing_mode: 'manual' },
        exports: [],
      };
    } else if (path === '/api/projects/99/chapters') {
      body = [{ id: 901, project_id: 99, index: 1, title: '第一章', original_text: '人物进入院子。', rewritten_text: null, word_count: 8, status: 'imported', start_line: 1, end_line: 1 }];
    } else if (path === '/api/chapters/901') {
      body = { chapter: { id: 901, project_id: 99, index: 1, title: '第一章', original_text: '人物进入院子。', rewritten_text: null, word_count: 8, status: 'imported', start_line: 1, end_line: 1 }, ai_outputs: { plot_summary: '', plot_characters: [], style_analysis: null, reviewed_style_analysis: null, style_analysis_status: null }, stage_statuses: [], errors: [] };
    } else if (path === '/api/chapters/901/rewrite-versions') {
      body = [{
        id: 1001, project_id: 99, chapter_id: 901, version: 1,
        parent_version_id: null, source_kind: 'ai', source_operation: 'plot_generation',
        source_run_id: 30, source_base_kind: 'original', source_base_version_id: null,
        source_hash: 'source-hash', rewritten_text: '人物进入院子。伏击结束。',
        content_hash: 'content-hash', facts_before: {}, facts_after: {},
        created_at: '2026-08-10T00:00:00', is_current: true,
      }];
    } else if (path === '/api/chapter-rewrite-versions/1001/anchors') {
      body = [{
        id: 1101, rewrite_version_id: 1001, segment_kind: 'scene',
        source_scene_id: 801, skeleton_version_id: null, node_id: null,
        segment_index: 0, start_offset: 0, end_offset: 16,
        mapping_method: 'semantic', confidence: 0.72, needs_remap: false,
        state_method: 'inherited_scene_chain', state_before: { location: '院门' },
        state_after: { location: '院子' }, facts_before: { location: '院门' },
        facts_after: { location: '院子' },
      }];
    } else if (path === '/api/chapter-rewrite-versions/1001/skeleton') {
      body = {
        rewrite_version_id: 1001,
        skeleton_id: 701,
        skeleton_version_id: 701 + skeletonVersion,
        structured: storedSkeleton,
        source_kind: 'rewrite_version',
        status: skeletonStatus,
      };
    } else if (path === '/api/story-anchors/preview' && route.request().method() === 'POST') {
      body = {
        resolved_version_id: 1001, resolved_start: 0, resolved_end: 16,
        text_excerpt: '人物进入院子。伏击结束。',
        state_before: { location: '院门' }, state_after: { location: '院子' },
        mapping_method: 'semantic', state_method: 'inherited_scene_chain',
        confidence: 0.72, semantic_map_hash: 'map-hash',
      };
    } else if (path === '/api/projects/99/style-synthesis') {
      body = null;
    } else if (path === '/api/projects/99/branches') {
      body = branches;
    } else if (path === '/api/chapters/901/scenes') {
      body = [{ id: 801, project_id: 99, chapter_id: 901, parent_scene_id: null, scene_index: 1, title: '院门场景', original_start_offset: 0, original_end_offset: 8, original_text: '人物进入院子。', source_version: 1, boundary_reasons: [], boundary_status: 'confirmed', scene_type: 'action', user_confirmed: true, confirmed_at: '' }];
    } else if (path === '/api/chapters/901/story-skeleton') {
      body = { format: 'structured', skeleton_id: 701, version: skeletonVersion, version_id: 701 + skeletonVersion, status: skeletonStatus, structured: storedSkeleton };
    } else if (path === '/api/story-skeletons/701/versions' && route.request().method() === 'POST') {
      storedSkeleton = route.request().postDataJSON().structured_skeleton;
      skeletonVersion += 1;
      skeletonStatus = 'draft';
      body = { skeleton_id: 701, version_id: 701 + skeletonVersion, version: skeletonVersion, status: skeletonStatus, nodes: storedSkeleton.event_nodes, structured: storedSkeleton };
    } else if (path.startsWith('/api/story-skeletons/701/confirm') && route.request().method() === 'POST') {
      skeletonStatus = 'confirmed';
      body = { skeleton_id: 701, version_id: 701 + skeletonVersion, version: skeletonVersion, status: skeletonStatus, nodes: storedSkeleton.event_nodes, structured: storedSkeleton };
    } else if (path === '/api/plot-generation/runs' && route.request().method() === 'POST') {
      lastPlotPayload = route.request().postDataJSON();
      body = plotRun(projectKind);
      if (projectKind === 'branch') branches = [{
        id: 21,
        project_id: 99,
        parent_branch_id: null,
        name: '分支 A',
        branch_mode: 'open_continuation',
        downstream_strategy: 'replace',
        status: 'draft',
      }];
    } else if (path === '/api/canon-change/runs' && route.request().method() === 'POST') {
      body = {
        id: 41, project_id: 99, branch_id: null, effective_order: 1, status: 'review',
        old_fact: { value: '旧设定' }, new_fact: { value: '新设定' }, fact_ledger: {},
        consistency_issues: [],
        patches: [{
          id: 51, run_id: 41, route_kind: 'chapter', target_id: 901,
          source_range: { start: 0, end: 2 }, source_hash: 'hash',
          original_text: '旧设定', replacement_text: '新设定',
          impact_type: 'direct_fact', reason: '事实变化', confidence: 0.99,
          evidence: ['旧设定'], requires_confirmation: true, status: 'draft',
        }],
      };
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  return { getLastPlotPayload: () => lastPlotPayload };
}

test('新建页只显示改写工程和扩写工程', async ({ page }) => {
  await page.route('http://127.0.0.1:8765/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path === '/api/models'
      ? [{ id: 1, display_name: 'Model', provider: 'openai_compatible', base_url: '', model_name: 'fake', is_default: true, created_at: '', updated_at: '' }]
      : path === '/api/prompts'
        ? [{ id: 1, name: 'Rewrite', global_rules: '', summary_rules: '', rewrite_rules: '', description: '', scene_rules: [], story_anchor: {}, characters: [], package_metadata: {}, version: 1, is_default: true, created_at: '', updated_at: '' }]
        : [{ id: 2, name: 'Analysis', description: '', analysis_dimensions: '', evidence_rules: '', synthesis_rules: '', output_requirements: '', version: 1, is_default: true, created_at: '', updated_at: '' }];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/new-project');
  await expect(page.getByRole('button', { name: /改写工程/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /扩写工程/ })).toBeVisible();
  await expect(page.getByText('提取工程')).toHaveCount(0);
});

test('改写工程提供三种操作、模块化细纲、接缝与补丁选择', async ({ page }) => {
  await mockWorkspace(page, 'rewrite');
  await page.goto('/workspace/99');
  await expect(page.getByRole('button', { name: '增加剧情' })).toBeVisible();
  await expect(page.getByRole('button', { name: '重写正文' })).toBeVisible();
  await page.getByRole('button', { name: '修改设定' }).click();
  await page.getByLabel('旧设定').fill('旧设定');
  await page.getByLabel('新设定').fill('新设定');
  await page.getByRole('button', { name: '扫描下游影响' }).click();
  await expect(page.getByLabel('设定变更影响列表')).toBeVisible();
  await page.getByRole('button', { name: '增加剧情' }).click();
  await page.getByLabel('新增剧情目标').fill('增加一场冲突');
  await page.getByRole('button', { name: '启动分析' }).click();
  await expect(page.getByLabel('模块化细纲编辑器')).toBeVisible();
  await page.getByRole('button', { name: '插入事件' }).click();
  await expect(page.getByRole('textbox', { name: '事件 2' })).toBeVisible();
});

test('正文版本可查看并作为新工作流的显式来源', async ({ page }) => {
  const state = await mockWorkspace(page, 'rewrite');
  await page.goto('/workspace/99');
  const versions = page.getByLabel('rewrite versions');
  await expect(versions).toContainText('v1');
  await versions.getByRole('button', { name: '基于此版本创建新操作' }).click();
  await page.getByLabel('插入点节点类型').selectOption('scene_end');
  await page.getByRole('button', { name: '预览锚点' }).first().click();
  await expect(page.getByLabel('插入点锚点预览')).toContainText('人物进入院子');
  await expect(page.getByLabel('插入点锚点预览')).toContainText('建议确认');
  await page.getByLabel('新增剧情目标').fill('从历史版本派生');
  await page.getByRole('button', { name: '启动分析' }).click();
  expect(state.getLastPlotPayload()?.source).toEqual({ kind: 'rewrite_version', version_id: 1001 });
});

test('扩写工程显示三种入口并可创建分支树节点', async ({ page }) => {
  await mockWorkspace(page, 'branch');
  await page.goto('/workspace/99');
  await expect(page.getByRole('button', { name: '从原文末尾续写' })).toBeVisible();
  await expect(page.getByRole('button', { name: '从指定节点建立分支' })).toBeVisible();
  await expect(page.getByRole('button', { name: '建立分支并接回原文' })).toBeVisible();
  await expect(page.getByLabel('分支树')).toContainText('原文');
  await page.getByLabel('剧情目标').fill('继续新的路线');
  await page.getByRole('button', { name: '启动分析并创建分支' }).click();
  await expect(page.getByLabel('分支树')).toContainText('分支 A');
});

test('统一锚点选择器提交真实场景和细纲节点', async ({ page }) => {
  const state = await mockWorkspace(page, 'branch');
  await page.goto('/workspace/99');
  await page.getByRole('button', { name: '从指定节点建立分支' }).click();
  await page.getByLabel('起点节点类型').selectOption('scene_end');
  await expect(page.getByLabel('起点场景')).toContainText('院门场景');
  await page.getByLabel('剧情目标').fill('从院门场景建立新路线');
  await page.getByRole('button', { name: '启动分析并创建分支' }).click();
  expect(state.getLastPlotPayload()?.start_anchor).toEqual({ anchor_type: 'scene_end', scene_id: 801 });
});

test('模块化细纲核心模块可编辑、保存确认并重新加载', async ({ page }) => {
  await mockWorkspace(page, 'rewrite');
  await page.goto('/workspace/99');
  await page.getByRole('button', { name: '重写正文' }).click();
  await page.getByLabel('源细纲').click();
  const editor = page.getByLabel('模块化细纲编辑器');
  await editor.getByRole('textbox', { name: '事件 1' }).fill('修改后的事件摘要');
  await editor.getByRole('button', { name: '新增人物状态变化' }).click();
  await editor.getByLabel('人物状态变化 1 人物').fill('主角');
  await editor.getByLabel('人物状态变化 1 属性').fill('勇气');
  await editor.getByLabel('人物状态变化 1 变化后').fill('坚定');
  await editor.getByRole('button', { name: '新增物品变化' }).click();
  await editor.getByLabel('物品变化 1 物品').fill('钥匙');
  await editor.getByLabel('物品变化 1 变化').fill('被取得');
  await editor.getByRole('button', { name: '新增知识变化' }).click();
  await editor.getByLabel('知识变化 1 事实').fill('密门存在');
  await editor.getByRole('button', { name: '新增关系变化' }).click();
  await editor.getByLabel('关系变化 1 变化').fill('从怀疑到信任');
  await editor.getByRole('button', { name: '新增伏笔' }).click();
  await editor.getByLabel('伏笔 1 内容').fill('钥匙上的刻痕');
  const start = editor.getByLabel('开始状态编辑器');
  await start.getByRole('button', { name: '增加字段' }).click();
  await start.getByLabel('开始状态 字段1', { exact: true }).fill('院子');
  const end = editor.getByLabel('结束状态 / 回接条件编辑器');
  await end.getByRole('button', { name: '增加字段' }).click();
  await end.getByLabel('结束状态 / 回接条件 字段1', { exact: true }).fill('客栈');
  await page.getByRole('button', { name: '保存并确认细纲版本' }).click();
  await expect(editor.getByLabel('细纲版本信息')).toContainText('v2 · 已确认');
  await page.reload();
  await page.getByRole('button', { name: '重写正文' }).click();
  await page.getByLabel('源细纲').click();
  await expect(page.getByRole('textbox', { name: '事件 1' })).toHaveValue('修改后的事件摘要');
  await expect(page.getByLabel('人物状态变化 1 变化后')).toHaveValue('坚定');
  await expect(page.getByLabel('结束状态 / 回接条件 字段1', { exact: true })).toHaveValue('客栈');
});

test('legacy_extract 显示只读兼容提示和迁移入口', async ({ page }) => {
  await mockWorkspace(page, 'legacy_extract');
  await page.goto('/workspace/99');
  await expect(page.getByText('此项目属于旧版分析工程。')).toBeVisible();
  await expect(page.getByText(/当前工作区只读/)).toBeVisible();
  await expect(page.getByRole('button', { name: '导出已有分析' })).toBeVisible();
  await expect(page.getByRole('button', { name: '基于此项目创建新工程' })).toBeVisible();
  await expect(page.getByRole('button', { name: /继续运行/ })).toHaveCount(0);
});
