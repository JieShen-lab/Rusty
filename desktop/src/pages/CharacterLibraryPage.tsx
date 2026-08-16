import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Folder, Plus, Search, Settings, Trash2, UserRound, X } from 'lucide-react';
import {
  assignCharacterCategory,
  assignCharacterTag,
  createCharacterCard,
  createCharacterCategory,
  createCharacterTag,
  deleteCharacterCard,
  deleteCharacterCategory,
  getCharacterCards,
  getCharacterCategories,
  getCharacterTags,
  renameCharacterCategory,
  updateCharacterCard,
} from '../api/client';
import type { CharacterCard, CharacterCategory, CharacterDraft as AICharacterDraft, CharacterStableField, ResourceTag } from '../api/types';
import { CharacterAIExtractionDialog, CharacterExtractionSettingsDialog, type CharacterExtractionLaunch } from '../components/CharacterCreationDialogs';
import { DangerButton } from '../components/DangerButton';
import {
  LibraryContextMenu,
  LibraryDetailSection,
  LibraryDialog,
  LibraryDivider,
  LibraryEmptyState,
  LibraryResourceCard,
  LibraryResourceGrid,
  LibrarySidebarItem,
  LibrarySidebarSectionTitle,
  LibraryTagChip,
} from '../components/LibraryPrimitives';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';

const DEFAULT_STABLE_FIELDS: CharacterStableField[] = [
  ['appearance', '外貌'], ['relationships', '人物关系'], ['personality', '性格'],
  ['speech_style', '语言风格'], ['action_constraints', '动作习惯 / 动作约束'],
  ['abilities_background', '能力与背景'], ['anti_ooc_rules', '反 OOC 规则'],
].map(([id, label], sort_order) => ({ id, label, value: '', sort_order }));

type EditorDraft = {
  name: string;
  identity: string;
  age: string;
  aliases: string;
  description: string;
  stable_fields: CharacterStableField[];
  selectedTags: string[];
  source_metadata: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
  raw_text: string;
};

