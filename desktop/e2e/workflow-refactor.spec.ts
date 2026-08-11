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
  let workflowState = { chapter_id: 901, chapter_index: 1, title: '第一章', active_scene_id: 801, current_stage: 'preanalysis', updated_at: '2026-08-11T10:00:00' };
  let preanalysis: Record<string, unknown> | null = null;
  let intent: Record<string, unknown> | null = null;
  let characterAnalysis: Record<string, unknown> | null = null;
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
      body = [{ id: 901, project_id: 99, index: 1, title: '第一章', original_text: '张三退到了墙边。\n要不是因为他挡在这里，王五早已经走了。\n刚刚挡下攻击的人握紧了长刀。', rewritten_text: null, word_count: 42, status: 'imported', start_line: 1, end_line: 3 }];
    } else if (path === '/api/projects/99/creative-workflow') {
      body = [workflowState];
    } else if (path === '/api/chapters/901/creative-workflow') {
      if (route.request().method() === 'PUT') {
        const request = route.request().postDataJSON() as { current_stage: string; active_scene_id: number | null };
        workflowState = { ...workflowState, current_stage: request.current_stage, active_scene_id: request.active_scene_id, updated_at: '2026-08-11T10:01:00' };
      }
      body = workflowState;
    } else if (path === '/api/projects/99/characters') {
      body = { character_cards: [{ id: 501, name: '李四', aliases: [], description: '使用剑，行动敏捷', priority: 50, is_main: true, relationship_notes: '', personality: '谨慎', speech_style: '', action_constraints: '优先闪避', anti_ooc_rules: '', profile: {}, source_metadata: {}, import_metadata: {}, scope: 'project', project_id: 99, source_character_card_id: null, source_version: null, version: 1, sort_order: 0, identity: '剑客', age: '', setting_text: '李四使用剑。', custom_fields: [], raw_text: '', analysis_status: 'analyzed', cover_path: null, cover_updated_at: null, tags: [], category_ids: [], categories: [], source_summary: { kind: 'manual', label: '本地创建' }, created_at: '', updated_at: '' }] };
    } else if (path === '/api/projects/99/materials') {
      body = [];
    } else if (path === '/api/scenes/801/preanalysis/run') {
      preanalysis = { scene_id: 801, summary: '张三在墙边挡下攻击。', characters: ['张三', '王五'], location: '墙边', time: '当前', scene_type: '冲突', basic_events: ['张三退到墙边', '张三挡下攻击', '张三握紧长刀'], status: 'draft', user_edited: false, confirmed_at: null, updated_at: '2026-08-11T10:02:00' };
      body = preanalysis;
    } else if (path === '/api/scenes/801/preanalysis/confirm') {
      preanalysis = { ...(preanalysis ?? {}), status: 'confirmed', confirmed_at: '2026-08-11T10:03:00' };
      workflowState = { ...workflowState, current_stage: 'direction' };
      body = preanalysis;
    } else if (path === '/api/scenes/801/preanalysis') {
      if (route.request().method() === 'PUT') preanalysis = { ...(route.request().postDataJSON() as Record<string, unknown>), scene_id: 801, status: 'draft', user_edited: true, confirmed_at: null, updated_at: '2026-08-11T10:02:30' };
      body = preanalysis;
    } else if (path === '/api/scenes/801/creative-intent') {
      if (route.request().method() === 'PUT') intent = { ...(route.request().postDataJSON() as Record<string, unknown>), scene_id: 801, status: 'draft', updated_at: '2026-08-11T10:04:00' };
      body = intent;
    } else if (path === '/api/scenes/801/character-modification-analysis/run') {
      characterAnalysis = {
        scene_id: 801, source_character: '张三', target_character_card_id: 501, target_character_name: '李四', status: 'draft', user_edited: false, confirmed_at: null, updated_at: '2026-08-11T10:05:00',
        explicit_mentions: [{ id: 'explicit-1', summary: '张三退到墙边', source_text: '张三退到了墙边。', start_offset: 0, end_offset: 8, inferred: false }],
        implicit_references: [{ id: 'implicit-1', summary: '“他”指张三', source_text: '要不是因为他挡在这里', start_offset: 9, end_offset: 20, inferred: true }],
        actions: [], dialogue: [], states: [],
        objects: [{ id: 'object-1', summary: '张三持有长刀', source_text: '刚刚挡下攻击的人握紧了长刀。', start_offset: 34, end_offset: 49, inferred: true }],
        spatial_relations: [], related_events: [],
        target_character_conflicts: [{ id: 'conflict-1', summary: '武器存在差异', source_text: '握紧了长刀', start_offset: 43, end_offset: 49, inferred: false, source_state: '张三使用长刀', target_state: '李四使用剑', difference: '存在差异' }],
      };
      body = characterAnalysis;
    } else if (path === '/api/scenes/801/character-modification-analysis/confirm') {
      characterAnalysis = { ...(characterAnalysis ?? {}), status: 'confirmed', confirmed_at: '2026-08-11T10:06:00' };
      workflowState = { ...workflowState, current_stage: 'target_design' };
      body = characterAnalysis;
    } else if (path === '/api/scenes/801/character-modification-analysis') {
      if (route.request().method() === 'PUT') characterAnalysis = { ...(route.request().postDataJSON() as Record<string, unknown>), status: 'draft', user_edited: true, updated_at: '2026-08-11T10:05:30' };
      body = characterAnalysis;
    } else if (path === '/api/chapters/901') {
      body = { chapter: { id: 901, project_id: 99, index: 1, title: '第一章', original_text: '张三退到了墙边。\n要不是因为他挡在这里，王五早已经走了。\n刚刚挡下攻击的人握紧了长刀。', rewritten_text: null, word_count: 42, status: 'imported', start_line: 1, end_line: 3 }, ai_outputs: { plot_summary: '', plot_characters: [], style_analysis: null, reviewed_style_analysis: null, style_analysis_status: null }, stage_statuses: [], errors: [] };
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
      body = [{ id: 801, project_id: 99, chapter_id: 901, parent_scene_id: null, scene_index: 1, title: '墙边交锋', original_start_offset: 0, original_end_offset: 49, original_text: '张三退到了墙边。\n要不是因为他挡在这里，王五早已经走了。\n刚刚挡下攻击的人握紧了长刀。', source_version: 1, boundary_reasons: [], boundary_status: 'confirmed', scene_type: 'action', user_confirmed: true, confirmed_at: '' }];
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
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  return { getLastPlotPayload: () => lastPlotPayload };
}

