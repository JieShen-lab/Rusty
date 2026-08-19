import { useEffect, useMemo, useRef, useState } from 'react';
import { Copy, Download, Plus, Save, Trash2, Upload } from 'lucide-react';
import {
  copyPromptDefinition,
  createPromptDefinition,
  deletePromptDefinition,
  exportPromptDefinition,
  getPromptDefinitions,
  importPromptDefinition,
  updatePromptDefinition,
} from '../api/client';
import type { CreativeStrategy, PromptDefinition, PromptDefinitionKind, PromptDefinitionWrite } from '../api/types';
import { TopBar } from '../components/TopBar';

const workflowLabels: Record<CreativeStrategy, string> = {
  plot_adjust: '调整剧情', expansion: '增加剧情', reimagine: '重新构思',
};

const emptyPrompt: PromptDefinitionWrite = {
  name: '', description: '', kind: 'master', workflow_key: null, task_key: null,
  content: '', input_description: '', is_default: false,
};

type PromptCategory = 'master' | 'common_task' | CreativeStrategy;

export function PromptManagePage() {
  const [items, setItems] = useState<PromptDefinition[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [category, setCategory] = useState<PromptCategory>('master');
  const [form, setForm] = useState<PromptDefinitionWrite>(emptyPrompt);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ error?: string; message?: string }>({});
  const fileInput = useRef<HTMLInputElement>(null);

  const selected = useMemo(() => items.find((item) => item.id === selectedId) ?? null, [items, selectedId]);
  const categoryItems = useMemo(() => items.filter((item) => categoryOf(item) === category), [category, items]);

  useEffect(() => { void reload(); }, []);

  async function reload(preferredId?: number | null) {
    try {
      const next = await getPromptDefinitions();
      setItems(next);
      const id = preferredId === null ? null : preferredId ?? selectedId ?? next[0]?.id ?? null;
      setSelectedId(id);
      const item = next.find((entry) => entry.id === id);
      if (item) { setForm(toWrite(item)); setCategory(categoryOf(item)); }
    } catch (reason) { setFeedback({ error: messageOf(reason) }); }
  }

  function select(item: PromptDefinition) {
    setSelectedId(item.id);
    setCategory(categoryOf(item));
    setForm(toWrite(item));
    setFeedback({});
  }

  function startNew(kind: PromptDefinitionKind = 'master', workflowKey: CreativeStrategy | null = null) {
    setSelectedId(null);
    setForm({ ...emptyPrompt, kind, workflow_key: workflowKey, task_key: kind === 'master' ? null : '' });
    setCategory(kind === 'master' ? 'master' : kind === 'common_task' ? 'common_task' : workflowKey ?? 'plot_adjust');
    setFeedback({});
  }

  function chooseCategory(value: PromptCategory) {
    const first = items.find((item) => categoryOf(item) === value);
    if (first) select(first);
    else startNewForCategory(value);
  }

  async function save() {
    await perform(async () => {
      const saved = selectedId ? await updatePromptDefinition(selectedId, form) : await createPromptDefinition(form);
      await reload(saved.id);
      setFeedback({ message: '提示词已保存。' });
    });
  }

  async function duplicate() {
    if (!selectedId) return;
    await perform(async () => {
      const copy = await copyPromptDefinition(selectedId);
      await reload(copy.id);
      setFeedback({ message: '已创建独立副本。' });
    });
  }

  async function remove() {
    if (!selectedId || !window.confirm('确认删除当前提示词？')) return;
    await perform(async () => {
      await deletePromptDefinition(selectedId);
      setForm(emptyPrompt);
      await reload(null);
      setFeedback({ message: '提示词已删除。' });
    });
  }

  async function exportJson() {
    if (!selectedId) return;
    await perform(async () => {
      const result = await exportPromptDefinition(selectedId);
      download(result.content, `${safeName(form.name || 'prompt')}.json`);
    });
  }

  async function importJson(file?: File) {
    if (!file) return;
    await perform(async () => {
      const imported = await importPromptDefinition(await file.text());
      await reload(imported.id);
      setFeedback({ message: '提示词已导入。' });
    });
    if (fileInput.current) fileInput.current.value = '';
  }

  async function perform(action: () => Promise<void>) {
    setBusy(true); setFeedback({});
    try { await action(); }
    catch (reason) { setFeedback({ error: messageOf(reason) }); }
    finally { setBusy(false); }
  }

  return <div className="prompt-definition-page">
    <TopBar
      title="提示词"
      actions={<><button className="button secondary" onClick={() => fileInput.current?.click()} type="button"><Upload size={15} />导入</button><button className="button primary" onClick={() => startNewForCategory(category)} type="button"><Plus size={15} />新建</button><input accept="application/json,.json" className="sr-only" ref={fileInput} onChange={(event) => void importJson(event.target.files?.[0])} type="file" /></>}
    />
    {feedback.error || feedback.message ? <div className={`inline-alert ${feedback.error ? 'error' : 'success'}`}>{feedback.error || feedback.message}</div> : null}
    <div className="prompt-definition-layout">
      <aside className="prompt-kind-tree">
        <button className={category === 'master' ? 'active category-button primary-category' : 'category-button primary-category'} onClick={() => chooseCategory('master')} type="button">总提示词</button>
        <div className="prompt-workflow-group"><strong className="prompt-primary-category">工作流</strong>{(Object.entries(workflowLabels) as Array<[CreativeStrategy, string]>).map(([key, label]) => <button className={category === key ? 'active category-button nested' : 'category-button nested'} key={key} onClick={() => chooseCategory(key)} type="button">{label}</button>)}</div>
        <button className={category === 'common_task' ? 'active category-button primary-category' : 'category-button primary-category'} onClick={() => chooseCategory('common_task')} type="button">公共任务提示词</button>
      </aside>
      <aside className="prompt-item-list">
        <div className="panel-heading"><h2>{categoryLabel(category)}</h2><span>{categoryItems.length} 个</span></div>
        {categoryItems.map((item) => <button className={item.id === selectedId ? 'active' : ''} key={item.id} onClick={() => select(item)} type="button"><strong>{item.name}</strong><small>{describeKind(item)}</small></button>)}
      </aside>
      <main className="prompt-definition-editor">
        <div className="prompt-editor-title"><div><input aria-label="名称" placeholder="提示词名称" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /><input aria-label="说明" placeholder="简短说明" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></div><label><input checked={form.is_default} onChange={(event) => setForm({ ...form, is_default: event.target.checked })} type="checkbox" />默认</label></div>
        <div className="prompt-definition-fields"><label><span>类型</span><select value={form.kind} onChange={(event) => changeKind(event.target.value as PromptDefinitionKind, form, setForm)}><option value="master">总提示词</option><option value="workflow_task">工作流提示词</option><option value="common_task">公共任务提示词</option></select></label>{form.kind === 'workflow_task' ? <label><span>工作流</span><select value={form.workflow_key ?? 'plot_adjust'} onChange={(event) => setForm({ ...form, workflow_key: event.target.value as CreativeStrategy })}>{Object.entries(workflowLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label> : null}{form.kind !== 'master' ? <label><span>Task key</span><input value={form.task_key ?? ''} onChange={(event) => setForm({ ...form, task_key: event.target.value })} /></label> : null}</div>
        <label className="prompt-content-field"><span>Prompt 正文</span><textarea value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} /></label>
        <label className="prompt-input-field"><span>运行时大致会获得哪些输入</span><textarea value={form.input_description} onChange={(event) => setForm({ ...form, input_description: event.target.value })} /></label>
        <footer><div><button className="button secondary compact" disabled={!selected} onClick={() => void duplicate()} type="button"><Copy size={15} />复制</button><button className="button secondary compact" disabled={!selected} onClick={() => void exportJson()} type="button"><Download size={15} />导出</button><button className="button danger compact" disabled={!selected} onClick={() => void remove()} type="button"><Trash2 size={15} />删除</button></div><button className="button primary" disabled={busy || !form.name.trim() || (form.kind !== 'master' && !form.task_key?.trim())} onClick={() => void save()} type="button"><Save size={15} />保存</button></footer>
      </main>
    </div>
  </div>;

  function startNewForCategory(value: PromptCategory) {
    if (value === 'master') startNew('master');
    else if (value === 'common_task') startNew('common_task');
    else startNew('workflow_task', value);
  }
}

function changeKind(kind: PromptDefinitionKind, form: PromptDefinitionWrite, setForm: (value: PromptDefinitionWrite) => void) {
  setForm({ ...form, kind, workflow_key: kind === 'workflow_task' ? form.workflow_key ?? 'plot_adjust' : null, task_key: kind === 'master' ? null : form.task_key ?? '' });
}
function toWrite(item: PromptDefinition): PromptDefinitionWrite { const { id: _id, created_at: _created, updated_at: _updated, ...write } = item; return write; }
function describeKind(item: PromptDefinition) { if (item.kind === 'master') return '总提示词'; if (item.kind === 'common_task') return `公共任务 · ${item.task_key}`; return `${workflowLabels[item.workflow_key as CreativeStrategy]} · ${item.task_key}`; }
function categoryOf(item: PromptDefinition): PromptCategory { return item.kind === 'master' ? 'master' : item.kind === 'common_task' ? 'common_task' : item.workflow_key ?? 'plot_adjust'; }
function categoryLabel(value: PromptCategory) { return value === 'master' ? '总提示词' : value === 'common_task' ? '公共任务提示词' : workflowLabels[value]; }
function messageOf(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
function safeName(value: string) { return value.replace(/[\\/:*?"<>|]/g, '_').trim() || 'prompt'; }
function download(content: string, fileName: string) { const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = fileName; link.click(); URL.revokeObjectURL(url); }
