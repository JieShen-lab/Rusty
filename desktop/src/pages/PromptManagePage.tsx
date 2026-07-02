import { useEffect, useState } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';
import { createPrompt, deletePrompt, getPrompts, updatePrompt } from '../api/client';
import type { PromptTemplate, PromptTemplateWrite } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { DangerButton } from '../components/DangerButton';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StatusPill } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

const emptyForm: PromptTemplateWrite = {
  name: '',
  global_rules: '',
  summary_rules: '',
  scene_detection_rules: '',
  rewrite_rules: '',
  is_default: false,
};

const tabs = [
  ['全局规则', 'global_rules'],
  ['总结规则', 'summary_rules'],
  ['场景识别', 'scene_detection_rules'],
  ['改写规则', 'rewrite_rules'],
] as const;

type PromptField = (typeof tabs)[number][1];

export function PromptManagePage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState<PromptTemplateWrite>(emptyForm);
  const [tab, setTab] = useState<PromptField>('global_rules');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function fillForm(template: PromptTemplate) {
    setForm({
      name: template.name,
      global_rules: template.global_rules,
      summary_rules: template.summary_rules,
      scene_detection_rules: template.scene_detection_rules,
      rewrite_rules: template.rewrite_rules,
      is_default: template.is_default,
    });
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
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }

  useEffect(() => {
    loadTemplates(null);
  }, []);

  function startNew() {
    setSelectedId(null);
    setForm(emptyForm);
    setMessage(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved = selectedId ? await updatePrompt(selectedId, form) : await createPrompt(form);
      setMessage('提示词模板已保存。');
      loadTemplates(saved.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selectedId || !window.confirm('确认删除当前提示词模板？')) return;
    setBusy(true);
    setError(null);
    try {
      await deletePrompt(selectedId);
      setMessage('提示词模板已删除。');
      setSelectedId(null);
      setForm(emptyForm);
      loadTemplates(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <TopBar title="提示词" subtitle="管理全局规则、总结规则、场景识别和改写规则。" onRefresh={() => loadTemplates(selectedId)} />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      {message && <GlassCard className="mb-5 border-emerald-300/25 text-emerald-100">{message}</GlassCard>}
      <div className="grid grid-cols-[360px_1fr] gap-5 max-lg:grid-cols-1">
        <GlassCard title="模板列表" strong>
          <SecondaryButton className="mb-4 w-full" onClick={startNew}>
            <Plus size={16} />
            新建模板
          </SecondaryButton>
          {templates.length === 0 ? (
            <EmptyState title="尚未配置提示词模板" description="创建一个模板后即可作为章节总结、识别和改写的默认策略。" />
          ) : (
            <div className="space-y-3">
              {templates.map((template) => (
                <button
                  className={`w-full cursor-pointer rounded-2xl border p-4 text-left transition ${selectedId === template.id ? 'border-amber-300/30 bg-amber-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                  key={template.id}
                  onClick={() => {
                    setSelectedId(template.id);
                    fillForm(template);
                  }}
                >
                  <p className="font-semibold text-white">{template.name}</p>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">version {template.version}</p>
                  {template.is_default && (
                    <div className="mt-3">
                      <StatusPill variant="warning">默认模板</StatusPill>
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard title={selectedId ? '编辑模板' : '新建模板'} eyebrow="Prompt Strategy" strong>
          <div className="mb-4 grid grid-cols-[1fr_auto] gap-3 max-md:grid-cols-1">
            <label>
              <span className="form-label">模板名称</span>
              <input className="form-input" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
            </label>
            <label className="mt-7 flex items-center gap-3 text-sm text-[var(--text-muted)] max-md:mt-0">
              <input checked={form.is_default} onChange={(event) => setForm({ ...form, is_default: event.target.checked })} type="checkbox" />
              默认模板
            </label>
          </div>
          <div className="mb-4 flex flex-wrap gap-2">
            {tabs.map(([label, key]) => (
              <button className={`rounded-full border px-3 py-1 text-xs ${tab === key ? 'border-amber-300/30 bg-amber-300/15 text-white' : 'border-white/10 bg-white/5 text-[var(--text-muted)]'}`} key={key} onClick={() => setTab(key)}>
                {label}
              </button>
            ))}
          </div>
          <textarea
            className="chapter-text min-h-[420px] w-full resize-y rounded-3xl border border-white/10 bg-slate-950/35 p-5 text-sm leading-8 text-slate-100 outline-none"
            value={form[tab]}
            onChange={(event) => setForm({ ...form, [tab]: event.target.value })}
          />
          <div className="mt-6 flex flex-wrap gap-3">
            <PrimaryButton disabled={busy} onClick={save}>
              <Save size={16} />
              保存
            </PrimaryButton>
            <DangerButton disabled={busy || !selectedId} onClick={remove}>
              <Trash2 size={16} />
              删除
            </DangerButton>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
