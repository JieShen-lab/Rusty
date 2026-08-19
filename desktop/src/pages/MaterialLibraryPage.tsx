import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Clock, Folder, Plus, Search, Settings, Sparkles, Trash2, X } from 'lucide-react';
import {
  applyAuthorStyleDimension,
  applyMaterialExtraction,
  createMaterialCategory,
  deleteMaterialCategory,
  deleteMaterial,
  exportAuthorStyleSettings,
  getMaterialAISettings,
  getMaterialCategories,
  getMaterials,
  getModels,
  importAuthorStyleSettings,
  previewAuthorStyleDimension,
  previewMaterialExtraction,
  renameMaterialCategory,
  updateMaterial,
  updateMaterialAISettings,
} from '../api/client';
import type {
  Material,
  MaterialAIDimension,
  MaterialAISettings,
  MaterialCategory,
  MaterialType,
  ModelConfig,
} from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { LibraryContextMenu, LibraryDialog, LibraryEmptyState, LibrarySidebarItem, LibrarySidebarSectionTitle } from '../components/LibraryPrimitives';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

type Shelf = { kind: 'all' | 'recent' } | { kind: 'category'; categoryId: number };
type Launch = { materialType: MaterialType; selectedText: string; sourceMetadata?: Record<string, unknown> };

const TYPE_LABEL = '作者风格';
const MATERIAL_TYPE: MaterialType = 'author_style';
const MATERIAL_TASK = 'author_style_extraction' as const;

