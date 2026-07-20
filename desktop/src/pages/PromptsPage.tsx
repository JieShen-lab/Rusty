import { useEffect, useState } from 'react';
import { getPrompts } from '../api/client';
import type { PromptTemplate } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { StatusPill } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

const tabs = [
  ['全局规则', 'global_rules'],
  ['总结规则', 'summary_rules'],
  ['改写规则', 'rewrite_rules'],
] as const;

export function PromptsPage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tab, setTab] = useState<(typeof tabs)[number][1]>('global_rules');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPrompts()
      .then((items) => {
        setTemplates(items);
        setSelectedId(items[0]?.id ?? null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const selected = templates.find((template) => template.id === selectedId) ?? null;

  return (
    <div>
      <TopBar title="提示词" subtitle="UI-R2 list-only 提示词策略入口。" />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      {templates.length === 0 ? (
        <EmptyState title="尚未配置提示词模板" description="请先在旧 PySide6 提示词页面添加模板；UI-R2 暂只读取模板列表。" />
      ) : (
        <div className="grid grid-cols-[360px_1fr] gap-5 max-lg:grid-cols-1">
          <GlassCard title="模板列表" strong>
            <div className="space-y-3">
              {templates.map((template) => (
                <button
                  className={`w-full cursor-pointer rounded-2xl border p-4 text-left transition ${selectedId === template.id ? 'border-amber-300/30 bg-amber-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                  key={template.id}
                  onClick={() => setSelectedId(template.id)}
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
          </GlassCard>
          <GlassCard title={selected?.name ?? '模板详情'} eyebrow="Read Only" strong>
            <div className="mb-4 flex flex-wrap gap-2">
              {tabs.map(([label, key]) => (
                <button className={`rounded-full border px-3 py-1 text-xs ${tab === key ? 'border-amber-300/30 bg-amber-300/15 text-white' : 'border-white/10 bg-white/5 text-[var(--text-muted)]'}`} key={key} onClick={() => setTab(key)}>
                  {label}
                </button>
              ))}
            </div>
            <pre className="chapter-text min-h-[420px] whitespace-pre-wrap rounded-3xl border border-white/10 bg-slate-950/35 p-5 text-sm leading-8 text-slate-100">
              {selected?.[tab] || '暂无内容。'}
            </pre>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
