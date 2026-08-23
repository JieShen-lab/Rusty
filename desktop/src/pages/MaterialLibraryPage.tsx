import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Plus, Search, Settings, Sparkles, Trash2 } from 'lucide-react';
import {
  applyMaterialExtraction,
  deleteMaterial,
  exportAuthorStyleSettings,
  getMaterialAISettings,
  getMaterials,
  getModels,
  importAuthorStyleSettings,
  previewMaterialExtraction,
  updateMaterial,
  updateMaterialAISettings,
} from '../api/client';
import type {
  Material,
  MaterialAIDimension,
  MaterialAISettings,
  MaterialType,
  ModelConfig,
} from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { FloatingNotice } from '../components/FloatingNotice';
import { LibraryDialog, LibraryEmptyState } from '../components/LibraryPrimitives';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

const MATERIAL_TYPE: MaterialType = 'author_style';
const MATERIAL_TASK = 'author_style_extraction' as const;

export function AuthorLibraryPage() {
  const type = MATERIAL_TYPE;
  const [query, setQuery] = useState('');
  const [materials, setMaterials] = useState<Material[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editing, setEditing] = useState<Material | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  useAutoDismiss(error, setError, 6000);
  useAutoDismiss(message, setMessage);

  const load = useCallback(async (preferred?: number | null) => {
    setLoading(true);
    try {
      const materialRows = await getMaterials();
      setMaterials(materialRows);
      setSelectedId((current) => {
        const wanted = preferred === undefined ? current : preferred;
        return materialRows.some((item) => item.id === wanted) ? wanted : materialRows[0]?.id ?? null;
      });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return materials.filter((item) => {
      if (item.material_type !== type) return false;
      const profile = authorProfile(item);
      return !needle || [profile.name, profile.work, item.categories.join(' ')]
        .join(' ').toLocaleLowerCase().includes(needle);
    });
  }, [materials, query, type]);
  const selected = materials.find((item) => item.id === selectedId && item.material_type === type) ?? null;

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try { await action(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  }

  function handleMaterialSaved(saved: Material) {
    setMaterials((current) => current.map((item) => item.id === saved.id ? saved : item));
    setSelectedId(saved.id);
    setEditing(saved);
    setMessage('作者档案已保存。');
  }

  return (
    <div className="document-library-page material-library-page">
      <TopBar title="作者" actions={(
        <>
          <PrimaryButton disabled={busy} onClick={() => setCreateOpen(true)}>
            <Plus size={16} />新建作者
          </PrimaryButton>
          <SecondaryButton aria-label="作者风格提取设置" className="icon-only" onClick={() => setSettingsOpen(true)}>
            <Settings size={16} />
          </SecondaryButton>
        </>
      )} />
      <FloatingNotice error={error} message={message} />

      <div className="document-library-layout material-browser-layout material-library-unified">
        <main className="document-shelf-panel material-browser-shelf">
          <header>
            <label className="search-field document-search material-library-search">
              <Search size={15} /><span className="sr-only">搜索作者</span>
              <input onChange={(event) => setQuery(event.target.value)} placeholder="搜索作者、作品或分类" type="search" value={query} />
            </label>
          </header>
          {loading ? <LibraryEmptyState title="正在读取作者档案…" /> : visible.length ? (
            <div className="document-shelf-scroll">
              <div className="author-profile-list" aria-label="作者列表">
                {visible.map((material) => {
                  const profile = authorProfile(material);
                  return <button
                    aria-pressed={selectedId === material.id}
                    className={`author-profile-row ${selectedId === material.id ? 'selected' : ''}`}
                    key={material.id}
                    onClick={() => setSelectedId(material.id)}
                    onDoubleClick={() => setEditing(material)}
                    type="button"
                  >
                    <span className="author-profile-copy"><strong>{profile.name}</strong><small>{profile.work || '尚未填写作品'}</small><em>修改日期：{formatDate(material.updated_at)}</em></span>
                  </button>;
                })}
              </div>
            </div>
          ) : (
            <LibraryEmptyState action={<PrimaryButton onClick={() => setCreateOpen(true)}><Plus size={16} />新建作者</PrimaryButton>} title="暂无作者" />
          )}
        </main>

        <aside className="document-detail-panel material-detail-panel">
          <header><h2>作者档案</h2></header>
          {selected ? (
            <>
              <div className="document-detail-scroll">
                <section className="document-detail-identity author-detail-identity"><div><h3>{authorProfile(selected).name}</h3></div></section>
                <section><div className="document-detail-heading"><span>作品</span></div><p className="material-detail-copy">{authorProfile(selected).work || '尚未填写作品'}</p></section>
                <section><div className="document-detail-heading"><span>整体风格</span></div><p className="material-detail-copy">{authorProfile(selected).overallStyle || '尚未形成整体风格总结'}</p></section>
                <AuthorDimensionTable content={selected.content} />
              </div>
              <footer className="library-detail-footer">
                <SecondaryButton onClick={() => setEditing(selected)}>编辑</SecondaryButton>
                <DangerButton onClick={() => void run(async () => { if (!window.confirm(`确认删除“${selected.name}”？`)) return; await deleteMaterial(selected.id); await load(null); })}>删除</DangerButton>
              </footer>
            </>
          ) : <LibraryEmptyState title="未选择作者" />}
        </aside>
      </div>

      {createOpen ? <CreateMaterialDialog busy={busy} onClose={() => setCreateOpen(false)} onError={setError} onSaved={async (id) => { setCreateOpen(false); await load(id); setMessage('作者风格已保存。'); }} /> : null}
      {settingsOpen ? <MaterialSettingsDialog materialType={type} onClose={() => setSettingsOpen(false)} onError={setError} onSaved={() => setMessage('提取设置已保存，并成为新的默认配置。')} /> : null}
      {editing ? <MaterialEditor material={editing} onClose={() => setEditing(null)} onError={setError} onSaved={handleMaterialSaved} /> : null}
    </div>
  );
}

function CreateMaterialDialog({ busy, onClose, onError, onSaved }: {
  busy: boolean;
  onClose: () => void; onError: (value: string) => void; onSaved: (id: number) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [sourcePath, setSourcePath] = useState('');
  const [working, setWorking] = useState(false);
  const selectedFileName = sourcePath.split(/[\\/]/).pop() || sourcePath;
  const workName = visibleFileName(sourcePath);
  async function chooseFile() {
    const picker = window.rustyDesktop?.selectBookFile;
    if (!picker) {
      onError('当前窗口不支持文件选择，请从 Rusty 桌面应用中打开。');
      return;
    }
    try {
      const selected = await picker();
      if (selected) setSourcePath(selected);
    } catch (reason) {
      onError(errorMessage(reason));
    }
  }
  async function extract() {
    if (!name.trim()) { onError('请填写作者姓名。'); return; }
    if (!sourcePath) { onError('请选择文件。'); return; }
    setWorking(true);
    try {
      const result = await previewMaterialExtraction({
        task_type: MATERIAL_TASK, name: name.trim(), source_path: sourcePath,
      });
      const candidate = result.candidates[0];
      if (!candidate) throw new Error('AI 未返回可预览内容。');
      const finalName = name.trim();
      if (!finalName) throw new Error('AI 未返回有效名称。');
      const applied = await applyMaterialExtraction({
        preview_token: result.preview_token,
        selected_candidate_ids: [candidate.candidate_id],
        candidates: [{ ...candidate, name: finalName, description: candidate.description || '', content: { ...candidate.content, work: workName }, selected: true, category_ids: [] }],
      });
      const created = applied.created[0]?.material_id;
      if (!created) throw new Error(applied.errors[0]?.error || '保存失败。');
      await onSaved(created);
    } catch (reason) { onError(errorMessage(reason)); } finally { setWorking(false); }
  }
  return <LibraryDialog className="material-create-dialog" footer={<><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || working || !name.trim() || !sourcePath} onClick={() => void extract()}><Sparkles size={15} />分析并建档</PrimaryButton></>} onClose={onClose} title="新建作者">
    <div className="author-create-form">
      <label className="author-create-row"><span>作者姓名</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} /></label>
      <div className="author-create-row"><span>选择文件</span><div className="author-create-file"><SecondaryButton onClick={() => void chooseFile()}>打开文件夹</SecondaryButton>{selectedFileName ? <span className="author-create-file-name" title={sourcePath}>已选择：{selectedFileName}</span> : null}</div></div>
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
  return <LibraryDialog className="material-settings-dialog" footer={<><SecondaryButton onClick={onClose}>关闭</SecondaryButton><PrimaryButton disabled={busy} onClick={() => void save()}>保存为当前默认配置</PrimaryButton></>} onClose={onClose} title="作者风格提取设置">
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

function MaterialEditor({ material, onClose, onError, onSaved }: { material: Material; onClose: () => void; onError: (value: string) => void; onSaved: (material: Material) => void }) {
  const profile = authorProfile(material);
  const [name, setName] = useState(profile.name);
  const [work, setWork] = useState(profile.work);
  const [overallStyle, setOverallStyle] = useState(profile.overallStyle);
  const [content, setContent] = useState<Record<string, unknown>>(material.content);
  const [busy, setBusy] = useState(false);
  function profileContent() {
    const next = { ...content, work: work.trim(), overall_style: overallStyle };
    delete next.author_name;
    delete next.introduction;
    delete next.source_works;
    return next;
  }
  async function save() {
    setBusy(true);
    try { const saved = await updateMaterial(material.id, { name: name.trim(), description: material.description, detail_level: material.detail_level, content: profileContent(), analysis_status: material.analysis_status, timeline_start_chapter: material.timeline_start_chapter, timeline_end_chapter: material.timeline_end_chapter, sort_order: material.sort_order }); onSaved(saved); }
    catch (reason) { onError(errorMessage(reason)); } finally { setBusy(false); }
  }
  return <LibraryDialog className="author-style-editor-dialog" footer={<><SecondaryButton onClick={onClose}>关闭</SecondaryButton><PrimaryButton disabled={busy || !name.trim()} onClick={() => void save()}>保存档案</PrimaryButton></>} onClose={onClose} title="编辑作者档案">
    <div className="library-form-grid"><label><span>作者姓名</span><input value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>作品</span><input value={work} onChange={(event) => setWork(event.target.value)} /></label><label className="wide"><span>整体风格</span><textarea value={overallStyle} onChange={(event) => setOverallStyle(event.target.value)} /></label></div>
    <AuthorDimensionList content={content} editable onChange={setContent} />
  </LibraryDialog>;
}

type AuthorDimension = { id: string; name: string; requirement: string; analysis: string; features: string[]; examples: string[] };
function AuthorDimensionList({ content, editable = false, onChange }: { content: Record<string, unknown>; editable?: boolean; onChange: (value: Record<string, unknown>) => void }) {
  const dimensions = authorDimensions(content.dimensions);
  const update = (id: string, value: Partial<AuthorDimension>) => onChange({ ...content, dimensions: dimensions.map((item) => item.id === id ? { ...item, ...value } : item) });
  return <section className="author-dimension-editor"><div className="section-heading"><h3>作者风格维度</h3>{editable ? <button onClick={() => onChange({ ...content, dimensions: [...dimensions, { id: crypto.randomUUID(), name: '新维度', requirement: '', analysis: '', features: [], examples: [] }] })} type="button"><Plus size={14} />新增维度</button> : null}</div>{dimensions.map((item, index) => <details key={item.id} open={index === 0}><summary><span>{item.name}</span><small>{item.analysis ? '已分析' : '待分析'}</small></summary><div className="author-dimension-body">{editable ? <><label><span>维度名称</span><input value={item.name} onChange={(event) => update(item.id, { name: event.target.value })} /></label><label><span>提取要求</span><textarea value={item.requirement} onChange={(event) => update(item.id, { requirement: event.target.value })} /></label><label><span>风格分析</span><textarea value={item.analysis} onChange={(event) => update(item.id, { analysis: event.target.value })} /></label><label><span>具体特征 / 常用表达（每行一项）</span><textarea value={item.features.join('\n')} onChange={(event) => update(item.id, { features: lines(event.target.value) })} /></label><label><span>原文实例（每行一项）</span><textarea value={item.examples.join('\n')} onChange={(event) => update(item.id, { examples: lines(event.target.value) })} /></label><div className="author-dimension-actions"><button disabled={index === 0} onClick={() => onChange({ ...content, dimensions: move(dimensions, index, index - 1) })} type="button"><ArrowUp size={14} />上移</button><button disabled={index === dimensions.length - 1} onClick={() => onChange({ ...content, dimensions: move(dimensions, index, index + 1) })} type="button"><ArrowDown size={14} />下移</button><button className="danger" onClick={() => onChange({ ...content, dimensions: dimensions.filter((value) => value.id !== item.id) })} type="button"><Trash2 size={14} />删除</button></div></> : <><p>{item.requirement}</p><p>{item.analysis || '尚未分析'}</p><ul>{item.features.map((value) => <li key={value}>{value}</li>)}</ul><blockquote>{item.examples.join('\n')}</blockquote></>}</div></details>)}</section>;
}

function authorDimensions(value: unknown): AuthorDimension[] { return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object')).map((item, index) => ({ id: String(item.id || `dimension-${index + 1}`), name: String(item.name || '未命名维度'), requirement: String(item.requirement || ''), analysis: String(item.analysis || ''), features: stringArray(item.features), examples: stringArray(item.examples) })) : []; }
function stringArray(value: unknown): string[] { return Array.isArray(value) ? value.map(String).filter(Boolean) : []; }
function lines(value: string): string[] { return value.split('\n').map((item) => item.trim()).filter(Boolean); }
function move<T>(items: T[], from: number, to: number): T[] { const copy = [...items]; const [item] = copy.splice(from, 1); if (item !== undefined) copy.splice(to, 0, item); return copy; }
function authorProfile(material: Material): { name: string; work: string; overallStyle: string } {
  const hasStoredWork = Object.prototype.hasOwnProperty.call(material.content, 'work');
  const hasStoredOverallStyle = Object.prototype.hasOwnProperty.call(material.content, 'overall_style');
  return {
    name: String(material.content.author_name || material.name),
    work: hasStoredWork ? String(material.content.work || '').trim() : sourceWorkName(material.source_metadata),
    overallStyle: hasStoredOverallStyle ? String(material.content.overall_style || '').trim() : String(material.content.summary || '').trim(),
  };
}

function sourceWorkName(metadata: Record<string, unknown>): string {
  if (String(metadata.source_type || '').trim().toLowerCase() === 'file') {
    for (const key of ['file_name', 'source_file_name', 'source_filename']) {
      const value = visibleFileName(metadata[key]);
      if (value) return value;
    }
  }
  for (const key of ['document_title', 'source_document_title', 'book_title']) {
    const value = String(metadata[key] || '').trim();
    if (value) return value;
  }
  for (const key of ['file_name', 'source_file_name', 'source_filename']) {
    const value = visibleFileName(metadata[key]);
    if (value) return value;
  }
  return '';
}

function visibleFileName(value: unknown): string {
  const name = String(value || '').trim().replace(/\\/g, '/').split('/').pop() || '';
  if (!name) return '';
  const extensionIndex = name.lastIndexOf('.');
  return extensionIndex > 0 ? name.slice(0, extensionIndex) : name;
}

function AuthorDimensionTable({ content }: { content: Record<string, unknown> }) {
  const dimensions = authorDimensions(content.dimensions);
  return <section className="author-dimension-table"><div className="document-detail-heading"><span>分析维度</span></div>{dimensions.length ? <div className="author-dimension-rows">{dimensions.map((item) => <article key={item.id}><div className="author-dimension-name"><strong>{item.name}</strong></div><div className="author-dimension-analysis"><p><b>分析：</b>{item.analysis || item.requirement || '尚未分析'}</p>{item.features.length ? <p><b>特征：</b>{item.features.join('、')}</p> : null}{item.examples.length ? <p><b>来源示例：</b>{item.examples.join('；')}</p> : null}</div></article>)}</div> : <p className="material-detail-copy">尚未添加分析维度</p>}</section>;
}

function formatDate(value: string): string { const timestamp = Date.parse(value); return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleDateString('zh-CN').replace(/\//g, '-') : '未知'; }
function compilePreview(settings: MaterialAISettings): string { return `${settings.system_prompt}\n\n任务：\n${settings.base_instruction}\n\n分析维度：\n${settings.dimensions.map((item, index) => `${index + 1}. ${item.name}\nID: ${item.id}\n提取要求：${item.requirement}`).join('\n\n')}\n\n附加要求：\n${settings.extra_requirements || '无'}\n\n输出协议：\n返回 overall_style、summary 与按稳定 ID 对齐的 dimensions（analysis / features / examples）；overall_style 是独立顶层字段，不属于 dimensions。`; }
function errorMessage(reason: unknown): string { return reason instanceof Error ? reason.message : String(reason); }
