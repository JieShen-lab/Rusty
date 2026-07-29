import { useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { Download, Plus, Save, Trash2, Upload } from 'lucide-react';
import {
  createPrompt,
  deletePrompt,
  exportPromptPackage,
  getPrompts,
  importPromptPackage,
  updatePrompt,
} from '../api/client';
import type {
  PromptSceneRule,
  PromptTemplate,
  PromptTemplateWrite,
} from '../api/types';

type RewriteTab = 'base' | 'recognition' | 'rewrite';

const emptyRewrite: PromptTemplateWrite = {
  name: '', description: '', global_rules: '', summary_rules: '', rewrite_rules: '',
  scene_rules: [], package_metadata: {}, source_project_id: null, is_default: false,
};

export function PromptManagePage() {
  const [rewriteTemplates, setRewriteTemplates] = useState<PromptTemplate[]>([]);
  const [rewriteId, setRewriteId] = useState<number | null>(null);
  const [rewriteForm, setRewriteForm] = useState<PromptTemplateWrite>(emptyRewrite);
  const [rewriteTab, setRewriteTab] = useState<RewriteTab>('base');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => { void reload(); }, []);

  async function reload(nextRewrite?: number | null) {
    setError(null);
    try {
      const rewrites = await getPrompts();
      setRewriteTemplates(rewrites);
      const targetRewrite = nextRewrite === null ? rewrites[0]?.id ?? null : nextRewrite ?? rewriteId ?? rewrites[0]?.id ?? null;
      setRewriteId(targetRewrite);
      const selectedRewrite = rewrites.find((item) => item.id === targetRewrite);
      if (selectedRewrite) setRewriteForm(toRewriteWrite(selectedRewrite));
    } catch (reason) { setError(messageOf(reason)); }
  }

  function selectTemplate(id: number) {
    setMessage(null); setError(null);
    const item = rewriteTemplates.find((template) => template.id === id);
    if (item) { setRewriteId(id); setRewriteForm(toRewriteWrite(item)); }
  }

  function startNew() {
    setMessage(null); setError(null);
    setRewriteId(null); setRewriteForm(emptyRewrite); setRewriteTab('base');
  }

  async function save() {
    setBusy(true); setError(null); setMessage(null);
    try {
      const item = rewriteId ? await updatePrompt(rewriteId, rewriteForm) : await createPrompt(rewriteForm);
      await reload(item.id);
      setMessage('模板已保存。');
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!rewriteId || !window.confirm('确认删除当前模板？')) return;
    setBusy(true); setError(null);
    try {
      await deletePrompt(rewriteId);
      setRewriteId(null); setRewriteForm(emptyRewrite);
      await reload(null);
      setMessage('模板已删除。');
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function importJson(file: File | undefined) {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const imported = await importPromptPackage(await file.text());
      await reload(imported.id);
      setMessage('改写提示词 JSON 已导入。');
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); if (fileInput.current) fileInput.current.value = ''; }
  }

  async function exportJson() {
    if (!rewriteId) return;
    setBusy(true); setError(null);
    try {
      const { content } = await exportPromptPackage(rewriteId);
      downloadJson(content, `${safeName(rewriteForm.name || 'rewrite-prompt')}.json`);
      setMessage('改写提示词 JSON 已导出。');
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  function addSceneRule() {
    const index = rewriteForm.scene_rules.length;
    setRewriteForm((current) => ({ ...current, scene_rules: [...current.scene_rules, {
      scene_key: `scene_${index + 1}`, display_name: `场景 ${index + 1}`, description: '', detection_prompt: '', rewrite_prompt: '', sort_order: index,
    }] }));
  }

  function updateSceneRule(index: number, patch: Partial<PromptSceneRule>) {
    setRewriteForm((current) => ({ ...current, scene_rules: current.scene_rules.map((rule, itemIndex) => itemIndex === index ? { ...rule, ...patch } : rule) }));
  }

  return (
    <div className="prompt-workbench">
      <header className="prompt-header"><h1>提示词</h1></header>
      {(error || message) ? <div className={`inline-alert ${error ? 'error' : 'success'}`}>{error || message}</div> : null}

      <div className="prompt-layout">
        <aside className="template-library">
          <div className="panel-heading"><h2>模板库</h2><span>{rewriteTemplates.length} 个</span></div>
          <div className="library-actions"><button className="button secondary" onClick={startNew} type="button"><Plus size={16} />新建</button><button className="button secondary" onClick={() => fileInput.current?.click()} type="button"><Upload size={16} />导入</button><input accept="application/json,.json" className="sr-only" ref={fileInput} onChange={(event) => void importJson(event.target.files?.[0])} type="file" /></div>
          <div className="template-list">
            {rewriteTemplates.map((item) => <button aria-pressed={item.id === rewriteId} className={`template-row ${item.id === rewriteId ? 'selected' : ''}`} key={item.id} onClick={() => selectTemplate(item.id)} type="button"><span><strong>{item.name}</strong><small>{item.description || '暂无说明'}</small></span>{item.is_default ? <em>默认</em> : null}</button>)}
            {rewriteTemplates.length === 0 ? <div className="compact-empty">暂无模板。</div> : null}
          </div>
        </aside>

        <main className="prompt-editor-shell">
          <div className="editor-title-row"><div><input aria-label="模板名称" className="title-input" placeholder="改写提示词名称" value={rewriteForm.name} onChange={(event) => setRewriteForm({ ...rewriteForm, name: event.target.value })} /><input aria-label="模板说明" className="description-input" placeholder="简短说明模板用途" value={rewriteForm.description} onChange={(event) => setRewriteForm({ ...rewriteForm, description: event.target.value })} /></div><label className="default-toggle"><input checked={rewriteForm.is_default} onChange={(event) => setRewriteForm({ ...rewriteForm, is_default: event.target.checked })} type="checkbox" />设为默认</label></div>
          <RewriteEditor form={rewriteForm} tab={rewriteTab} onAdd={addSceneRule} onRemove={(index) => setRewriteForm((current) => ({ ...current, scene_rules: current.scene_rules.filter((_, itemIndex) => itemIndex !== index) }))} onTab={setRewriteTab} onUpdate={updateSceneRule} setForm={setRewriteForm} />
        </main>

      </div>

      <footer className="prompt-save-bar">
        <div className="prompt-save-meta">
          <span>{`改写模板 · ${rewriteForm.scene_rules.length} 个识别类别`}</span>
          <div className="prompt-utility-actions">
            <button className="button ghost" disabled={!rewriteId || busy} onClick={() => void exportJson()} type="button"><Download size={15} />导出</button>
            <button className="button ghost danger-quiet" disabled={!rewriteId || busy} onClick={() => void remove()} type="button"><Trash2 size={15} />删除</button>
          </div>
        </div>
        <div><button className="button primary wide" disabled={busy || !rewriteForm.name.trim()} onClick={() => void save()} type="button"><Save size={16} />{busy ? '保存中…' : '保存模板'}</button></div>
      </footer>
    </div>
  );
}

function RewriteEditor({ form, onAdd, onRemove, onTab, onUpdate, setForm, tab }: { form: PromptTemplateWrite; onAdd: () => void; onRemove: (index: number) => void; onTab: (tab: RewriteTab) => void; onUpdate: (index: number, patch: Partial<PromptSceneRule>) => void; setForm: Dispatch<SetStateAction<PromptTemplateWrite>>; tab: RewriteTab }) {
  return (
    <div className="editor-body">
      <div className="editor-tabs" role="tablist">
        {([['base', '基础规则'], ['recognition', '识别规则'], ['rewrite', '改写规则']] as const).map(([key, label]) => (
          <button aria-selected={tab === key} key={key} onClick={() => onTab(key)} role="tab" type="button">{label}</button>
        ))}
      </div>
      {tab === 'base' ? (
        <PromptField label="基础规则" value={form.global_rules} onChange={(value) => setForm({ ...form, global_rules: value })} />
      ) : null}
      {tab === 'recognition' ? (
        <div className="structured-editor">
          <div className="section-heading"><div><strong>场景类别</strong></div><button className="button secondary" onClick={onAdd} type="button"><Plus size={16} />添加类别</button></div>
          <div className="scene-table">
            {form.scene_rules.map((rule, index) => <SceneRuleEditor index={index} key={`${rule.scene_key}-${index}`} mode="recognition" onRemove={() => onRemove(index)} onUpdate={(patch) => onUpdate(index, patch)} rule={rule} />)}
            {form.scene_rules.length === 0 ? <div className="compact-empty">暂无类别。可添加对话推进、动作冲突、情绪转折等场景。</div> : null}
          </div>
        </div>
      ) : null}
      {tab === 'rewrite' ? (
        <div className="rewrite-rules-layout">
          <PromptField label="通用改写规则" value={form.rewrite_rules} onChange={(value) => setForm({ ...form, rewrite_rules: value })} />
          <div className="structured-editor scene-rules-column">
            <div className="section-heading"><div><strong>场景具体改写规则</strong></div></div>
            <div className="scene-table">
              {form.scene_rules.map((rule, index) => <SceneRuleEditor index={index} key={`${rule.scene_key}-${index}`} mode="rewrite" onRemove={() => onRemove(index)} onUpdate={(patch) => onUpdate(index, patch)} rule={rule} />)}
              {form.scene_rules.length === 0 ? <div className="compact-empty">请先在“识别规则”中添加场景类别。</div> : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PromptField({ compact = false, label, onChange, value }: { compact?: boolean; label: string; onChange: (value: string) => void; value: string }) { return <label className={`prompt-field ${compact ? 'compact' : ''}`}><span><strong>{label}</strong></span><textarea value={value} onChange={(event) => onChange(event.target.value)} /></label>; }

function SceneRuleEditor({ index, mode, onRemove, onUpdate, rule }: { index: number; mode: 'recognition' | 'rewrite'; onRemove: () => void; onUpdate: (patch: Partial<PromptSceneRule>) => void; rule: PromptSceneRule }) { return <section className="scene-rule"><div className="scene-rule-head"><span>{index + 1}</span><input aria-label="场景 key" value={rule.scene_key} onChange={(event) => onUpdate({ scene_key: event.target.value })} /><input aria-label="场景名称" value={rule.display_name} onChange={(event) => onUpdate({ display_name: event.target.value })} /><button aria-label="删除场景类别" className="icon-button danger-icon" onClick={onRemove} type="button"><Trash2 size={15} /></button></div>{mode === 'recognition' ? <><input className="text-input" placeholder="场景说明" value={rule.description} onChange={(event) => onUpdate({ description: event.target.value })} /><textarea className="rule-textarea" placeholder="具体识别条件" value={rule.detection_prompt} onChange={(event) => onUpdate({ detection_prompt: event.target.value })} /></> : <textarea className="rule-textarea large" placeholder="识别到此场景时执行的改写规则" value={rule.rewrite_prompt} onChange={(event) => onUpdate({ rewrite_prompt: event.target.value })} />}</section>; }

function toRewriteWrite(item: PromptTemplate): PromptTemplateWrite { const { id: _id, version: _version, ...write } = item; return write; }
function messageOf(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
function safeName(value: string) { return value.replace(/[\\/:*?"<>|]/g, '_').trim() || 'rewrite-prompt'; }
function downloadJson(content: string, fileName: string) { const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = fileName; link.click(); URL.revokeObjectURL(url); }
