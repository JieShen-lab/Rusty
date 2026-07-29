import { expect, test, type Page } from '@playwright/test';

async function mockWorkspace(page: Page, projectKind: 'rewrite' | 'branch' | 'legacy_extract') {
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
    } else if (path === '/api/projects/99/style-synthesis') {
      body = null;
    } else if (path === '/api/projects/99/branches' && route.request().method() === 'POST') {
      body = {
        id: 21,
        project_id: 99,
        parent_branch_id: null,
        name: '分支 A',
        branch_mode: 'open_continuation',
        downstream_strategy: 'replace',
        status: 'draft',
      };
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
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
  await expect(page.getByLabel('设定变更影响列表')).toBeVisible();
  await page.getByRole('button', { name: /目标骨架/ }).click();
  await expect(page.getByLabel('模块化细纲编辑器')).toBeVisible();
  await page.getByRole('button', { name: '插入事件' }).click();
  await expect(page.getByRole('textbox', { name: '事件 2' })).toBeVisible();
  await page.getByLabel('接缝审查').getByRole('button', { name: '确认' }).click();
  await expect(page.getByLabel('接缝审查')).toContainText('已确认');
});

test('扩写工程显示三种入口并可创建分支树节点', async ({ page }) => {
  await mockWorkspace(page, 'branch');
  await page.goto('/workspace/99');
  await expect(page.getByRole('button', { name: '从原文末尾续写' })).toBeVisible();
  await expect(page.getByRole('button', { name: '从指定节点建立分支' })).toBeVisible();
  await expect(page.getByRole('button', { name: '建立分支并接回原文' })).toBeVisible();
  await expect(page.getByLabel('分支树')).toContainText('原文');
  await page.getByRole('button', { name: '创建子分支' }).click();
  await expect(page.getByLabel('分支树')).toContainText('分支 A');
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
