import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import {
  ArrowDown,
  ArrowUp,
  BriefcaseBusiness,
  Check,
  ChevronDown,
  Filter,
  FolderOpen,
  Pencil,
  Plus,
  Search,
  Settings,
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
  copyPublicCharacterToProject,
  deleteCharacterCard,
  deleteCharacterCategory,
  deleteCharacterTag,
  getCharacterCards,
  getCharacterCategories,
  getCharacterProjectSummaries,
  getCharacterTags,
  getExistingCharacterProjectCopy,
  getProjectCharacters,
  removeCharacterCover,
  publishProjectCharacterToPublic,
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
import {
  CharacterCreateDialog,
  CharacterExtractionSettingsDialog,
  type CharacterExtractionLaunch,
} from '../components/CharacterCreationDialogs';
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
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [extractionLaunch, setExtractionLaunch] = useState<CharacterExtractionLaunch | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
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
    const launch = window.history.state?.characterExtraction as CharacterExtractionLaunch | undefined;
    if (!launch?.selectedText) return;
    setExtractionLaunch(launch);
    setCreateDialogOpen(true);
    window.history.replaceState(null, '', window.location.href);
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
        description: draft.description,
        priority: card.priority,
        is_main: card.is_main,
        relationship_notes: draft.relationship_notes,
        personality: draft.personality,
        speech_style: draft.speech_style,
        action_constraints: draft.action_constraints,
        anti_ooc_rules: draft.anti_ooc_rules,
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
      if (saved.scope === 'public') {
        const desiredCategoryIds = new Set(draft.category_ids);
        if (!card.id && selection.kind === 'public-category') desiredCategoryIds.add(selection.categoryId);
        for (const category of categories) {
          const wasSelected = card.category_ids.includes(category.id);
          const selectedNow = desiredCategoryIds.has(category.id);
          if (wasSelected !== selectedNow) await assignCharacterCategory(saved.id, category.id, selectedNow);
        }
      }
      let coverUploadFailed = false;
      try {
        if (draft.coverFile) {
          await saveCharacterCover(saved.id, arrayBufferToBase64(await draft.coverFile.arrayBuffer()));
        } else if (draft.removeCover && card.cover_path) {
          await removeCharacterCover(saved.id);
        }
      } catch {
        coverUploadFailed = true;
      }
      setEditing(null);
      await refresh(saved.id);
      if (coverUploadFailed) {
        setError('角色已保存，但封面上传失败。请重新打开角色并重试封面上传。');
      } else {
        setMessage(card.id ? '角色已保存。' : '角色已创建。');
      }
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
        actions={(
          <>
            <PrimaryButton disabled={busy} onClick={() => { setExtractionLaunch(null); setCreateDialogOpen(true); }}><Plus size={16} />新建角色</PrimaryButton>
            <SecondaryButton aria-label="角色提取设置" disabled={busy} onClick={() => setSettingsOpen(true)}><Settings size={16} /></SecondaryButton>
          </>
        )}
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
            <div className="document-shelf-scroll resource-list-scroll">
              <div aria-label="角色条目" className="resource-row-list">
                {filteredCards.map((card) => (
                  <button
                    aria-pressed={selectedId === card.id}
                    className={`resource-list-row character-resource-row ${selectedId === card.id ? 'selected' : ''}`}
                    key={card.id}
                    onClick={() => setSelectedId(card.id)}
                    onDoubleClick={() => setEditing(card)}
                    type="button"
                  >
                    <strong className="resource-row-name">{card.name}</strong>
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
          categories={categories}
          projects={projects}
          tags={tags}
          onClose={() => setEditing(null)}
          onCoverChanged={(id) => void refresh(id)}
          onProjectCopied={(copied) => {
            setEditing(null);
            setSelection({ kind: 'project', projectId: copied.project_id! });
            window.setTimeout(() => void refresh(copied.id), 0);
            setMessage(`已添加到工程 ${projects.find((project) => project.project_id === copied.project_id)?.project_name ?? ''}`);
          }}
          onSave={saveCharacter}
        />
      ) : null}
      {createDialogOpen ? (
        <CharacterCreateDialog
          categories={categories}
          initialLaunch={extractionLaunch}
          initialProjectId={selection.kind === 'project' ? selection.projectId : null}
          projects={projects}
          tags={tags}
          onClose={() => { setCreateDialogOpen(false); setExtractionLaunch(null); }}
          onCreated={(cardIds, scope, projectId) => {
            setCreateDialogOpen(false);
            setExtractionLaunch(null);
            if (scope === 'project' && projectId !== null) {
              setSelection({ kind: 'project', projectId });
            } else {
              setSelection({ kind: 'public-all' });
            }
            window.setTimeout(() => void refresh(cardIds[0] ?? null), 0);
            setMessage(`已创建 ${cardIds.length} 个角色。`);
          }}
          onManual={() => {
            setCreateDialogOpen(false);
            setExtractionLaunch(null);
            createBlank();
          }}
        />
      ) : null}
      {settingsOpen ? <CharacterExtractionSettingsDialog onClose={() => setSettingsOpen(false)} /> : null}
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
  description: string;
  identity: string;
  age: string;
  setting_text: string;
  relationship_notes: string;
  personality: string;
  speech_style: string;
  action_constraints: string;
  anti_ooc_rules: string;
  raw_text: string;
  analysis_status: 'unanalyzed' | 'analyzed';
  custom_fields: CharacterCustomField[];
  tag_ids: number[];
  category_ids: number[];
  coverFile: File | null;
  removeCover: boolean;
};

function CharacterEditor({ busy, card, categories, onClose, onCoverChanged, onProjectCopied, onSave, projects, tags }: {
  busy: boolean;
  card: CharacterCard;
  categories: CharacterCategory[];
  onClose: () => void;
  onCoverChanged: (id: number) => void;
  onProjectCopied: (card: CharacterCard) => void;
  onSave: (card: CharacterCard, draft: CharacterDraft) => void;
  projects: CharacterProjectSummary[];
  tags: ResourceTag[];
}) {
  const [draft, setDraft] = useState<CharacterDraft>({
    name: card.name,
    aliases: card.aliases.join('、'),
    description: card.description,
    identity: card.identity,
    age: card.age,
    setting_text: card.setting_text,
    relationship_notes: card.relationship_notes,
    personality: card.personality,
    speech_style: card.speech_style,
    action_constraints: card.action_constraints,
    anti_ooc_rules: card.anti_ooc_rules,
    raw_text: card.raw_text,
    analysis_status: card.analysis_status,
    custom_fields: card.custom_fields,
    tag_ids: tags.filter((tagItem) => card.tags.includes(tagItem.name)).map((tagItem) => tagItem.id),
    category_ids: card.category_ids,
    coverFile: null,
    removeCover: false,
  });
  const [warningOpen, setWarningOpen] = useState(false);
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [localTags, setLocalTags] = useState(tags);
  const [previewUrl, setPreviewUrl] = useState('');
  const initialSnapshot = useMemo(() => JSON.stringify({ ...draft, coverFile: null }), []);
  const dirty = JSON.stringify({ ...draft, coverFile: draft.coverFile?.name ?? null }) !== initialSnapshot;

  useEffect(() => {
    if (!draft.coverFile) {
      setPreviewUrl('');
      return;
    }
    const url = URL.createObjectURL(draft.coverFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [draft.coverFile]);

  function requestClose() {
    if (!dirty || window.confirm('有未保存的内容，确认关闭角色编辑器吗？')) onClose();
  }

  function requestSave() {
    const labels = draft.custom_fields.map((field) => field.label.trim().toLocaleLowerCase());
    if (labels.some((label) => !label)) return void window.alert('自定义字段名不能为空。');
    if (new Set(labels).size !== labels.length) return void window.alert('自定义字段名不能重复。');
    if (!draft.identity.trim() || !draft.age.trim() || !draft.setting_text.trim()) {
      setWarningOpen(true);
      return;
    }
    onSave(card, draft);
  }

  function moveField(index: number, offset: number) {
    const next = [...draft.custom_fields];
    const target = index + offset;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setDraft({ ...draft, custom_fields: next });
  }

  async function addTag() {
    if (!newTagName.trim()) return;
    const created = await createCharacterTag(newTagName.trim());
    setLocalTags((current) => current.some((item) => item.id === created.id) ? current : [...current, created]);
    setDraft((current) => ({ ...current, tag_ids: [...new Set([...current.tag_ids, created.id])] }));
    setNewTagName('');
  }

  return (
    <>
      <LibraryDialog
        className="character-editor-dialog"
        closeOnBackdrop={false}
        footer={<div className="character-editor-actions"><div>{card.id && card.scope === 'public' ? <SecondaryButton disabled={busy} onClick={() => setProjectPickerOpen(true)}>添加到工程…</SecondaryButton> : null}{card.id && card.scope === 'project' ? <SecondaryButton disabled={busy} onClick={() => setPublishOpen(true)}>保存为公共角色…</SecondaryButton> : null}</div><div><SecondaryButton disabled={busy} onClick={requestClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !draft.name.trim()} onClick={requestSave}>保存</PrimaryButton></div></div>}
        onClose={requestClose}
        subtitle={card.scope === 'project' ? '工程角色' : '公共角色'}
        title={card.id ? '编辑角色' : '新建角色'}
      >
        <section className="character-editor-section">
          <h3>基本信息</h3>
          <div className="character-basic-grid">
            <Field className="character-name-field" label="角色名称"><input autoFocus onChange={(event) => setDraft({ ...draft, name: event.target.value })} value={draft.name} /></Field>
            <Field className="character-identity-field" label="身份"><input onChange={(event) => setDraft({ ...draft, identity: event.target.value })} value={draft.identity} /></Field>
            <Field className="character-age-field" label="年龄"><input onChange={(event) => setDraft({ ...draft, age: event.target.value })} value={draft.age} /></Field>
            <Field className="character-alias-field" label="别名"><input onChange={(event) => setDraft({ ...draft, aliases: event.target.value })} placeholder="使用顿号或逗号分隔" value={draft.aliases} /></Field>
            <Field className="character-description-field" label="简介"><input onChange={(event) => setDraft({ ...draft, description: event.target.value })} value={draft.description} /></Field>
            <Field className="character-setting-field" label="设定"><textarea onChange={(event) => setDraft({ ...draft, setting_text: event.target.value })} value={draft.setting_text} /></Field>
          </div>
        </section>
        <section className="character-editor-section">
          <h3>资源信息</h3>
          <div className="character-resource-grid">
            <div className="character-cover-panel">
              <strong>当前封面</strong>
              <div className="character-cover-preview" style={{ '--character-cover': coverColor(draft.name) } as CSSProperties}>{previewUrl ? <img alt="新封面预览" src={previewUrl} /> : card.cover_path && !draft.removeCover ? <img alt="当前封面" src={`${characterCoverUrl(card.id)}?v=${encodeURIComponent(card.cover_updated_at ?? '')}`} /> : <span>{draft.name.slice(0, 1) || <UserRound size={28} />}</span>}</div>
              <div className="character-cover-buttons"><label className="secondary-button">选择图片<input accept="image/png,image/jpeg,image/webp" hidden onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                if (file && file.size > 5 * 1024 * 1024) return void window.alert('封面不能超过 5 MB。');
                setDraft({ ...draft, coverFile: file, removeCover: false });
              }} type="file" /></label><SecondaryButton disabled={!card.cover_path && !draft.coverFile} onClick={() => setDraft({ ...draft, coverFile: null, removeCover: true })}>移除</SecondaryButton></div>
              <small title={draft.coverFile?.name}>{draft.coverFile ? truncateFileName(draft.coverFile.name) : 'PNG/JPEG/WebP，最大 5 MB'}</small>
            </div>
            <div className="character-tag-panel">
              <strong>标签</strong>
              {localTags.length ? <div className="character-editor-pills">{localTags.map((tagItem) => <label key={tagItem.id}><input checked={draft.tag_ids.includes(tagItem.id)} onChange={(event) => setDraft({ ...draft, tag_ids: event.target.checked ? [...draft.tag_ids, tagItem.id] : draft.tag_ids.filter((id) => id !== tagItem.id) })} type="checkbox" /><span>{tagItem.name}</span></label>)}</div> : <p>尚未创建角色标签</p>}
              <div className="character-inline-create"><input onChange={(event) => setNewTagName(event.target.value)} placeholder="创建新标签" value={newTagName} /><SecondaryButton disabled={!newTagName.trim()} onClick={() => void addTag()}><Plus size={14} />创建</SecondaryButton></div>
              {card.scope === 'public' ? <div className="character-category-editor"><strong>我的分类</strong>{categories.length ? <div className="character-editor-pills">{categories.map((category) => <label key={category.id}><input checked={draft.category_ids.includes(category.id)} onChange={(event) => setDraft({ ...draft, category_ids: event.target.checked ? [...draft.category_ids, category.id] : draft.category_ids.filter((id) => id !== category.id) })} type="checkbox" /><span>{category.name}</span></label>)}</div> : <p>尚未创建公共角色分类</p>}</div> : null}
            </div>
          </div>
        </section>
        <section className="character-editor-section">
          <div className="character-section-heading"><h3>自定义稳定信息</h3><SecondaryButton onClick={() => setDraft({ ...draft, custom_fields: [...draft.custom_fields, { id: crypto.randomUUID(), label: '', value: '', sort_order: draft.custom_fields.length }] })}><Plus size={14} />添加字段</SecondaryButton></div>
          <div className="character-custom-field-list">{draft.custom_fields.map((field, index) => <div className="character-custom-field-row" draggable key={field.id}><input aria-label="字段名" onChange={(event) => setDraft({ ...draft, custom_fields: draft.custom_fields.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item) })} placeholder="字段名" value={field.label} /><textarea aria-label="字段内容" onChange={(event) => setDraft({ ...draft, custom_fields: draft.custom_fields.map((item, itemIndex) => itemIndex === index ? { ...item, value: event.target.value } : item) })} placeholder="字段内容" rows={2} value={field.value} /><button aria-label="上移" disabled={index === 0} onClick={() => moveField(index, -1)} type="button"><ArrowUp size={15} /></button><button aria-label="下移" disabled={index === draft.custom_fields.length - 1} onClick={() => moveField(index, 1)} type="button"><ArrowDown size={15} /></button><button aria-label="删除字段" className="danger" onClick={() => setDraft({ ...draft, custom_fields: draft.custom_fields.filter((_, itemIndex) => itemIndex !== index) })} type="button"><Trash2 size={15} /></button></div>)}</div>
        </section>
      </LibraryDialog>
      {warningOpen ? <LibraryDialog footer={<><SecondaryButton onClick={() => setWarningOpen(false)}>返回补充</SecondaryButton><PrimaryButton onClick={() => { setWarningOpen(false); onSave(card, draft); }}>仍然保存</PrimaryButton></>} onClose={() => setWarningOpen(false)} title="部分基础信息为空"><p>以下项目尚未填写，但仍可保存：{[!draft.identity && '身份', !draft.age && '年龄', !draft.setting_text && '设定'].filter(Boolean).join('、')}。</p></LibraryDialog> : null}
      {projectPickerOpen ? <CopyToProjectDialog card={card} projects={projects} onClose={() => setProjectPickerOpen(false)} onCopied={onProjectCopied} /> : null}
      {publishOpen ? <PublishCharacterDialog card={card} onClose={() => setPublishOpen(false)} /> : null}
    </>
  );
}

