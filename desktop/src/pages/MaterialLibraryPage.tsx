import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  ArrowDown,
  ArrowUp,
  Boxes,
  Filter,
  FolderPlus,
  ListTree,
  Pencil,
  Plus,
  Search,
  Settings,
  Sparkles,
  Tag,
  Trash2,
  X,
} from 'lucide-react';
import {
  applyMaterialExtraction,
  assignMaterialCategory,
  assignMaterialTag,
  createMaterial,
  createMaterialCategory,
  createMaterialTag,
  deleteMaterial,
  deleteMaterialCategory,
  deleteMaterialTag,
  getMaterialAISettings,
  getMaterialCategories,
  getMaterials,
  getMaterialTags,
  getModels,
  previewMaterialExtraction,
  renameMaterialCategory,
  renameMaterialTag,
  resetMaterialAISettings,
  updateMaterial,
  updateMaterialAISettings,
} from '../api/client';
import type {
  AnalysisStatus,
  Material,
  MaterialAISettings,
  MaterialAITask,
  MaterialCategory,
  MaterialExtractionCandidate,
  MaterialExtractionPreview,
  MaterialTagGroup,
  MaterialType,
  ModelConfig,
  ResourceTag,
} from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { LibraryDialog, LibraryEmptyState, LibrarySidebarItem } from '../components/LibraryPrimitives';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

type MaterialLibrarySelection =
  | { materialType: MaterialType; kind: 'all' }
  | { materialType: MaterialType; kind: 'pending' }
  | { materialType: MaterialType; kind: 'category'; categoryId: number };

type MaterialQueryState = {
  query: string;
  activeTagId: number | null;
  analysisStatus: 'all' | AnalysisStatus;
  untaggedOnly: boolean;
};

type MaterialExtractionLaunch = {
  materialType: MaterialType;
  taskType?: MaterialAITask;
  selectedText: string;
  sourceMetadata: Record<string, unknown>;
};

const DEFAULT_QUERY: MaterialQueryState = {
  query: '',
  activeTagId: null,
  analysisStatus: 'all',
  untaggedOnly: false,
};

const MATERIAL_SECTIONS: Array<{ type: MaterialType; label: string; icon: ReactNode }> = [
  { type: 'plot_skeleton', label: '剧情骨架', icon: <ListTree size={16} /> },
  { type: 'scene_reference', label: '场景素材', icon: <Boxes size={16} /> },
];

const TASK_LABELS: Record<MaterialAITask, string> = {
  narrative_to_plot_skeleton: '叙事文本 → 剧情骨架',
  plot_text_to_normalized_skeleton: '剧情文本 → 规范骨架',
  source_text_to_scene_material: '来源文本 → 场景素材',
};

