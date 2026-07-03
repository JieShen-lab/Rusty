import { useEffect, useState } from 'react';
import { Copy, FileInput, Plus, Save, Trash2 } from 'lucide-react';
import {
  createStyleTemplate,
  deleteStyleTemplate,
  exportStyleTemplate,
  getStyleTemplates,
  importStyleTemplate,
  updateStyleTemplate,
} from '../api/client';
import type { StyleDetailLevel, StyleTemplate, StyleTemplateWrite } from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StatusPill } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

const emptyForm: StyleTemplateWrite = {
  name: '',
  description: '',
  detail_level: 'standard',
  global_prompt: '',
  rewrite_prompt: '',
  style_profile: {},
  generated_prompt: '',
  source_metadata: {},
  import_metadata: {},
};

const tabs = [
  ['风格画像', 'style_profile'],
  ['全局补充', 'global_prompt'],
  ['改写规则', 'rewrite_prompt'],
  ['生成提示词', 'generated_prompt'],
] as const;

type StyleTab = (typeof tabs)[number][1];

export function StyleManagePage() {
  const [templates, setTemplates] = useState<StyleTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState<StyleTemplateWrite>(emptyForm);
  const [styleProfileText, setStyleProfileText] = useState('{}');
  const [tab, setTab] = useState<StyleTab>('style_profile');
  const [importText, setImportText] = useState('');
  const [exportText, setExportText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function fillForm(template: StyleTemplate) {
    setForm({
      name: template.name,
      description: template.description,
      detail_level: template.detail_level,
      global_prompt: template.global_prompt,
      rewrite_prompt: template.rewrite_prompt,
      style_profile: template.style_profile,
      generated_prompt: template.generated_prompt,
      source_metadata: template.source_metadata,
      import_metadata: template.import_metadata,
    });
    setStyleProfileText(JSON.stringify(template.style_profile, null, 2));
  }

  function loadTemplates(nextSelectedId?: number | null) {
    setError(null);
    getStyleTemplates()
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
    setStyleProfileText('{}');
    setExportText('');
    setMessage(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const parsedProfile = styleProfileText.trim() ? JSON.parse(styleProfileText) : {};
      if (!parsedProfile || Array.isArray(parsedProfile) || typeof parsedProfile !== 'object') {
        throw new Error('风格画像 JSON 必须是对象');
      }
      const payload = { ...form, style_profile: parsedProfile as Record<string, unknown> };
      const saved = selectedId ? await updateStyleTemplate(selectedId, payload) : await createStyleTemplate(payload);
      setMessage('风格模板已保存。');
      loadTemplates(saved.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selectedId || !window.confirm('确认删除当前风格模板？')) return;
    setBusy(true);
    setError(null);
    try {
      await deleteStyleTemplate(selectedId);
      setMessage('风格模板已删除。');
      setSelectedId(null);
      setForm(emptyForm);
      loadTemplates(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function importTemplate() {
    if (!importText.trim()) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const imported = await importStyleTemplate(importText);
      setMessage('风格模板已导入。');
      setImportText('');
      loadTemplates(imported.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function exportTemplate() {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await exportStyleTemplate(selectedId);
      setExportText(result.content);
      setMessage('风格模板已导出到下方文本框。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const activeValue =
    tab === 'style_profile'
      ? styleProfileText
      : String(form[tab] ?? '');

  return (
    <div>
      <TopBar title="风格模板" subtitle="管理文章风格画像、改写风格规则，并导入导出结构化 JSON。" onRefresh={() => loadTemplates(selectedId)} />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      {message && <GlassCard className="mb-5 border-emerald-300/25 text-emerald-100">{message}</GlassCard>}
      <div className="grid grid-cols-[360px_1fr] gap-5 max-lg:grid-cols-1">
        <GlassCard title="模板列表" strong>
          <SecondaryButton className="mb-4 w-full" onClick={startNew}>
            <Plus size={16} />
            新建风格模板
          </SecondaryButton>
          {templates.length === 0 ? (
            <EmptyState title="尚未配置风格模板" description="可以手动创建，也可以粘贴导出的 JSON 导入。" />
          ) : (
            <div className="space-y-3">
              {templates.map((template) => (
                <button
                  className={`w-full cursor-pointer rounded-2xl border p-4 text-left transition ${selectedId === template.id ? 'border-sky-300/30 bg-sky-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                  key={template.id}
                  onClick={() => {
                    setSelectedId(template.id);
                    fillForm(template);
                  }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-white">{template.name}</p>
                      <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">{template.description || '无描述'}</p>
                    </div>
                    <StatusPill variant="info">{template.detail_level}</StatusPill>
                  </div>
                  <p className="mt-2 text-xs text-[var(--text-soft)]">version {template.version}</p>
                </button>
              ))}
            </div>
          )}
        </GlassCard>

        <div className="space-y-5">
          <GlassCard title={selectedId ? '编辑风格模板' : '新建风格模板'} eyebrow="Style Template" strong>
            <div className="mb-4 grid grid-cols-[1fr_180px] gap-3 max-md:grid-cols-1">
              <label>
                <span className="form-label">模板名称</span>
                <input className="form-input" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
              </label>
              <label>
                <span className="form-label">细节等级</span>
                <select className="form-input" value={form.detail_level} onChange={(event) => setForm({ ...form, detail_level: event.target.value as StyleDetailLevel })}>
                  <option value="brief">brief</option>
                  <option value="standard">standard</option>
                  <option value="detailed">detailed</option>
                </select>
              </label>
            </div>
            <label>
              <span className="form-label">描述</span>
              <input className="form-input" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
            </label>
            <div className="my-4 flex flex-wrap gap-2">
              {tabs.map(([label, key]) => (
                <button className={`rounded-full border px-3 py-1 text-xs ${tab === key ? 'border-sky-300/30 bg-sky-300/15 text-white' : 'border-white/10 bg-white/5 text-[var(--text-muted)]'}`} key={key} onClick={() => setTab(key)}>
                  {label}
                </button>
              ))}
            </div>
            <textarea
              className="chapter-text min-h-[360px] w-full resize-y rounded-3xl border border-white/10 bg-slate-950/35 p-5 font-mono text-sm leading-7 text-slate-100 outline-none"
              value={activeValue}
              onChange={(event) => {
                if (tab === 'style_profile') setStyleProfileText(event.target.value);
                else setForm({ ...form, [tab]: event.target.value });
              }}
            />
            <div className="mt-6 flex flex-wrap gap-3">
              <PrimaryButton disabled={busy} onClick={save}>
                <Save size={16} />
                保存
              </PrimaryButton>
              <SecondaryButton disabled={busy || !selectedId} onClick={exportTemplate}>
                <Copy size={16} />
                导出 JSON
              </SecondaryButton>
              <DangerButton disabled={busy || !selectedId} onClick={remove}>
                <Trash2 size={16} />
                删除
              </DangerButton>
            </div>
          </GlassCard>

          <div className="grid grid-cols-2 gap-5 max-xl:grid-cols-1">
            <GlassCard title="导入 JSON">
              <textarea
                className="chapter-text min-h-[220px] w-full resize-y rounded-3xl border border-white/10 bg-slate-950/35 p-4 font-mono text-xs leading-6 text-slate-100 outline-none"
                placeholder="粘贴 Rusty 风格模板 JSON，或兼容旧格式 JSON。"
                value={importText}
                onChange={(event) => setImportText(event.target.value)}
              />
              <SecondaryButton className="mt-4" disabled={busy || !importText.trim()} onClick={importTemplate}>
                <FileInput size={16} />
                导入
              </SecondaryButton>
            </GlassCard>
            <GlassCard title="导出结果">
              <textarea
                className="chapter-text min-h-[220px] w-full resize-y rounded-3xl border border-white/10 bg-slate-950/35 p-4 font-mono text-xs leading-6 text-slate-100 outline-none"
                readOnly
                value={exportText}
              />
            </GlassCard>
          </div>
        </div>
      </div>
    </div>
  );
}
