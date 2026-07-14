import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { BookOpen, Download, Plus, Save, Trash2, Upload, Users } from 'lucide-react';
import {
  createPrompt,
  deletePrompt,
  exportPromptPackage,
  getPrompts,
  importPromptPackage,
  updatePrompt,
} from '../api/client';
import type { PromptSceneRule, PromptTemplate, PromptTemplateWrite } from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StatusPill } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

type Tab = 'system' | 'scene' | 'rewrite' | 'story' | 'characters';

const emptyForm: PromptTemplateWrite = {
  name: '',
  description: '',
  global_rules: '',
  summary_rules: '',
  scene_detection_rules: '',
  rewrite_rules: '',
  story_anchor: {},
  characters: [],
  scene_rules: [],
  package_metadata: {},
  source_project_id: null,
  is_default: false,
};

const tabs: Array<{ key: Tab; label: string }> = [
  { key: 'system', label: '系统规则' },
  { key: 'scene', label: '场景识别' },
  { key: 'rewrite', label: '改写规则' },
  { key: 'story', label: '故事锚点' },
  { key: 'characters', label: '人物锚点' },
];

export function PromptManagePage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState<PromptTemplateWrite>(emptyForm);
  const [tab, setTab] = useState<Tab>('system');
  const [storyJson, setStoryJson] = useState('{}');
  const [charactersJson, setCharactersJson] = useState('[]');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function fillForm(template: PromptTemplate) {
    setForm({
      name: template.name,
      description: template.description,
      global_rules: template.global_rules,
      summary_rules: template.summary_rules,
      scene_detection_rules: template.scene_detection_rules,
      rewrite_rules: template.rewrite_rules,
      story_anchor: template.story_anchor,
      characters: template.characters,
      scene_rules: template.scene_rules,
      package_metadata: template.package_metadata,
      source_project_id: template.source_project_id,
      is_default: template.is_default,
    });
    setStoryJson(JSON.stringify(template.story_anchor, null, 2));
    setCharactersJson(JSON.stringify(template.characters, null, 2));
  }

  function loadTemplates(nextSelectedId?: number | null) {
    setError(null);
    getPrompts()
      .then((items) => {
        setTemplates(items);
        const id = nextSelectedId ?? selectedId ?? items[0]?.id ?? null;
        setSelectedId(id);
        const selected = items.find((template) => template.id === id);
        if (selected) fillForm(selected);
      })
      .catch((err: unknown) => setError(errorMessage(err)));
  }

  useEffect(() => {
    loadTemplates(null);
    // Initial load only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startNew() {
    setSelectedId(null);
    setForm(emptyForm);
    setStoryJson('{}');
    setCharactersJson('[]');
    setMessage(null);
    setTab('system');
  }

  function updateSceneRule(index: number, patch: Partial<PromptSceneRule>) {
    setForm((current) => ({
      ...current,
      scene_rules: current.scene_rules.map((rule, ruleIndex) => ruleIndex === index ? { ...rule, ...patch } : rule),
    }));
  }

  function addSceneRule() {
    const index = form.scene_rules.length;
    setForm((current) => ({
      ...current,
      scene_rules: [
        ...current.scene_rules,
        {
          scene_key: `scene_${index + 1}`,
          display_name: `新场景 ${index + 1}`,
          description: '',
          detection_prompt: '',
          rewrite_prompt: '',
          sort_order: index,
        },
      ],
    }));
  }

  function removeSceneRule(index: number) {
    setForm((current) => ({
      ...current,
      scene_rules: current.scene_rules
        .filter((_, ruleIndex) => ruleIndex !== index)
        .map((rule, ruleIndex) => ({ ...rule, sort_order: ruleIndex })),
    }));
  }

  function payloadFromEditors(): PromptTemplateWrite {
    const story = JSON.parse(storyJson) as unknown;
    const characters = JSON.parse(charactersJson) as unknown;
    if (!story || typeof story !== 'object' || Array.isArray(story)) throw new Error('故事锚点必须是 JSON 对象。');
    if (!Array.isArray(characters)) throw new Error('人物锚点必须是 JSON 数组。');
    return {
      ...form,
      story_anchor: story as Record<string, unknown>,
      characters: characters.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item))),
    };
  }

  async function save() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const payload = payloadFromEditors();
      const saved = selectedId ? await updatePrompt(selectedId, payload) : await createPrompt(payload);
      setMessage('提示词包已保存。');
      loadTemplates(saved.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selectedId || !window.confirm('确认删除当前提示词包？')) return;
    setBusy(true);
    setError(null);
    try {
      await deletePrompt(selectedId);
      setMessage('提示词包已删除。');
      startNew();
      loadTemplates(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleImport(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const imported = await importPromptPackage(await file.text());
      setMessage(`已导入：${imported.name}`);
      loadTemplates(imported.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function handleExport() {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const { content } = await exportPromptPackage(selectedId);
      const url = URL.createObjectURL(new Blob([content], { type: 'application/json;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${safeFileName(form.name || 'prompt-package')}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setMessage('提示词包 JSON 已导出。');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TopBar title="提示词包" subtitle="改写规则、故事发展与人物设定使用同一个项目级 JSON。" onRefresh={() => loadTemplates(selectedId)} />
      {(error || message) && (
        <div className={`mb-3 rounded-xl border px-4 py-2 text-sm ${error ? 'border-rose-300/25 bg-rose-400/10 text-rose-100' : 'border-emerald-300/25 bg-emerald-400/10 text-emerald-100'}`}>
          {error || message}
        </div>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-[280px_1fr] gap-4 max-lg:grid-cols-1">
        <GlassCard className="min-h-0 overflow-y-auto" title="提示词包" strong>
          <div className="mb-4 grid grid-cols-2 gap-2">
            <SecondaryButton onClick={startNew}><Plus size={15} />新建</SecondaryButton>
            <SecondaryButton onClick={() => fileInputRef.current?.click()}><Upload size={15} />导入</SecondaryButton>
            <input ref={fileInputRef} accept="application/json,.json" className="hidden" onChange={(event) => void handleImport(event.target.files?.[0])} type="file" />
          </div>
          {templates.length === 0 ? (
            <EmptyState title="还没有提示词包" description="可以新建，也可以从分析项目提取或导入 JSON。" />
          ) : (
            <div className="space-y-2">
              {templates.map((template) => (
                <button
                  className={`w-full rounded-xl border p-3 text-left transition ${selectedId === template.id ? 'border-sky-300/35 bg-sky-300/12' : 'border-white/10 bg-white/[0.035] hover:bg-white/[0.07]'}`}
                  key={template.id}
                  onClick={() => { setSelectedId(template.id); fillForm(template); }}
                  type="button"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-semibold text-white">{template.name}</span>
                    {template.is_default && <StatusPill variant="warning">默认</StatusPill>}
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">{template.description || `${template.scene_rules.length} 个场景分类 · v${template.version}`}</p>
                </button>
              ))}
            </div>
          )}
        </GlassCard>

        <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950/35">
          <header className="shrink-0 border-b border-white/10 px-5 py-4">
            <div className="flex items-start justify-between gap-4">
              <div className="grid min-w-0 flex-1 grid-cols-[minmax(220px,420px)_1fr] gap-3 max-xl:grid-cols-1">
                <input className="form-input py-2" placeholder="提示词包名称" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
                <input className="form-input py-2" placeholder="用途说明" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
              </div>
              <label className="flex shrink-0 items-center gap-2 text-xs text-[var(--text-muted)]">
                <input checked={form.is_default} onChange={(event) => setForm({ ...form, is_default: event.target.checked })} type="checkbox" />默认
              </label>
            </div>
            <nav className="mt-4 flex gap-1 overflow-x-auto border-b border-white/10">
              {tabs.map((item) => (
                <button className={`shrink-0 border-b-2 px-4 py-2 text-sm transition ${tab === item.key ? 'border-sky-400 text-white' : 'border-transparent text-[var(--text-muted)] hover:text-white'}`} key={item.key} onClick={() => setTab(item.key)} type="button">
                  {item.label}
                </button>
              ))}
            </nav>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            {tab === 'system' && <SystemEditor form={form} setForm={setForm} />}
            {tab === 'scene' && <SceneEditor form={form} onAdd={addSceneRule} onRemove={removeSceneRule} onUpdate={updateSceneRule} setForm={setForm} />}
            {tab === 'rewrite' && <RewriteEditor form={form} onUpdate={updateSceneRule} setForm={setForm} />}
            {tab === 'story' && <JsonEditor icon={<BookOpen size={17} />} label="故事发展锚点" value={storyJson} onChange={setStoryJson} />}
            {tab === 'characters' && <JsonEditor icon={<Users size={17} />} label="人物锚点数组" value={charactersJson} onChange={setCharactersJson} />}
          </div>

          <footer className="flex shrink-0 items-center justify-between border-t border-white/10 bg-slate-950/70 px-5 py-3">
            <div className="text-xs text-[var(--text-muted)]">{form.scene_rules.length} 个场景分类 · {form.characters.length} 个人物锚点</div>
            <div className="flex gap-2">
              <SecondaryButton disabled={busy || !selectedId} onClick={() => void handleExport()}><Download size={15} />导出 JSON</SecondaryButton>
              <DangerButton disabled={busy || !selectedId} onClick={() => void remove()}><Trash2 size={15} />删除</DangerButton>
              <PrimaryButton disabled={busy || !form.name.trim()} onClick={() => void save()}><Save size={15} />保存全部</PrimaryButton>
            </div>
          </footer>
        </section>
      </div>
    </div>
  );
}

function SystemEditor({ form, setForm }: { form: PromptTemplateWrite; setForm: (value: PromptTemplateWrite) => void }) {
  return (
    <div className="space-y-5">
      <EditorBlock label="系统规则" hint="全局注入，但只写任务边界、事实约束和输出要求。">
        <textarea className="prompt-editor" value={form.global_rules} onChange={(event) => setForm({ ...form, global_rules: event.target.value })} />
      </EditorBlock>
      <EditorBlock label="章节分析规则" hint="用于分析项目生成章节摘要，也是提取完整提示词包的材料。">
        <textarea className="prompt-editor min-h-44" value={form.summary_rules} onChange={(event) => setForm({ ...form, summary_rules: event.target.value })} />
      </EditorBlock>
    </div>
  );
}

function SceneEditor({ form, onAdd, onRemove, onUpdate, setForm }: {
  form: PromptTemplateWrite;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onUpdate: (index: number, patch: Partial<PromptSceneRule>) => void;
  setForm: (value: PromptTemplateWrite) => void;
}) {
  return (
    <div className="space-y-5">
      <EditorBlock label="场景识别总规则" hint="定义模型如何判断场景与是否需要改写。">
        <textarea className="prompt-editor min-h-40" value={form.scene_detection_rules} onChange={(event) => setForm({ ...form, scene_detection_rules: event.target.value })} />
      </EditorBlock>
      <div className="flex items-center justify-between">
        <div><h3 className="text-sm font-semibold text-white">剧情场景分类</h3><p className="mt-1 text-xs text-[var(--text-muted)]">识别阶段只返回这些 key，后续自动匹配具体改写规则。</p></div>
        <SecondaryButton onClick={onAdd}><Plus size={15} />添加分类</SecondaryButton>
      </div>
      {form.scene_rules.map((rule, index) => (
        <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4" key={`${rule.scene_key}-${index}`}>
          <div className="grid grid-cols-[140px_220px_1fr_auto] gap-3 max-xl:grid-cols-2">
            <input className="form-input py-2 text-sm" placeholder="scene_key" value={rule.scene_key} onChange={(event) => onUpdate(index, { scene_key: event.target.value })} />
            <input className="form-input py-2 text-sm" placeholder="显示名称" value={rule.display_name} onChange={(event) => onUpdate(index, { display_name: event.target.value })} />
            <input className="form-input py-2 text-sm" placeholder="分类说明" value={rule.description} onChange={(event) => onUpdate(index, { description: event.target.value })} />
            <button className="stage-icon-button" onClick={() => onRemove(index)} title="删除分类" type="button"><Trash2 size={14} /></button>
          </div>
          <textarea className="prompt-editor mt-3 min-h-28" placeholder="识别此类场景的具体规则" value={rule.detection_prompt} onChange={(event) => onUpdate(index, { detection_prompt: event.target.value })} />
        </div>
      ))}
      {form.scene_rules.length === 0 && <EmptyState title="还没有场景分类" description="添加战斗、情感、对话、过渡等分类，并为每类配置识别条件。" />}
    </div>
  );
}

function RewriteEditor({ form, onUpdate, setForm }: {
  form: PromptTemplateWrite;
  onUpdate: (index: number, patch: Partial<PromptSceneRule>) => void;
  setForm: (value: PromptTemplateWrite) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-5 max-xl:grid-cols-1">
      <EditorBlock label="通用改写规则" hint="所有场景统一执行。风格要求放在这里。">
        <textarea className="prompt-editor min-h-[430px]" value={form.rewrite_rules} onChange={(event) => setForm({ ...form, rewrite_rules: event.target.value })} />
      </EditorBlock>
      <div>
        <h3 className="text-sm font-semibold text-white">场景具体规则</h3>
        <p className="mt-1 text-xs text-[var(--text-muted)]">只在识别到对应 scene_key 时注入。</p>
        <div className="mt-4 space-y-4">
          {form.scene_rules.map((rule, index) => (
            <EditorBlock key={`${rule.scene_key}-${index}`} label={rule.display_name || rule.scene_key} hint={rule.scene_key}>
              <textarea className="prompt-editor min-h-32" value={rule.rewrite_prompt} onChange={(event) => onUpdate(index, { rewrite_prompt: event.target.value })} />
            </EditorBlock>
          ))}
          {form.scene_rules.length === 0 && <EmptyState title="暂无具体规则" description="先到“场景识别”添加分类。" />}
        </div>
      </div>
    </div>
  );
}

function JsonEditor({ icon, label, onChange, value }: { icon: ReactNode; label: string; onChange: (value: string) => void; value: string }) {
  return (
    <EditorBlock label={<span className="flex items-center gap-2">{icon}{label}</span>} hint="保存和导出时会校验 JSON 结构。">
      <textarea className="prompt-editor min-h-[500px] font-mono text-xs" spellCheck={false} value={value} onChange={(event) => onChange(event.target.value)} />
    </EditorBlock>
  );
}

function EditorBlock({ children, hint, label }: { children: ReactNode; hint?: string; label: ReactNode }) {
  return (
    <section>
      <h3 className="text-sm font-semibold text-white">{label}</h3>
      {hint && <p className="mt-1 text-xs text-[var(--text-muted)]">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function safeFileName(name: string) {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim() || 'prompt-package';
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