function CopyToProjectDialog({
  card,
  onClose,
  onCopied,
  projects,
}: {
  card: CharacterCard;
  onClose: () => void;
  onCopied: (card: CharacterCard) => void;
  projects: CharacterProjectSummary[];
}) {
  const [projectId, setProjectId] = useState<number | null>(null);
  const [existing, setExisting] = useState<CharacterCard | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function copy(force = false) {
    if (projectId === null) return;
    setBusy(true);
    setError('');
    try {
      if (!force) {
        const found = await getExistingCharacterProjectCopy(card.id, projectId);
        if (found) {
          setExisting(found);
          return;
        }
      }
      onCopied(await copyPublicCharacterToProject(card.id, projectId, force));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <LibraryDialog
      footer={<><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || projectId === null} onClick={() => void copy()}>添加到工程</PrimaryButton></>}
      onClose={onClose}
      title="添加公共角色到工程"
    >
      {error ? <div className="inline-alert error">{error}</div> : null}
      <label className="dialog-stacked-field"><span>目标工程</span><select onChange={(event) => { setProjectId(event.target.value ? Number(event.target.value) : null); setExisting(null); }} value={projectId ?? ''}><option value="">请选择工程</option>{projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.project_name}（{project.character_count}）</option>)}</select></label>
      {existing ? <div className="character-duplicate-warning"><strong>该公共角色已添加过</strong><p>目标工程已有来源相同的有效副本“{existing.name}”。</p><div><SecondaryButton onClick={() => onCopied(existing)}>打开已有工程角色</SecondaryButton><PrimaryButton onClick={() => void copy(true)}>仍然创建新副本</PrimaryButton></div></div> : null}
    </LibraryDialog>
  );
}