export function MaterialLibraryPage() {
  const [selection, setSelection] = useState<MaterialLibrarySelection>({
    materialType: 'plot_skeleton',
    kind: 'all',
  });
  const [queryState, setQueryState] = useState<MaterialQueryState>(DEFAULT_QUERY);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [categories, setCategories] = useState<MaterialCategory[]>([]);
  const [tags, setTags] = useState<ResourceTag[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Material | null>(null);
  const [newType, setNewType] = useState<MaterialType | null>(null);
  const [extractionLaunch, setExtractionLaunch] = useState<MaterialExtractionLaunch | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [assignmentManager, setAssignmentManager] = useState<{
    kind: 'tags' | 'categories';
    material: Material;
  } | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [categoryDialog, setCategoryDialog] = useState<{
    materialType: MaterialType;
    category?: MaterialCategory;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useAutoDismiss(message, setMessage);
  useAutoDismiss(error, setError, 5200);

  const load = useCallback(async (preferredId?: number | null) => {
    setLoading(true);
    try {
      const [materialItems, categoryItems, tagItems] = await Promise.all([
        getMaterials(),
        getMaterialCategories(),
        getMaterialTags(),
      ]);
      const normalizedMaterials = materialItems.map(normalizeMaterial);
      setMaterials(normalizedMaterials);
      setCategories(categoryItems);
      setTags(tagItems);
      setSelectedId((current) => {
        const requested = preferredId === undefined ? current : preferredId;
        return normalizedMaterials.some((item) => item.id === requested) ? requested : null;
      });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const launch = window.history.state?.materialExtraction as MaterialExtractionLaunch | undefined;
    if (!launch?.selectedText || !launch.materialType) return;
    setSelection({ materialType: launch.materialType, kind: 'all' });
    setExtractionLaunch(launch);
    setNewType(launch.materialType);
    window.history.replaceState(null, '', window.location.href);
  }, []);

  const activeTag = tags.find((tagItem) => tagItem.id === queryState.activeTagId) ?? null;
  const visible = useMemo(() => {
    const normalizedQuery = queryState.query.trim().toLocaleLowerCase();
    return materials.filter((material) => {
      if (material.material_type !== selection.materialType) return false;
      if (selection.kind === 'pending' && !isPendingImport(material)) return false;
      if (selection.kind === 'category' && !material.category_ids.includes(selection.categoryId)) return false;
      if (activeTag && !material.tags.includes(activeTag.name)) return false;
      if (queryState.analysisStatus !== 'all' && material.analysis_status !== queryState.analysisStatus) return false;
      if (queryState.untaggedOnly && material.tags.length > 0) return false;
      if (!normalizedQuery) return true;
      return [
        material.name,
        material.description,
        material.raw_text,
        material.categories.join(' '),
        material.tags.join(' '),
      ].join(' ').toLocaleLowerCase().includes(normalizedQuery);
    });
  }, [activeTag, materials, queryState, selection]);

  const selected = materials.find((item) => item.id === selectedId) ?? null;
  const counts = useMemo(() => ({
    plot_skeleton: materials.filter((item) => item.material_type === 'plot_skeleton').length,
    scene_reference: materials.filter((item) => item.material_type === 'scene_reference').length,
  }), [materials]);

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

  async function removeMaterial(material: Material) {
    if (!window.confirm(`确认删除素材“${material.name}”？`)) return;
    await runBusy(async () => {
      await deleteMaterial(material.id);
      await load(null);
      setMessage('素材已删除。');
    });
  }

  async function saveCategory(name: string) {
    if (!categoryDialog || !name.trim()) return;
    await runBusy(async () => {
      const item = categoryDialog.category
        ? await renameMaterialCategory(categoryDialog.category.id, name.trim())
        : await createMaterialCategory(categoryDialog.materialType, name.trim());
      setCategoryDialog(null);
      setSelection({ materialType: item.material_type, kind: 'category', categoryId: item.id });
      await load(selectedId);
    });
  }

  async function removeCategory(category: MaterialCategory) {
    if (!window.confirm('删除分类只解除分类关系，不会删除素材。确认继续？')) return;
    await runBusy(async () => {
      await deleteMaterialCategory(category.id);
      if (selection.kind === 'category' && selection.categoryId === category.id) {
        setSelection({ materialType: category.material_type, kind: 'all' });
      }
      await load(selectedId);
    });
  }

  const filterCount = Number(queryState.analysisStatus !== 'all')
    + Number(queryState.untaggedOnly)
    + Number(queryState.activeTagId !== null);

  return (
    <div className="document-library-page material-library-page">
      <TopBar
        title="素材库"
        actions={(
          <>
            <PrimaryButton disabled={busy} onClick={() => setNewType('plot_skeleton')}>
              <Plus size={16} />新建剧情骨架
            </PrimaryButton>
            <PrimaryButton disabled={busy} onClick={() => setNewType('scene_reference')}>
              <Plus size={16} />新建场景素材
            </PrimaryButton>
            <SecondaryButton aria-label="素材 AI 设置" disabled={busy} onClick={() => setSettingsOpen(true)}>
              <Settings size={16} />
            </SecondaryButton>
          </>
        )}
      />
      {error ? <div className="inline-alert error document-library-alert" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success document-library-alert" role="status">{message}</div> : null}

      <div className="document-library-layout material-browser-layout material-library-unified">
        <aside className="document-tag-panel material-library-sidebar">
          <nav aria-label="素材范围">
            {MATERIAL_SECTIONS.map((section) => {
              const sectionCategories = categories.filter((item) => item.material_type === section.type);
              return (
                <section className="material-sidebar-section" key={section.type}>
                  <div className="document-tag-heading"><span>{section.label}</span></div>
                  <LibrarySidebarItem
                    active={selection.materialType === section.type && selection.kind === 'all'}
                    count={counts[section.type]}
                    icon={section.icon}
                    label="全部内容"
                    onClick={() => setSelection({ materialType: section.type, kind: 'all' })}
                  />
                  <LibrarySidebarItem
                    active={selection.materialType === section.type && selection.kind === 'pending'}
                    count={materials.filter((item) => item.material_type === section.type && isPendingImport(item)).length}
                    icon={<Sparkles size={16} />}
                    label="最近导入"
                    onClick={() => setSelection({ materialType: section.type, kind: 'pending' })}
                  />
                  <div className="document-tag-heading material-category-heading">
                    <span>我的分类</span>
                    <button
                      aria-label={`新建${section.label}分类`}
                      className="document-add-tag"
                      onClick={() => setCategoryDialog({ materialType: section.type })}
                      type="button"
                    >
                      <FolderPlus size={14} />
                    </button>
                  </div>
                  {sectionCategories.map((category) => (
                    <div className="library-tag-row material-category-row" key={category.id}>
                      <LibrarySidebarItem
                        active={selection.kind === 'category' && selection.categoryId === category.id}
                        count={category.resource_count}
                        icon={<Tag size={15} />}
                        label={category.name}
                        onClick={() => setSelection({
                          materialType: section.type,
                          kind: 'category',
                          categoryId: category.id,
                        })}
                      />
                      <button aria-label={`重命名分类 ${category.name}`} onClick={() => setCategoryDialog({ materialType: section.type, category })} type="button"><Pencil size={12} /></button>
                      <button aria-label={`删除分类 ${category.name}`} onClick={() => void removeCategory(category)} type="button"><Trash2 size={12} /></button>
                    </div>
                  ))}
                </section>
              );
            })}
          </nav>
        </aside>

        <main className="document-shelf-panel material-browser-shelf">
          <header>
            <div className="document-shelf-tools material-shelf-tools">
              <label className="search-field document-search">
                <Search size={15} />
                <span className="sr-only">搜索素材</span>
                <input
                  onChange={(event) => setQueryState((current) => ({ ...current, query: event.target.value }))}
                  placeholder="搜索名称、摘要、来源或标签"
                  type="search"
                  value={queryState.query}
                />
              </label>
              <div className="material-filter-anchor">
                <SecondaryButton aria-expanded={filterOpen} onClick={() => setFilterOpen((value) => !value)}>
                  <Filter size={15} />筛选{filterCount ? ` ${filterCount}` : ''}
                </SecondaryButton>
                {filterOpen ? (
                  <MaterialFilterPopover
                    queryState={queryState}
                    onChange={setQueryState}
                    onClose={() => setFilterOpen(false)}
                  />
                ) : null}
              </div>
            </div>
            <div className="material-filter-chips">
              {activeTag ? (
                <button onClick={() => setQueryState((current) => ({ ...current, activeTagId: null }))} type="button">
                  标签：{activeTag.name}<X size={12} />
                </button>
              ) : null}
              {queryState.analysisStatus !== 'all' ? (
                <button onClick={() => setQueryState((current) => ({ ...current, analysisStatus: 'all' }))} type="button">
                  {queryState.analysisStatus === 'analyzed' ? '已分析' : '未分析'}<X size={12} />
                </button>
              ) : null}
              {queryState.untaggedOnly ? (
                <button onClick={() => setQueryState((current) => ({ ...current, untaggedOnly: false }))} type="button">
                  仅无标签<X size={12} />
                </button>
              ) : null}
            </div>
          </header>
          {loading ? <LibraryEmptyState title="正在读取素材库…" /> : visible.length ? (
            <div className="document-shelf-scroll resource-list-scroll">
              <div aria-label="素材条目" className="resource-row-list">
                {visible.map((material) => (
                  <button
                    aria-pressed={selectedId === material.id}
                    className={`resource-list-row material-resource-row ${selectedId === material.id ? 'selected' : ''}`}
                    key={material.id}
                    onClick={() => setSelectedId(material.id)}
                    onDoubleClick={() => setEditing(material)}
                    type="button"
                  >
                    <strong className="resource-row-name">{material.name}</strong>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <LibraryEmptyState
              action={<PrimaryButton onClick={() => setNewType(selection.materialType)}><Plus size={16} />新建素材</PrimaryButton>}
              description="可手动创建、保存来源，或先由 AI 生成候选再确认。"
              title="当前范围暂无素材"
            />
          )}
        </main>

        <aside className="document-detail-panel material-detail-panel material-summary-panel">
          <header><h2>素材详情</h2></header>
          {selected ? (
            <>
              <div className="document-detail-scroll">
                <section className="material-detail-identity">
                  <h3>{selected.name}</h3>
                  <p>{typeLabel(selected.material_type)}</p>
                  <div className="document-detail-badges">
                    <span>{selected.analysis_status === 'analyzed' ? '已分析' : '未分析'}</span>
                  </div>
                </section>
                <SummarySection label="来源">
                  <p className="material-detail-copy">{selected.source_summary.label}</p>
                </SummarySection>
                <SummarySection label="内容摘要">
                  <p className="material-detail-copy material-clamped-summary">
                    {selected.description || contentSummary(selected.content) || selected.raw_text || '尚未填写摘要'}
                  </p>
                </SummarySection>
                <SummarySection label="所属分类" action={<button aria-label="管理素材分类" onClick={() => setAssignmentManager({ kind: 'categories', material: selected })} type="button"><Plus size={13} /></button>}>
                  <div className="document-detail-badges material-clickable-chips">
                    {selected.categories.length
                      ? selected.categories.map((name, index) => (
                        <button
                          key={`${name}-${selected.category_ids[index]}`}
                          onClick={() => setSelection({
                            materialType: selected.material_type,
                            kind: 'category',
                            categoryId: selected.category_ids[index],
                          })}
                          type="button"
                        >
                          {name}
                        </button>
                      ))
                      : <span>未分类</span>}
                  </div>
                </SummarySection>
                <SummarySection label="通用标签" action={<button aria-label="管理素材标签" onClick={() => setAssignmentManager({ kind: 'tags', material: selected })} type="button"><Plus size={13} /></button>}>
                  <TagChips
                    activeTagName={activeTag?.name ?? null}
                    names={selected.general_tags}
                    onClick={(name) => {
                      const tagItem = tags.find((item) => item.name === name && (item.tag_group ?? 'general') === 'general');
                      if (tagItem) setQueryState((current) => ({
                        ...current,
                        activeTagId: current.activeTagId === tagItem.id ? null : tagItem.id,
                      }));
                    }}
                  />
                </SummarySection>
                <SummarySection label="适用场景" action={<button aria-label="管理适用场景标签" onClick={() => setAssignmentManager({ kind: 'tags', material: selected })} type="button"><Plus size={13} /></button>}>
                  <TagChips
                    activeTagName={activeTag?.name ?? null}
                    names={selected.applicable_scene_tags}
                    onClick={(name) => {
                      const tagItem = tags.find((item) => item.name === name && item.tag_group === 'applicable_scene');
                      if (tagItem) setQueryState((current) => ({
                        ...current,
                        activeTagId: current.activeTagId === tagItem.id ? null : tagItem.id,
                      }));
                    }}
                  />
                </SummarySection>
              </div>
              <footer className="library-detail-footer material-detail-footer">
                <SecondaryButton disabled={busy} onClick={() => setEditing(selected)}><Pencil size={15} />编辑</SecondaryButton>
                <DangerButton disabled={busy} onClick={() => void removeMaterial(selected)}><Trash2 size={15} />删除</DangerButton>
              </footer>
            </>
          ) : <LibraryEmptyState description="选择中央素材卡后查看摘要、分类和标签。" title="选择一个素材" />}
        </aside>
      </div>

      {newType ? (
        <NewMaterialWorkflow
          busy={busy}
          categories={categories.filter((item) => item.material_type === newType)}
          initialLaunch={extractionLaunch?.materialType === newType ? extractionLaunch : null}
          materialType={newType}
          tags={tags}
          onClose={() => {
            setNewType(null);
            setExtractionLaunch(null);
          }}
          onCreate={async (payload) => {
            await runBusy(async () => {
              const created = await createMaterial(payload);
              setNewType(null);
              setExtractionLaunch(null);
              setSelection({ materialType: created.material_type, kind: 'all' });
              await load(created.id);
              if (created.analysis_status === 'analyzed') setEditing(created);
              setMessage(created.analysis_status === 'analyzed' ? '素材已创建。' : '来源已保存到最近导入。');
            });
          }}
          onApply={async (preview, candidates) => {
            await runBusy(async () => {
              const result = await applyMaterialExtraction({
                preview_token: preview.preview_token,
                candidates,
                selected_candidate_ids: candidates.filter((item) => item.selected).map((item) => item.candidate_id),
              });
              if (result.errors.length) {
                setError(result.errors.map((item) => item.error).filter(Boolean).join('；'));
                return;
              }
              const selectedCount = candidates.filter((item) => item.selected).length;
              if (result.created.length !== selectedCount || result.created.length === 0) {
                setError('素材创建未全部成功，请修改候选后重试。');
                return;
              }
              setNewType(null);
              setExtractionLaunch(null);
              await load(result.created[0]?.material_id ?? null);
              setMessage(`已创建 ${result.created.length} 条素材。`);
            });
          }}
          onError={setError}
        />
      ) : null}
      {editing ? (
        <MaterialEditor
          busy={busy}
          categories={categories.filter((item) => item.material_type === editing.material_type)}
          material={editing}
          tags={tags}
          onClose={() => setEditing(null)}
          onSave={async (payload) => {
            await runBusy(async () => {
              const updated = await updateMaterial(editing.id, payload);
              setEditing(null);
              await load(updated.id);
              setMessage('素材已保存。');
            });
          }}
        />
      ) : null}
      {settingsOpen ? (
        <MaterialSettingsDialog busy={busy} onClose={() => setSettingsOpen(false)} onError={setError} />
      ) : null}
      {categoryDialog ? (
        <NameDialog
          busy={busy}
          initialName={categoryDialog.category?.name ?? ''}
          onClose={() => setCategoryDialog(null)}
          onSave={saveCategory}
          title={categoryDialog.category ? '重命名素材分类' : '新建素材分类'}
        />
      ) : null}
      {assignmentManager ? (
        <MaterialAssignmentDialog
          busy={busy}
          categories={categories.filter((item) => item.material_type === assignmentManager.material.material_type)}
          kind={assignmentManager.kind}
          material={assignmentManager.material}
          tags={tags}
          onClose={() => setAssignmentManager(null)}
          onError={setError}
          onSaved={async () => {
            const id = assignmentManager.material.id;
            setAssignmentManager(null);
            await load(id);
            setMessage('素材关系已更新。');
          }}
        />
      ) : null}
    </div>
  );
}

function MaterialFilterPopover({
  onChange,
  onClose,
  queryState,
}: {
  onChange: (value: MaterialQueryState) => void;
  onClose: () => void;
  queryState: MaterialQueryState;
}) {
  return (
    <div className="material-filter-popover">
      <div className="document-detail-heading"><span>分析状态</span></div>
      <div className="material-filter-options">
        {([
          ['all', '全部'],
          ['unanalyzed', '未分析'],
          ['analyzed', '已分析'],
        ] as const).map(([value, label]) => (
          <button
            aria-pressed={queryState.analysisStatus === value}
            key={value}
            onClick={() => onChange({ ...queryState, analysisStatus: value })}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>
      <label className="material-filter-check">
        <input
          checked={queryState.untaggedOnly}
          onChange={(event) => onChange({ ...queryState, untaggedOnly: event.target.checked })}
          type="checkbox"
        />
        仅无标签
      </label>
      <SecondaryButton onClick={onClose}>完成</SecondaryButton>
    </div>
  );
}

function NewMaterialWorkflow({
  busy,
  categories,
  initialLaunch,
  materialType,
  onApply,
  onClose,
  onCreate,
  onError,
  tags,
}: {
  busy: boolean;
  categories: MaterialCategory[];
  initialLaunch: MaterialExtractionLaunch | null;
  materialType: MaterialType;
  onApply: (preview: MaterialExtractionPreview, candidates: MaterialExtractionCandidate[]) => Promise<void>;
  onClose: () => void;
  onCreate: (payload: Parameters<typeof createMaterial>[0]) => Promise<void>;
  onError: (value: string) => void;
  tags: ResourceTag[];
}) {
  const [mode, setMode] = useState<'manual' | 'source'>(initialLaunch ? 'source' : 'manual');
  const [name, setName] = useState('');
  const [text, setText] = useState(initialLaunch?.selectedText ?? '');
  const [fileName, setFileName] = useState('');
  const [sourceMode, setSourceMode] = useState<'paste' | 'file' | 'selection'>(
    initialLaunch ? 'selection' : 'paste',
  );
  const [taskType, setTaskType] = useState<MaterialAITask>(
    initialLaunch?.taskType
      ?? (materialType === 'scene_reference' ? 'source_text_to_scene_material' : 'narrative_to_plot_skeleton'),
  );
  const [preview, setPreview] = useState<MaterialExtractionPreview | null>(null);
  const [candidates, setCandidates] = useState<MaterialExtractionCandidate[]>([]);

  async function generatePreview() {
    if (!text.trim()) {
      onError('请先填写来源文本。');
      return;
    }
    try {
      const value = await previewMaterialExtraction({
        task_type: taskType,
        name: name.trim() || null,
        sample_text: text,
        source_metadata: initialLaunch?.sourceMetadata ?? (
          sourceMode === 'file'
            ? { source_kind: 'file_import', source_type: 'file', file_name: fileName }
            : { source_kind: 'pasted_text', source_type: 'paste' }
        ),
      });
      setPreview(value);
      setCandidates(value.candidates.map((item) => ({
        ...item,
        confirmed_general_tags: [],
        confirmed_applicable_scene_tags: [],
        category_ids: [],
      })));
    } catch (reason) {
      onError(errorMessage(reason));
    }
  }

  const footer = preview ? (
    <>
      <SecondaryButton disabled={busy} onClick={() => setPreview(null)}>返回来源</SecondaryButton>
      <PrimaryButton
        disabled={busy || !candidates.some((item) => item.selected && item.name.trim())}
        onClick={() => void onApply(preview, candidates)}
      >
        确认创建
      </PrimaryButton>
    </>
  ) : (
    <>
      <SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton>
      {mode === 'manual' ? (
        <PrimaryButton
          disabled={busy || !name.trim()}
          onClick={() => void onCreate({
            material_type: materialType,
            scope: 'public',
            name: name.trim(),
            description: '',
            raw_text: '',
            content: {},
            analysis_status: 'analyzed',
            tag_ids: [],
            category_ids: [],
          })}
        >
          创建并编辑
        </PrimaryButton>
      ) : (
        <>
          <SecondaryButton
            disabled={busy || !name.trim() || !text.trim()}
            onClick={() => void onCreate({
              material_type: materialType,
              scope: 'public',
              name: name.trim(),
              description: '',
              raw_text: text,
              content: {},
              analysis_status: 'unanalyzed',
              source_metadata: initialLaunch?.sourceMetadata ?? (
                sourceMode === 'file'
                  ? { source_kind: 'file_import', source_type: 'file', file_name: fileName }
                  : { source_kind: 'pasted_text', source_type: 'paste' }
              ),
              import_metadata: { created_by: 'pending_material_import' },
              tag_ids: [],
              category_ids: [],
            })}
          >
            仅保存来源
          </SecondaryButton>
          <PrimaryButton disabled={busy || !text.trim()} onClick={() => void generatePreview()}>
            <Sparkles size={15} />生成候选
          </PrimaryButton>
        </>
      )}
    </>
  );

  return (
    <LibraryDialog
      bodyClassName="material-workflow-body"
      className="material-workflow-dialog"
      closeOnBackdrop={!busy}
      footer={footer}
      onClose={onClose}
      subtitle={typeLabel(materialType)}
      title={preview ? '确认候选素材' : `新建${typeLabel(materialType)}`}
    >
      {!preview ? (
        <>
          <div className="material-workflow-tabs" role="tablist">
            <button aria-selected={mode === 'manual'} onClick={() => setMode('manual')} role="tab" type="button">手动创建</button>
            <button aria-selected={mode === 'source'} onClick={() => setMode('source')} role="tab" type="button">从来源整理</button>
          </div>
          <div className="library-form-grid material-create-form">
            <Field label={`素材名称${mode === 'source' ? '（可选）' : ''}`}>
              <input onChange={(event) => setName(event.target.value)} value={name} />
            </Field>
            {mode === 'source' && materialType === 'plot_skeleton' ? (
              <Field label="整理任务">
                <select onChange={(event) => setTaskType(event.target.value as MaterialAITask)} value={taskType}>
                  <option value="narrative_to_plot_skeleton">叙事文本 → 剧情骨架</option>
                  <option value="plot_text_to_normalized_skeleton">剧情文本 → 规范骨架</option>
                </select>
              </Field>
            ) : null}
            {mode === 'source' ? (
              <div className="wide material-source-field">
                <span>来源文本</span>
                <div className="material-source-options">
                  <button aria-pressed={sourceMode === 'paste'} onClick={() => { setSourceMode('paste'); setFileName(''); }} type="button">粘贴文本</button>
                  <label>
                    文件
                    <input
                      accept=".txt,.md,text/plain,text/markdown"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (!file) return;
                        if (file.size > 5 * 1024 * 1024) {
                          onError('来源文件不能超过 5 MB。');
                          return;
                        }
                        void file.text().then((value) => {
                          if (value.length > 50000) {
                            onError('来源文本不能超过 50,000 字符。');
                            return;
                          }
                          setText(value);
                          setFileName(file.name);
                          setSourceMode('file');
                        });
                      }}
                      type="file"
                    />
                  </label>
                  {sourceMode === 'selection' ? <span>文档/工程选区</span> : null}
                  {fileName ? <small title={fileName}>{fileName}</small> : null}
                </div>
                <textarea
                  aria-label="来源文本"
                  className="material-source-textarea"
                  maxLength={50000}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="粘贴文本，或从文档选区进入此流程"
                  value={text}
                />
              </div>
            ) : (
              <p className="wide material-form-hint">手动创建不调用 AI，创建后使用结构化编辑器补充内容。</p>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="inline-alert" role="status">来源：{preview.source_summary.label}</div>
          <CandidateEditor
            candidates={candidates}
            categories={categories}
            onChange={setCandidates}
            tags={tags}
          />
        </>
      )}
    </LibraryDialog>
  );
}

function CandidateEditor({
  candidates,
  categories,
  onChange,
  tags,
}: {
  candidates: MaterialExtractionCandidate[];
  categories: MaterialCategory[];
  onChange: (value: MaterialExtractionCandidate[]) => void;
  tags: ResourceTag[];
}) {
  const patch = (candidateId: string, value: Partial<MaterialExtractionCandidate>) => {
    onChange(candidates.map((item) => item.candidate_id === candidateId ? { ...item, ...value } : item));
  };
  return (
    <div className="material-candidate-list">
      {candidates.map((candidate, index) => (
        <section className={`material-candidate-card ${candidate.selected ? '' : 'disabled'}`} key={candidate.candidate_id}>
          <header>
            <label>
              <input checked={candidate.selected} onChange={(event) => patch(candidate.candidate_id, { selected: event.target.checked })} type="checkbox" />
              候选 {index + 1}
            </label>
            <span>{candidate.evidence_summary || '模型未提供证据摘要'}</span>
          </header>
          <Field label="名称">
            <input value={candidate.name} onChange={(event) => patch(candidate.candidate_id, { name: event.target.value })} />
          </Field>
          <Field label="摘要">
            <textarea value={candidate.description} onChange={(event) => patch(candidate.candidate_id, { description: event.target.value })} />
          </Field>
          <StructuredContentEditor
            content={candidate.content}
            materialType={candidate.material_type}
            onChange={(content) => patch(candidate.candidate_id, { content })}
          />
          <CandidateTags
            candidate={candidate}
            group="general"
            tags={tags}
            onChange={(names) => patch(candidate.candidate_id, { confirmed_general_tags: names })}
          />
          <CandidateTags
            candidate={candidate}
            group="applicable_scene"
            tags={tags}
            onChange={(names) => patch(candidate.candidate_id, { confirmed_applicable_scene_tags: names })}
          />
          <fieldset className="library-tag-picker">
            <legend>分类</legend>
            <div>{categories.map((category) => (
              <label key={category.id}>
                <input
                  checked={(candidate.category_ids ?? []).includes(category.id)}
                  onChange={(event) => patch(candidate.candidate_id, {
                    category_ids: event.target.checked
                      ? [...(candidate.category_ids ?? []), category.id]
                      : (candidate.category_ids ?? []).filter((id) => id !== category.id),
                  })}
                  type="checkbox"
                />
                {category.name}
              </label>
            ))}</div>
          </fieldset>
        </section>
      ))}
    </div>
  );
}

function CandidateTags({
  candidate,
  group,
  onChange,
  tags,
}: {
  candidate: MaterialExtractionCandidate;
  group: MaterialTagGroup;
  onChange: (names: string[]) => void;
  tags: ResourceTag[];
}) {
  const suggested = group === 'general'
    ? candidate.suggested_general_tags
    : candidate.suggested_applicable_scene_tags;
  const confirmed = group === 'general'
    ? candidate.confirmed_general_tags ?? []
    : candidate.confirmed_applicable_scene_tags ?? [];
  const available = Array.from(new Set([
    ...suggested,
    ...tags.filter((item) => (item.tag_group ?? 'general') === group).map((item) => item.name),
  ]));
  return (
    <fieldset className="library-tag-picker">
      <legend>{group === 'general' ? '通用标签建议（确认后才创建）' : '适用场景标签建议（确认后才创建）'}</legend>
      <div>{available.map((name) => (
        <label key={name}>
          <input
            checked={confirmed.includes(name)}
            onChange={(event) => onChange(
              event.target.checked ? [...confirmed, name] : confirmed.filter((item) => item !== name),
            )}
            type="checkbox"
          />
          {name}
        </label>
      ))}</div>
    </fieldset>
  );
}

function MaterialEditor({
  busy,
  categories,
  material,
  onClose,
  onSave,
  tags,
}: {
  busy: boolean;
  categories: MaterialCategory[];
  material: Material;
  onClose: () => void;
  onSave: (payload: Parameters<typeof updateMaterial>[1]) => Promise<void>;
  tags: ResourceTag[];
}) {
  const [name, setName] = useState(material.name);
  const [description, setDescription] = useState(material.description);
  const [rawText, setRawText] = useState(material.raw_text);
  const [content, setContent] = useState(material.content);
  const [tagIds, setTagIds] = useState(() => tags.filter((tagItem) => material.tags.includes(tagItem.name)).map((tagItem) => tagItem.id));
  const [categoryIds, setCategoryIds] = useState(material.category_ids);
  const [rawChanged, setRawChanged] = useState(false);

  const save = () => onSave({
    name: name.trim(),
    description,
    detail_level: material.detail_level,
    raw_text: rawText,
    content,
    analysis_status: rawChanged ? 'unanalyzed' : material.analysis_status,
    timeline_start_chapter: material.timeline_start_chapter,
    timeline_end_chapter: material.timeline_end_chapter,
    sort_order: material.sort_order,
    tag_ids: tagIds,
    category_ids: categoryIds,
  });

  return (
    <LibraryDialog
      bodyClassName="material-editor-body"
      className="material-editor-dialog"
      footer={(
        <>
          <SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton>
          <PrimaryButton disabled={busy || !name.trim()} onClick={() => void save()}>保存</PrimaryButton>
        </>
      )}
      onClose={onClose}
      subtitle={typeLabel(material.material_type)}
      title="编辑素材"
    >
      <div className="library-form-grid material-editor-basics">
        <Field label="素材名称"><input value={name} onChange={(event) => setName(event.target.value)} /></Field>
        <Field label="摘要"><input value={description} onChange={(event) => setDescription(event.target.value)} /></Field>
        <Field className="wide" label="原始来源">
          <textarea
            className="material-source-textarea"
            value={rawText}
            onChange={(event) => {
              setRawText(event.target.value);
              setRawChanged(event.target.value !== material.raw_text);
            }}
          />
        </Field>
      </div>
      {material.analysis_status === 'unanalyzed' || rawChanged ? (
        <div className="material-pending-notice">
          <div><Sparkles size={18} /><span>来源尚未整理；修改来源后也会重新标记为未分析。</span></div>
          <small>可先保存来源，再从素材详情重新进入整理流程。</small>
        </div>
      ) : (
        <StructuredContentEditor content={content} materialType={material.material_type} onChange={setContent} />
      )}
      <div className="material-editor-resources">
        <fieldset className="library-tag-picker">
          <legend>我的分类</legend>
          <div>{categories.length ? categories.map((category) => (
            <label key={category.id}>
              <input
                checked={categoryIds.includes(category.id)}
                onChange={(event) => setCategoryIds(event.target.checked
                  ? [...categoryIds, category.id]
                  : categoryIds.filter((id) => id !== category.id))}
                type="checkbox"
              />
              {category.name}
            </label>
          )) : <span>尚未创建分类</span>}</div>
        </fieldset>
        <fieldset className="library-tag-picker">
          <legend>素材标签</legend>
          <div>{tags.length ? tags.map((tagItem) => (
            <label key={tagItem.id}>
              <input
                checked={tagIds.includes(tagItem.id)}
                onChange={(event) => setTagIds(event.target.checked
                  ? [...tagIds, tagItem.id]
                  : tagIds.filter((id) => id !== tagItem.id))}
                type="checkbox"
              />
              {tagItem.name}<small>{tagItem.tag_group === 'applicable_scene' ? ' · 适用场景' : ''}</small>
            </label>
          )) : <span>尚未创建素材标签</span>}</div>
        </fieldset>
      </div>
    </LibraryDialog>
  );
}

function StructuredContentEditor({
  content,
  materialType,
  onChange,
}: {
  content: Record<string, unknown>;
  materialType: MaterialType;
  onChange: (value: Record<string, unknown>) => void;
}) {
  const scalarKey = materialType === 'plot_skeleton' ? 'premise' : 'summary';
  const listKeys = materialType === 'plot_skeleton'
    ? ['stages', 'conflicts', 'turning_points', 'hooks']
    : ['key_beats', 'actions', 'environment', 'sensory', 'writing_guidance', 'source_cues', 'avoidances', 'applicable_conditions'];
  return (
    <section className="material-structured-editor">
      <h3>结构化内容</h3>
      <Field label={humanizeKey(scalarKey)}>
        <textarea
          value={String(content[scalarKey] ?? '')}
          onChange={(event) => onChange({ ...content, [scalarKey]: event.target.value })}
        />
      </Field>
      {listKeys.map((key) => {
        const items = structuredItems(content[key], key);
        return (
          <div className="material-structured-section" key={key}>
            <div className="section-heading">
              <strong>{humanizeKey(key)}</strong>
              <button
                onClick={() => onChange({
                  ...content,
                  [key]: [...items, { id: `${key}-${crypto.randomUUID()}`, summary: '' }],
                })}
                type="button"
              >
                <Plus size={14} />添加
              </button>
            </div>
            {items.map((item, index) => (
              <div className="material-structured-row" key={item.id}>
                <StructuredItemFields
                  item={item}
                  label={`${humanizeKey(key)} ${index + 1}`}
                  materialType={materialType}
                  onChange={(value) => onChange({
                    ...content,
                    [key]: items.map((current) => current.id === item.id ? value : current),
                  })}
                />
                <button
                  aria-label="上移"
                  disabled={index === 0}
                  onClick={() => onChange({ ...content, [key]: moveItem(items, index, index - 1) })}
                  type="button"
                ><ArrowUp size={14} /></button>
                <button
                  aria-label="下移"
                  disabled={index === items.length - 1}
                  onClick={() => onChange({ ...content, [key]: moveItem(items, index, index + 1) })}
                  type="button"
                ><ArrowDown size={14} /></button>
                <button
                  aria-label="删除"
                  className="danger"
                  onClick={() => onChange({ ...content, [key]: items.filter((current) => current.id !== item.id) })}
                  type="button"
                ><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
        );
      })}
      {materialType === 'plot_skeleton' ? (['climax', 'resolution'] as const).map((key) => {
        const value = content[key];
        const objectValue = value && typeof value === 'object' ? value as Record<string, unknown> : {};
        return (
          <div className="material-structured-section" key={key}>
            <strong>{key === 'climax' ? '高潮' : '结局'}</strong>
            <StructuredItemFields
              item={{
                ...objectValue,
                id: String(objectValue.id ?? key),
                summary: String(objectValue.summary ?? value ?? ''),
              }}
              label={key === 'climax' ? '高潮' : '结局'}
              materialType={materialType}
              onChange={(next) => onChange({
                ...content,
                [key]: next,
              })}
            />
          </div>
        );
      }) : null}
    </section>
  );
}

const PLOT_ITEM_ARRAY_FIELDS = [
  'causes',
  'effects',
  'characters',
  'locations',
  'must_keep_details',
  'forbidden_changes',
] as const;

function StructuredItemFields({
  item,
  label,
  materialType,
  onChange,
}: {
  item: { id: string; summary: string; [key: string]: unknown };
  label: string;
  materialType: MaterialType;
  onChange: (value: { id: string; summary: string; [key: string]: unknown }) => void;
}) {
  const patch = (value: Record<string, unknown>) => onChange({ ...item, ...value });
  return (
    <div className="material-structured-fields">
      <label>
        <span>标题或名称</span>
        <input
          aria-label={`${label} 标题`}
          value={String(item.title ?? '')}
          onChange={(event) => patch({ title: event.target.value })}
        />
      </label>
      <label>
        <span>摘要或正文</span>
        <textarea
          aria-label={label}
          value={item.summary}
          onChange={(event) => patch({ summary: event.target.value })}
        />
      </label>
      <label>
        <span>证据或来源提示</span>
        <textarea
          aria-label={`${label} 证据`}
          value={String(item.evidence_summary ?? item.source_hint ?? '')}
          onChange={(event) => patch({ evidence_summary: event.target.value })}
        />
      </label>
      {materialType === 'plot_skeleton' ? PLOT_ITEM_ARRAY_FIELDS.map((field) => (
        <label key={field}>
          <span>{humanizeKey(field)}（每行一项）</span>
          <textarea
            aria-label={`${label} ${humanizeKey(field)}`}
            value={stringArray(item[field]).join('\n')}
            onChange={(event) => patch({
              [field]: event.target.value.split('\n').map((value) => value.trim()).filter(Boolean),
            })}
          />
        </label>
      )) : null}
    </div>
  );
}

function MaterialAssignmentDialog({
  busy,
  categories,
  kind,
  material,
  onClose,
  onError,
  onSaved,
  tags,
}: {
  busy: boolean;
  categories: MaterialCategory[];
  kind: 'tags' | 'categories';
  material: Material;
  onClose: () => void;
  onError: (value: string) => void;
  onSaved: () => Promise<void>;
  tags: ResourceTag[];
}) {
  const [localTags, setLocalTags] = useState(tags);
  const [localCategories, setLocalCategories] = useState(categories);
  const [selectedTagIds, setSelectedTagIds] = useState(
    tags.filter((item) => material.tags.includes(item.name)).map((item) => item.id),
  );
  const [selectedCategoryIds, setSelectedCategoryIds] = useState(material.category_ids);
  const [newName, setNewName] = useState('');
  const [newGroup, setNewGroup] = useState<MaterialTagGroup>('general');

  async function createItem() {
    if (!newName.trim()) return;
    try {
      if (kind === 'tags') {
        const created = await createMaterialTag(newName.trim(), newGroup);
        setLocalTags((items) => [...items, created]);
        setSelectedTagIds((items) => [...items, created.id]);
      } else {
        const created = await createMaterialCategory(material.material_type, newName.trim());
        setLocalCategories((items) => [...items, created]);
        setSelectedCategoryIds((items) => [...items, created.id]);
      }
      setNewName('');
    } catch (reason) {
      onError(errorMessage(reason));
    }
  }

  async function renameItem(item: ResourceTag | MaterialCategory) {
    const name = window.prompt('新名称', item.name)?.trim();
    if (!name) return;
    try {
      if (kind === 'tags') {
        const renamed = await renameMaterialTag(item.id, name);
        setLocalTags((items) => items.map((current) => current.id === item.id ? renamed : current));
      } else {
        const renamed = await renameMaterialCategory(item.id, name);
        setLocalCategories((items) => items.map((current) => current.id === item.id ? renamed : current));
      }
    } catch (reason) {
      onError(errorMessage(reason));
    }
  }

  async function removeItem(item: ResourceTag | MaterialCategory) {
    if (!window.confirm(kind === 'tags'
      ? '删除标签只解除关联，不会删除素材。确认继续？'
      : '删除分类只解除分类关系，不会删除素材。确认继续？')) return;
    try {
      if (kind === 'tags') {
        await deleteMaterialTag(item.id);
        setLocalTags((items) => items.filter((current) => current.id !== item.id));
        setSelectedTagIds((items) => items.filter((id) => id !== item.id));
      } else {
        await deleteMaterialCategory(item.id);
        setLocalCategories((items) => items.filter((current) => current.id !== item.id));
        setSelectedCategoryIds((items) => items.filter((id) => id !== item.id));
      }
    } catch (reason) {
      onError(errorMessage(reason));
    }
  }

  async function save() {
    try {
      if (kind === 'tags') {
        await Promise.all(localTags.map((item) => assignMaterialTag(
          material.id,
          item.id,
          selectedTagIds.includes(item.id),
        )));
      } else {
        await Promise.all(localCategories.map((item) => assignMaterialCategory(
          material.id,
          item.id,
          selectedCategoryIds.includes(item.id),
        )));
      }
      await onSaved();
    } catch (reason) {
      onError(errorMessage(reason));
    }
  }

  const items = kind === 'tags' ? localTags : localCategories;
  return (
    <LibraryDialog
      className="material-assignment-dialog"
      footer={(
        <>
          <SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>保存关联</PrimaryButton>
        </>
      )}
      onClose={onClose}
      title={kind === 'tags' ? '管理素材标签' : '管理素材分类'}
    >
      <div className="material-assignment-create">
        <input placeholder={kind === 'tags' ? '新标签名称' : '新分类名称'} value={newName} onChange={(event) => setNewName(event.target.value)} />
        {kind === 'tags' ? (
          <select value={newGroup} onChange={(event) => setNewGroup(event.target.value as MaterialTagGroup)}>
            <option value="general">通用标签</option>
            <option value="applicable_scene">适用场景</option>
          </select>
        ) : null}
        <SecondaryButton disabled={!newName.trim()} onClick={() => void createItem()}><Plus size={14} />创建</SecondaryButton>
      </div>
      <div className="material-assignment-list">
        {items.length ? items.map((item) => {
          const selected = kind === 'tags'
            ? selectedTagIds.includes(item.id)
            : selectedCategoryIds.includes(item.id);
          return (
            <div key={item.id}>
              <label>
                <input
                  checked={selected}
                  onChange={(event) => {
                    if (kind === 'tags') {
                      setSelectedTagIds((current) => event.target.checked
                        ? [...current, item.id]
                        : current.filter((id) => id !== item.id));
                    } else {
                      setSelectedCategoryIds((current) => event.target.checked
                        ? [...current, item.id]
                        : current.filter((id) => id !== item.id));
                    }
                  }}
                  type="checkbox"
                />
                <span>{item.name}</span>
                {kind === 'tags' ? <small>{(item as ResourceTag).tag_group === 'applicable_scene' ? '适用场景' : '通用'}</small> : null}
              </label>
              <button aria-label={`重命名 ${item.name}`} onClick={() => void renameItem(item)} type="button"><Pencil size={13} /></button>
              <button aria-label={`删除 ${item.name}`} className="danger" onClick={() => void removeItem(item)} type="button"><Trash2 size={13} /></button>
            </div>
          );
        }) : <p>尚未创建可用项目。</p>}
      </div>
    </LibraryDialog>
  );
}

function MaterialSettingsDialog({
  busy,
  onClose,
  onError,
}: {
  busy: boolean;
  onClose: () => void;
  onError: (value: string) => void;
}) {
  const [settings, setSettings] = useState<MaterialAISettings[]>([]);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [task, setTask] = useState<MaterialAITask>('narrative_to_plot_skeleton');
  useEffect(() => {
    void Promise.all([getMaterialAISettings(), getModels()])
      .then(([value, modelItems]) => {
        setSettings(value as MaterialAISettings[]);
        setModels(modelItems);
      })
      .catch((reason) => onError(errorMessage(reason)));
  }, [onError]);
  const current = settings.find((item) => item.task_type === task) ?? null;
  const patch = (value: Partial<MaterialAISettings>) => setSettings((items) => items.map((item) => item.task_type === task ? { ...item, ...value } : item));
  return (
    <LibraryDialog
      bodyClassName="material-settings-body"
      className="material-settings-dialog"
      footer={(
        <>
          <SecondaryButton disabled={busy || !current} onClick={() => {
            void resetMaterialAISettings(task).then((value) => setSettings((items) => items.map((item) => item.task_type === task ? value : item))).catch((reason) => onError(errorMessage(reason)));
          }}>恢复当前任务默认值</SecondaryButton>
          <PrimaryButton disabled={busy || !current} onClick={() => {
            if (!current) return;
            void updateMaterialAISettings(task, {
              model_id: current.model_id,
              detail_level: current.detail_level,
              max_candidates: current.max_candidates,
              system_prompt: current.system_prompt,
              user_prompt_template: current.user_prompt_template,
              analysis_dimensions: current.analysis_dimensions,
              generate_general_tags: current.generate_general_tags,
              generate_applicable_scene_tags: current.generate_applicable_scene_tags,
              custom_requirements: current.custom_requirements,
            }).then((value) => {
              setSettings((items) => items.map((item) => item.task_type === task ? value : item));
              onClose();
            }).catch((reason) => onError(errorMessage(reason)));
          }}>保存设置</PrimaryButton>
        </>
      )}
      onClose={onClose}
      title="素材 AI 设置"
    >
      <div className="material-settings-tabs">
        {(Object.keys(TASK_LABELS) as MaterialAITask[]).map((taskType) => (
          <button aria-pressed={task === taskType} key={taskType} onClick={() => setTask(taskType)} type="button">{TASK_LABELS[taskType]}</button>
        ))}
      </div>
      {current ? (
        <div className="library-form-grid">
          <Field label="默认模型">
            <select value={current.model_id ?? ''} onChange={(event) => patch({ model_id: Number(event.target.value) || null })}>
              <option value="">使用系统默认模型</option>
              {models.map((model) => <option key={model.id} value={model.id}>{model.display_name}</option>)}
            </select>
          </Field>
          <Field label="细化程度">
            <select value={current.detail_level} onChange={(event) => patch({ detail_level: event.target.value as MaterialAISettings['detail_level'] })}>
              <option value="brief">brief</option>
              <option value="standard">standard</option>
              <option value="detailed">detailed</option>
            </select>
          </Field>
          <Field label="最大候选数">
            <input max={20} min={1} type="number" value={current.max_candidates} onChange={(event) => patch({ max_candidates: Number(event.target.value) || 1 })} />
          </Field>
          <label className="material-settings-check">
            <input checked={current.generate_general_tags} onChange={(event) => patch({ generate_general_tags: event.target.checked })} type="checkbox" />
            生成通用标签建议
          </label>
          <label className="material-settings-check">
            <input checked={current.generate_applicable_scene_tags} onChange={(event) => patch({ generate_applicable_scene_tags: event.target.checked })} type="checkbox" />
            生成适用场景标签建议
          </label>
          <Field className="wide" label="分析维度（每行一项）">
            <textarea
              value={current.analysis_dimensions.join('\n')}
              onChange={(event) => patch({
                analysis_dimensions: event.target.value.split('\n').map((item) => item.trim()).filter(Boolean),
              })}
            />
          </Field>
          <Field className="wide" label="用户提示词模板">
            <textarea value={current.user_prompt_template} onChange={(event) => patch({ user_prompt_template: event.target.value })} />
          </Field>
          <Field className="wide" label="附加要求">
            <textarea value={current.custom_requirements} onChange={(event) => patch({ custom_requirements: event.target.value })} />
          </Field>
          <Field className="wide" label="系统提示词（不会显示 API key）">
            <textarea className="material-system-prompt" value={current.system_prompt} onChange={(event) => patch({ system_prompt: event.target.value })} />
          </Field>
          <p className="wide material-form-hint">最后更新：{current.updated_at || '尚未记录'}</p>
        </div>
      ) : <LibraryEmptyState title="正在读取设置…" />}
    </LibraryDialog>
  );
}

function NameDialog({
  busy,
  initialName,
  onClose,
  onSave,
  title,
}: {
  busy: boolean;
  initialName: string;
  onClose: () => void;
  onSave: (value: string) => Promise<void>;
  title: string;
}) {
  const [name, setName] = useState(initialName);
  return (
    <LibraryDialog
      footer={(
        <>
          <SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton>
          <PrimaryButton disabled={busy || !name.trim()} onClick={() => void onSave(name)}>保存</PrimaryButton>
        </>
      )}
      onClose={onClose}
      title={title}
    >
      <Field label="分类名称"><input autoFocus value={name} onChange={(event) => setName(event.target.value)} /></Field>
    </LibraryDialog>
  );
}

function SummarySection({ action, children, label }: { action?: ReactNode; children: ReactNode; label: string }) {
  return <section><div className="document-detail-heading"><span>{label}</span>{action}</div>{children}</section>;
}

function TagChips({
  activeTagName,
  names,
  onClick,
}: {
  activeTagName: string | null;
  names: string[];
  onClick: (name: string) => void;
}) {
  return names.length ? (
    <div className="document-detail-badges material-clickable-chips">
      {names.map((name) => <button aria-pressed={activeTagName === name} key={name} onClick={() => onClick(name)} type="button">{name}</button>)}
    </div>
  ) : <p className="material-detail-copy">尚未设置</p>;
}

function Field({ children, className = '', label }: { children: ReactNode; className?: string; label: string }) {
  return <label className={className}><span>{label}</span>{children}</label>;
}

function typeLabel(type: MaterialType) {
  return type === 'plot_skeleton' ? '剧情骨架' : '场景素材';
}

function isPendingImport(material: Material) {
  const createdBy = String(material.import_metadata.created_by ?? '');
  return material.analysis_status === 'unanalyzed'
    && ['pending_material_import', 'selection_context_menu', 'json_batch_import'].includes(createdBy);
}

function contentSummary(content: Record<string, unknown>) {
  return String(content.premise ?? content.summary ?? '').trim();
}

function humanizeKey(key: string) {
  const labels: Record<string, string> = {
    premise: '前提',
    summary: '摘要',
    stages: '阶段',
    conflicts: '冲突',
    turning_points: '转折',
    hooks: '后续钩子',
    key_beats: '关键节拍',
    actions: '动作',
    environment: '环境',
    sensory: '感官',
    writing_guidance: '写作提示',
    source_cues: '来源线索',
    avoidances: '避免事项',
    applicable_conditions: '适用条件',
    causes: '原因',
    effects: '影响',
    characters: '人物',
    locations: '地点',
    must_keep_details: '必须保留',
    forbidden_changes: '禁止改动',
  };
  return labels[key] ?? key;
}

function structuredItems(value: unknown, prefix: string): Array<{ id: string; summary: string; [key: string]: unknown }> {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    if (item && typeof item === 'object') {
      const object = item as Record<string, unknown>;
      return {
        ...object,
        id: String(object.id ?? `${prefix}-${index + 1}`),
        summary: String(object.summary ?? object.text ?? object.title ?? ''),
      };
    }
    return { id: `${prefix}-${index + 1}`, summary: String(item ?? '') };
  });
}

function moveItem<T>(items: T[], from: number, to: number) {
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : typeof value === 'string' && value.trim() ? [value] : [];
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}

function normalizeMaterial(material: Material): Material {
  return {
    ...material,
    general_tags: material.general_tags ?? material.tags ?? [],
    applicable_scene_tags: material.applicable_scene_tags ?? [],
    category_ids: material.category_ids ?? [],
    categories: material.categories ?? [],
    source_summary: material.source_summary ?? {
      kind: 'manual',
      label: '本地创建',
    },
  };
}