export function CharacterLibraryPage() {
  const [cards, setCards] = useState<CharacterCard[]>([]);
  const [categories, setCategories] = useState<CharacterCategory[]>([]);
  const [tags, setTags] = useState<ResourceTag[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [activeCategoryId, setActiveCategoryId] = useState<number | null>(null);
  const [activeTagId, setActiveTagId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [editor, setEditor] = useState<{ card: CharacterCard | null; draft: EditorDraft } | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [extractionLaunch, setExtractionLaunch] = useState<CharacterExtractionLaunch | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [manager, setManager] = useState<'category' | 'tag' | null>(null);
  const [categoryNameDialog, setCategoryNameDialog] = useState<{ category?: CharacterCategory } | null>(null);
  const [categoryMenu, setCategoryMenu] = useState<{ category: CharacterCategory; x: number; y: number } | null>(null);

  const selected = cards.find((card) => card.id === selectedId) ?? null;
  const activeTag = tags.find((tag) => tag.id === activeTagId) ?? null;
  const visibleCards = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return cards.filter((card) => (
      (activeCategoryId === null || card.category_ids.includes(activeCategoryId))
      && (activeTag === null || card.tags.includes(activeTag.name))
      && (!needle || [card.name, card.identity, card.description, ...card.aliases].join(' ').toLocaleLowerCase().includes(needle))
    ));
  }, [activeCategoryId, activeTag, cards, query]);

  async function refresh(preferredId?: number | null) {
    const [cardItems, categoryItems, tagItems] = await Promise.all([getCharacterCards(), getCharacterCategories(), getCharacterTags()]);
    setCards(cardItems);
    setCategories(categoryItems);
    setTags(tagItems);
    const nextId = preferredId ?? selectedId;
    setSelectedId(nextId && cardItems.some((item) => item.id === nextId) ? nextId : cardItems[0]?.id ?? null);
  }

  useEffect(() => { void refresh().catch((reason) => setError(errorMessage(reason))); }, []);
  useEffect(() => {
    const launch = window.history.state?.characterExtraction as CharacterExtractionLaunch | undefined;
    if (!launch?.selectedText) return;
    setExtractionLaunch(launch);
    setAiOpen(true);
    window.history.replaceState({}, document.title);
  }, []);

  function openManual() {
    setEditor({ card: null, draft: emptyDraft() });
  }

  function openCard(card: CharacterCard) {
    setEditor({ card, draft: draftFromCard(card) });
  }

  function openAIDraft(draft: AICharacterDraft) {
    setAiOpen(false);
    setEditor({
      card: null,
      draft: {
        name: draft.name,
        identity: draft.identity,
        age: draft.age,
        aliases: draft.aliases.join('、'),
        description: draft.description,
        stable_fields: draft.stable_fields,
        selectedTags: draft.suggested_tags,
        source_metadata: draft.source_metadata,
        import_metadata: draft.import_metadata,
        raw_text: draft.raw_text,
      },
    });
  }

  async function saveEditor(card: CharacterCard | null, draft: EditorDraft) {
    setBusy(true);
    setError('');
    try {
      const tagIds: number[] = [];
      const currentTags = [...tags];
      for (const tagName of uniqueNames(draft.selectedTags)) {
        let tag = currentTags.find((item) => item.name.toLocaleLowerCase() === tagName.toLocaleLowerCase());
        if (!tag) { tag = await createCharacterTag(tagName); currentTags.push(tag); }
        tagIds.push(tag.id);
      }
      const stableFields = draft.stable_fields.map((field, sort_order) => ({ ...field, label: field.label.trim(), sort_order }));
      const byId = Object.fromEntries(stableFields.map((field) => [field.id, field.value]));
      const payload = {
        name: draft.name.trim(), aliases: splitValues(draft.aliases), description: draft.description,
        priority: card?.priority ?? 50, is_main: card?.is_main ?? false,
        relationship_notes: byId.relationships ?? '', personality: byId.personality ?? '',
        speech_style: byId.speech_style ?? '', action_constraints: byId.action_constraints ?? '',
        anti_ooc_rules: byId.anti_ooc_rules ?? '', setting_text: byId.abilities_background ?? '',
        profile: card?.profile ?? {}, source_metadata: draft.source_metadata,
        import_metadata: draft.import_metadata, scope: 'public' as const, project_id: null,
        identity: draft.identity, age: draft.age, stable_fields: stableFields,
        custom_fields: stableFields.filter((field) => !DEFAULT_STABLE_FIELDS.some((item) => item.id === field.id)),
        raw_text: draft.raw_text, analysis_status: 'analyzed' as const, tag_ids: tagIds,
      };
      const saved = card ? await updateCharacterCard(card.id, payload) : await createCharacterCard(payload);
      setTags(currentTags);
      setEditor(null);
      await refresh(saved.id);
      setMessage('角色卡已保存。');
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  async function removeCard() {
    if (!selected || !window.confirm(`确认删除角色“${selected.name}”？工程引用会一并解除，其他角色卡不受影响。`)) return;
    await runBusy(async () => { await deleteCharacterCard(selected.id); await refresh(null); setMessage('角色卡已删除。'); });
  }

  async function runBusy(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  return <div className="document-library-page character-library-page">
    <TopBar title="角色卡" actions={<><PrimaryButton disabled={busy} onClick={() => { setExtractionLaunch(null); setAiOpen(true); }}><Plus size={16} />AI 新建</PrimaryButton><PrimaryButton disabled={busy} onClick={openManual}><Plus size={16} />手动新建</PrimaryButton><SecondaryButton aria-label="角色 AI 提取设置" className="icon-only" disabled={busy} onClick={() => setSettingsOpen(true)}><Settings size={16} /></SecondaryButton></>} />
    {error ? <div className="inline-alert error document-library-alert" role="alert">{error}</div> : null}
    {message ? <div className="inline-alert success document-library-alert" role="status">{message}</div> : null}
    <div className="document-library-layout character-browser-layout">
      <aside className="document-tag-panel character-range-panel"><nav aria-label="角色分类">
        <LibrarySidebarItem active={activeCategoryId === null} count={cards.length} icon={<UserRound size={16} />} label="全部角色" onClick={() => setActiveCategoryId(null)} />
        <LibraryDivider />
        <LibrarySidebarSectionTitle action={<button aria-label="新建角色分类" className="document-add-tag" onClick={() => setCategoryNameDialog({})} type="button"><Plus size={15} /></button>}>我的分类</LibrarySidebarSectionTitle>
        {categories.map((category) => <LibrarySidebarItem active={activeCategoryId === category.id} count={category.resource_count} icon={<Folder size={15} />} key={category.id} label={category.name} onClick={() => setActiveCategoryId(category.id)} onContextMenu={(event) => { event.preventDefault(); setCategoryMenu({ category, x: event.clientX, y: event.clientY }); }} />)}
      </nav></aside>
      <main className="document-shelf-panel character-browser-shelf"><header><div className="document-shelf-tools character-search-tools"><label className="search-field document-search"><Search size={15} /><span className="sr-only">搜索角色</span><input onChange={(event) => setQuery(event.target.value)} placeholder="搜索角色名称、身份或简介" type="search" value={query} /></label>{activeTag ? <button className="character-active-tag" onClick={() => setActiveTagId(null)} type="button">标签：{activeTag.name}<X size={13} /></button> : null}</div></header>
        {visibleCards.length ? <div className="document-shelf-scroll"><LibraryResourceGrid className="document-character-grid">{visibleCards.map((card) => <LibraryResourceCard ariaLabel={card.name} key={card.id} onClick={() => setSelectedId(card.id)} onDoubleClick={() => openCard(card)} selected={selectedId === card.id}><CharacterBookCover card={card} /></LibraryResourceCard>)}</LibraryResourceGrid></div> : <LibraryEmptyState description="当前分类、标签和搜索文字没有共同匹配的角色。" title="没有匹配的角色" />}
      </main>
      <aside className="document-detail-panel character-detail-panel"><header><h2>角色详情</h2></header>{selected ? <><div className="document-detail-scroll"><section className="document-detail-identity"><div><strong className="character-detail-name">{selected.name}</strong><span>{[selected.identity, selected.age].filter(Boolean).join(' / ') || '未填写身份与年龄'}</span></div></section><LibraryDetailSection title="简介"><p className="character-detail-description">{selected.description || '暂无简介'}</p></LibraryDetailSection><LibraryDetailSection action={<button aria-label="管理角色标签" className="document-inline-plus" onClick={() => setManager('tag')} type="button"><Plus size={14} /></button>} title="角色标签"><div className="document-tag-checks">{selected.tags.length ? tags.filter((item) => selected.tags.includes(item.name)).map((tag) => <LibraryTagChip active={activeTagId === tag.id} key={tag.id} onClick={() => setActiveTagId(tag.id)}>{tag.name}</LibraryTagChip>) : <span className="document-resource-empty">未设置标签</span>}</div></LibraryDetailSection></div><footer className="library-detail-footer"><SecondaryButton onClick={() => openCard(selected)}>编辑</SecondaryButton><DangerButton onClick={() => void removeCard()}><Trash2 size={15} />删除</DangerButton></footer></> : <LibraryEmptyState description="选择中央区域中的角色卡查看摘要。" title="选择一个角色" />}</aside>
    </div>
    {editor ? <CharacterEditor busy={busy} card={editor.card} draft={editor.draft} onClose={() => setEditor(null)} onSave={(draft) => void saveEditor(editor.card, draft)} tags={tags} /> : null}
    {aiOpen ? <CharacterAIExtractionDialog initialLaunch={extractionLaunch} onClose={() => setAiOpen(false)} onDraft={openAIDraft} /> : null}
    {settingsOpen ? <CharacterExtractionSettingsDialog onClose={() => setSettingsOpen(false)} /> : null}
    {manager && selected ? <AssignmentDialog card={selected} entity={manager} items={manager === 'category' ? categories : tags} onClose={() => setManager(null)} onCreate={async (name) => { if (manager === 'category') await createCharacterCategory(name); else await createCharacterTag(name); await refresh(selected.id); }} onToggle={async (id, checked) => { if (manager === 'category') await assignCharacterCategory(selected.id, id, checked); else await assignCharacterTag(selected.id, id, checked); await refresh(selected.id); }} /> : null}
    {categoryNameDialog ? <NameDialog initial={categoryNameDialog.category?.name ?? ''} onClose={() => setCategoryNameDialog(null)} onSave={(name) => void runBusy(async () => { if (categoryNameDialog.category) await renameCharacterCategory(categoryNameDialog.category.id, name); else await createCharacterCategory(name); setCategoryNameDialog(null); await refresh(); })} title={categoryNameDialog.category ? '重命名分类' : '新建分类'} /> : null}
    {categoryMenu ? <LibraryContextMenu actions={[{ label: '重命名', onSelect: () => setCategoryNameDialog({ category: categoryMenu.category }) }, { danger: true, label: '删除分类', onSelect: () => void runBusy(async () => { await deleteCharacterCategory(categoryMenu.category.id); if (activeCategoryId === categoryMenu.category.id) setActiveCategoryId(null); await refresh(); }) }]} label={`${categoryMenu.category.name} 分类操作`} onClose={() => setCategoryMenu(null)} x={categoryMenu.x} y={categoryMenu.y} /> : null}
  </div>;
}

function CharacterBookCover({ card }: { card: CharacterCard }) {
  return <div className="character-book-cover"><div className="character-book-monogram">{card.name.slice(0, 1)}</div><strong>{card.name}</strong><span>{card.identity || card.description || '角色卡'}</span><div className="character-book-tags">{card.tags.slice(0, 2).map((tag) => <span key={tag}>{tag}</span>)}{card.tags.length > 2 ? <span>+{card.tags.length - 2}</span> : null}</div></div>;
}

function CharacterEditor({ busy, card, draft: initial, onClose, onSave, tags }: { busy: boolean; card: CharacterCard | null; draft: EditorDraft; onClose: () => void; onSave: (draft: EditorDraft) => void; tags: ResourceTag[] }) {
  const [draft, setDraft] = useState(initial);
  const [tagsOpen, setTagsOpen] = useState(false);
  function moveField(index: number, offset: number) { const target = index + offset; if (target < 0 || target >= draft.stable_fields.length) return; const fields = [...draft.stable_fields]; [fields[index], fields[target]] = [fields[target], fields[index]]; setDraft({ ...draft, stable_fields: fields }); }
  return <><LibraryDialog className="character-editor-dialog" closeOnBackdrop={false} footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !draft.name.trim()} onClick={() => onSave(draft)}>保存</PrimaryButton></>} onClose={onClose} title={card ? '编辑角色' : '新建角色'}><div className="character-editor-content"><section><h3>基本信息</h3><div className="character-basic-grid"><Field className="character-name-field" label="角色名称"><input autoFocus onChange={(event) => setDraft({ ...draft, name: event.target.value })} value={draft.name} /></Field><Field className="character-identity-field" label="身份"><input onChange={(event) => setDraft({ ...draft, identity: event.target.value })} value={draft.identity} /></Field><Field className="character-age-field" label="年龄"><input onChange={(event) => setDraft({ ...draft, age: event.target.value })} value={draft.age} /></Field><Field className="character-alias-field" label="别名"><input onChange={(event) => setDraft({ ...draft, aliases: event.target.value })} value={draft.aliases} /></Field><Field className="character-description-field" label="简介"><textarea onChange={(event) => setDraft({ ...draft, description: event.target.value })} rows={4} value={draft.description} /></Field></div></section><section><div className="character-section-heading"><h3>设定</h3><SecondaryButton onClick={() => setDraft({ ...draft, stable_fields: [...draft.stable_fields, { id: `custom_${crypto.randomUUID()}`, label: '新设定', value: '', sort_order: draft.stable_fields.length }] })}><Plus size={14} />添加字段</SecondaryButton></div><div className="character-stable-field-list">{draft.stable_fields.map((field, index) => <div className="character-stable-field" key={field.id}><input aria-label="设定名称" onChange={(event) => setDraft({ ...draft, stable_fields: draft.stable_fields.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item) })} value={field.label} /><textarea aria-label={`${field.label}内容`} onChange={(event) => setDraft({ ...draft, stable_fields: draft.stable_fields.map((item, itemIndex) => itemIndex === index ? { ...item, value: event.target.value } : item) })} rows={3} value={field.value} /><div><button aria-label="上移" disabled={index === 0} onClick={() => moveField(index, -1)} type="button">↑</button><button aria-label="下移" disabled={index === draft.stable_fields.length - 1} onClick={() => moveField(index, 1)} type="button">↓</button><button aria-label="删除设定" className="danger" onClick={() => setDraft({ ...draft, stable_fields: draft.stable_fields.filter((_, itemIndex) => itemIndex !== index) })} type="button">×</button></div></div>)}</div></section><section><div className="character-section-heading"><h3>角色标签</h3><button aria-label="管理编辑器标签" className="document-inline-plus" onClick={() => setTagsOpen(true)} type="button"><Plus size={14} /></button></div><div className="document-tag-checks">{draft.selectedTags.map((tag) => <LibraryTagChip key={tag}>{tag}</LibraryTagChip>)}</div></section></div></LibraryDialog>{tagsOpen ? <TagSelectionDialog available={tags} onClose={() => setTagsOpen(false)} onSave={(selectedTags) => { setDraft({ ...draft, selectedTags }); setTagsOpen(false); }} selected={draft.selectedTags} /> : null}</>;
}