export function MaterialLibraryPage() {
  const type = MATERIAL_TYPE;
  const [shelf, setShelf] = useState<Shelf>({ kind: 'all' });
  const [query, setQuery] = useState('');
  const [materials, setMaterials] = useState<Material[]>([]);
  const [categories, setCategories] = useState<MaterialCategory[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editing, setEditing] = useState<Material | null>(null);
  const [launch, setLaunch] = useState<Launch | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [categoryMenu, setCategoryMenu] = useState<{ category: MaterialCategory; x: number; y: number } | null>(null);
  useAutoDismiss(error, setError, 6000);
  useAutoDismiss(message, setMessage);

  const load = useCallback(async (preferred?: number | null) => {
    setLoading(true);
    try {
      const [materialRows, categoryRows] = await Promise.all([getMaterials(), getMaterialCategories()]);
      setMaterials(materialRows);
      setCategories(categoryRows);
      setSelectedId((current) => {
        const wanted = preferred === undefined ? current : preferred;
        return materialRows.some((item) => item.id === wanted) ? wanted : null;
      });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const incoming = window.history.state?.materialExtraction as Launch | undefined;
    if (!incoming?.selectedText || !incoming.materialType) return;
    setShelf({ kind: 'all' });
    setLaunch(incoming);
    setCreateOpen(true);
    window.history.replaceState(null, '', window.location.href);
  }, []);

  const currentCategories = useMemo(
    () => categories.filter((item) => item.material_type === type),
    [categories, type],
  );
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return materials.filter((item) => {
      if (item.material_type !== type) return false;
      if (shelf.kind === 'category' && !item.category_ids.includes(shelf.categoryId)) return false;
      if (shelf.kind === 'recent' && !isRecent(item.created_at)) return false;
      return !needle || [item.name, item.description, item.tags.join(' '), item.categories.join(' ')]
        .join(' ').toLocaleLowerCase().includes(needle);
    });
  }, [materials, query, shelf, type]);
  const selected = materials.find((item) => item.id === selectedId && item.material_type === type) ?? null;

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try { await action(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  }

  async function addCategory() {
    const name = window.prompt(`新建${TYPE_LABEL}分类`)?.trim();
    if (!name) return;
    await run(async () => {
      const category = await createMaterialCategory(type, name);
      await load(selectedId);
      setShelf({ kind: 'category', categoryId: category.id });
    });
  }

  return (
    <div className="document-library-page material-library-page">
      <TopBar title="素材库" actions={(
        <>
          <PrimaryButton disabled={busy} onClick={() => { setLaunch(null); setCreateOpen(true); }}>
            <Plus size={16} />新建作者风格
          </PrimaryButton>
          <SecondaryButton aria-label="作者风格提取设置" className="icon-only" onClick={() => setSettingsOpen(true)}>
            <Settings size={16} />
          </SecondaryButton>
        </>
      )} />
      {error ? <div className="inline-alert error document-library-alert" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success document-library-alert" role="status">{message}</div> : null}

      <div className="document-library-layout material-browser-layout material-library-unified">
        <aside className="document-tag-panel material-library-sidebar">
          <nav aria-label="作者风格分类">
            <LibrarySidebarItem active={shelf.kind === 'all'} count={materials.filter((item) => item.material_type === type).length} icon={<Folder size={15} />} label="全部内容" onClick={() => setShelf({ kind: 'all' })} />
            <LibrarySidebarItem active={shelf.kind === 'recent'} count={materials.filter((item) => item.material_type === type && isRecent(item.created_at)).length} icon={<Clock size={15} />} label="最近导入" onClick={() => setShelf({ kind: 'recent' })} />
            <LibrarySidebarSectionTitle action={<button aria-label="新建分类" className="document-add-tag" onClick={() => void addCategory()} type="button"><Plus size={14} /></button>}>
              我的分类
            </LibrarySidebarSectionTitle>
            {currentCategories.map((category) => (
              <LibrarySidebarItem
                active={shelf.kind === 'category' && shelf.categoryId === category.id}
                count={category.resource_count}
                icon={<Folder size={15} />}
                key={category.id}
                label={category.name}
                onClick={() => setShelf({ kind: 'category', categoryId: category.id })}
                onContextMenu={(event) => { event.preventDefault(); setCategoryMenu({ category, x: event.clientX, y: event.clientY }); }}
              />
            ))}
          </nav>
        </aside>

        <main className="document-shelf-panel material-browser-shelf">
          <header>
            <label className="search-field document-search material-library-search">
              <Search size={15} /><span className="sr-only">搜索素材</span>
              <input onChange={(event) => setQuery(event.target.value)} placeholder="搜索作者风格、分类或标签" type="search" value={query} />
            </label>
          </header>
          {loading ? <LibraryEmptyState title="正在读取素材库…" /> : visible.length ? (
            <div className="document-shelf-scroll">
              <div className="document-shelf-grid material-book-grid" aria-label="作者风格列表">
                {visible.map((material) => (
                  <button
                    aria-pressed={selectedId === material.id}
                    className={`document-book ${selectedId === material.id ? 'selected' : ''}`}
                    key={material.id}
                    onClick={() => setSelectedId(material.id)}
                    onDoubleClick={() => setEditing(material)}
                    type="button"
                  >
                    <MaterialBookCover material={material} />
                    <strong className="document-book-title">{material.name}</strong>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <LibraryEmptyState action={<PrimaryButton onClick={() => setCreateOpen(true)}><Plus size={16} />新建作者风格</PrimaryButton>} description="可粘贴文本、使用文档选区或导入文本文件后由 AI 提取。" title="暂无作者风格" />
          )}
        </main>

        <aside className="document-detail-panel material-detail-panel">
          <header><h2>素材详情</h2></header>
          {selected ? (
            <>
              <div className="document-detail-scroll">
                <section className="document-detail-identity">
                  <MaterialBookCover compact material={selected} />
                  <div><h3>{selected.name}</h3><p>作者风格</p></div>
                </section>
                <section><div className="document-detail-heading"><span>概览</span></div><p className="material-detail-copy">{selected.description || contentSummary(selected)}</p></section>
                <section><div className="document-detail-heading"><span>标签</span></div><div className="document-detail-badges">{selected.tags.length ? selected.tags.map((name) => <span key={name}>{name}</span>) : <span>无标签</span>}</div></section>
                {selected.material_type === 'author_style' && 'legacy_scene_reference' in selected.content ? <div className="inline-alert">该素材来自旧版素材，可继续编辑或使用来源文本重新提取作者风格。</div> : null}
              </div>
              <footer className="library-detail-footer">
                <SecondaryButton onClick={() => setEditing(selected)}>编辑</SecondaryButton>
                <DangerButton onClick={() => void run(async () => { if (!window.confirm(`确认删除“${selected.name}”？`)) return; await deleteMaterial(selected.id); await load(null); })}>删除</DangerButton>
              </footer>
            </>
          ) : <LibraryEmptyState description="单击素材查看详情，双击进入编辑。" title="未选择素材" />}
        </aside>
      </div>

      {createOpen ? <CreateMaterialDialog busy={busy} categories={currentCategories} launch={launch} materialType={type} onClose={() => setCreateOpen(false)} onError={setError} onSaved={async (id) => { setCreateOpen(false); setLaunch(null); await load(id); setMessage('作者风格已保存。'); }} /> : null}
      {settingsOpen ? <MaterialSettingsDialog materialType={type} onClose={() => setSettingsOpen(false)} onError={setError} onSaved={() => setMessage('提取设置已保存，并成为新的默认配置。')} /> : null}
      {editing ? <MaterialEditor material={editing} onClose={() => setEditing(null)} onError={setError} onSaved={async (id) => { await load(id); const updated = (await getMaterials()).find((item) => item.id === id) ?? null; setEditing(updated); setMessage('素材已保存。'); }} /> : null}
      {categoryMenu ? <LibraryContextMenu actions={[
        { label: '重命名', onSelect: () => { const name = window.prompt('重命名分类', categoryMenu.category.name)?.trim(); if (name) void run(async () => { await renameMaterialCategory(categoryMenu.category.id, name); await load(selectedId); }); } },
        { danger: true, label: '删除分类', onSelect: () => { if (!window.confirm(`确认删除分类“${categoryMenu.category.name}”？素材本身不会被删除。`)) return; void run(async () => { await deleteMaterialCategory(categoryMenu.category.id); if (shelf.kind === 'category' && shelf.categoryId === categoryMenu.category.id) setShelf({ kind: 'all' }); await load(selectedId); }); } },
      ]} label={`${categoryMenu.category.name} 分类操作`} onClose={() => setCategoryMenu(null)} x={categoryMenu.x} y={categoryMenu.y} /> : null}
    </div>
  );
}

function MaterialBookCover({ compact = false, material }: { compact?: boolean; material: Material }) {
  const palette = ['indigo', 'terracotta', 'jade', 'slate', 'ochre'][material.id % 5];
  return <span className={`default-book-cover palette-${palette} ${compact ? 'compact' : ''}`}><span className="default-book-spine" /><span className="default-book-brand">RUSTY MATERIAL</span><strong>{material.name}</strong><span className="default-book-author">作者风格档案</span></span>;
}

function CreateMaterialDialog({ busy, categories, launch, materialType, onClose, onError, onSaved }: {
  busy: boolean; categories: MaterialCategory[]; launch: Launch | null; materialType: MaterialType;
  onClose: () => void; onError: (value: string) => void; onSaved: (id: number) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [text, setText] = useState(launch?.selectedText ?? '');
  const [working, setWorking] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  async function extract() {
    if (!text.trim()) { onError('请输入或选择用于分析的来源文本。'); return; }
    setWorking(true);
    try {
      const result = await previewMaterialExtraction({
        task_type: MATERIAL_TASK, name: name.trim() || null, sample_text: text,
        source_metadata: launch?.sourceMetadata ?? { source_type: 'paste' },
      });
      const candidate = result.candidates[0];
      if (!candidate) throw new Error('AI 未返回可预览内容。');
      const finalName = name.trim() || candidate.name.trim();
      if (!finalName) throw new Error('AI 未返回有效名称。');
      const applied = await applyMaterialExtraction({
        preview_token: result.preview_token,
        selected_candidate_ids: [candidate.candidate_id],
        candidates: [{ ...candidate, name: finalName, selected: true, category_ids: [] }],
      });
      const created = applied.created[0]?.material_id;
      if (!created) throw new Error(applied.errors[0]?.error || '保存失败。');
      await onSaved(created);
    } catch (reason) { onError(errorMessage(reason)); } finally { setWorking(false); }
  }
  return <LibraryDialog className="material-create-dialog" footer={<><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || working || !text.trim()} onClick={() => void extract()}><Sparkles size={15} />AI 提取</PrimaryButton></>} onClose={onClose} title="新建作者风格">
    <div className="library-form-grid">
      <label className="wide"><span>名称</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label className="wide"><span>来源文本</span><textarea className="tall" maxLength={50000} value={text} onChange={(event) => setText(event.target.value)} /></label>
      <div className="wide material-source-options"><SecondaryButton onClick={() => fileRef.current?.click()}>选择文本文件</SecondaryButton><input ref={fileRef} hidden accept=".txt,.md,text/plain,text/markdown" type="file" onChange={(event) => { const file = event.target.files?.[0]; if (file) void file.text().then(setText); }} /></div>
    </div>
  </LibraryDialog>;
}

function MaterialSettingsDialog({ materialType, onClose, onError, onSaved }: { materialType: MaterialType; onClose: () => void; onError: (value: string) => void; onSaved: () => void }) {
  const [settings, setSettings] = useState<MaterialAISettings | null>(null);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [busy, setBusy] = useState(true);
  const importRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    void Promise.all([getMaterialAISettings(MATERIAL_TASK), getModels()]).then(([value, modelRows]) => { setSettings(value as MaterialAISettings); setModels(modelRows); }).catch((reason) => onError(errorMessage(reason))).finally(() => setBusy(false));
  }, [materialType, onError]);
  async function save(next = settings) {
    if (!next) return;
    setBusy(true);
    try {
      const updated = await updateMaterialAISettings(next.task_type, {
        model_id: next.model_id, detail_level: next.detail_level, system_prompt: next.system_prompt,
        base_instruction: next.base_instruction, dimensions: next.dimensions, extra_requirements: next.extra_requirements,
      });
      setSettings(updated); onSaved();
    } catch (reason) { onError(errorMessage(reason)); } finally { setBusy(false); }
  }
  async function exportJson() {
    try {
      const value = await exportAuthorStyleSettings();
      const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'author-style-extraction.json'; anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) { onError(errorMessage(reason)); }
  }
  if (!settings) return <LibraryDialog footer={<SecondaryButton onClick={onClose}>关闭</SecondaryButton>} onClose={onClose} title="作者风格提取设置"><LibraryEmptyState title={busy ? '正在加载设置…' : '设置加载失败'} /></LibraryDialog>;
  const patch = (value: Partial<MaterialAISettings>) => setSettings({ ...settings, ...value, prompt_preview: compilePreview({ ...settings, ...value }) });
  return <LibraryDialog className="material-settings-dialog" footer={<><SecondaryButton onClick={onClose}>关闭</SecondaryButton><PrimaryButton disabled={busy} onClick={() => void save()}>保存为当前默认配置</PrimaryButton></>} onClose={onClose} subtitle="当前保存内容就是以后提取使用的唯一默认配置" title="作者风格提取设置">
    <div className="material-settings-grid">
      <section className="library-form-grid">
        <label><span>默认模型</span><select value={settings.model_id ?? ''} onChange={(event) => patch({ model_id: event.target.value ? Number(event.target.value) : null })}><option value="">使用全局默认模型</option>{models.map((model) => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select></label>
        <label><span>细化程度</span><select value={settings.detail_level} onChange={(event) => patch({ detail_level: event.target.value as MaterialAISettings['detail_level'] })}><option value="brief">简洁</option><option value="standard">标准</option><option value="detailed">详细</option></select></label>
        <label className="wide"><span>系统提示词</span><textarea value={settings.system_prompt} onChange={(event) => patch({ system_prompt: event.target.value })} /></label>
        <label className="wide"><span>任务说明 / 基础提示词</span><textarea value={settings.base_instruction} onChange={(event) => patch({ base_instruction: event.target.value })} /></label>
      </section>
      <DimensionSettings dimensions={settings.dimensions} onChange={(dimensions) => patch({ dimensions })} />
      <label className="material-extra-requirements"><span>附加要求</span><textarea value={settings.extra_requirements} onChange={(event) => patch({ extra_requirements: event.target.value })} /></label>
      {materialType === 'author_style' ? <div className="material-settings-transfer"><SecondaryButton onClick={() => void exportJson()}>导出 JSON</SecondaryButton><SecondaryButton onClick={() => importRef.current?.click()}>导入 JSON</SecondaryButton><input ref={importRef} hidden accept="application/json,.json" type="file" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; void file.text().then(async (text) => { try { const value = JSON.parse(text); if (!window.confirm('导入后将覆盖当前作者风格提取设置。当前设置不会作为另一套方案保存。是否继续？')) return; const imported = await importAuthorStyleSettings(value); setSettings(imported); onSaved(); } catch (reason) { onError(errorMessage(reason)); } }); }} /></div> : null}
      <section className="material-prompt-preview"><h3>Prompt 预览</h3><pre>{settings.prompt_preview || compilePreview(settings)}</pre></section>
    </div>
  </LibraryDialog>;
}

function DimensionSettings({ dimensions, onChange }: { dimensions: MaterialAIDimension[]; onChange: (value: MaterialAIDimension[]) => void }) {
  function patch(id: string, value: Partial<MaterialAIDimension>) { onChange(dimensions.map((item) => item.id === id ? { ...item, ...value } : item)); }
  return <section className="material-dimension-settings"><div className="section-heading"><h3>分析维度</h3><button onClick={() => onChange([...dimensions, { id: crypto.randomUUID(), name: '新维度', requirement: '' }])} type="button"><Plus size={14} />新增分析维度</button></div>{dimensions.map((item, index) => <article key={item.id}><div className="dimension-order"><button aria-label="上移维度" disabled={index === 0} onClick={() => onChange(move(dimensions, index, index - 1))} type="button"><ArrowUp size={14} /></button><button aria-label="下移维度" disabled={index === dimensions.length - 1} onClick={() => onChange(move(dimensions, index, index + 1))} type="button"><ArrowDown size={14} /></button></div><label><span>维度名称</span><input value={item.name} onChange={(event) => patch(item.id, { name: event.target.value })} /></label><label><span>提取要求</span><textarea value={item.requirement} onChange={(event) => patch(item.id, { requirement: event.target.value })} /></label><button aria-label="删除维度" className="danger" onClick={() => onChange(dimensions.filter((value) => value.id !== item.id))} type="button"><Trash2 size={14} /></button></article>)}</section>;
}

function MaterialEditor({ material, onClose, onError, onSaved }: { material: Material; onClose: () => void; onError: (value: string) => void; onSaved: (id: number) => Promise<void> }) {
  const [name, setName] = useState(material.name);
  const [description, setDescription] = useState(material.description);
  const [rawText, setRawText] = useState(material.raw_text);
  const [content, setContent] = useState<Record<string, unknown>>(material.content);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try { await updateMaterial(material.id, { name: name.trim(), description, detail_level: material.detail_level, raw_text: rawText, content, analysis_status: material.analysis_status, timeline_start_chapter: material.timeline_start_chapter, timeline_end_chapter: material.timeline_end_chapter, sort_order: material.sort_order }); await onSaved(material.id); }
    catch (reason) { onError(errorMessage(reason)); } finally { setBusy(false); }
  }
  async function extractDimension(dimension: AuthorDimension) {
    if (dimension.analysis || dimension.features.length || dimension.examples.length) {
      if (!window.confirm('重新提取将覆盖该维度当前的 AI 分析、具体特征和原文实例，不会影响其他维度。')) return;
    }
    setBusy(true);
    try {
      await updateMaterial(material.id, { name: name.trim(), description, detail_level: material.detail_level, raw_text: rawText, content, analysis_status: material.analysis_status, timeline_start_chapter: material.timeline_start_chapter, timeline_end_chapter: material.timeline_end_chapter, sort_order: material.sort_order });
      const preview = await previewAuthorStyleDimension(material.id, { dimension_id: dimension.id, dimension_name: dimension.name, dimension_requirement: dimension.requirement });
      const summary = `风格分析：\n${preview.analysis}\n\n具体特征：\n${preview.features.join('\n')}\n\n原文实例：\n${preview.examples.join('\n')}\n\n确认应用到当前维度？`;
      if (!window.confirm(summary)) return;
      const updated = await applyAuthorStyleDimension(material.id, preview.preview_token);
      setContent(updated.content); await onSaved(material.id);
    } catch (reason) { onError(errorMessage(reason)); } finally { setBusy(false); }
  }
  return <LibraryDialog className="author-style-editor-dialog" footer={<><SecondaryButton onClick={onClose}>关闭</SecondaryButton><PrimaryButton disabled={busy || !name.trim()} onClick={() => void save()}>保存</PrimaryButton></>} onClose={onClose} subtitle="作者风格" title="作者风格编辑器">
    <div className="library-form-grid"><label><span>名称</span><input value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>概览</span><input value={description} onChange={(event) => setDescription(event.target.value)} /></label><label className="wide"><span>原始分析文本</span><textarea value={rawText} onChange={(event) => setRawText(event.target.value)} /></label></div>
    <AuthorDimensionList content={content} editable onChange={setContent} onExtract={(dimension) => void extractDimension(dimension)} />
  </LibraryDialog>;
}

type AuthorDimension = { id: string; name: string; requirement: string; analysis: string; features: string[]; examples: string[] };
function AuthorDimensionList({ content, editable = false, onChange, onExtract }: { content: Record<string, unknown>; editable?: boolean; onChange: (value: Record<string, unknown>) => void; onExtract?: (value: AuthorDimension) => void }) {
  const dimensions = authorDimensions(content.dimensions);
  const update = (id: string, value: Partial<AuthorDimension>) => onChange({ ...content, dimensions: dimensions.map((item) => item.id === id ? { ...item, ...value } : item) });
  return <section className="author-dimension-editor"><div className="section-heading"><h3>作者风格维度</h3>{editable ? <button onClick={() => onChange({ ...content, dimensions: [...dimensions, { id: crypto.randomUUID(), name: '新维度', requirement: '', analysis: '', features: [], examples: [] }] })} type="button"><Plus size={14} />新增维度</button> : null}</div>{dimensions.map((item, index) => <details key={item.id} open={index === 0}><summary><span>{item.name}</span><small>{item.analysis ? '已分析' : '待分析'}</small></summary><div className="author-dimension-body">{editable ? <><label><span>维度名称</span><input value={item.name} onChange={(event) => update(item.id, { name: event.target.value })} /></label><label><span>提取要求</span><textarea value={item.requirement} onChange={(event) => update(item.id, { requirement: event.target.value })} /></label><label><span>风格分析</span><textarea value={item.analysis} onChange={(event) => update(item.id, { analysis: event.target.value })} /></label><label><span>具体特征 / 常用表达（每行一项）</span><textarea value={item.features.join('\n')} onChange={(event) => update(item.id, { features: lines(event.target.value) })} /></label><label><span>原文实例（每行一项）</span><textarea value={item.examples.join('\n')} onChange={(event) => update(item.id, { examples: lines(event.target.value) })} /></label><div className="author-dimension-actions"><button disabled={index === 0} onClick={() => onChange({ ...content, dimensions: move(dimensions, index, index - 1) })} type="button"><ArrowUp size={14} />上移</button><button disabled={index === dimensions.length - 1} onClick={() => onChange({ ...content, dimensions: move(dimensions, index, index + 1) })} type="button"><ArrowDown size={14} />下移</button><button onClick={() => onExtract?.(item)} type="button"><Sparkles size={14} />{item.analysis ? 'AI 重新提取' : 'AI 提取此维度'}</button><button className="danger" onClick={() => onChange({ ...content, dimensions: dimensions.filter((value) => value.id !== item.id) })} type="button"><Trash2 size={14} />删除</button></div></> : <><p>{item.requirement}</p><p>{item.analysis || '尚未分析'}</p><ul>{item.features.map((value) => <li key={value}>{value}</li>)}</ul><blockquote>{item.examples.join('\n')}</blockquote></>}</div></details>)}</section>;
}

function authorDimensions(value: unknown): AuthorDimension[] { return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object')).map((item, index) => ({ id: String(item.id || `dimension-${index + 1}`), name: String(item.name || '未命名维度'), requirement: String(item.requirement || ''), analysis: String(item.analysis || ''), features: stringArray(item.features), examples: stringArray(item.examples) })) : []; }
function stringArray(value: unknown): string[] { return Array.isArray(value) ? value.map(String).filter(Boolean) : []; }
function lines(value: string): string[] { return value.split('\n').map((item) => item.trim()).filter(Boolean); }
function move<T>(items: T[], from: number, to: number): T[] { const copy = [...items]; const [item] = copy.splice(from, 1); if (item !== undefined) copy.splice(to, 0, item); return copy; }
function contentSummary(material: Material): string { return String(material.content.summary ?? material.content.premise ?? material.raw_text ?? '暂无概览'); }
function isRecent(value: string): boolean { const timestamp = Date.parse(value); return Number.isFinite(timestamp) && Date.now() - timestamp <= 30 * 24 * 60 * 60 * 1000; }
function compilePreview(settings: MaterialAISettings): string { return `${settings.system_prompt}\n\n任务：\n${settings.base_instruction}\n\n分析维度：\n${settings.dimensions.map((item, index) => `${index + 1}. ${item.name}\nID: ${item.id}\n提取要求：${item.requirement}`).join('\n\n')}\n\n附加要求：\n${settings.extra_requirements || '无'}\n\n输出协议：\n返回 summary 与按稳定 ID 对齐的 dimensions（analysis / features / examples）。`; }
function errorMessage(reason: unknown): string { return reason instanceof Error ? reason.message : String(reason); }