const PUBLISH_FIELDS: Array<[string, string]> = [
  ['name', '名称'],
  ['aliases', '别名'],
  ['description', '简介'],
  ['identity', '身份'],
  ['age', '年龄'],
  ['setting_text', '设定'],
  ['relationship_notes', '人物关系'],
  ['personality', '性格'],
  ['speech_style', '语言风格'],
  ['action_constraints', '动作约束'],
  ['anti_ooc_rules', '反 OOC 规则'],
  ['profile', 'profile'],
  ['custom_fields', '自定义稳定信息'],
  ['tags', '标签'],
  ['cover', '封面'],
];

function PublishCharacterDialog({ card, onClose }: { card: CharacterCard; onClose: () => void }) {
  const baseline = (card.source_metadata.public_baseline as { stable_fields?: Record<string, unknown> } | undefined)?.stable_fields;
  const current = stableCardValues(card);
  const defaultFields = baseline
    ? PUBLISH_FIELDS.filter(([key]) => JSON.stringify(current[key]) !== JSON.stringify(baseline[key])).map(([key]) => key)
    : PUBLISH_FIELDS.map(([key]) => key);
  const [selectedFields, setSelectedFields] = useState(defaultFields);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function publish() {
    setBusy(true);
    try {
      const published = await publishProjectCharacterToPublic(card.id, selectedFields);
      setMessage(`已创建独立公共角色“${published.name}”。`);
    } catch (reason) {
      setMessage(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <LibraryDialog
      className="character-publish-dialog"
      footer={<><SecondaryButton onClick={onClose}>关闭</SecondaryButton><PrimaryButton disabled={busy || !selectedFields.includes('name')} onClick={() => void publish()}>保存为公共角色</PrimaryButton></>}
      onClose={onClose}
      subtitle="仅导出勾选的稳定字段"
      title="保存为公共角色"
    >
      {message ? <div className="inline-alert">{message}</div> : null}
      <p>将创建新的公共角色，不覆盖来源角色，也不会复制工程绑定、事实账本或场景人物状态。</p>
      <div className="character-publish-fields">{PUBLISH_FIELDS.map(([key, label]) => {
        const hasBaseline = Boolean(baseline);
        const changed = hasBaseline && JSON.stringify(current[key]) !== JSON.stringify(baseline?.[key]);
        const added = changed && (baseline?.[key] === '' || baseline?.[key] === null || baseline?.[key] === undefined);
        return <label key={key}><input checked={selectedFields.includes(key)} onChange={(event) => setSelectedFields(event.target.checked ? [...selectedFields, key] : selectedFields.filter((field) => field !== key))} type="checkbox" /><span>{label}</span><small>{!hasBaseline ? '工程角色字段' : added ? '工程中新增加' : changed ? '相对公共基线已修改' : '未变化'}</small></label>;
      })}</div>
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

function stableCardValues(card: CharacterCard): Record<string, unknown> {
  return {
    name: card.name,
    aliases: card.aliases,
    description: card.description,
    identity: card.identity,
    age: card.age,
    setting_text: card.setting_text,
    relationship_notes: card.relationship_notes,
    personality: card.personality,
    speech_style: card.speech_style,
    action_constraints: card.action_constraints,
    anti_ooc_rules: card.anti_ooc_rules,
    profile: card.profile,
    custom_fields: card.custom_fields,
    tags: card.tags,
    cover: card.cover_path,
  };
}

function truncateFileName(name: string) {
  return name.length <= 32 ? name : `${name.slice(0, 20)}…${name.slice(-9)}`;
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
