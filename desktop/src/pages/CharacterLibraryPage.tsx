import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import {
  BriefcaseBusiness,
  Check,
  ChevronDown,
  Filter,
  FolderOpen,
  Pencil,
  Plus,
  Search,
  Tag,
  Trash2,
  UserRound,
  UsersRound,
  X,
} from 'lucide-react';
import {
  assignCharacterCategory,
  assignCharacterTag,
  characterCoverUrl,
  createCharacterCard,
  createCharacterCategory,
  createCharacterTag,
  deleteCharacterCard,
  deleteCharacterCategory,
  deleteCharacterTag,
  getCharacterCards,
  getCharacterCategories,
  getCharacterProjectSummaries,
  getCharacterTags,
  getProjectCharacters,
  removeCharacterCover,
  renameCharacterCategory,
  renameCharacterTag,
  saveCharacterCover,
  updateCharacterCard,
} from '../api/client';
import type {
  CharacterCard,
  CharacterCategory,
  CharacterCustomField,
  CharacterLibrarySelection,
  CharacterProjectSummary,
  CharacterQueryState,
  ResourceTag,
} from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { LibraryDialog, LibraryEmptyState, LibrarySidebarItem } from '../components/LibraryPrimitives';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

const DEFAULT_QUERY: CharacterQueryState = {
  query: '',
  activeTagId: null,
  analysisStatus: 'all',
  untaggedOnly: false,
};

