import { useEffect, useState } from 'react';
import { KeyRound, Plus, Save, Trash2, Wifi } from 'lucide-react';
import { createModel, deleteModel, getModels, testModel, updateModel } from '../api/client';
import type { ModelConfig, ModelWrite } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { DangerButton } from '../components/DangerButton';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StatusPill } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

const emptyForm: ModelWrite = {
  display_name: '',
  provider: 'openai_compatible',
  base_url: 'https://api.openai.com/v1',
  model_name: '',
  api_key: '',
  temperature: 0.7,
  max_tokens: null,
  timeout_seconds: 60,
  is_default: false,
};

export function ModelManagePage() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState<ModelWrite>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function fillForm(model: ModelConfig) {
    setForm({
      display_name: model.display_name,
      provider: model.provider,
      base_url: model.base_url,
      model_name: model.model_name,
      api_key: '',
      temperature: model.temperature,
      max_tokens: model.max_tokens,
      timeout_seconds: model.timeout_seconds,
      is_default: model.is_default,
    });
  }

  function loadModels(nextSelectedId?: number | null) {
    setError(null);
    getModels()
      .then((items) => {
        setModels(items);
        const id = nextSelectedId ?? selectedId ?? items[0]?.id ?? null;
        setSelectedId(id);
        const selected = items.find((model) => model.id === id);
        if (selected) fillForm(selected);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }

  useEffect(() => {
    loadModels(null);
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
      const payload = { ...form, api_key: form.api_key?.trim() || null };
      const saved = selectedId ? await updateModel(selectedId, payload) : await createModel(payload);
      setMessage('模型配置已保存。');
      loadModels(saved.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selectedId || !window.confirm('确认删除当前模型配置？')) return;
    setBusy(true);
    setError(null);
    try {
      await deleteModel(selectedId);
      setMessage('模型已删除。');
      setSelectedId(null);
      setForm(emptyForm);
      loadModels(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function testConnection() {
    if (!selectedId) {
      setError('请先保存并选择一个模型。');
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await testModel(selectedId);
      setMessage(result.ok ? `连接成功：${result.message}` : `连接失败：${result.message}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <TopBar title="模型" subtitle="管理 OpenAI-compatible API 模型配置。API Key 只写入后端 keyring，不会回显。" onRefresh={() => loadModels(selectedId)} />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      {message && <GlassCard className="mb-5 border-emerald-300/25 text-emerald-100">{message}</GlassCard>}
      <div className="grid grid-cols-[360px_1fr] gap-5 max-lg:grid-cols-1">
        <GlassCard title="模型列表" strong>
          <SecondaryButton className="mb-4 w-full" onClick={startNew}>
            <Plus size={16} />
            新建模型
          </SecondaryButton>
          {models.length === 0 ? (
            <EmptyState title="尚未配置模型" description="创建一个 OpenAI-compatible 模型配置后即可用于章节总结、识别和改写。" />
          ) : (
            <div className="space-y-3">
              {models.map((model) => (
                <button
                  className={`w-full cursor-pointer rounded-2xl border p-4 text-left transition ${selectedId === model.id ? 'border-sky-300/30 bg-sky-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                  key={model.id}
                  onClick={() => {
                    setSelectedId(model.id);
                    fillForm(model);
                  }}
                >
                  <p className="font-semibold text-white">{model.display_name}</p>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">{model.provider} · {model.model_name}</p>
                  <div className="mt-3 flex gap-2">
                    {model.is_default && <StatusPill variant="success">默认</StatusPill>}
                    <StatusPill variant={model.has_api_key ? 'info' : 'warning'}>{model.has_api_key ? '已保存 Key' : '未配置 Key'}</StatusPill>
                  </div>
                </button>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard title={selectedId ? '编辑模型' : '新建模型'} eyebrow="Model Config" strong>
          <div className="grid grid-cols-2 gap-4 max-xl:grid-cols-1">
            <Field label="Display name" value={form.display_name} onChange={(value) => setForm({ ...form, display_name: value })} />
            <Field label="Provider" value={form.provider} onChange={(value) => setForm({ ...form, provider: value })} />
            <Field label="Base URL" value={form.base_url} onChange={(value) => setForm({ ...form, base_url: value })} />
            <Field label="Model" value={form.model_name} onChange={(value) => setForm({ ...form, model_name: value })} />
            <Field label="API Key（留空则不更新）" type="password" value={form.api_key ?? ''} onChange={(value) => setForm({ ...form, api_key: value })} />
            <Field label="Temperature" type="number" step="0.1" value={String(form.temperature)} onChange={(value) => setForm({ ...form, temperature: Number(value) })} />
            <Field label="Max tokens（0 表示不限制）" type="number" value={String(form.max_tokens ?? 0)} onChange={(value) => setForm({ ...form, max_tokens: Number(value) || null })} />
            <Field label="Timeout seconds" type="number" value={String(form.timeout_seconds)} onChange={(value) => setForm({ ...form, timeout_seconds: Number(value) || 60 })} />
          </div>
          <label className="mt-5 flex items-center gap-3 text-sm text-[var(--text-muted)]">
            <input checked={form.is_default} onChange={(event) => setForm({ ...form, is_default: event.target.checked })} type="checkbox" />
            设为默认模型
          </label>
          <div className="mt-7 flex flex-wrap gap-3">
            <PrimaryButton disabled={busy} onClick={save}>
              <Save size={16} />
              保存
            </PrimaryButton>
            <SecondaryButton disabled={busy || !selectedId} onClick={testConnection}>
              <Wifi size={16} />
              测试连接
            </SecondaryButton>
            <DangerButton disabled={busy || !selectedId} onClick={remove}>
              <Trash2 size={16} />
              删除
            </DangerButton>
          </div>
          <div className="mt-6 rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-sm text-[var(--text-muted)]">
            <KeyRound className="mb-2 text-[var(--accent-gold)]" size={20} />
            后端仅返回 has_api_key，不会把真实 API Key 传给前端。
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text', step }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string }) {
  return (
    <label>
      <span className="form-label">{label}</span>
      <input className="form-input" type={type} step={step} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
