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
  confirmCharacterAnalysis,
  copyCharacterCard,
  createCharacterCard,
  createCharacterTag,
  deleteCharacterCard,
  deleteCharacterTag,
  renameCharacterTag,
  getCharacterCards,
  getCharacterTags,
  getProjects,
  updateCharacterCard,
  saveCharacterCover,
  removeCharacterCover,
  characterCoverUrl,
} from '../api/client';
import type { AnalysisStatus, CharacterAnalysisProposal, CharacterCard, CharacterCustomField, Project, ResourceTag } from '../api/types';
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
  const [analysisProposal, setAnalysisProposal] = useState<{ card: CharacterCard; result: CharacterAnalysisProposal } | null>(null);
  const [tagDialog, setTagDialog] = useState<{ mode: 'create' | 'rename'; tag?: ResourceTag } | null>(null);

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

  async function saveTag(name: string) {
    await runBusy(async () => {
      const tag = tagDialog?.mode === 'rename' && tagDialog.tag
        ? await renameCharacterTag(tagDialog.tag.id, name.trim())
        : await createCharacterTag(name.trim());
      await load(selectedId);
      setTagId(tag.id);
      setTagDialog(null);
      setMessage(tagDialog?.mode === 'rename' ? `标签已重命名为“${tag.name}”。` : `已创建标签“${tag.name}”。`);
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
    await runBusy(async () => {
      const result = await analyzeCharacterCard(card.id);
      setAnalysisProposal({ card, result });
      setMessage('模型分析完成，请确认字段差异后保存。');
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
        aliases: card.aliases,
        description: card.description,
        priority: card.priority,
        is_main: card.is_main,
        relationship_notes: card.relationship_notes,
        personality: card.personality,
        speech_style: card.speech_style,
        action_constraints: card.action_constraints,
        anti_ooc_rules: card.anti_ooc_rules,
        profile: card.profile,
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
        tag_ids: draft.tag_ids,
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
              <button aria-label="新建角色标签" className="document-add-tag" disabled={busy} onClick={() => setTagDialog({ mode: 'create' })} type="button"><FolderPlus size={15} /></button>
            </div>
            {tags.length ? tags.map((item) => (
              <div className="library-tag-row" key={item.id}>
                <LibrarySidebarItem active={tagId === item.id} count={item.resource_count} icon={<Tag size={16} />} label={item.name} onClick={() => { setTagId(item.id); setFilter('all'); }} />
                <button aria-label={`重命名标签 ${item.name}`} disabled={busy} onClick={() => setTagDialog({ mode: 'rename', tag: item })} type="button"><Pencil size={13} /></button>
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
                      {card.cover_path ? <img alt="" src={`${characterCoverUrl(card.id)}?v=${encodeURIComponent(card.cover_updated_at ?? '')}`} /> : <span>{card.name.trim().slice(0, 1) || <UserRound size={28} />}</span>}
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
                  <div className="character-detail-avatar">{selected.cover_path ? <img alt={`${selected.name} 封面`} src={`${characterCoverUrl(selected.id)}?v=${encodeURIComponent(selected.cover_updated_at ?? '')}`} /> : <span>{selected.name.slice(0, 1) || <UserRound size={30} />}</span>}</div>
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
                <DetailSection label="设定" value={selected.setting_text} />
                <DetailSection label="角色标签" value={selected.tags.join(' / ')} />
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
      {editing ? <CharacterEditor busy={busy} card={editing} tags={tags} onClose={() => setEditing(null)} onSave={save} onCoverChanged={async (id) => { await load(id); setEditing(null); }} /> : null}
      {analysisProposal ? <CharacterAnalysisDialog busy={busy} proposal={analysisProposal} onClose={() => setAnalysisProposal(null)} onConfirm={async () => {
        await runBusy(async () => {
          const updated = await confirmCharacterAnalysis(analysisProposal.card.id, {
            ...analysisProposal.result.merged,
            invocation_id: analysisProposal.result.invocation_id,
          });
          setAnalysisProposal(null);
          await load(updated.id);
          setMessage('已按确认结果保存角色分析。');
        });
      }} /> : null}
      {tagDialog ? <TagNameDialog busy={busy} initialName={tagDialog.tag?.name ?? ''} onClose={() => setTagDialog(null)} onSave={saveTag} title={tagDialog.mode === 'rename' ? '重命名角色标签' : '新建角色标签'} /> : null}
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
  tag_ids: number[];
};

function CharacterEditor({ busy, card, onClose, onSave, onCoverChanged, tags }: {
  busy: boolean;
  card: CharacterCard;
  onClose: () => void;
  onSave: (card: CharacterCard, draft: CharacterDraft) => void;
  onCoverChanged: (id: number) => void;
  tags: ResourceTag[];
}) {
  const [showMissing, setShowMissing] = useState(false);
  const [fieldError, setFieldError] = useState('');
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<CharacterDraft>({
    name: card.name,
    identity: card.identity,
    age: card.age,
    setting_text: card.setting_text,
    custom_fields: card.custom_fields,
    raw_text: card.raw_text,
    analysis_status: card.analysis_status,
    tag_ids: tags.filter((tag) => card.tags.includes(tag.name)).map((tag) => tag.id),
  });
  function updateField(index: number, patch: Partial<CharacterCustomField>) {
    setDraft((current) => ({
      ...current,
      custom_fields: current.custom_fields.map((field, itemIndex) => itemIndex === index ? { ...field, ...patch } : field),
    }));
  }
  function moveField(from: number, to: number) {
    if (to < 0 || to >= draft.custom_fields.length || from === to) return;
    const next = [...draft.custom_fields];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    setDraft({ ...draft, custom_fields: next.map((field, index) => ({ ...field, sort_order: index })) });
  }
  function requestSave() {
    const labels = draft.custom_fields.map((field) => field.label.trim().toLocaleLowerCase());
    if (labels.some((label) => !label)) {
      setFieldError('自定义属性名不能为空。');
      return;
    }
    if (new Set(labels).size !== labels.length) {
      setFieldError('同一角色中不能存在重复的自定义属性名。');
      return;
    }
    setFieldError('');
    if (!draft.identity.trim() || !draft.age.trim() || !draft.setting_text.trim()) {
      setShowMissing(true);
      return;
    }
    onSave(card, draft);
  }
  async function uploadCover(file: File | undefined) {
    if (!file || !card.id) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      setFieldError('封面只支持 PNG、JPEG 或 WebP。');
      return;
    }
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    bytes.forEach((value) => { binary += String.fromCharCode(value); });
    await saveCharacterCover(card.id, btoa(binary));
    onCoverChanged(card.id);
  }
  return (
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !draft.name.trim()} onClick={requestSave}>{busy ? '保存中…' : '保存'}</PrimaryButton></>}
      onClose={onClose}
      subtitle={card.id ? `角色 #${card.id} · v${card.version}` : '新角色'}
      title={card.id ? '编辑角色卡' : '新建角色卡'}
    >
      <div className="library-form-grid">
        <Field label="角色名称"><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
        <Field label="身份"><input value={draft.identity} onChange={(event) => setDraft({ ...draft, identity: event.target.value })} /></Field>
        <Field label="年龄"><input value={draft.age} onChange={(event) => setDraft({ ...draft, age: event.target.value })} /></Field>
        <Field className="wide" label="设定"><textarea value={draft.setting_text} onChange={(event) => setDraft({ ...draft, setting_text: event.target.value })} /></Field>
        <div className="wide character-cover-editor">
          <span>自定义封面</span>
          {card.id ? <><input accept="image/png,image/jpeg,image/webp" type="file" onChange={(event) => void uploadCover(event.target.files?.[0])} /><SecondaryButton disabled={busy || !card.cover_path} onClick={async () => { await removeCharacterCover(card.id); onCoverChanged(card.id); }}>移除封面</SecondaryButton></> : <small>先保存角色卡后即可上传封面。</small>}
        </div>
        <fieldset className="wide library-tag-picker">
          <legend>标签</legend>
          {tags.map((tag) => <label key={tag.id}><input checked={draft.tag_ids.includes(tag.id)} type="checkbox" onChange={(event) => setDraft({ ...draft, tag_ids: event.target.checked ? [...draft.tag_ids, tag.id] : draft.tag_ids.filter((id) => id !== tag.id) })} />{tag.name}</label>)}
        </fieldset>
      </div>
      <section className="library-form-section">
        <div className="document-detail-heading"><span>自定义稳定信息</span></div>
        <div className="custom-field-list">
          {draft.custom_fields.map((field, index) => (
            <div className="custom-field-row" draggable key={field.id} onDragStart={() => setDragIndex(index)} onDragOver={(event) => event.preventDefault()} onDrop={() => { if (dragIndex !== null) moveField(dragIndex, index); setDragIndex(null); }}>
              <input placeholder="字段名" value={field.label} onChange={(event) => updateField(index, { label: event.target.value })} />
              <input placeholder="内容" value={field.value} onChange={(event) => updateField(index, { value: event.target.value })} />
              <button aria-label="上移字段" disabled={index === 0} onClick={() => moveField(index, index - 1)} type="button">↑</button>
              <button aria-label="下移字段" disabled={index === draft.custom_fields.length - 1} onClick={() => moveField(index, index + 1)} type="button">↓</button>
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
      {fieldError ? <div className="inline-alert error" role="alert">{fieldError}</div> : null}
      {showMissing ? (
        <div className="library-confirm-panel" role="dialog" aria-label="空字段保存提醒">
          <p>以下信息尚未填写：</p>
          <ul>{!draft.identity.trim() ? <li>身份</li> : null}{!draft.age.trim() ? <li>年龄</li> : null}{!draft.setting_text.trim() ? <li>设定</li> : null}</ul>
          <div><SecondaryButton onClick={() => setShowMissing(false)}>返回补充</SecondaryButton><PrimaryButton onClick={() => onSave(card, draft)}>仍然保存</PrimaryButton></div>
        </div>
      ) : null}
    </LibraryDialog>
  );
}

function Field({ children, className = '', label }: { children: ReactNode; className?: string; label: string }) {
  return <label className={className}><span>{label}</span>{children}</label>;
}

function TagNameDialog({ busy, initialName, onClose, onSave, title }: {
  busy: boolean;
  initialName: string;
  onClose: () => void;
  onSave: (name: string) => void;
  title: string;
}) {
  const [name, setName] = useState(initialName);
  return (
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !name.trim()} onClick={() => onSave(name)}>保存</PrimaryButton></>}
      onClose={onClose}
      title={title}
    >
      <Field label="标签名称"><input autoFocus value={name} onChange={(event) => setName(event.target.value)} /></Field>
    </LibraryDialog>
  );
}

function CharacterAnalysisDialog({ busy, onClose, onConfirm, proposal }: {
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
  proposal: { card: CharacterCard; result: CharacterAnalysisProposal };
}) {
  const { result } = proposal;
  return (
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy} onClick={onConfirm}>{busy ? '保存中…' : '确认并保存'}</PrimaryButton></>}
      onClose={onClose}
      subtitle="已有非空字段不会被模型自动覆盖。"
      title="确认角色分析"
    >
      {result.conflicts.length ? (
        <div className="analysis-conflict-list">
          {result.conflicts.map((conflict) => <div key={conflict.field}><strong>{conflict.field}</strong><p>已有：{conflict.existing}</p><p>模型建议：{conflict.proposed}</p></div>)}
        </div>
      ) : <p>未发现与已有非空字段冲突的建议。</p>}
      <div className="library-form-grid">
        <LibraryDefinition label="身份" value={result.merged.identity || '未填写'} />
        <LibraryDefinition label="年龄" value={result.merged.age || '未填写'} />
        <LibraryDefinition label="设定" value={result.merged.setting_text || '未填写'} />
      </div>
    </LibraryDialog>
  );
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
