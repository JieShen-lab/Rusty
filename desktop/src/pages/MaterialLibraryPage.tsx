import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Boxes,
  BriefcaseBusiness,
  Copy,
  FileInput,
  FolderPlus,
  LayoutGrid,
  LibraryBig,
  ListTree,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Tag,
  Tags,
  Trash2,
} from 'lucide-react';
import {
  analyzeMaterial,
  copyMaterial,
  createMaterial,
  createMaterialTag,
  deleteMaterial,
  deleteMaterialTag,
  extractMaterials,
  getMaterialTags,
  getMaterials,
  getProjects,
  importMaterial,
  importMaterialJson,
  renameMaterialTag,
  updateMaterial,
} from '../api/client';
import type { AnalysisStatus, Material, MaterialScope, MaterialType, Project, ResourceTag } from '../api/types';
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

type Filter = 'all' | 'unanalyzed' | 'plot_skeleton' | 'scene_reference' | 'untagged';

export function MaterialLibraryPage() {
  const [scope, setScope] = useState<MaterialScope>('public');
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [tags, setTags] = useState<ResourceTag[]>([]);
  const [filter, setFilter] = useState<Filter>('all');
  const [tagId, setTagId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Material | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [rawImportOpen, setRawImportOpen] = useState(false);
  const [extractOpen, setExtractOpen] = useState(false);
  const [tagDialog, setTagDialog] = useState<{ mode: 'create' | 'rename'; tag?: ResourceTag } | null>(null);
  const [moreId, setMoreId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selected = materials.find((item) => item.id === selectedId) ?? null;
  const activeTag = tags.find((tag) => tag.id === tagId)?.name ?? null;
  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return materials.filter((material) => {
      if (filter === 'unanalyzed' && material.analysis_status !== 'unanalyzed') return false;
      if (filter === 'untagged' && material.tags.length > 0) return false;
      if (filter === 'scene_reference' && material.material_type !== 'scene_reference') return false;
      if (filter === 'plot_skeleton' && material.material_type !== 'plot_skeleton') return false;
      if (activeTag && !material.tags.includes(activeTag)) return false;
      if (!normalizedQuery) return true;
      return [
        material.name,
        material.description,
        material.raw_text,
        material.tags.join(' '),
      ].join(' ').toLocaleLowerCase().includes(normalizedQuery);
    });
  }, [activeTag, filter, materials, query]);

  useAutoDismiss(message, setMessage);
  useAutoDismiss(error, setError, 5200);

  async function load(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const [projectItems, tagItems] = await Promise.all([getProjects(), getMaterialTags()]);
      const nextProjectId = projectId ?? projectItems[0]?.id ?? null;
      const materialItems = await getMaterials({
        scope,
        project_id: scope === 'project' && nextProjectId ? nextProjectId : undefined,
      });
      setProjects(projectItems);
      setProjectId(nextProjectId);
      setTags(tagItems);
      setMaterials(materialItems);
      const nextId = preferredId === undefined ? selectedId : preferredId;
      setSelectedId(materialItems.some((material) => material.id === nextId) ? nextId : materialItems[0]?.id ?? null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [scope, projectId]);

  function selectScope(nextScope: MaterialScope) {
    setScope(nextScope);
    setFilter('all');
    setTagId(null);
    setSelectedId(null);
  }

  async function saveTag(name: string) {
    await runBusy(async () => {
      const created = tagDialog?.mode === 'rename' && tagDialog.tag
        ? await renameMaterialTag(tagDialog.tag.id, name.trim())
        : await createMaterialTag(name.trim());
      await load(selectedId);
      setTagId(created.id);
      setTagDialog(null);
      setMessage(tagDialog?.mode === 'rename' ? `标签已重命名为“${created.name}”。` : `已创建标签“${created.name}”。`);
    });
  }

  async function removeTag(id: number) {
    if (!window.confirm('删除标签只会解除关联，不会删除素材。确认继续？')) return;
    await runBusy(async () => {
      await deleteMaterialTag(id);
      if (tagId === id) setTagId(null);
      await load(selectedId);
      setMessage('素材标签已删除。');
    });
  }

  async function copySelected(material: Material) {
    await runBusy(async () => {
      if (material.scope === 'public') {
        if (!projectId) throw new Error('请先选择目标工程。');
        const copied = await copyMaterial(material.id, 'project', projectId);
        setScope('project');
        setSelectedId(copied.id);
        setMessage('已复制为独立的工程素材副本。');
      } else {
        const copied = await copyMaterial(material.id, 'public', null);
        setScope('public');
        setSelectedId(copied.id);
        setMessage('已复制为独立的公共素材副本。');
      }
    });
  }

  async function runAnalyze(material: Material) {
    await runBusy(async () => {
      const updated = await analyzeMaterial(material.id);
      await load(updated.id);
      setMessage('模型分析完成，结构化结果已保存。');
    });
  }

  async function deleteSelected(material: Material) {
    if (!window.confirm(`确认删除素材“${material.name}”？该操作不会删除已复制的独立副本。`)) return;
    await runBusy(async () => {
      await deleteMaterial(material.id);
      await load(null);
      setMessage('素材已删除。');
    });
  }

  async function saveMaterial(material: Material, draft: MaterialDraft) {
    if (!draft.name.trim()) {
      setError('素材名称不能为空。');
      return;
    }
    await runBusy(async () => {
      const content = parseObject(draft.content);
      const updated = await updateMaterial(material.id, {
        name: draft.name.trim(),
        description: draft.description,
        raw_text: draft.raw_text,
        content,
        analysis_status: draft.analysis_status,
        detail_level: material.detail_level,
        timeline_start_chapter: material.timeline_start_chapter,
        timeline_end_chapter: material.timeline_end_chapter,
        sort_order: material.sort_order,
        tag_ids: draft.tag_ids,
      });
      setEditing(null);
      await load(updated.id);
      setMessage('素材已保存。');
    });
  }

  async function createFromDraft(draft: NewMaterialDraft) {
    await runBusy(async () => {
      const created = await createMaterial({
        material_type: draft.material_type,
        scope,
        project_id: scope === 'project' ? projectId : null,
        name: draft.name.trim(),
        description: draft.description,
        raw_text: draft.raw_text,
        content: {
          events: [],
        },
        analysis_status: draft.analysis_status,
        tag_ids: [],
      });
      setCreateOpen(false);
      await load(created.id);
      setEditing(created);
      setMessage('素材已创建，可继续补充结构化内容。');
    });
  }

  async function importFromDraft(draft: NewMaterialDraft) {
    await runBusy(async () => {
      const created = await importMaterial({
        material_type: draft.material_type,
        scope,
        project_id: scope === 'project' ? projectId : null,
        name: draft.name.trim(),
        description: draft.description,
        raw_text: draft.raw_text,
        content: {
          source_imported: true,
        },
        analysis_status: 'unanalyzed',
        source_metadata: { source_kind: 'manual_import' },
        tag_ids: [],
      });
      setImportOpen(false);
      setRawImportOpen(false);
      await load(created.id);
      setMessage('素材已导入，等待结构化分析。');
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
    all: materials.length,
    unanalyzed: materials.filter((item) => item.analysis_status === 'unanalyzed').length,
    plot_skeleton: materials.filter((item) => item.material_type === 'plot_skeleton').length,
    scene_reference: materials.filter((item) => item.material_type === 'scene_reference').length,
    untagged: materials.filter((item) => item.tags.length === 0).length,
  };

  return (
    <div className="document-library-page material-library-page">
      <TopBar
        title="素材"
        actions={(
          <>
            <SecondaryButton disabled={busy} onClick={() => setImportOpen(true)}><FileInput size={16} />导入</SecondaryButton>
            <SecondaryButton disabled={busy} onClick={() => setRawImportOpen(true)}><FileInput size={16} />导入原始文字</SecondaryButton>
            <SecondaryButton disabled={busy} onClick={() => setExtractOpen(true)}><Sparkles size={16} />AI 提取</SecondaryButton>
            <PrimaryButton disabled={busy || (scope === 'project' && !projectId)} onClick={() => setCreateOpen(true)}><Plus size={16} />新建素材</PrimaryButton>
          </>
        )}
      />
      {error ? <div className="inline-alert error document-library-alert" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success document-library-alert" role="status">{message}</div> : null}

      <div className="document-library-layout material-browser-layout">
        <aside className="document-tag-panel">
          <header><h2>素材库</h2></header>
          <nav aria-label="素材筛选">
            <LibrarySidebarItem active={scope === 'public'} count={scope === 'public' ? materials.length : 0} icon={<LibraryBig size={16} />} label="公共素材" onClick={() => selectScope('public')} />
            <LibrarySidebarItem active={scope === 'project'} count={scope === 'project' ? materials.length : 0} icon={<BriefcaseBusiness size={16} />} label="工程素材" onClick={() => selectScope('project')} />
            <div className="library-project-selector">
              <label htmlFor="material-project">当前工程</label>
              <select id="material-project" value={projectId ?? ''} onChange={(event) => setProjectId(Number(event.target.value) || null)}>
                {projects.length ? projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>) : <option value="">暂无工程</option>}
              </select>
            </div>
            <div className="document-tag-heading"><span>素材类型</span></div>
            <LibrarySidebarItem active={filter === 'plot_skeleton'} count={counts.plot_skeleton} icon={<ListTree size={16} />} label="剧情骨架" onClick={() => { setFilter('plot_skeleton'); setTagId(null); }} />
            <LibrarySidebarItem active={filter === 'scene_reference'} count={counts.scene_reference} icon={<Boxes size={16} />} label="场景素材" onClick={() => { setFilter('scene_reference'); setTagId(null); }} />
            <div className="document-tag-heading"><span>系统筛选</span></div>
            <LibrarySidebarItem active={filter === 'all' && tagId === null} count={counts.all} icon={<LayoutGrid size={16} />} label="全部" onClick={() => { setFilter('all'); setTagId(null); }} />
            <LibrarySidebarItem active={filter === 'unanalyzed' && tagId === null} count={counts.unanalyzed} icon={<Sparkles size={16} />} label="未分析" onClick={() => { setFilter('unanalyzed'); setTagId(null); }} />
            <LibrarySidebarItem active={filter === 'untagged' && tagId === null} count={counts.untagged} icon={<Tags size={16} />} label="无标签" onClick={() => { setFilter('untagged'); setTagId(null); }} />
            <div className="document-tag-heading">
              <span>我的标签</span>
              <button aria-label="新建素材标签" className="document-add-tag" disabled={busy} onClick={() => setTagDialog({ mode: 'create' })} type="button"><FolderPlus size={15} /></button>
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

        <main className="document-shelf-panel material-browser-shelf">
          <header>
            <div className="document-shelf-tools">
              <label className="search-field document-search">
                <Search size={15} />
                <span className="sr-only">搜索素材</span>
                <input onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、摘要、原文或标签" type="search" value={query} />
              </label>
            </div>
          </header>
          {loading ? <LibraryEmptyState title="正在读取素材库…" /> : filtered.length ? (
            <div className="document-shelf-scroll">
                <div className="library-material-grid">
                  {filtered.map((material) => (
                    <div
                      aria-pressed={selectedId === material.id}
                      className={`library-material-card ${selectedId === material.id ? 'selected' : ''}`}
                      key={material.id}
                      onClick={() => setSelectedId(material.id)}
                      onDoubleClick={() => setEditing(material)}
                      onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelectedId(material.id); }}
                      role="button"
                      tabIndex={0}
                    >
                      <header><strong>{material.name}</strong><span>{typeLabel(material)}</span></header>
                      <p>{material.description || material.raw_text.slice(0, 110) || structuredSummary(material.content)}</p>
                      <div className="library-material-meta">
                        <span>{material.source_material_id ? `来源 #${material.source_material_id}` : `v${material.version}`}</span>
                        <span>{material.analysis_status === 'unanalyzed' ? '未分析' : '已分析'}</span>
                      </div>
                      <div className="document-detail-badges">{material.tags.slice(0, 3).map((name) => <span key={name}>{name}</span>)}</div>
                      {material.scope === 'project' ? (
                        <span className="library-card-more" onClick={(event) => event.stopPropagation()}>
                          <button aria-haspopup="menu" aria-expanded={moreId === material.id} aria-label="素材更多操作" type="button" onClick={() => setMoreId(moreId === material.id ? null : material.id)}><MoreHorizontal size={15} /></button>
                          {moreId === material.id ? <span className="library-card-menu" role="menu"><button role="menuitem" type="button" onClick={() => { setMoreId(null); void copySelected(material); }}>添加到公共素材</button></span> : null}
                        </span>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
          ) : materials.length === 0 ? (
            <LibraryEmptyState
              action={<PrimaryButton onClick={() => setCreateOpen(true)}><Plus size={16} />新建第一个素材</PrimaryButton>}
              description={scope === 'project' ? '当前工程还没有独立素材副本。' : '公共素材可以复制到任意工程。'}
              title="素材库还是空的"
            />
          ) : <LibraryEmptyState description="尝试调整左侧筛选或清空搜索词。" title="没有匹配的素材" />}
        </main>

        <aside className="document-detail-panel material-detail-panel">
          <header><h2>素材详情</h2></header>
          {selected ? (
            <>
              <div className="document-detail-scroll">
                <section className="material-detail-identity">
                  <h3>{selected.name}</h3>
                  <p>{typeLabel(selected)}</p>
                  <div className="document-detail-badges">
                    <span>{selected.scope === 'public' ? '公共素材' : '工程素材'}</span>
                    <span>v{selected.version}</span>
                    <span>{selected.analysis_status === 'unanalyzed' ? '未分析' : '已分析'}</span>
                  </div>
                </section>
                <section className="document-detail-metadata">
                  <LibraryDefinition label="来源" value={selected.source_material_id ? `素材 #${selected.source_material_id}` : String(selected.source_metadata.source_kind ?? '本地创建')} />
                  <LibraryDefinition label="来源版本" value={selected.source_version ? `v${selected.source_version}` : '—'} />
                  <LibraryDefinition label="更新时间" value={formatDate(selected.updated_at)} />
                </section>
                <DetailSection label="描述" value={selected.description} />
                <DetailSection label="标签" value={selected.tags.join(' / ')} />
                <StructuredMaterial content={selected.content} />
                <DetailSection label="适用场景" value={textValue(selected.content.applicable_scenes)} />
                <details className="material-json-details">
                  <summary>查看结构数据</summary>
                  <pre>{JSON.stringify(selected.content, null, 2)}</pre>
                </details>
              </div>
              <footer className="library-detail-footer material-detail-footer">
                <SecondaryButton disabled={busy} onClick={() => setEditing(selected)}><Pencil size={15} />编辑</SecondaryButton>
                <SecondaryButton disabled={busy} onClick={() => void copySelected(selected)}><Copy size={15} />{selected.scope === 'public' ? '复制到工程' : '复制到公共库'}</SecondaryButton>
                <SecondaryButton disabled={busy} onClick={() => void runAnalyze(selected)}><Sparkles size={15} />AI 分析</SecondaryButton>
                <DangerButton disabled={busy} onClick={() => void deleteSelected(selected)}><Trash2 size={15} />删除</DangerButton>
              </footer>
            </>
          ) : <LibraryEmptyState description="单击中央区域中的素材后，可读结构、来源和时间线会显示在这里。" title="选择一个素材查看详情" />}
        </aside>
      </div>

      {createOpen ? <NewMaterialDialog busy={busy} mode="create" onClose={() => setCreateOpen(false)} onSave={createFromDraft} /> : null}
      {importOpen ? (
        <JsonImportDialog
          busy={busy}
          onClose={() => setImportOpen(false)}
          onImport={async (value) => {
            await runBusy(async () => {
              const result = await importMaterialJson(value, scope, scope === 'project' ? projectId : null);
              setImportOpen(false);
              await load(result.imported[0]?.id ?? selectedId);
              setMessage(`已导入 ${result.imported.length} 条素材${result.errors.length ? `，${result.errors.length} 条未导入` : ''}。`);
              if (result.errors.length) setError(result.errors.map((item) => `第 ${item.index + 1} 条：${item.error}`).join('；'));
            });
          }}
        />
      ) : null}
      {rawImportOpen ? <NewMaterialDialog busy={busy} mode="import" onClose={() => setRawImportOpen(false)} onSave={importFromDraft} /> : null}
      {extractOpen ? (
        <MaterialExtractDialog
          busy={busy}
          projectId={scope === 'project' ? projectId : null}
          scope={scope}
          onClose={() => setExtractOpen(false)}
          onError={setError}
          onFinished={async (saved) => {
            setExtractOpen(false);
            await load(saved[0]?.id ?? selectedId);
            setMessage(`已保留 ${saved.length} 条提取素材。`);
          }}
        />
      ) : null}
      {editing ? <MaterialEditor busy={busy} material={editing} tags={tags} onClose={() => setEditing(null)} onSave={saveMaterial} /> : null}
      {tagDialog ? <TagNameDialog busy={busy} initialName={tagDialog.tag?.name ?? ''} onClose={() => setTagDialog(null)} onSave={saveTag} title={tagDialog.mode === 'rename' ? '重命名素材标签' : '新建素材标签'} /> : null}
    </div>
  );
}

type MaterialDraft = {
  name: string;
  description: string;
  raw_text: string;
  content: string;
  analysis_status: AnalysisStatus;
  tag_ids: number[];
};

type NewMaterialDraft = {
  material_type: MaterialType;
  name: string;
  description: string;
  raw_text: string;
  analysis_status: AnalysisStatus;
};

function MaterialEditor({ busy, material, onClose, onSave, tags }: {
  busy: boolean;
  material: Material;
  onClose: () => void;
  onSave: (material: Material, draft: MaterialDraft) => void;
  tags: ResourceTag[];
}) {
  const [draft, setDraft] = useState<MaterialDraft>({
    name: material.name,
    description: material.description,
    raw_text: material.raw_text,
    content: JSON.stringify(material.content, null, 2),
    analysis_status: material.analysis_status,
    tag_ids: tags.filter((tag) => material.tags.includes(tag.name)).map((tag) => tag.id),
  });
  return (
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !draft.name.trim()} onClick={() => onSave(material, draft)}>{busy ? '保存中…' : '保存'}</PrimaryButton></>}
      onClose={onClose}
      subtitle={`${typeLabel(material)} · v${material.version}`}
      title="编辑素材"
    >
      <div className="library-form-grid">
        <Field label="素材名称"><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
        <Field label="分析状态"><select value={draft.analysis_status} onChange={(event) => setDraft({ ...draft, analysis_status: event.target.value as AnalysisStatus })}><option value="unanalyzed">未分析</option><option value="analyzed">已分析</option></select></Field>
        <Field className="wide" label="描述"><textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></Field>
        <Field className="wide" label="原始来源"><textarea value={draft.raw_text} onChange={(event) => setDraft({ ...draft, raw_text: event.target.value })} /></Field>
        <fieldset className="wide library-tag-picker">
          <legend>标签</legend>
          {tags.length ? tags.map((tag) => (
            <label key={tag.id}>
              <input
                checked={draft.tag_ids.includes(tag.id)}
                type="checkbox"
                onChange={(event) => setDraft({
                  ...draft,
                  tag_ids: event.target.checked
                    ? [...draft.tag_ids, tag.id]
                    : draft.tag_ids.filter((id) => id !== tag.id),
                })}
              />
              {tag.name}
            </label>
          )) : <small>请先在左侧新建标签。</small>}
        </fieldset>
      </div>
      <details className="library-advanced-editor">
        <summary>高级结构化编辑（JSON）</summary>
        <textarea value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} />
      </details>
    </LibraryDialog>
  );
}

function NewMaterialDialog({ busy, mode, onClose, onSave }: {
  busy: boolean;
  mode: 'create' | 'import';
  onClose: () => void;
  onSave: (draft: NewMaterialDraft) => void;
}) {
  const [draft, setDraft] = useState<NewMaterialDraft>({
    material_type: 'scene_reference',
    name: '',
    description: '',
    raw_text: '',
    analysis_status: mode === 'import' ? 'unanalyzed' : 'analyzed',
  });
  return (
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !draft.name.trim() || (mode === 'import' && !draft.raw_text.trim())} onClick={() => onSave(draft)}>{busy ? '处理中…' : mode === 'import' ? '导入' : '创建'}</PrimaryButton></>}
      onClose={onClose}
      subtitle={mode === 'import' ? '保留原始来源，后续再结构化' : '创建可复用素材'}
      title={mode === 'import' ? '导入素材' : '新建素材'}
    >
      <div className="material-kind-picker">
        {([
          ['plot_skeleton', '剧情骨架', '按因果顺序排列的事件节点'],
          ['scene_reference', '场景素材', '为特定场景提供写法、动作和细节参考'],
        ] as const).map(([kind, label, description]) => (
          <button className={draft.material_type === kind ? 'selected' : ''} key={kind} onClick={() => setDraft({ ...draft, material_type: kind })} type="button"><strong>{label}</strong><span>{description}</span></button>
        ))}
      </div>
      <div className="library-form-grid">
        <Field label="素材名称"><input autoFocus value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
        <Field className="wide" label="展示摘要"><textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></Field>
        {mode === 'import' ? <Field className="wide" label="原始来源"><textarea className="tall" value={draft.raw_text} onChange={(event) => setDraft({ ...draft, raw_text: event.target.value })} /></Field> : null}
      </div>
    </LibraryDialog>
  );
}

function MaterialExtractDialog({ busy, onClose, onError, onFinished, projectId, scope }: {
  busy: boolean;
  onClose: () => void;
  onError: (message: string) => void;
  onFinished: (materials: Material[]) => Promise<void>;
  projectId: number | null;
  scope: MaterialScope;
}) {
  const [sourceText, setSourceText] = useState('');
  const [type, setType] = useState<MaterialType>('scene_reference');
  const [results, setResults] = useState<Material[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [working, setWorking] = useState(false);
  async function extract() {
    setWorking(true);
    onError('');
    try {
      const response = await extractMaterials({
        detail_level: 'standard',
        sample_text: sourceText,
        material_type: type,
        scope,
        project_id: scope === 'project' ? projectId : null,
      });
      setResults(response.materials);
      setSelectedIds(new Set(response.materials.map((item) => item.id)));
    } catch (reason) {
      onError(errorMessage(reason));
    } finally {
      setWorking(false);
    }
  }
  async function keepSelected() {
    setWorking(true);
    try {
      const selected = results.filter((item) => selectedIds.has(item.id));
      await Promise.all(results.filter((item) => !selectedIds.has(item.id)).map((item) => deleteMaterial(item.id)));
      await onFinished(selected);
    } catch (reason) {
      onError(errorMessage(reason));
    } finally {
      setWorking(false);
    }
  }
  return (
    <LibraryDialog
      footer={results.length ? (
        <><SecondaryButton disabled={working} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={working || selectedIds.size === 0} onClick={() => void keepSelected()}>{working ? '保存中…' : `保存所选（${selectedIds.size}）`}</PrimaryButton></>
      ) : <><SecondaryButton disabled={working} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={working || !sourceText.trim() || busy} onClick={() => void extract()}>{working ? '提取中…' : '开始提取'}</PrimaryButton></>}
      onClose={onClose}
      subtitle="先提取结构，再选择要保留的素材"
      title="AI 提取素材"
    >
      {results.length ? (
        <div className="material-extract-results">
          {results.map((item) => (
            <label key={item.id}>
              <input checked={selectedIds.has(item.id)} onChange={(event) => setSelectedIds((current) => {
                const next = new Set(current);
                if (event.target.checked) next.add(item.id); else next.delete(item.id);
                return next;
              })} type="checkbox" />
              <span><strong>{item.name}</strong><small>{typeLabel(item)} · {item.description || '暂无摘要'}</small></span>
            </label>
          ))}
        </div>
      ) : (
        <div className="library-form-grid">
          <Field label="提取类型"><select value={type} onChange={(event) => setType(event.target.value as MaterialType)}><option value="scene_reference">场景素材</option><option value="plot_skeleton">剧情骨架</option></select></Field>
          <Field className="wide" label="来源文本"><textarea className="tall" value={sourceText} onChange={(event) => setSourceText(event.target.value)} /></Field>
        </div>
      )}
    </LibraryDialog>
  );
}

function StructuredMaterial({ content }: { content: Record<string, unknown> }) {
  const entries = Object.entries(content).filter(([key]) => key !== 'material_kind').slice(0, 8);
  return (
    <section>
      <div className="document-detail-heading"><span>结构化内容</span></div>
      {entries.length ? <div className="material-readable-structure">{entries.map(([key, value]) => <div key={key}><strong>{humanizeKey(key)}</strong><p>{textValue(value) || '—'}</p></div>)}</div> : <p className="material-detail-copy">尚未提取结构化维度。</p>}
    </section>
  );
}

function DetailSection({ label, value }: { label: string; value: string }) {
  return <section><div className="document-detail-heading"><span>{label}</span></div><p className="material-detail-copy">{value || '未填写'}</p></section>;
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

function JsonImportDialog({ busy, onClose, onImport }: {
  busy: boolean;
  onClose: () => void;
  onImport: (value: unknown) => void;
}) {
  const [text, setText] = useState('');
  const [value, setValue] = useState<unknown>(null);
  const [parseError, setParseError] = useState('');
  function parse(nextText: string) {
    setText(nextText);
    try {
      const parsed = JSON.parse(nextText) as unknown;
      if (!parsed || (typeof parsed !== 'object')) throw new Error('JSON 必须是对象或对象数组。');
      setValue(parsed);
      setParseError('');
    } catch (reason) {
      setValue(null);
      setParseError(errorMessage(reason));
    }
  }
  async function readFile(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.json')) {
      setParseError('请选择 .json 文件。');
      return;
    }
    parse(await file.text());
  }
  const preview = value ? (Array.isArray(value) ? value : [value]).map((item, index) => {
    const row = item && typeof item === 'object' ? item as Record<string, unknown> : {};
    const type = row.material_type === 'scene_reference' ? '场景素材' : row.material_type === 'plot_skeleton' || row.material_type === 'outline' ? '剧情骨架' : '类型无效';
    return { index, name: String(row.name ?? '未命名'), type, tags: Array.isArray(row.tags) ? row.tags.join(' / ') : '' };
  }) : [];
  return (
    <LibraryDialog
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !value} onClick={() => value && onImport(value)}>确认批量导入</PrimaryButton></>}
      onClose={onClose}
      subtitle="只接受 JSON 对象或对象数组；非法项会单独报告。"
      title="导入 JSON 素材"
    >
      <Field label="选择 JSON 文件"><input accept=".json,application/json" type="file" onChange={(event) => void readFile(event.target.files?.[0])} /></Field>
      <details className="library-advanced-editor" open>
        <summary>高级 JSON 输入</summary>
        <textarea className="tall" placeholder='[{"material_type":"scene_reference","name":"示例"}]' value={text} onChange={(event) => parse(event.target.value)} />
      </details>
      {parseError ? <div className="inline-alert error" role="alert">{parseError}</div> : null}
      {preview.length ? <div className="material-extract-results">{preview.map((item) => <div key={item.index}><strong>{item.name}</strong><small>{item.type}{item.tags ? ` · ${item.tags}` : ''}</small></div>)}</div> : null}
    </LibraryDialog>
  );
}

function typeLabel(material: Material) {
  return material.material_type === 'plot_skeleton' ? '剧情骨架' : '场景素材';
}

function structuredSummary(content: Record<string, unknown>) {
  const keys = Object.keys(content).filter((key) => key !== 'material_kind');
  return keys.length ? keys.map(humanizeKey).join(' / ') : '暂无结构化内容';
}

function humanizeKey(key: string) {
  const labels: Record<string, string> = {
    events: '事件节点',
    characters: '人物',
    locations: '地点',
    timeline: '时间线',
    conflicts: '冲突',
    outcomes: '结果',
    conditions: '适用条件',
    applicable_scenes: '适用场景',
    plot_dimensions: '剧情维度',
    impact: '影响范围',
    objects: '物品变化',
    open_threads: '新增悬念',
    event: '事件',
  };
  return labels[key] ?? key.replace(/_/g, ' ');
}

function textValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => textValue(item)).filter(Boolean).join('；');
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${humanizeKey(key)}：${textValue(item)}`)
      .join('；');
  }
  return String(value ?? '');
}

function parseObject(value: string) {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('结构化内容必须是 JSON 对象。');
  return parsed as Record<string, unknown>;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}