export function CharacterLibraryPage() {
  const [selection, setSelection] = useState<CharacterLibrarySelection>({ kind: 'public-all' });
  const [queryState, setQueryState] = useState<CharacterQueryState>(DEFAULT_QUERY);
  const [cards, setCards] = useState<CharacterCard[]>([]);
  const [tags, setTags] = useState<ResourceTag[]>([]);
  const [categories, setCategories] = useState<CharacterCategory[]>([]);
  const [projects, setProjects] = useState<CharacterProjectSummary[]>([]);
  const [publicCount, setPublicCount] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<CharacterCard | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  const [projectQuery, setProjectQuery] = useState('');
  const [tagManagerOpen, setTagManagerOpen] = useState(false);
  const [categoryManagerOpen, setCategoryManagerOpen] = useState(false);
  const [nameDialog, setNameDialog] = useState<NameDialogState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selected = cards.find((card) => card.id === selectedId) ?? null;
  const activeTag = tags.find((tagItem) => tagItem.id === queryState.activeTagId) ?? null;
  const recentProjects = projects.slice(0, 3);

  const filteredCards = useMemo(() => {
    const normalizedQuery = queryState.query.trim().toLocaleLowerCase();
    return cards.filter((card) => {
      if (activeTag && !card.tags.includes(activeTag.name)) return false;
      if (queryState.analysisStatus !== 'all' && card.analysis_status !== queryState.analysisStatus) return false;
      if (queryState.untaggedOnly && card.tags.length > 0) return false;
      if (!normalizedQuery) return true;
      return [
        card.name,
        card.aliases.join(' '),
        card.identity,
        card.source_summary.label,
        card.tags.join(' '),
      ].join(' ').toLocaleLowerCase().includes(normalizedQuery);
    });
  }, [activeTag, cards, queryState]);

  useAutoDismiss(message, setMessage);
  useAutoDismiss(error, setError, 5200);

  async function loadMetadata() {
    const [tagItems, categoryItems, projectItems, publicItems] = await Promise.all([
      getCharacterTags(),
      getCharacterCategories(),
      getCharacterProjectSummaries(),
      getCharacterCards('public'),
    ]);
    setTags(tagItems);
    setCategories(categoryItems);
    setProjects(projectItems);
    setPublicCount(publicItems.length);
  }

  async function loadCards(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const items = selection.kind === 'project'
        ? (await getProjectCharacters(selection.projectId)).character_cards
        : await getCharacterCards(
          'public',
          null,
          selection.kind === 'public-category' ? selection.categoryId : null,
        );
      setCards(items);
      const candidate = preferredId === undefined ? selectedId : preferredId;
      setSelectedId(items.some((card) => card.id === candidate) ? candidate : items[0]?.id ?? null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }

  async function refresh(preferredId?: number | null) {
    await Promise.all([loadMetadata(), loadCards(preferredId)]);
  }

  useEffect(() => {
    void loadMetadata().catch((reason) => setError(errorMessage(reason)));
  }, []);

  useEffect(() => {
    void loadCards();
  }, [selection]);

  function selectMainRange(next: CharacterLibrarySelection) {
    setSelection(next);
    setSelectedId(null);
  }

  function createBlank() {
    const projectId = selection.kind === 'project' ? selection.projectId : null;
    setEditing(emptyCharacter(projectId));
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

  async function saveCharacter(card: CharacterCard, draft: CharacterDraft) {
    if (!draft.name.trim()) {
      setError('角色名称不能为空。');
      return;
    }
    await runBusy(async () => {
      const payload = {
        name: draft.name.trim(),
        aliases: splitValues(draft.aliases),
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
        project_id: card.project_id,
        identity: draft.identity,
        age: draft.age,
        setting_text: draft.setting_text,
        custom_fields: normalizeFields(draft.custom_fields),
        raw_text: draft.raw_text,
        analysis_status: draft.analysis_status,
        tag_ids: draft.tag_ids,
      };
      const saved = card.id
        ? await updateCharacterCard(card.id, payload)
        : await createCharacterCard(payload);
      if (!card.id && selection.kind === 'public-category') {
        await assignCharacterCategory(saved.id, selection.categoryId, true);
      }
      setEditing(null);
      await refresh(saved.id);
      setMessage(card.id ? '角色已保存。' : '角色已创建。');
    });
  }

  async function deleteCard(card: CharacterCard) {
    if (!window.confirm(`确认删除角色“${card.name}”？已复制的独立副本不会被删除。`)) return;
    await runBusy(async () => {
      await deleteCharacterCard(card.id);
      await refresh(null);
      setMessage('角色已删除。');
    });
  }

  function activateTag(tagId: number) {
    setQueryState((current) => ({
      ...current,
      activeTagId: current.activeTagId === tagId ? null : tagId,
    }));
  }

  async function toggleTag(tagId: number, checked: boolean) {
    if (!selected) return;
    await runBusy(async () => {
      await assignCharacterTag(selected.id, tagId, checked);
      await refresh(selected.id);
    });
  }

  async function toggleCategory(categoryId: number, checked: boolean) {
    if (!selected || selected.scope !== 'public') return;
    await runBusy(async () => {
      await assignCharacterCategory(selected.id, categoryId, checked);
      await refresh(selected.id);
    });
  }

  async function saveName(name: string) {
    if (!nameDialog) return;
    await runBusy(async () => {
      if (nameDialog.entity === 'category') {
        const category = nameDialog.item
          ? await renameCharacterCategory(nameDialog.item.id, name)
          : await createCharacterCategory(name);
        await loadMetadata();
        if (!nameDialog.item) selectMainRange({ kind: 'public-category', categoryId: category.id });
      } else {
        await (nameDialog.item
          ? renameCharacterTag(nameDialog.item.id, name)
          : createCharacterTag(name));
        await loadMetadata();
      }
      setNameDialog(null);
    });
  }

  async function removeCategory(category: CharacterCategory) {
    if (!window.confirm('删除分类只解除分类，不删除角色卡。确认继续？')) return;
    await runBusy(async () => {
      await deleteCharacterCategory(category.id);
      if (selection.kind === 'public-category' && selection.categoryId === category.id) {
        setSelection({ kind: 'public-all' });
      }
      await loadMetadata();
      setMessage('分类已删除，角色卡保持不变。');
    });
  }

  async function removeTag(tagItem: ResourceTag) {
    if (!window.confirm('删除标签只解除关联，不删除角色卡。确认继续？')) return;
    await runBusy(async () => {
      await deleteCharacterTag(tagItem.id);
      if (queryState.activeTagId === tagItem.id) {
        setQueryState((current) => ({ ...current, activeTagId: null }));
      }
      await refresh(selectedId);
    });
  }

  const rangeLabel = selection.kind === 'project'
    ? projects.find((project) => project.project_id === selection.projectId)?.project_name ?? '工程角色'
    : selection.kind === 'public-category'
      ? categories.find((category) => category.id === selection.categoryId)?.name ?? '公共分类'
      : '全部公共角色';

  return (
    <div className="document-library-page character-library-page">
      <TopBar
        title="角色卡库"
        actions={<PrimaryButton disabled={busy} onClick={createBlank}><Plus size={16} />新建角色</PrimaryButton>}
      />
      {error ? <div className="inline-alert error document-library-alert" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success document-library-alert" role="status">{message}</div> : null}

      <div className="document-library-layout character-browser-layout">
        <aside className="document-tag-panel character-range-panel">
          <nav aria-label="角色库范围">
            <div className="character-nav-heading"><span>工程角色</span></div>
            {recentProjects.map((project) => (
              <LibrarySidebarItem
                active={selection.kind === 'project' && selection.projectId === project.project_id}
                count={project.character_count}
                icon={<BriefcaseBusiness size={16} />}
                key={project.project_id}
                label={project.project_name}
                onClick={() => selectMainRange({ kind: 'project', projectId: project.project_id })}
              />
            ))}
            {projects.length > 3 ? (
              <button className="character-more-projects" onClick={() => setProjectDialogOpen(true)} type="button">
                <FolderOpen size={15} />展开更多工程<ChevronDown size={14} />
              </button>
            ) : null}

            <div className="character-nav-heading"><span>公共角色</span></div>
            <LibrarySidebarItem
              active={selection.kind === 'public-all'}
              count={publicCount}
              icon={<UsersRound size={16} />}
              label="全部角色"
              onClick={() => selectMainRange({ kind: 'public-all' })}
            />

            <div className="character-nav-heading">
              <span>我的分类</span>
              <button
                aria-label="新建角色分类"
                className="document-add-tag"
                disabled={busy}
                onClick={() => setNameDialog({ entity: 'category' })}
                type="button"
              ><Plus size={15} /></button>
            </div>
            {categories.map((category) => (
              <div className="character-category-row" key={category.id}>
                <LibrarySidebarItem
                  active={selection.kind === 'public-category' && selection.categoryId === category.id}
                  count={category.resource_count}
                  icon={<Tag size={15} />}
                  label={category.name}
                  onClick={() => selectMainRange({ kind: 'public-category', categoryId: category.id })}
                />
                <div className="character-row-actions">
                  <button aria-label={`重命名分类 ${category.name}`} onClick={() => setNameDialog({ entity: 'category', item: category })} type="button"><Pencil size={12} /></button>
                  <button aria-label={`删除分类 ${category.name}`} onClick={() => void removeCategory(category)} type="button"><Trash2 size={12} /></button>
                </div>
              </div>
            ))}
          </nav>
        </aside>

        <main className="document-shelf-panel character-browser-shelf">
          <header>
            <div>
              <h2>{rangeLabel}</h2>
              <span>{filteredCards.length} 个角色</span>
            </div>
            <div className="document-shelf-tools character-search-tools">
              <label className="search-field document-search">
                <Search size={15} />
                <span className="sr-only">搜索角色</span>
                <input
                  onChange={(event) => setQueryState((current) => ({ ...current, query: event.target.value }))}
                  placeholder="搜索角色名称或来源"
                  type="search"
                  value={queryState.query}
                />
              </label>
              <div className="character-filter-anchor">
                <SecondaryButton aria-expanded={filterOpen} onClick={() => setFilterOpen((open) => !open)}>
                  <Filter size={15} />筛选
                </SecondaryButton>
                {filterOpen ? (
                  <div className="character-filter-popover">
                    <strong>分析状态</strong>
                    {(['all', 'unanalyzed', 'analyzed'] as const).map((status) => (
                      <label key={status}>
                        <input
                          checked={queryState.analysisStatus === status}
                          name="analysis-status"
                          onChange={() => setQueryState((current) => ({ ...current, analysisStatus: status }))}
                          type="radio"
                        />
                        {status === 'all' ? '全部' : status === 'unanalyzed' ? '未分析' : '已分析'}
                      </label>
                    ))}
                    <strong>标签状态</strong>
                    <label>
                      <input
                        checked={queryState.untaggedOnly}
                        onChange={(event) => setQueryState((current) => ({ ...current, untaggedOnly: event.target.checked }))}
                        type="checkbox"
                      />仅无标签
                    </label>
                  </div>
                ) : null}
              </div>
            </div>
          </header>
          <div className="character-active-filters">
            {activeTag ? <FilterChip label={`标签：${activeTag.name}`} onClear={() => setQueryState((current) => ({ ...current, activeTagId: null }))} /> : null}
            {queryState.analysisStatus !== 'all' ? <FilterChip label={queryState.analysisStatus === 'analyzed' ? '已分析' : '未分析'} onClear={() => setQueryState((current) => ({ ...current, analysisStatus: 'all' }))} /> : null}
            {queryState.untaggedOnly ? <FilterChip label="仅无标签" onClear={() => setQueryState((current) => ({ ...current, untaggedOnly: false }))} /> : null}
          </div>

          {loading ? <LibraryEmptyState title="正在读取角色…" /> : filteredCards.length ? (
            <div className="document-shelf-scroll">
              <div className="document-character-grid character-compact-grid">
                {filteredCards.map((card) => (
                  <button
                    aria-pressed={selectedId === card.id}
                    className={`library-character-card character-compact-card ${selectedId === card.id ? 'selected' : ''}`}
                    key={card.id}
                    onClick={() => setSelectedId(card.id)}
                    onDoubleClick={() => setEditing(card)}
                    type="button"
                  >
                    <CharacterCover card={card} />
                    <div className="library-character-card-body">
                      <strong>{card.name}</strong>
                      <span className={`character-analysis-badge ${card.analysis_status}`}>{card.analysis_status === 'analyzed' ? '已分析' : '未分析'}</span>
                      <p title={card.source_summary.label}>来源：{card.source_summary.label}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <LibraryEmptyState
              action={cards.length === 0 ? <PrimaryButton onClick={createBlank}><Plus size={16} />新建角色</PrimaryButton> : undefined}
              description={cards.length === 0 ? '当前范围还没有角色。' : '尝试清除搜索词或临时筛选条件。'}
              title={cards.length === 0 ? '角色库为空' : '没有匹配的角色'}
            />
          )}
        </main>

        <aside className="document-detail-panel character-detail-panel">
          <header><h2>角色详情</h2></header>
          {selected ? (
            <>
              <div className="document-detail-scroll character-summary-scroll">
                <section className="character-detail-identity">
                  <CharacterCover card={selected} large />
                  <div>
                    <h3>{selected.name}</h3>
                    <p>{selected.identity || selected.aliases.join(' / ') || '身份摘要未填写'}</p>
                    <span className={`character-analysis-badge ${selected.analysis_status}`}>{selected.analysis_status === 'analyzed' ? '已分析' : '未分析'}</span>
                  </div>
                </section>
                <DetailSection label="来源" value={selected.source_summary.label} />
                <DetailSection label="设定摘要" value={selected.setting_text || selected.description || '尚未填写设定摘要'} clamp />
                {selected.scope === 'public' ? (
                  <PillSection
                    addLabel="管理所属分类"
                    label="所属分类"
                    onAdd={() => setCategoryManagerOpen(true)}
                    pills={selected.categories.map((name) => ({
                      active: selection.kind === 'public-category' && categories.find((item) => item.name === name)?.id === selection.categoryId,
                      label: name,
                      onClick: () => {
                        const category = categories.find((item) => item.name === name);
                        if (category) selectMainRange({ kind: 'public-category', categoryId: category.id });
                      },
                    }))}
                  />
                ) : null}
                <PillSection
                  addLabel="管理角色标签"
                  label="角色标签"
                  onAdd={() => setTagManagerOpen(true)}
                  pills={selected.tags.map((name) => {
                    const tagItem = tags.find((item) => item.name === name);
                    return {
                      active: tagItem?.id === queryState.activeTagId,
                      label: name,
                      onClick: () => tagItem && activateTag(tagItem.id),
                    };
                  })}
                />
              </div>
              <footer className="library-detail-footer character-detail-footer">
                <SecondaryButton disabled={busy} onClick={() => setEditing(selected)}><Pencil size={15} />编辑</SecondaryButton>
                <DangerButton disabled={busy} onClick={() => void deleteCard(selected)}><Trash2 size={15} />删除</DangerButton>
              </footer>
            </>
          ) : <LibraryEmptyState description="选择中央区域中的角色卡查看摘要。" title="选择一个角色" />}
        </aside>
      </div>

      {editing ? (
        <CharacterEditor
          busy={busy}
          card={editing}
          tags={tags}
          onClose={() => setEditing(null)}
          onCoverChanged={(id) => void refresh(id)}
          onSave={saveCharacter}
        />
      ) : null}
      {projectDialogOpen ? (
        <ProjectPicker
          projects={projects}
          query={projectQuery}
          onChangeQuery={setProjectQuery}
          onClose={() => setProjectDialogOpen(false)}
          onSelect={(projectId) => {
            setProjectDialogOpen(false);
            selectMainRange({ kind: 'project', projectId });
          }}
        />
      ) : null}
      {selected && tagManagerOpen ? (
        <AssignmentManager
          busy={busy}
          items={tags}
          selectedNames={selected.tags}
          title="管理角色标签"
          onClose={() => setTagManagerOpen(false)}
          onCreate={() => setNameDialog({ entity: 'tag' })}
          onDelete={(item) => void removeTag(item as ResourceTag)}
          onRename={(item) => setNameDialog({ entity: 'tag', item: item as ResourceTag })}
          onToggle={(id, checked) => void toggleTag(id, checked)}
        />
      ) : null}
      {selected?.scope === 'public' && categoryManagerOpen ? (
        <AssignmentManager
          busy={busy}
          items={categories}
          selectedNames={selected.categories}
          title="管理所属分类"
          onClose={() => setCategoryManagerOpen(false)}
          onCreate={() => setNameDialog({ entity: 'category' })}
          onDelete={(item) => void removeCategory(item as CharacterCategory)}
          onRename={(item) => setNameDialog({ entity: 'category', item: item as CharacterCategory })}
          onToggle={(id, checked) => void toggleCategory(id, checked)}
        />
      ) : null}
      {nameDialog ? (
        <NameDialog
          busy={busy}
          initialName={nameDialog.item?.name ?? ''}
          title={`${nameDialog.item ? '重命名' : '新建'}${nameDialog.entity === 'tag' ? '标签' : '分类'}`}
          onClose={() => setNameDialog(null)}
          onSave={(name) => void saveName(name)}
        />
      ) : null}
    </div>
  );
}

type NamedItem = ResourceTag | CharacterCategory;
type NameDialogState =
  | { entity: 'tag'; item?: ResourceTag }
  | { entity: 'category'; item?: CharacterCategory };

function CharacterCover({ card, large = false }: { card: CharacterCard; large?: boolean }) {
  return (
    <div
      className={`${large ? 'character-detail-avatar' : 'library-character-cover'} character-cover`}
      style={{ '--character-cover': coverColor(card.name) } as CSSProperties}
    >
      {card.cover_path
        ? <img alt="" src={`${characterCoverUrl(card.id)}?v=${encodeURIComponent(card.cover_updated_at ?? '')}`} />
        : <span>{card.name.trim().slice(0, 1) || <UserRound size={large ? 30 : 24} />}</span>}
    </div>
  );
}

function FilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  return <span className="character-filter-chip">{label}<button aria-label={`清除${label}`} onClick={onClear} type="button"><X size={12} /></button></span>;
}

function DetailSection({ clamp = false, label, value }: { clamp?: boolean; label: string; value: string }) {
  return (
    <section>
      <div className="document-detail-heading"><span>{label}</span></div>
      <p className={`character-detail-copy ${clamp ? 'clamped' : ''}`}>{value}</p>
    </section>
  );
}

function PillSection({ addLabel, label, onAdd, pills }: {
  addLabel: string;
  label: string;
  onAdd: () => void;
  pills: Array<{ active: boolean; label: string; onClick: () => void }>;
}) {
  return (
    <section>
      <div className="document-detail-heading">
        <span>{label}</span>
        <button aria-label={addLabel} className="character-section-add" onClick={onAdd} type="button"><Plus size={14} /></button>
      </div>
      <div className="character-pill-list">
        {pills.length ? pills.map((pill) => (
          <button className={pill.active ? 'active' : ''} key={pill.label} onClick={pill.onClick} type="button">{pill.label}</button>
        )) : <span className="character-empty-inline">暂无</span>}
      </div>
    </section>
  );
}

function ProjectPicker({ onChangeQuery, onClose, onSelect, projects, query }: {
  onChangeQuery: (value: string) => void;
  onClose: () => void;
  onSelect: (projectId: number) => void;
  projects: CharacterProjectSummary[];
  query: string;
}) {
  const normalized = query.trim().toLocaleLowerCase();
  const visible = projects.filter((project) => project.project_name.toLocaleLowerCase().includes(normalized));
  return (
    <LibraryDialog footer={<SecondaryButton onClick={onClose}>关闭</SecondaryButton>} onClose={onClose} title="选择工程">
      <label className="search-field character-project-search"><Search size={15} /><input autoFocus onChange={(event) => onChangeQuery(event.target.value)} placeholder="搜索工程" value={query} /></label>
      <div className="character-project-list">
        {visible.map((project) => (
          <button key={project.project_id} onClick={() => onSelect(project.project_id)} type="button">
            <span><strong>{project.project_name}</strong><small>{project.updated_at}</small></span>
            <b>{project.character_count}</b>
          </button>
        ))}
      </div>
    </LibraryDialog>
  );
}

function AssignmentManager({ busy, items, onClose, onCreate, onDelete, onRename, onToggle, selectedNames, title }: {
  busy: boolean;
  items: NamedItem[];
  onClose: () => void;
  onCreate: () => void;
  onDelete: (item: NamedItem) => void;
  onRename: (item: NamedItem) => void;
  onToggle: (id: number, checked: boolean) => void;
  selectedNames: string[];
  title: string;
}) {
  return (
    <LibraryDialog
      footer={<SecondaryButton onClick={onClose}>完成</SecondaryButton>}
      onClose={onClose}
      title={title}
    >
      <div className="character-manager-heading"><span>选择关联项</span><SecondaryButton disabled={busy} onClick={onCreate}><Plus size={14} />新建</SecondaryButton></div>
      <div className="character-assignment-list">
        {items.map((item) => (
          <div key={item.id}>
            <label>
              <input checked={selectedNames.includes(item.name)} disabled={busy} onChange={(event) => onToggle(item.id, event.target.checked)} type="checkbox" />
              <span>{item.name}</span>
              {selectedNames.includes(item.name) ? <Check size={14} /> : null}
            </label>
            <button aria-label={`重命名 ${item.name}`} onClick={() => onRename(item)} type="button"><Pencil size={13} /></button>
            <button aria-label={`删除 ${item.name}`} onClick={() => onDelete(item)} type="button"><Trash2 size={13} /></button>
          </div>
        ))}
      </div>
    </LibraryDialog>
  );
}

function NameDialog({ busy, initialName, onClose, onSave, title }: {
  busy: boolean;
  initialName: string;
  onClose: () => void;
  onSave: (name: string) => void;
  title: string;
}) {
  const [name, setName] = useState(initialName);
  return (
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !name.trim()} onClick={() => onSave(name.trim())}>保存</PrimaryButton></>}
      onClose={onClose}
      title={title}
    >
      <Field label="名称"><input autoFocus maxLength={40} onChange={(event) => setName(event.target.value)} value={name} /></Field>
    </LibraryDialog>
  );
}

type CharacterDraft = {
  name: string;
  aliases: string;
  identity: string;
  age: string;
  setting_text: string;
  raw_text: string;
  analysis_status: 'unanalyzed' | 'analyzed';
  custom_fields: CharacterCustomField[];
  tag_ids: number[];
};

function CharacterEditor({ busy, card, onClose, onCoverChanged, onSave, tags }: {
  busy: boolean;
  card: CharacterCard;
  onClose: () => void;
  onCoverChanged: (id: number) => void;
  onSave: (card: CharacterCard, draft: CharacterDraft) => void;
  tags: ResourceTag[];
}) {
  const [draft, setDraft] = useState<CharacterDraft>({
    name: card.name,
    aliases: card.aliases.join('、'),
    identity: card.identity,
    age: card.age,
    setting_text: card.setting_text,
    raw_text: card.raw_text,
    analysis_status: card.analysis_status,
    custom_fields: card.custom_fields,
    tag_ids: tags.filter((tagItem) => card.tags.includes(tagItem.name)).map((tagItem) => tagItem.id),
  });

  async function uploadCover(file?: File) {
    if (!file || !card.id) return;
    const data = await file.arrayBuffer();
    const base64 = arrayBufferToBase64(data);
    await saveCharacterCover(card.id, base64);
    onCoverChanged(card.id);
  }

  return (
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !draft.name.trim()} onClick={() => onSave(card, draft)}>保存</PrimaryButton></>}
      onClose={onClose}
      subtitle={card.scope === 'project' ? '工程角色' : '公共角色'}
      title={card.id ? '编辑角色' : '新建角色'}
    >
      <div className="library-form-grid">
        <Field label="角色名"><input autoFocus onChange={(event) => setDraft({ ...draft, name: event.target.value })} value={draft.name} /></Field>
        <Field label="别名"><input onChange={(event) => setDraft({ ...draft, aliases: event.target.value })} placeholder="使用顿号或逗号分隔" value={draft.aliases} /></Field>
        <Field label="身份摘要"><input onChange={(event) => setDraft({ ...draft, identity: event.target.value })} value={draft.identity} /></Field>
        <Field label="年龄"><input onChange={(event) => setDraft({ ...draft, age: event.target.value })} value={draft.age} /></Field>
        <Field className="wide" label="设定"><textarea onChange={(event) => setDraft({ ...draft, setting_text: event.target.value })} value={draft.setting_text} /></Field>
        <fieldset className="wide library-tag-picker">
          <legend>标签</legend>
          {tags.map((tagItem) => (
            <label key={tagItem.id}>
              <input
                checked={draft.tag_ids.includes(tagItem.id)}
                onChange={(event) => setDraft({
                  ...draft,
                  tag_ids: event.target.checked
                    ? [...draft.tag_ids, tagItem.id]
                    : draft.tag_ids.filter((id) => id !== tagItem.id),
                })}
                type="checkbox"
              />{tagItem.name}
            </label>
          ))}
        </fieldset>
        <div className="wide character-cover-editor">
          <span>封面</span>
          {card.id ? (
            <>
              <input accept="image/png,image/jpeg,image/webp" onChange={(event) => void uploadCover(event.target.files?.[0])} type="file" />
              <SecondaryButton disabled={busy || !card.cover_path} onClick={async () => { await removeCharacterCover(card.id); onCoverChanged(card.id); }}>移除封面</SecondaryButton>
            </>
          ) : <small>保存角色后可上传封面。</small>}
        </div>
      </div>
    </LibraryDialog>
  );
}

function Field({ children, className = '', label }: { children: ReactNode; className?: string; label: string }) {
  return <label className={className}><span>{label}</span>{children}</label>;
}

function emptyCharacter(projectId: number | null): CharacterCard {
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
    scope: projectId === null ? 'public' : 'project',
    project_id: projectId,
    source_character_card_id: null,
    source_version: null,
    version: 1,
    sort_order: 0,
    identity: '',
    age: '',
    setting_text: '',
    custom_fields: [],
    raw_text: '',
    analysis_status: 'unanalyzed',
    cover_path: null,
    cover_updated_at: null,
    tags: [],
    category_ids: [],
    categories: [],
    source_summary: { kind: 'manual', label: '手动创建' },
    created_at: '',
    updated_at: '',
  };
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

function arrayBufferToBase64(buffer: ArrayBuffer) {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < bytes.length; index += 1) binary += String.fromCharCode(bytes[index]);
  return btoa(binary);
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}
