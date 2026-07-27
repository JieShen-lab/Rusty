import { useEffect, useMemo, useState } from 'react';
import { Copy, MoreHorizontal, Pencil, Plus, Search, Sparkles, Tag, Trash2, UserRound } from 'lucide-react';
import {
  analyzeCharacterCard,
  copyCharacterCard,
  createCharacterCard,
  createCharacterTag,
  deleteCharacterCard,
  deleteCharacterTag,
  getCharacterCards,
  getCharacterTags,
  getProjects,
  updateCharacterCard,
} from '../api/client';
import type { AnalysisStatus, CharacterCard, CharacterCustomField, Project, ResourceTag } from '../api/types';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';

type Scope = 'public' | 'project';
type Filter = 'all' | 'unanalyzed' | 'untagged';

export function CharacterLibraryPage() {
  const [scope, setScope] = useState<Scope>('public');
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [cards, setCards] = useState<CharacterCard[]>([]);
  const [tags, setTags] = useState<ResourceTag[]>([]);
  const [filter, setFilter] = useState<Filter>('all');
  const [tagId, setTagId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<CharacterCard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = cards.find((item) => item.id === selectedId) ?? cards[0] ?? null;
  const filtered = useMemo(() => cards.filter((card) => {
    const text = `${card.name} ${card.identity} ${card.setting_text} ${card.raw_text} ${card.tags.join(' ')}`.toLowerCase();
    return !query.trim() || text.includes(query.trim().toLowerCase());
  }), [cards, query]);

  async function load(preferredId?: number | null) {
    setError(null);
    try {
      const [projectItems, tagItems] = await Promise.all([getProjects(), getCharacterTags()]);
      const nextProjectId = projectId ?? projectItems[0]?.id ?? null;
      const items = await getCharacterCards(scope, scope === 'project' ? nextProjectId : null);
      setProjects(projectItems);
      setProjectId(nextProjectId);
      setTags(tagItems);
      setCards(items.filter((card) => {
        if (filter === 'unanalyzed' && card.analysis_status !== 'unanalyzed') return false;
        if (filter === 'untagged' && card.tags.length > 0) return false;
        if (tagId && !card.tags.includes(tagItems.find((tag) => tag.id === tagId)?.name ?? '')) return false;
        return true;
      }));
      setSelectedId(preferredId ?? items[0]?.id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  useEffect(() => {
    void load();
  }, [scope, projectId, filter, tagId]);

  async function createBlank() {
    setEditing({
      id: 0,
      name: '',
      aliases: [],
      description: '',
      priority: 50,
      is_main: false,
      relationship_notes: '',
      personality: '',
      speech_style: '',
      action_constraints: '',
      anti_ooc_rules: '',
      profile: {},
      source_metadata: {},
      import_metadata: {},
      scope,
      project_id: scope === 'project' ? projectId : null,
      source_character_card_id: null,
      source_version: null,
      version: 1,
      sort_order: 0,
      identity: '',
      age: '',
      setting_text: '',
      custom_fields: [],
      raw_text: '',
      analysis_status: 'analyzed',
      cover_path: null,
      cover_updated_at: null,
      tags: [],
    });
  }

  async function addTag() {
    const name = window.prompt('新增标签');
    if (!name?.trim()) return;
    const tag = await createCharacterTag(name);
    setTagId(tag.id);
    await load(selectedId);
  }

  async function removeTag(id: number) {
    if (!window.confirm('删除标签只会解除关联，不会删除角色卡。')) return;
    await deleteCharacterTag(id);
    if (tagId === id) setTagId(null);
    await load(selectedId);
  }

  async function copyCard(card: CharacterCard) {
    if (card.scope === 'public') {
      if (!projectId) {
        setError('请先选择目标工程。');
        return;
      }
      const copied = await copyCharacterCard(card.id, 'project', projectId);
      await load(copied.id);
      return;
    }
    if (!window.confirm('确认保存为新的公共角色卡副本？')) return;
    const copied = await copyCharacterCard(card.id, 'public', null);
    await load(copied.id);
  }

  async function runAnalyze(card: CharacterCard) {
    const raw = window.prompt('粘贴 AI 分析得到的 JSON：identity、age、setting_text、custom_fields。', JSON.stringify({
      identity: card.identity,
      age: card.age,
      setting_text: card.setting_text,
      custom_fields: card.custom_fields,
    }, null, 2));
    if (!raw) return;
    const parsed = JSON.parse(raw) as { identity?: string; age?: string; setting_text?: string; custom_fields?: CharacterCustomField[] };
    const updated = await analyzeCharacterCard(card.id, {
      identity: parsed.identity ?? '',
      age: parsed.age ?? '',
      setting_text: parsed.setting_text ?? '',
      custom_fields: parsed.custom_fields ?? [],
    });
    await load(updated.id);
  }

  async function save(card: CharacterCard, draft: CharacterDraft) {
    if (!draft.name.trim()) {
      setError('角色名不能为空。');
      return;
    }
    const missing = [
      !draft.identity.trim() ? '身份' : '',
      !draft.age.trim() ? '年龄' : '',
      !draft.setting_text.trim() ? '设定' : '',
    ].filter(Boolean);
    if (missing.length && !window.confirm(`以下字段为空：${missing.join('、')}。仍然保存？`)) return;
    const payload = {
      name: draft.name.trim(),
      aliases: [],
      description: draft.setting_text,
      priority: card.priority,
      is_main: card.is_main,
      relationship_notes: '',
      personality: '',
      speech_style: '',
      action_constraints: '',
      anti_ooc_rules: '',
      profile: {},
      source_metadata: card.source_metadata,
      import_metadata: card.import_metadata,
      scope,
      project_id: scope === 'project' ? projectId : null,
      identity: draft.identity,
      age: draft.age,
      setting_text: draft.setting_text,
      custom_fields: normalizeFields(draft.custom_fields),
      raw_text: draft.raw_text,
      analysis_status: draft.analysis_status,
    };
    const saved = card.id ? await updateCharacterCard(card.id, payload) : await createCharacterCard(payload);
    setEditing(null);
    await load(saved.id);
  }

  return (
    <div className="resource-page">
      <TopBar title="角色卡库" actions={<PrimaryButton onClick={createBlank}><Plus size={16} />新建角色</PrimaryButton>} />
      {error ? <div className="inline-alert error">{error}</div> : null}
      <div className="resource-layout">
        <aside className="resource-sidebar">
          <button className={scope === 'public' ? 'selected' : ''} onClick={() => { setScope('public'); setTagId(null); }}>公共角色</button>
          <button className={scope === 'project' ? 'selected' : ''} onClick={() => { setScope('project'); setTagId(null); }}>工程角色</button>
          {scope === 'project' ? <select value={projectId ?? ''} onChange={(event) => setProjectId(Number(event.target.value) || null)}>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select> : null}
          <hr />
          <button className={filter === 'all' && tagId === null ? 'selected' : ''} onClick={() => { setFilter('all'); setTagId(null); }}>全部角色</button>
          <button className={filter === 'unanalyzed' ? 'selected' : ''} onClick={() => { setFilter('unanalyzed'); setTagId(null); }}>未分析</button>
          <button className={filter === 'untagged' ? 'selected' : ''} onClick={() => { setFilter('untagged'); setTagId(null); }}>无标签</button>
          <div className="resource-sidebar-title"><span>我的标签</span><button onClick={addTag} type="button"><Plus size={14} /></button></div>
          {tags.map((item) => (
            <div className="resource-tag-row" key={item.id}>
              <button className={tagId === item.id ? 'selected' : ''} onClick={() => { setTagId(item.id); setFilter('all'); }}><Tag size={14} />{item.name}<small>{item.resource_count}</small></button>
              <button aria-label="删除标签" onClick={() => removeTag(item.id)} type="button"><Trash2 size={13} /></button>
            </div>
          ))}
        </aside>
        <main className="resource-main">
          <label className="search-field"><Search size={15} /><input placeholder="搜索角色名、身份、设定或标签" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <div className="character-cover-grid">
            {filtered.map((card) => (
              <article className={`character-cover-card ${selectedId === card.id ? 'selected' : ''}`} key={card.id} onClick={() => setSelectedId(card.id)} onDoubleClick={() => setEditing(card)}>
                <div className="character-cover" style={{ background: defaultCover(card.name) }}><UserRound size={34} /></div>
                <header><strong>{card.name}</strong><span>{card.identity || card.setting_text.slice(0, 24) || '未填写设定'}</span></header>
                <div className="resource-badges"><span>{card.analysis_status === 'unanalyzed' ? '未分析' : '已分析'}</span>{card.tags.slice(0, 2).map((tag) => <span key={tag}>{tag}</span>)}</div>
                <div className="resource-card-menu">
                  <button onClick={(event) => { event.stopPropagation(); setEditing(card); }} type="button"><Pencil size={15} /></button>
                  <button onClick={(event) => { event.stopPropagation(); copyCard(card); }} type="button"><Copy size={15} /></button>
                  {card.analysis_status === 'unanalyzed' ? <button onClick={(event) => { event.stopPropagation(); runAnalyze(card); }} type="button"><Sparkles size={15} /></button> : null}
                  <button onClick={(event) => { event.stopPropagation(); if (window.confirm('确认删除角色卡？')) deleteCharacterCard(card.id).then(() => load(null)); }} type="button"><MoreHorizontal size={15} /></button>
                </div>
              </article>
            ))}
          </div>
        </main>
        <aside className="resource-detail">
          {selected ? (
            <>
              <h2>{selected.name}</h2>
              <p>{selected.identity || '身份未填'} · {selected.age || '年龄未填'} · {selected.analysis_status === 'unanalyzed' ? '未分析' : '已分析'}</p>
              <section><h3>设定</h3><p>{selected.setting_text || '未填写'}</p></section>
              <section><h3>标签</h3><p>{selected.tags.length ? selected.tags.join(' / ') : '无标签'}</p></section>
              <section><h3>自定义字段</h3>{selected.custom_fields.length ? selected.custom_fields.map((field) => <p key={field.id}><strong>{field.label}：</strong>{field.value}</p>) : <p>暂无</p>}</section>
              <section><h3>原始文字</h3><p>{selected.raw_text ? selected.raw_text.slice(0, 300) : '无'}</p></section>
            </>
          ) : <p>选择一个角色查看详情。</p>}
        </aside>
      </div>
      {editing ? <CharacterEditor card={editing} onClose={() => setEditing(null)} onSave={save} /> : null}
    </div>
  );
}

type CharacterDraft = {
  name: string;
  identity: string;
  age: string;
  setting_text: string;
  custom_fields: CharacterCustomField[];
  raw_text: string;
  analysis_status: AnalysisStatus;
};

function CharacterEditor({ card, onClose, onSave }: {
  card: CharacterCard;
  onClose: () => void;
  onSave: (card: CharacterCard, draft: CharacterDraft) => void;
}) {
  const [draft, setDraft] = useState<CharacterDraft>({
    name: card.name,
    identity: card.identity,
    age: card.age,
    setting_text: card.setting_text,
    custom_fields: card.custom_fields,
    raw_text: card.raw_text,
    analysis_status: card.analysis_status,
  });
  function updateField(index: number, patch: Partial<CharacterCustomField>) {
    setDraft((current) => ({
      ...current,
      custom_fields: current.custom_fields.map((field, itemIndex) => itemIndex === index ? { ...field, ...patch } : field),
    }));
  }
  return (
    <div className="modal-backdrop">
      <section className="resource-editor" role="dialog" aria-modal="true">
        <header><h2>{card.id ? '编辑角色卡' : '新建角色卡'}</h2></header>
        <label>角色名<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label>身份<input value={draft.identity} onChange={(event) => setDraft({ ...draft, identity: event.target.value })} /></label>
        <label>年龄<input value={draft.age} onChange={(event) => setDraft({ ...draft, age: event.target.value })} /></label>
        <label>设定<textarea value={draft.setting_text} onChange={(event) => setDraft({ ...draft, setting_text: event.target.value })} /></label>
        <label>分析状态<select value={draft.analysis_status} onChange={(event) => setDraft({ ...draft, analysis_status: event.target.value as AnalysisStatus })}><option value="unanalyzed">未分析</option><option value="analyzed">已分析</option></select></label>
        <div className="custom-field-list">
          <strong>自定义字段</strong>
          {draft.custom_fields.map((field, index) => (
            <div className="custom-field-row" key={field.id}>
              <input value={field.label} onChange={(event) => updateField(index, { label: event.target.value })} />
              <input value={field.value} onChange={(event) => updateField(index, { value: event.target.value })} />
              <button onClick={() => setDraft({ ...draft, custom_fields: draft.custom_fields.filter((_, itemIndex) => itemIndex !== index) })} type="button"><Trash2 size={14} /></button>
            </div>
          ))}
          <SecondaryButton onClick={() => setDraft({ ...draft, custom_fields: [...draft.custom_fields, { id: crypto.randomUUID(), label: '', value: '', sort_order: draft.custom_fields.length }] })}><Plus size={14} />新增字段</SecondaryButton>
        </div>
        <label>原始文字<textarea value={draft.raw_text} onChange={(event) => setDraft({ ...draft, raw_text: event.target.value })} /></label>
        <footer><SecondaryButton onClick={onClose}>返回补充</SecondaryButton><PrimaryButton disabled={!draft.name.trim()} onClick={() => onSave(card, draft)}>保存</PrimaryButton></footer>
      </section>
    </div>
  );
}

function normalizeFields(fields: CharacterCustomField[]) {
  const seen = new Set<string>();
  return fields.filter((field) => {
    const key = field.label.trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map((field, index) => ({ ...field, label: field.label.trim(), sort_order: index }));
}

function defaultCover(name: string) {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const hue = hash % 360;
  return `linear-gradient(135deg, hsl(${hue} 58% 38%), hsl(${(hue + 42) % 360} 48% 24%))`;
}
