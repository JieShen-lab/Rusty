import { useEffect, useMemo, useState } from 'react';
import { BookOpenText, FileText, Save, Settings2, Sparkles } from 'lucide-react';
import { getPromptDefinitions, updatePromptDefinition } from '../api/client';
import type { CreativeStrategy, PromptDefinition, PromptDefinitionWrite } from '../api/types';
import { FloatingNotice } from '../components/FloatingNotice';
import { TopBar } from '../components/TopBar';

type PromptSlot = 'system' | 'summary' | CreativeStrategy | 'writing';
const SLOTS: Array<{ key: PromptSlot; label: string; icon: typeof Settings2 }> = [
  { key: 'system', label: '系统提示词', icon: Settings2 },
  { key: 'summary', label: '内容总结', icon: BookOpenText },
  { key: 'plot_adjust', label: '调整剧情', icon: FileText },
  { key: 'expansion', label: '增加剧情', icon: FileText },
  { key: 'plot_rewrite', label: '重写剧情', icon: FileText },
  { key: 'writing', label: '写作', icon: Sparkles },
];

export function PromptManagePage() {
  const [items, setItems] = useState<PromptDefinition[]>([]);
  const [slot, setSlot] = useState<PromptSlot>('system');
  const [form, setForm] = useState<PromptDefinitionWrite | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ error?: string; message?: string }>({});
  const selected = useMemo(() => items.find((item) => slotOf(item) === slot) ?? null, [items, slot]);

  useEffect(() => { void reload(); }, []);
  useEffect(() => { setForm(selected ? toWrite(selected) : null); }, [selected]);

  async function reload(preferred: PromptSlot = slot) {
    try { const next = await getPromptDefinitions(); setItems(next); setSlot(preferred); }
    catch (reason) { setFeedback({ error: messageOf(reason) }); }
  }

  async function save() {
    if (!selected || !form) return;
    setBusy(true); setFeedback({});
    try { await updatePromptDefinition(selected.id, form); await reload(slot); setFeedback({ message: '提示词已保存。' }); }
    catch (reason) { setFeedback({ error: messageOf(reason) }); }
    finally { setBusy(false); }
  }

  const meta = SLOTS.find((item) => item.key === slot) ?? SLOTS[0];
  return <div className="prompt-definition-page fixed-prompt-page">
    <TopBar title="提示词" />
    <FloatingNotice error={feedback.error} message={feedback.message} />
    <div className="fixed-prompt-layout">
      <aside className="fixed-prompt-menu">
        {SLOTS.map(({ icon: Icon, key, label }) => <button className={slot === key ? 'active' : ''} key={key} onClick={() => { setFeedback({}); setSlot(key); }} type="button"><Icon size={18} /><strong>{label}</strong></button>)}
      </aside>
      <main className="fixed-prompt-editor">
        <header><h1>{meta.label}</h1></header>
        {form ? <>
          <label className="prompt-body"><span>提示词正文</span><textarea value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} /></label>
          <footer><button className="button primary" disabled={busy || !form.content.trim()} onClick={() => void save()} type="button"><Save size={15} />保存</button></footer>
        </> : <div className="prompt-slot-missing">当前提示词尚未初始化，请重新启动 Rusty 完成数据库升级。</div>}
      </main>
    </div>
  </div>;
}

function slotOf(item: PromptDefinition): PromptSlot | null {
  if (item.kind === 'master') return 'system';
  if (item.kind === 'common_task' && item.task_key === 'chapter_summary') return 'summary';
  if (item.kind === 'common_task' && item.task_key === 'writing') return 'writing';
  if (item.kind === 'workflow_task' && item.task_key === 'special_analysis') return item.workflow_key;
  return null;
}
function toWrite(item: PromptDefinition): PromptDefinitionWrite { const { id: _id, created_at: _created, updated_at: _updated, ...write } = item; return write; }
function messageOf(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