function AssignmentDialog({ card, entity, items, onClose, onCreate, onToggle }: { card: CharacterCard; entity: 'category' | 'tag'; items: Array<CharacterCategory | ResourceTag>; onClose: () => void; onCreate: (name: string) => Promise<void>; onToggle: (id: number, checked: boolean) => Promise<void> }) { const [name, setName] = useState(''); const selected = entity === 'category' ? card.category_ids : items.filter((item) => card.tags.includes(item.name)).map((item) => item.id); return <LibraryDialog footer={<SecondaryButton onClick={onClose}>完成</SecondaryButton>} onClose={onClose} title={entity === 'category' ? '管理所属分类' : '管理角色标签'}><div className="library-assignment-list">{items.map((item) => <label key={item.id}><input checked={selected.includes(item.id)} onChange={(event) => void onToggle(item.id, event.target.checked)} type="checkbox" /><span>{item.name}</span></label>)}</div><div className="character-inline-create"><input onChange={(event) => setName(event.target.value)} placeholder={entity === 'category' ? '新分类名称' : '新标签名称'} value={name} /><PrimaryButton disabled={!name.trim()} onClick={() => void onCreate(name.trim()).then(() => setName(''))}><Plus size={14} />新建</PrimaryButton></div></LibraryDialog>; }
function TagSelectionDialog({ available, onClose, onSave, selected }: { available: ResourceTag[]; onClose: () => void; onSave: (value: string[]) => void; selected: string[] }) { const [value, setValue] = useState(selected); const [custom, setCustom] = useState(''); const options = uniqueNames([...available.map((item) => item.name), ...value]); return <LibraryDialog footer={<><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton onClick={() => onSave(value)}>确定</PrimaryButton></>} onClose={onClose} title="选择角色标签"><div className="library-assignment-list">{options.map((name) => <label key={name}><input checked={value.includes(name)} onChange={(event) => setValue(event.target.checked ? [...value, name] : value.filter((item) => item !== name))} type="checkbox" /><span>{name}</span></label>)}</div><div className="character-inline-create"><input onChange={(event) => setCustom(event.target.value)} placeholder="新增标签" value={custom} /><SecondaryButton disabled={!custom.trim()} onClick={() => { setValue(uniqueNames([...value, custom.trim()])); setCustom(''); }}><Plus size={14} />添加</SecondaryButton></div></LibraryDialog>; }
function NameDialog({ initial, onClose, onSave, title }: { initial: string; onClose: () => void; onSave: (name: string) => void; title: string }) { const [name, setName] = useState(initial); return <LibraryDialog footer={<><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={!name.trim()} onClick={() => onSave(name.trim())}>保存</PrimaryButton></>} onClose={onClose} title={title}><label className="dialog-stacked-field"><span>分类名称</span><input autoFocus onChange={(event) => setName(event.target.value)} value={name} /></label></LibraryDialog>; }
function Field({ children, className = '', label }: { children: ReactNode; className?: string; label: string }) { return <label className={className}><span>{label}</span>{children}</label>; }
function emptyDraft(): EditorDraft { return { name: '', identity: '', age: '', aliases: '', description: '', stable_fields: DEFAULT_STABLE_FIELDS.map((field) => ({ ...field })), selectedTags: [], source_metadata: {}, import_metadata: { created_by: 'manual' }, raw_text: '' }; }
function draftFromCard(card: CharacterCard): EditorDraft { return { name: card.name, identity: card.identity, age: card.age, aliases: card.aliases.join('、'), description: card.description, stable_fields: card.stable_fields.length ? card.stable_fields : DEFAULT_STABLE_FIELDS.map((field) => ({ ...field })), selectedTags: card.tags, source_metadata: card.source_metadata, import_metadata: card.import_metadata, raw_text: card.raw_text }; }
function splitValues(value: string) { return value.split(/[、，,]/).map((item) => item.trim()).filter(Boolean); }
function uniqueNames(values: string[]) { const seen = new Set<string>(); return values.map((item) => item.trim()).filter((item) => { const key = item.toLocaleLowerCase(); if (!item || seen.has(key)) return false; seen.add(key); return true; }); }
function errorMessage(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
