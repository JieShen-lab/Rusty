import { useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { Copy, Download, Plus, Save, Trash2, Upload } from 'lucide-react';
import {
  createAnalysisPrompt,
  createPrompt,
  deleteAnalysisPrompt,
  deletePrompt,
  exportPromptPackage,
  getAnalysisPrompts,
  getPrompts,
  importPromptPackage,
  updateAnalysisPrompt,
  updatePrompt,
} from '../api/client';
import type {
  AnalysisPromptTemplate,
  AnalysisPromptTemplateWrite,
  PromptSceneRule,
  PromptTemplate,
  PromptTemplateWrite,
} from '../api/types';

type Mode = 'rewrite' | 'analysis';
type RewriteTab = 'base' | 'recognition' | 'rewrite';
type AnalysisTab = 'dimensions' | 'evidence' | 'synthesis';

const emptyRewrite: PromptTemplateWrite = {
  name: '', description: '', global_rules: '', summary_rules: '', scene_detection_rules: '', rewrite_rules: '',
  scene_rules: [], package_metadata: {}, source_project_id: null, is_default: false,
};
const emptyAnalysis: AnalysisPromptTemplateWrite = {
  name: '', description: '', analysis_dimensions: '', evidence_rules: '', synthesis_rules: '', output_requirements: '', is_default: false,
};

export function PromptManagePage() {
  const [mode, setMode] = useState<Mode>('rewrite');
  const [rewriteTemplates, setRewriteTemplates] = useState<PromptTemplate[]>([]);
  const [analysisTemplates, setAnalysisTemplates] = useState<AnalysisPromptTemplate[]>([]);
  const [rewriteId, setRewriteId] = useState<number | null>(null);
  const [analysisId, setAnalysisId] = useState<number | null>(null);
  const [rewriteForm, setRewriteForm] = useState<PromptTemplateWrite>(emptyRewrite);
  const [analysisForm, setAnalysisForm] = useState<AnalysisPromptTemplateWrite>(emptyAnalysis);
  const [rewriteTab, setRewriteTab] = useState<RewriteTab>('base');
  const [analysisTab, setAnalysisTab] = useState<AnalysisTab>('dimensions');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => { void reload(); }, []);

  async function reload(nextRewrite?: number | null, nextAnalysis?: number | null) {
    setError(null);
    try {
      const [rewrites, analyses] = await Promise.all([getPrompts(), getAnalysisPrompts()]);
      setRewriteTemplates(rewrites);
      setAnalysisTemplates(analyses);
      const targetRewrite = nextRewrite === null ? rewrites[0]?.id ?? null : nextRewrite ?? rewriteId ?? rewrites[0]?.id ?? null;
      const targetAnalysis = nextAnalysis === null ? analyses[0]?.id ?? null : nextAnalysis ?? analysisId ?? analyses[0]?.id ?? null;
      setRewriteId(targetRewrite);
      setAnalysisId(targetAnalysis);
      const selectedRewrite = rewrites.find((item) => item.id === targetRewrite);
      const selectedAnalysis = analyses.find((item) => item.id === targetAnalysis);
      if (selectedRewrite) setRewriteForm(toRewriteWrite(selectedRewrite));
      if (selectedAnalysis) setAnalysisForm(toAnalysisWrite(selectedAnalysis));
    } catch (reason) { setError(messageOf(reason)); }
  }

  const templates = mode === 'rewrite' ? rewriteTemplates : analysisTemplates;
  const selectedId = mode === 'rewrite' ? rewriteId : analysisId;

  function selectTemplate(id: number) {
    setMessage(null); setError(null);
    if (mode === 'rewrite') {
      const item = rewriteTemplates.find((template) => template.id === id);
      if (item) { setRewriteId(id); setRewriteForm(toRewriteWrite(item)); }
    } else {
      const item = analysisTemplates.find((template) => template.id === id);
      if (item) { setAnalysisId(id); setAnalysisForm(toAnalysisWrite(item)); }
    }
  }

  function startNew() {
    setMessage(null); setError(null);
    if (mode === 'rewrite') { setRewriteId(null); setRewriteForm(emptyRewrite); setRewriteTab('base'); }
    else { setAnalysisId(null); setAnalysisForm(emptyAnalysis); setAnalysisTab('dimensions'); }
  }

  async function save() {
    setBusy(true); setError(null); setMessage(null);
    try {
      if (mode === 'rewrite') {
        const item = rewriteId ? await updatePrompt(rewriteId, rewriteForm) : await createPrompt(rewriteForm);
        await reload(item.id, analysisId);
      } else {
        const item = analysisId ? await updateAnalysisPrompt(analysisId, analysisForm) : await createAnalysisPrompt(analysisForm);
        await reload(rewriteId, item.id);
      }
      setMessage('模板已保存。');
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!selectedId || !window.confirm('确认删除当前模板？')) return;
    setBusy(true); setError(null);
    try {
      if (mode === 'rewrite') await deletePrompt(selectedId); else await deleteAnalysisPrompt(selectedId);
      if (mode === 'rewrite') { setRewriteId(null); setRewriteForm(emptyRewrite); }
      else { setAnalysisId(null); setAnalysisForm(emptyAnalysis); }
      await reload(mode === 'rewrite' ? null : rewriteId, mode === 'analysis' ? null : analysisId);
      setMessage('模板已删除。');
    } catch (reason) { setError(messageOf(reason)); }
    finally { setBusy(false); }
  }

  async function importJson(file: File | undefined) {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const imported = await importPromptPackage(await file.text());
      await reload(imported.id, analysisId);
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
      <header className="prompt-header"><h1>提示词管理</h1></header>
      {(error || message) ? <div className={`inline-alert ${error ? 'error' : 'success'}`}>{error || message}</div> : null}

      <div className="prompt-layout">
        <aside className="template-library">
          <div className="panel-heading"><h2>模板库</h2><span>{templates.length} 个</span></div>
          <div aria-label="提示词类型" className="library-mode-switch" role="tablist">
            <button aria-selected={mode === 'rewrite'} onClick={() => setMode('rewrite')} role="tab" type="button">改写</button>
            <button aria-selected={mode === 'analysis'} onClick={() => setMode('analysis')} role="tab" type="button">分析</button>
          </div>
          <div className="library-actions"><button className="button secondary" onClick={startNew} type="button"><Plus size={16} />新建</button>{mode === 'rewrite' ? <button className="button secondary" onClick={() => fileInput.current?.click()} type="button"><Upload size={16} />导入 JSON</button> : null}<input accept="application/json,.json" className="sr-only" ref={fileInput} onChange={(event) => void importJson(event.target.files?.[0])} type="file" /></div>
          <div className="template-list">
            {templates.map((item) => <button aria-pressed={item.id === selectedId} className={`template-row ${item.id === selectedId ? 'selected' : ''}`} key={item.id} onClick={() => selectTemplate(item.id)} type="button"><span><strong>{item.name}</strong><small>{item.description || '暂无说明'}</small></span>{item.is_default ? <em>默认</em> : null}</button>)}
            {templates.length === 0 ? <div className="compact-empty">暂无模板。</div> : null}
          </div>
        </aside>

        <main className="prompt-editor-shell">
          <div className="editor-title-row"><div><input aria-label="模板名称" className="title-input" placeholder={mode === 'rewrite' ? '改写提示词名称' : '分析提示词名称'} value={mode === 'rewrite' ? rewriteForm.name : analysisForm.name} onChange={(event) => mode === 'rewrite' ? setRewriteForm({ ...rewriteForm, name: event.target.value }) : setAnalysisForm({ ...analysisForm, name: event.target.value })} /><input aria-label="模板说明" className="description-input" placeholder="简短说明模板用途" value={mode === 'rewrite' ? rewriteForm.description : analysisForm.description} onChange={(event) => mode === 'rewrite' ? setRewriteForm({ ...rewriteForm, description: event.target.value }) : setAnalysisForm({ ...analysisForm, description: event.target.value })} /></div><label className="default-toggle"><input checked={mode === 'rewrite' ? rewriteForm.is_default : analysisForm.is_default} onChange={(event) => mode === 'rewrite' ? setRewriteForm({ ...rewriteForm, is_default: event.target.checked }) : setAnalysisForm({ ...analysisForm, is_default: event.target.checked })} type="checkbox" />设为默认</label></div>
          {mode === 'rewrite' ? (
            <RewriteEditor form={rewriteForm} tab={rewriteTab} onAdd={addSceneRule} onRemove={(index) => setRewriteForm((current) => ({ ...current, scene_rules: current.scene_rules.filter((_, itemIndex) => itemIndex !== index) }))} onTab={setRewriteTab} onUpdate={updateSceneRule} setForm={setRewriteForm} />
          ) : (
            <AnalysisEditor form={analysisForm} tab={analysisTab} onTab={setAnalysisTab} setForm={setAnalysisForm} />
          )}
        </main>

      </div>

      <footer className="prompt-save-bar">
        <div className="prompt-save-meta">
          <span>{mode === 'rewrite' ? `改写模板 · ${rewriteForm.scene_rules.length} 个识别类别` : '分析模板 · 分析维度 / 证据规则 / 归纳输出'}</span>
          <div className="prompt-utility-actions">
            {mode === 'rewrite' ? <button className="button ghost" disabled={!rewriteId || busy} onClick={() => void exportJson()} type="button"><Download size={15} />导出</button> : null}
            <button className="button ghost" disabled={!selectedId} onClick={() => void navigator.clipboard?.writeText(mode === 'rewrite' ? JSON.stringify(rewriteForm, null, 2) : JSON.stringify(analysisForm, null, 2))} type="button"><Copy size={15} />复制</button>
            <button className="button ghost danger-quiet" disabled={!selectedId || busy} onClick={() => void remove()} type="button"><Trash2 size={15} />删除</button>
          </div>
        </div>
        <div><button className="button secondary wide" disabled={busy || !selectedId} onClick={() => selectTemplate(selectedId!)} type="button">还原修改</button><button className="button primary wide" disabled={busy || !(mode === 'rewrite' ? rewriteForm.name.trim() : analysisForm.name.trim())} onClick={() => void save()} type="button"><Save size={16} />{busy ? '保存中…' : '保存模板'}</button></div>
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
        <PromptField hint="任务边界、事实保留和输出要求。" label="基础规则" value={form.global_rules} onChange={(value) => setForm({ ...form, global_rules: value })} />
      ) : null}
      {tab === 'recognition' ? (
        <div className="structured-editor">
          <PromptField hint="模型如何识别场景，以及如何返回类别。" label="通用识别规则" value={form.scene_detection_rules} onChange={(value) => setForm({ ...form, scene_detection_rules: value })} compact />
          <div className="section-heading"><div><strong>场景类别</strong><span>识别结果会匹配同 key 的具体改写规则</span></div><button className="button secondary" onClick={onAdd} type="button"><Plus size={16} />添加类别</button></div>
          <div className="scene-table">
            {form.scene_rules.map((rule, index) => <SceneRuleEditor index={index} key={`${rule.scene_key}-${index}`} mode="recognition" onRemove={() => onRemove(index)} onUpdate={(patch) => onUpdate(index, patch)} rule={rule} />)}
            {form.scene_rules.length === 0 ? <div className="compact-empty">暂无类别。可添加对话推进、动作冲突、情绪转折等场景。</div> : null}
          </div>
        </div>
      ) : null}
      {tab === 'rewrite' ? (
        <div className="rewrite-rules-layout">
          <PromptField hint="所有场景都执行的改写要求。" label="通用改写规则" value={form.rewrite_rules} onChange={(value) => setForm({ ...form, rewrite_rules: value })} />
          <div className="structured-editor scene-rules-column">
            <div className="section-heading"><div><strong>场景具体改写规则</strong><span>只在识别到对应类别时注入</span></div></div>
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

function AnalysisEditor({ form, onTab, setForm, tab }: { form: AnalysisPromptTemplateWrite; onTab: (tab: AnalysisTab) => void; setForm: Dispatch<SetStateAction<AnalysisPromptTemplateWrite>>; tab: AnalysisTab }) {
  return <div className="editor-body"><div className="editor-tabs" role="tablist">{([['dimensions', '分析维度'], ['evidence', '证据规则'], ['synthesis', '归纳输出']] as const).map(([key, label]) => <button aria-selected={tab === key} key={key} onClick={() => onTab(key)} role="tab" type="button">{label}</button>)}</div>{tab === 'dimensions' ? <PromptField hint="例如动作、对话、人物关系、心理、节奏、视角、环境和转场。" label="需要观察的维度" value={form.analysis_dimensions} onChange={(value) => setForm({ ...form, analysis_dimensions: value })} /> : null}{tab === 'evidence' ? <PromptField hint="规定如何引用文本证据，以及如何区分稳定规律和偶然写法。" label="证据与去内容化规则" value={form.evidence_rules} onChange={(value) => setForm({ ...form, evidence_rules: value })} /> : null}{tab === 'synthesis' ? <div className="analysis-output-grid"><PromptField hint="跨章节如何去重、处理冲突并归纳稳定规律。" label="全书归纳规则" value={form.synthesis_rules} onChange={(value) => setForm({ ...form, synthesis_rules: value })} /><PromptField hint="最终如何输出基础、识别和改写规则 JSON。" label="输出要求" value={form.output_requirements} onChange={(value) => setForm({ ...form, output_requirements: value })} /></div> : null}</div>;
}

function PromptField({ compact = false, hint, label, onChange, value }: { compact?: boolean; hint: string; label: string; onChange: (value: string) => void; value: string }) { return <label className={`prompt-field ${compact ? 'compact' : ''}`}><span><strong>{label}</strong><small>{hint}</small></span><textarea value={value} onChange={(event) => onChange(event.target.value)} /></label>; }

function SceneRuleEditor({ index, mode, onRemove, onUpdate, rule }: { index: number; mode: 'recognition' | 'rewrite'; onRemove: () => void; onUpdate: (patch: Partial<PromptSceneRule>) => void; rule: PromptSceneRule }) { return <section className="scene-rule"><div className="scene-rule-head"><span>{index + 1}</span><input aria-label="场景 key" value={rule.scene_key} onChange={(event) => onUpdate({ scene_key: event.target.value })} /><input aria-label="场景名称" value={rule.display_name} onChange={(event) => onUpdate({ display_name: event.target.value })} /><button aria-label="删除场景类别" className="icon-button danger-icon" onClick={onRemove} type="button"><Trash2 size={15} /></button></div>{mode === 'recognition' ? <><input className="text-input" placeholder="场景说明" value={rule.description} onChange={(event) => onUpdate({ description: event.target.value })} /><textarea className="rule-textarea" placeholder="具体识别条件" value={rule.detection_prompt} onChange={(event) => onUpdate({ detection_prompt: event.target.value })} /></> : <textarea className="rule-textarea large" placeholder="识别到此场景时执行的改写规则" value={rule.rewrite_prompt} onChange={(event) => onUpdate({ rewrite_prompt: event.target.value })} />}</section>; }

function toRewriteWrite(item: PromptTemplate): PromptTemplateWrite { const { id: _id, version: _version, ...write } = item; return write; }
function toAnalysisWrite(item: AnalysisPromptTemplate): AnalysisPromptTemplateWrite { const { id: _id, version: _version, ...write } = item; return write; }
function messageOf(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
function safeName(value: string) { return value.replace(/[\\/:*?"<>|]/g, '_').trim() || 'rewrite-prompt'; }
function downloadJson(content: string, fileName: string) { const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = fileName; link.click(); URL.revokeObjectURL(url); }
