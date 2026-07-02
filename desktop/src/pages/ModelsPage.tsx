import { useEffect, useState } from 'react';
import { KeyRound } from 'lucide-react';
import { getModels } from '../api/client';
import type { ModelConfig } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { StatusPill } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

export function ModelsPage() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getModels()
      .then((items) => {
        setModels(items);
        setSelectedId(items[0]?.id ?? null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const selected = models.find((model) => model.id === selectedId) ?? null;

  return (
    <div>
      <TopBar title="模型" subtitle="UI-R2 list-only 模型配置入口，不暴露 API Key。" />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      {models.length === 0 ? (
        <EmptyState title="尚未配置模型" description="请先在旧 PySide6 模型页面添加模型；UI-R2 暂只读取模型列表。" />
      ) : (
        <div className="grid grid-cols-[360px_1fr] gap-5 max-lg:grid-cols-1">
          <GlassCard title="模型列表" strong>
            <div className="space-y-3">
              {models.map((model) => (
                <button
                  className={`w-full cursor-pointer rounded-2xl border p-4 text-left transition ${selectedId === model.id ? 'border-sky-300/30 bg-sky-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                  key={model.id}
                  onClick={() => setSelectedId(model.id)}
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
          </GlassCard>
          <GlassCard title="模型详情" eyebrow="Read Only" strong>
            {selected && (
              <div className="space-y-4">
                <Detail label="Display name" value={selected.display_name} />
                <Detail label="Provider" value={selected.provider} />
                <Detail label="Base URL" value={selected.base_url} />
                <Detail label="Model" value={selected.model_name} />
                <Detail label="Temperature" value={selected.temperature} />
                <Detail label="Max tokens" value={selected.max_tokens ?? '未设置'} />
                <Detail label="Timeout" value={`${selected.timeout_seconds}s`} />
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-sm text-[var(--text-muted)]">
                  <KeyRound className="mb-2 text-[var(--accent-gold)]" size={20} />
                  UI-R2 不读取、不显示真实 API Key。编辑与测试连接保留在旧 PySide6 页面，后续 UI-R3 再接入安全写入。
                </div>
              </div>
            )}
          </GlassCard>
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.14em] text-[var(--text-soft)]">{label}</p>
      <p className="mt-1 break-all text-sm text-white">{value}</p>
    </div>
  );
}
