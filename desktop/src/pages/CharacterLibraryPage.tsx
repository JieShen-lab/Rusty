import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import {
  BriefcaseBusiness,
  Copy,
  Folder,
  FolderPlus,
  LibraryBig,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Tag,
  Tags,
  Trash2,
  UserRound,
  UsersRound,
} from 'lucide-react';
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
import { DangerButton } from '../components/DangerButton';
import {
  LibraryDefinition,
  LibraryDialog,
  LibraryEmptyState,
  LibrarySidebarItem,
} from '../components/LibraryPrimitives';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

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
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selected = cards.find((item) => item.id === selectedId) ?? null;
  const activeTag = tags.find((tag) => tag.id === tagId)?.name ?? null;
  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return cards.filter((card) => {
      if (filter === 'unanalyzed' && card.analysis_status !== 'unanalyzed') return false;
      if (filter === 'untagged' && card.tags.length > 0) return false;
      if (activeTag && !card.tags.includes(activeTag)) return false;
      if (!normalizedQuery) return true;
      const text = [
        card.name,
        card.aliases.join(' '),
        card.identity,
        card.description,
        card.setting_text,
        card.tags.join(' '),
      ].join(' ').toLocaleLowerCase();
      return text.includes(normalizedQuery);
    });
  }, [activeTag, cards, filter, query]);

  useAutoDismiss(message, setMessage);
  useAutoDismiss(error, setError, 5200);

  async function load(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const [projectItems, tagItems] = await Promise.all([getProjects(), getCharacterTags()]);
      const nextProjectId = projectId ?? projectItems[0]?.id ?? null;
      const items = await getCharacterCards(scope, scope === 'project' ? nextProjectId : null);
      setProjects(projectItems);
      setProjectId(nextProjectId);
      setTags(tagItems);
      setCards(items);
      const nextId = preferredId === undefined ? selectedId : preferredId;
      setSelectedId(items.some((card) => card.id === nextId) ? nextId : items[0]?.id ?? null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [scope, projectId]);

  function selectScope(nextScope: Scope) {
    setScope(nextScope);
    setFilter('all');
    setTagId(null);
    setSelectedId(null);
  }

  function createBlank() {
    setEditing(emptyCharacter(scope, projectId));
  }

  async function addTag() {
    const name = window.prompt('新建角色标签');
    if (!name?.trim()) return;
    await runBusy(async () => {
      const tag = await createCharacterTag(name.trim());
      await load(selectedId);
      setTagId(tag.id);
      setMessage(`已创建标签“${tag.name}”。`);
    });
  }

  async function removeTag(id: number) {
    if (!window.confirm('删除标签只会解除关联，不会删除角色卡。确认继续？')) return;
    await runBusy(async () => {
      await deleteCharacterTag(id);
      if (tagId === id) setTagId(null);
      await load(selectedId);
      setMessage('标签已删除。');
    });
  }

  async function copyCard(card: CharacterCard) {
    await runBusy(async () => {
      if (card.scope === 'public') {
        if (!projectId) throw new Error('请先选择目标工程。');
        const copied = await copyCharacterCard(card.id, 'project', projectId);
        setScope('project');
        setSelectedId(copied.id);
        setMessage('已复制为独立的工程角色副本。');
      } else {
        const copied = await copyCharacterCard(card.id, 'public', null);
        setScope('public');
        setSelectedId(copied.id);
        setMessage('已复制为独立的公共角色副本。');
      }
    });
  }

  async function runAnalyze(card: CharacterCard) {
    const raw = window.prompt('粘贴 AI 分析得到的结构化 JSON。保存前会校验对象格式。', JSON.stringify({
      identity: card.identity,
      age: card.age,
      setting_text: card.setting_text,
      custom_fields: card.custom_fields,
    }, null, 2));
    if (!raw) return;
    await runBusy(async () => {
      const parsed = JSON.parse(raw) as {
        identity?: string;
        age?: string;
        setting_text?: string;
        custom_fields?: CharacterCustomField[];
      };
      const updated = await analyzeCharacterCard(card.id, {
        identity: parsed.identity ?? '',
        age: parsed.age ?? '',
        setting_text: parsed.setting_text ?? '',
        custom_fields: parsed.custom_fields ?? [],
      });
      await load(updated.id);
      setMessage('角色分析结果已保存。');
    });
  }

  async function deleteCard(card: CharacterCard) {
    if (!window.confirm(`确认删除角色卡“${card.name}”？该操作不会删除已复制的独立副本。`)) return;
    await runBusy(async () => {
      await deleteCharacterCard(card.id);
      await load(null);
      setMessage('角色卡已删除。');
    });
  }

  async function save(card: CharacterCard, draft: CharacterDraft) {
    if (!draft.name.trim()) {
      setError('角色名称不能为空。');
      return;
    }
    await runBusy(async () => {
      const payload = {
        name: draft.name.trim(),
        aliases: splitValues(draft.aliases),
        description: draft.description,
        priority: draft.priority,
        is_main: draft.is_main,
        relationship_notes: draft.relationship_notes,
        personality: draft.personality,
        speech_style: draft.speech_style,
        action_constraints: draft.action_constraints,
        anti_ooc_rules: draft.anti_ooc_rules,
        profile: draft.profile,
        source_metadata: card.source_metadata,
        import_metadata: card.import_metadata,
        scope: card.scope,
        project_id: card.scope === 'project' ? (card.project_id ?? projectId) : null,
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
      setMessage(card.id ? '角色卡已保存。' : '角色卡已创建。');
    });
  }

  async function runBusy(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const counts = {
    all: cards.length,
    unanalyzed: cards.filter((card) => card.analysis_status === 'unanalyzed').length,
    untagged: cards.filter((card) => card.tags.length === 0).length,
  };

  return (
    <div className="document-library-page character-library-page">
      <TopBar
        title="角色卡"
        actions={(
          <>
            <SecondaryButton disabled={busy || !selected} onClick={() => selected && void runAnalyze(selected)}>
              <Sparkles size={16} />AI 分析
            </SecondaryButton>
            <PrimaryButton disabled={busy} onClick={createBlank}>
              <Plus size={16} />新建角色
            </PrimaryButton>
          </>
        )}
      />
      {error ? <div className="inline-alert error document-library-alert" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success document-library-alert" role="status">{message}</div> : null}

      <div className="document-library-layout character-browser-layout">
        <aside className="document-tag-panel">
          <header><h2>角色卡</h2></header>
          <nav aria-label="角色筛选">
            <LibrarySidebarItem active={scope === 'public'} count={scope === 'public' ? cards.length : 0} icon={<LibraryBig size={16} />} label="公共角色" onClick={() => selectScope('public')} />
            <LibrarySidebarItem active={scope === 'project'} count={scope === 'project' ? cards.length : 0} icon={<BriefcaseBusiness size={16} />} label="工程角色" onClick={() => selectScope('project')} />
            <div className="library-project-selector">
              <label htmlFor="character-project">当前工程</label>
              <select id="character-project" value={projectId ?? ''} onChange={(event) => setProjectId(Number(event.target.value) || null)}>
                {projects.length ? projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>) : <option value="">暂无工程</option>}
              </select>
            </div>
            <div className="document-tag-heading"><span>系统筛选</span></div>
            <LibrarySidebarItem active={filter === 'all' && tagId === null} count={counts.all} icon={<UsersRound size={16} />} label="全部角色" onClick={() => { setFilter('all'); setTagId(null); }} />
            <LibrarySidebarItem active={filter === 'unanalyzed' && tagId === null} count={counts.unanalyzed} icon={<Sparkles size={16} />} label="未分析" onClick={() => { setFilter('unanalyzed'); setTagId(null); }} />
            <LibrarySidebarItem active={filter === 'untagged' && tagId === null} count={counts.untagged} icon={<Tags size={16} />} label="无标签" onClick={() => { setFilter('untagged'); setTagId(null); }} />
            <div className="document-tag-heading">
              <span>我的标签</span>
              <button aria-label="新建角色标签" className="document-add-tag" disabled={busy} onClick={() => void addTag()} type="button"><FolderPlus size={15} /></button>
            </div>
            {tags.length ? tags.map((item) => (
              <div className="library-tag-row" key={item.id}>
                <LibrarySidebarItem active={tagId === item.id} count={item.resource_count} icon={<Tag size={16} />} label={item.name} onClick={() => { setTagId(item.id); setFilter('all'); }} />
                <button aria-label={`删除标签 ${item.name}`} disabled={busy} onClick={() => void removeTag(item.id)} type="button"><Trash2 size={13} /></button>
              </div>
            )) : <p className="document-tag-empty">暂无自定义标签</p>}
          </nav>
        </aside>

        <main className="document-shelf-panel character-browser-shelf">
          <header>
            <div className="document-shelf-tools">
              <label className="search-field document-search">
                <Search size={15} />
                <span className="sr-only">搜索角色</span>
                <input onChange={(event) => setQuery(event.target.value)} placeholder="搜索角色名、身份、设定或标签" type="search" value={query} />
              </label>
            </div>
          </header>
          {loading ? <LibraryEmptyState title="正在读取角色卡…" /> : filtered.length ? (
            <div className="document-shelf-scroll">
              <div className="document-character-grid">
                {filtered.map((card) => (
                  <button
                    aria-pressed={selectedId === card.id}
                    className={`library-character-card ${selectedId === card.id ? 'selected' : ''}`}
                    key={card.id}
                    onClick={() => setSelectedId(card.id)}
                    onDoubleClick={() => setEditing(card)}
                    type="button"
                  >
                    <div className="library-character-cover" style={{ '--character-cover': coverColor(card.name) } as CSSProperties}>
                      <UserRound size={28} />
                    </div>
                    <div className="library-character-card-body">
                      <strong>{card.name}</strong>
                      <span>{card.identity || '身份未填写'}</span>
                      <p>{card.description || card.setting_text || '尚未填写人物简介。'}</p>
                      <div className="document-detail-badges">
                        <span>{card.analysis_status === 'unanalyzed' ? '未分析' : '已分析'}</span>
                        {card.tags.slice(0, 2).map((name) => <span key={name}>{name}</span>)}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : cards.length === 0 ? (
            <LibraryEmptyState
              action={<PrimaryButton onClick={createBlank}><Plus size={16} />新建第一个角色</PrimaryButton>}
              description={scope === 'project' ? '当前工程还没有角色副本。' : '公共角色可以复制到任意工程。'}
              title="角色卡库还是空的"
            />
          ) : <LibraryEmptyState description="尝试调整左侧筛选或清空搜索词。" title="没有匹配的角色" />}
        </main>

        <aside className="document-detail-panel character-detail-panel">
          <header><h2>角色详情</h2></header>
          {selected ? (
            <>
              <div className="document-detail-scroll">
                <section className="character-detail-identity">
                  <div className="character-detail-avatar"><UserRound size={30} /></div>
                  <div>
                    <h3>{selected.name}</h3>
                    <p>{selected.aliases.length ? selected.aliases.join(' / ') : '暂无别名'}</p>
                    <div className="document-detail-badges">
                      <span>{selected.scope === 'public' ? '公共角色' : '工程角色'}</span>
                      <span>v{selected.version}</span>
                      <span>{selected.analysis_status === 'unanalyzed' ? '未分析' : '已分析'}</span>
                    </div>
                  </div>
                </section>
                <section className="document-detail-metadata">
                  <LibraryDefinition label="身份" value={selected.identity || '未填写'} />
                  <LibraryDefinition label="年龄" value={selected.age || '未填写'} />
                  <LibraryDefinition label="来源" value={selected.source_character_card_id ? `角色 #${selected.source_character_card_id}` : '本地创建'} />
                  <LibraryDefinition label="来源版本" value={selected.source_version ? `v${selected.source_version}` : '—'} />
                  <LibraryDefinition label="所属范围" value={selected.scope === 'public' ? '公共角色' : '工程角色'} />
                  <LibraryDefinition label="分析状态" value={selected.analysis_status === 'analyzed' ? '已分析' : '未分析'} />
                  <LibraryDefinition label="更新时间" value={formatDateTime(selected.updated_at)} />
                </section>
                <DetailSection label="人物简介" value={selected.description || selected.setting_text} />
                <DetailSection label="角色标签" value={selected.tags.join(' / ')} />
                <DetailSection label="长期性格" value={selected.personality} />
                <DetailSection label="核心动机" value={profileText(selected.profile, 'core_motivation')} />
                <DetailSection label="外貌" value={profileText(selected.profile, 'appearance')} />
                <DetailSection label="说话方式" value={selected.speech_style} />
                <DetailSection label="能力" value={profileText(selected.profile, 'abilities')} />
                <DetailSection label="限制" value={selected.action_constraints} />
                <DetailSection label="背景" value={profileText(selected.profile, 'background')} />
                <DetailSection label="不可改变的设定" value={selected.anti_ooc_rules} />
                {selected.custom_fields.length ? (
                  <section>
                    <div className="document-detail-heading"><span>其他稳定信息</span></div>
                    <div className="character-custom-details">
                      {selected.custom_fields.map((field) => <LibraryDefinition key={field.id} label={field.label} value={field.value || '—'} />)}
                    </div>
                  </section>
                ) : null}
              </div>
              <footer className="library-detail-footer character-detail-footer">
                <SecondaryButton disabled={busy} onClick={() => setEditing(selected)}><Pencil size={15} />编辑</SecondaryButton>
                <SecondaryButton disabled={busy} onClick={() => void copyCard(selected)}><Copy size={15} />{selected.scope === 'public' ? '复制到工程' : '复制到公共库'}</SecondaryButton>
                <SecondaryButton disabled={busy} onClick={() => void runAnalyze(selected)}><Sparkles size={15} />AI 分析</SecondaryButton>
                <DangerButton disabled={busy} onClick={() => void deleteCard(selected)}><Trash2 size={15} />删除</DangerButton>
              </footer>
            </>
          ) : <LibraryEmptyState description="单击中央区域中的角色卡后，稳定设定和来源信息会显示在这里。" title="选择一个角色查看详情" />}
        </aside>
      </div>
      {editing ? <CharacterEditor busy={busy} card={editing} onClose={() => setEditing(null)} onSave={save} /> : null}
    </div>
  );
}

type CharacterDraft = {
  name: string;
  aliases: string;
  description: string;
  identity: string;
  age: string;
  setting_text: string;
  personality: string;
  speech_style: string;
  action_constraints: string;
  anti_ooc_rules: string;
  relationship_notes: string;
  priority: number;
  is_main: boolean;
  profile: Record<string, unknown>;
  custom_fields: CharacterCustomField[];
  raw_text: string;
  analysis_status: AnalysisStatus;
};

function CharacterEditor({ busy, card, onClose, onSave }: {
  busy: boolean;
  card: CharacterCard;
  onClose: () => void;
  onSave: (card: CharacterCard, draft: CharacterDraft) => void;
}) {
  const [draft, setDraft] = useState<CharacterDraft>({
    name: card.name,
    aliases: card.aliases.join('、'),
    description: card.description,
    identity: card.identity,
    age: card.age,
    setting_text: card.setting_text,
    personality: card.personality,
    speech_style: card.speech_style,
    action_constraints: card.action_constraints,
    anti_ooc_rules: card.anti_ooc_rules,
    relationship_notes: card.relationship_notes,
    priority: card.priority,
    is_main: card.is_main,
    profile: card.profile,
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
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !draft.name.trim()} onClick={() => onSave(card, draft)}>{busy ? '保存中…' : '保存'}</PrimaryButton></>}
      onClose={onClose}
      subtitle={card.id ? `角色 #${card.id} · v${card.version}` : '新角色'}
      title={card.id ? '编辑角色卡' : '新建角色卡'}
    >
      <div className="library-form-grid">
        <Field label="角色名称"><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
        <Field label="别名"><input placeholder="使用顿号或逗号分隔" value={draft.aliases} onChange={(event) => setDraft({ ...draft, aliases: event.target.value })} /></Field>
        <Field label="身份"><input value={draft.identity} onChange={(event) => setDraft({ ...draft, identity: event.target.value })} /></Field>
        <Field label="年龄"><input value={draft.age} onChange={(event) => setDraft({ ...draft, age: event.target.value })} /></Field>
        <Field className="wide" label="人物简介"><textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></Field>
        <Field className="wide" label="长期设定"><textarea value={draft.setting_text} onChange={(event) => setDraft({ ...draft, setting_text: event.target.value })} /></Field>
        <Field label="长期性格"><textarea value={draft.personality} onChange={(event) => setDraft({ ...draft, personality: event.target.value })} /></Field>
        <Field label="说话方式"><textarea value={draft.speech_style} onChange={(event) => setDraft({ ...draft, speech_style: event.target.value })} /></Field>
        <Field label="能力与限制"><textarea value={draft.action_constraints} onChange={(event) => setDraft({ ...draft, action_constraints: event.target.value })} /></Field>
        <Field label="不可改变的设定"><textarea value={draft.anti_ooc_rules} onChange={(event) => setDraft({ ...draft, anti_ooc_rules: event.target.value })} /></Field>
      </div>
      <section className="library-form-section">
        <div className="document-detail-heading"><span>自定义稳定信息</span></div>
        <div className="custom-field-list">
          {draft.custom_fields.map((field, index) => (
            <div className="custom-field-row" key={field.id}>
              <input placeholder="字段名" value={field.label} onChange={(event) => updateField(index, { label: event.target.value })} />
              <input placeholder="内容" value={field.value} onChange={(event) => updateField(index, { value: event.target.value })} />
              <button aria-label="删除字段" onClick={() => setDraft({ ...draft, custom_fields: draft.custom_fields.filter((_, itemIndex) => itemIndex !== index) })} type="button"><Trash2 size={14} /></button>
            </div>
          ))}
          <SecondaryButton onClick={() => setDraft({ ...draft, custom_fields: [...draft.custom_fields, { id: crypto.randomUUID(), label: '', value: '', sort_order: draft.custom_fields.length }] })}><Plus size={14} />新增字段</SecondaryButton>
        </div>
      </section>
      <details className="library-advanced-editor">
        <summary>高级来源文本</summary>
        <textarea value={draft.raw_text} onChange={(event) => setDraft({ ...draft, raw_text: event.target.value })} />
      </details>
    </LibraryDialog>
  );
}

function Field({ children, className = '', label }: { children: ReactNode; className?: string; label: string }) {
  return <label className={className}><span>{label}</span>{children}</label>;
}

function DetailSection({ label, value }: { label: string; value: string }) {
  return (
    <section>
      <div className="document-detail-heading"><span>{label}</span></div>
      <p className="character-detail-copy">{value || '未填写'}</p>
    </section>
  );
}

function emptyCharacter(scope: Scope, projectId: number | null): CharacterCard {
  return {
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
    created_at: '',
    updated_at: '',
  };
}

function formatDateTime(value: string): string {
  if (!value) return '—';
  const date = new Date(value.replace(' ', 'T') + (value.endsWith('Z') ? '' : 'Z'));
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function normalizeFields(fields: CharacterCustomField[]) {
  const seen = new Set<string>();
  return fields.filter((field) => {
    const key = field.label.trim().toLocaleLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map((field, index) => ({ ...field, label: field.label.trim(), sort_order: index }));
}

function splitValues(value: string) {
  return value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean);
}

function coverColor(name: string) {
  let hash = 0;
  for (const char of name || '角色') hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const palette = ['#dce3f1', '#eadbd1', '#d9e8df', '#dee1e5', '#ece2c8', '#e7dce8'];
  return palette[hash % palette.length];
}

function profileText(profile: Record<string, unknown>, key: string) {
  const value = profile[key];
  if (Array.isArray(value)) return value.map(String).join(' / ');
  if (value && typeof value === 'object') return Object.values(value).map(String).join(' / ');
  return String(value ?? '');
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}