test('新建页直接创建统一普通小说工程', async ({ page }) => {
  await page.route('http://127.0.0.1:8765/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path === '/api/models'
      ? [{ id: 1, display_name: 'Model', provider: 'openai_compatible', base_url: '', model_name: 'fake', is_default: true, created_at: '', updated_at: '' }]
      : path === '/api/prompt-definitions'
        ? [{ id: 1, name: '总规则', description: '', kind: 'master', workflow_key: null, task_key: null, content: '', input_description: '', is_default: true, created_at: '', updated_at: '' }]
        : [];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/new-project');
  await expect(page.getByRole('heading', { name: '导入文件' })).toBeVisible();
  await expect(page.getByRole('button', { name: /改写工程/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /扩写工程/ })).toHaveCount(0);
});

test('rewrite 工程进入章节中心三栏工作台', async ({ page }) => {
  await mockWorkspace(page, 'rewrite');
  await page.goto('/workspace/99');
  const chapterRail = page.getByLabel('章节导航');
  await expect(chapterRail).toContainText('第一章');
  await expect(chapterRail).not.toContainText('墙边交锋');
  await expect(page.getByRole('heading', { name: '场景' })).toBeVisible();
  await expect(page.getByRole('button', { name: /墙边交锋/ })).toBeVisible();
  await expect(page.getByLabel('章节创作阶段')).toContainText('预分析');
  await expect(page.getByRole('heading', { name: '当前上下文' })).toBeVisible();
  await expect(page.getByRole('button', { name: '场景改写' })).toHaveCount(0);
});

test('历史 branch 工程也进入同一工作台', async ({ page }) => {
  await mockWorkspace(page, 'branch');
  await page.goto('/workspace/99');
  await expect(page.getByLabel('章节导航')).toContainText('第一章');
  await expect(page.getByRole('heading', { name: '场景' })).toBeVisible();
  await expect(page.getByRole('button', { name: '继续写' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '写另一种发展' })).toHaveCount(0);
});

test('预分析、方向和人物专项分析形成可确认纵向流程', async ({ page }) => {
  await mockWorkspace(page, 'rewrite');
  await page.goto('/workspace/99');
  await page.getByRole('button', { name: '运行预分析' }).click();
  await expect(page.getByLabel('摘要')).toHaveValue('张三在墙边挡下攻击。');
  await page.getByRole('button', { name: '确认预分析' }).click();
  await expect(page.getByRole('heading', { name: '怎样处理这个场景？' })).toBeVisible();
  await page.getByRole('button', { name: /贴合原文/ }).click();
  await page.getByPlaceholder(/把张三替换成李四/).fill('把张三替换成李四，战斗过程尽量保留。');
  await page.getByRole('checkbox', { name: '李四' }).check();
  await page.getByRole('button', { name: '进入专项分析' }).click();
  await expect(page.getByRole('heading', { name: '贴合原文 / 人物修改' })).toBeVisible();
  await page.getByRole('button', { name: '运行人物专项分析' }).click();
  await expect(page.locator('input[value="张三退到墙边"]')).toBeVisible();
  await expect(page.locator('input[value="“他”指张三"]')).toBeVisible();
  await expect(page.locator('input[value="张三持有长刀"]')).toBeVisible();
  await expect(page.locator('input[value="存在差异"]')).toBeVisible();
  await page.getByRole('button', { name: '确认分析' }).click();
  await expect(page.getByRole('heading', { name: '目标设计' })).toBeVisible();
  await expect(page.getByText(/第二阶段实现/)).toBeVisible();
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
