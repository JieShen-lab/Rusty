import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import {
  BookOpenText,
  Boxes,
  ChevronDown,
  ChevronRight,
  Clock3,
  Copy,
  FileJson,
  Folder,
  FolderPlus,
  Import,
  Layers3,
  LibraryBig,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import {
  copyMaterial,
  createMaterialCategory,
  deleteMaterial,
  extractMaterials,
  getLibraryDocuments,
  getMaterialCategories,
  getMaterials,
  getProjects,
  importMaterial,
  updateMaterial,
} from '../api/client';
import type {
  LibraryDocument,
  Material,
  MaterialCategory,
  MaterialScope,
  MaterialType,
  Project,
  StyleDetailLevel,
} from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

const materialTypes: Array<{ key: MaterialType; label: string; icon: typeof BookOpenText }> = [
  { key: 'outline', label: '大纲', icon: BookOpenText },
  { key: 'plot_skeleton', label: '剧情骨架', icon: Layers3 },
  { key: 'snippet', label: '小素材', icon: Boxes },
];

type ExtractSource = 'paste' | 'project' | 'document';
type MaterialDraft = {
  name: string;
  description: string;
  detail_level: StyleDetailLevel;
  contentText: string;
  timeline_start_chapter: string;
  timeline_end_chapter: string;
};

export function MaterialLibraryPage() {
  const initialQuery = useMemo(() => new URLSearchParams(window.location.search), []);
  const [scope, setScope] = useState<MaterialScope>(() => initialQuery.get('scope') === 'project' ? 'project' : 'public');
  const [activeType, setActiveType] = useState<MaterialType>(() => {
    const type = initialQuery.get('type');
    return type === 'plot_skeleton' || type === 'snippet' ? type : 'outline';
  });
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [uncategorizedOnly, setUncategorizedOnly] = useState(false);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [categories, setCategories] = useState<MaterialCategory[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState('');
  const [hiddenLanes, setHiddenLanes] = useState<Set<MaterialType>>(() => new Set());
  const [extractOpen, setExtractOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const deferredSearch = useDeferredValue(searchText.trim().toLocaleLowerCase());
  const selected = materials.find((item) => item.id === selectedId) ?? null;
  const visibleMaterials = useMemo(() => materials.filter((item) => {
    if (scope === 'public' && item.material_type !== activeType) return false;
    if (uncategorizedOnly && item.categories.length > 0) return false;
    if (categoryId !== null && !item.categories.includes(categories.find((entry) => entry.id === categoryId)?.name ?? '')) return false;
    if (!deferredSearch) return true;
    return `${item.name} ${item.description} ${item.categories.join(' ')}`
      .toLocaleLowerCase()
      .includes(deferredSearch);
  }), [activeType, categories, categoryId, deferredSearch, materials, scope, uncategorizedOnly]);

  useAutoDismiss(message, setMessage);
  useAutoDismiss(error, setError, 5200);

  async function load(preferredId?: number | null) {
    setError(null);
    try {
      const [projectItems, categoryItems, documentItems] = await Promise.all([
        getProjects(),
        getMaterialCategories(),
        getLibraryDocuments(),
      ]);
      const nextProjectId = projectId ?? projectItems[0]?.id ?? null;
      const materialItems = await getMaterials({
        scope,
        project_id: scope === 'project' && nextProjectId !== null ? nextProjectId : undefined,
      });
      setProjects(projectItems);
      setCategories(categoryItems);
      setDocuments(documentItems);
      setProjectId(nextProjectId);
      setMaterials(materialItems);
      const nextId = preferredId === undefined ? selectedId : preferredId;
      setSelectedId(materialItems.some((item) => item.id === nextId) ? nextId : materialItems[0]?.id ?? null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [scope, projectId]);

  function switchScope(nextScope: MaterialScope) {
    setScope(nextScope);
    setCategoryId(null);
    setUncategorizedOnly(false);
    setSelectedId(null);
    setEditing(false);
    setMessage(null);
  }

  async function addCategory() {
    const name = window.prompt(`为“${typeLabel(activeType)}”新增分类`);
    if (!name?.trim()) return;
    await runBusy(async () => {
      const created = await createMaterialCategory(name, activeType);
      setCategoryId(created.id);
      setUncategorizedOnly(false);
      await load(selectedId);
      setMessage(`已创建分类“${created.name}”。`);
    });
  }

  async function removeSelected() {
    if (!selected || !window.confirm(`确认删除素材“${selected.name}”？已有副本不会受到影响。`)) return;
    await runBusy(async () => {
      await deleteMaterial(selected.id);
      setSelectedId(null);
      setEditing(false);
      await load(null);
      setMessage('素材已删除。');
    });
  }

  async function copySelected() {
    if (!selected) return;
    const targetScope: MaterialScope = selected.scope === 'public' ? 'project' : 'public';
    const targetProjectId = targetScope === 'project' ? projectId : null;
    if (targetScope === 'project' && targetProjectId === null) {
      setError('请先创建工程，再复制公共素材。');
      return;
    }
    await runBusy(async () => {
      const copied = await copyMaterial(selected.id, targetScope, targetProjectId);
      setMessage(targetScope === 'project' ? '已生成独立的工程素材副本。' : '已生成独立的公共素材副本。');
      if (scope === targetScope) await load(copied.id);
    });
  }

  async function saveDraft(draft: MaterialDraft) {
    if (!selected) return;
    await runBusy(async () => {
      const content = parseJsonObject(draft.contentText);
      const saved = await updateMaterial(selected.id, {
        name: draft.name,
        description: draft.description,
        detail_level: draft.detail_level,
        content,
        timeline_start_chapter: positiveNumber(draft.timeline_start_chapter),
        timeline_end_chapter: positiveNumber(draft.timeline_end_chapter),
        sort_order: selected.sort_order,
        category_ids: selected.scope === 'public'
          ? categories.filter((item) => selected.categories.includes(item.name)).map((item) => item.id)
          : undefined,
      });
      setEditing(false);
      await load(saved.id);
      setMessage('素材已保存。');
    });
  }

  async function runBusy(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="material-library-page">
      <TopBar
        title="素材"
        actions={(
          <>
            <SecondaryButton disabled={busy} onClick={() => setImportOpen(true)}>
              <Import size={16} />导入
            </SecondaryButton>
            <PrimaryButton disabled={busy} onClick={() => setExtractOpen(true)}>
              <Sparkles size={16} />AI 提取
            </PrimaryButton>
          </>
        )}
      />

      <div className={`material-command-row ${scope === 'public' ? 'public-hidden' : ''}`}>
        <div className="material-scope-switch" role="tablist" aria-label="素材作用域">
          <button aria-selected={scope === 'public'} className={scope === 'public' ? 'selected' : ''} onClick={() => switchScope('public')} role="tab" type="button">公共素材</button>
          <button aria-selected={scope === 'project'} className={scope === 'project' ? 'selected' : ''} onClick={() => switchScope('project')} role="tab" type="button">工程素材</button>
        </div>
        {scope === 'project' ? (
          <label className="material-project-select">
            <span className="sr-only">选择工程</span>
            <select value={projectId ?? ''} onChange={(event) => setProjectId(Number(event.target.value) || null)}>
              {projects.length ? projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>) : <option value="">暂无工程</option>}
            </select>
            <ChevronDown size={14} />
          </label>
        ) : null}
        <label className="search-field material-search">
          <Search size={15} /><span className="sr-only">搜索素材</span>
          <input placeholder="搜索名称、摘要或分类" type="search" value={searchText} onChange={(event) => setSearchText(event.target.value)} />
        </label>
      </div>

      {error ? <div className="inline-alert error material-alert" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success material-alert" role="status">{message}</div> : null}

      {scope === 'public' ? (
        <PublicMaterialLibrary
          activeType={activeType}
          categories={categories}
          categoryId={categoryId}
          uncategorizedOnly={uncategorizedOnly}
          loading={loading}
          allMaterials={materials.filter((item) => item.material_type === activeType)}
          materials={visibleMaterials}
          searchText={searchText}
          onSearchChange={setSearchText}
          onAddCategory={() => void addCategory()}
          onCategoryChange={(id) => {
            setCategoryId(id);
            setUncategorizedOnly(false);
          }}
          onUncategorizedChange={() => {
            setCategoryId(null);
            setUncategorizedOnly(true);
          }}
          onSelect={setSelectedId}
          onTypeChange={(type) => {
            setActiveType(type);
            setCategoryId(null);
            setUncategorizedOnly(false);
            setSelectedId(null);
          }}
          onScopeChange={switchScope}
          selected={selected}
          selectedId={selectedId}
          onCopy={() => void copySelected()}
          onDelete={() => void removeSelected()}
          onEdit={() => setEditing(true)}
        />
      ) : (
        <ProjectMaterialTimeline
          hiddenLanes={hiddenLanes}
          loading={loading}
          materials={visibleMaterials}
          onSelect={(id) => {
            setSelectedId(id);
            setEditing(true);
          }}
          onToggleLane={(type) => {
            setHiddenLanes((current) => {
              const next = new Set(current);
              if (next.has(type)) next.delete(type);
              else next.add(type);
              return next;
            });
          }}
        />
      )}

      {extractOpen ? (
        <ExtractDialog
          busy={busy}
          defaultProjectId={scope === 'project' ? projectId : null}
          defaultType={activeType}
          documents={documents}
          projects={projects}
          scope={scope}
          onClose={() => setExtractOpen(false)}
          onExtract={(payload) => void runBusy(async () => {
            const result = await extractMaterials(payload);
            setExtractOpen(false);
            await load(result.materials[0]?.id ?? null);
            setMessage(`AI 已生成 ${result.materials.length} 条${typeLabel(payload.material_type)}素材。`);
          })}
        />
      ) : null}

      {importOpen ? (
        <ImportDialog
          busy={busy}
          defaultProjectId={scope === 'project' ? projectId : null}
          defaultType={activeType}
          scope={scope}
          onClose={() => setImportOpen(false)}
          onImport={(raw, type) => void runBusy(async () => {
            const data = parseJsonObject(raw);
            const imported = await importMaterial({
              material_type: type,
              scope,
              project_id: scope === 'project' ? projectId : null,
              name: String(data.name || '导入素材'),
              description: String(data.description || ''),
              detail_level: isDetailLevel(data.detail_level) ? data.detail_level : 'standard',
              content: isObject(data.content) ? data.content : data,
              timeline_start_chapter: numberOrNull(data.timeline_start_chapter),
              timeline_end_chapter: numberOrNull(data.timeline_end_chapter),
            });
            setImportOpen(false);
            await load(imported.id);
            setMessage('JSON 素材已导入。');
          })}
        />
      ) : null}

      {editing && selected ? (
        <MaterialEditor
          busy={busy}
          material={selected}
          onClose={() => setEditing(false)}
          onCopy={() => void copySelected()}
          onDelete={() => void removeSelected()}
          onSave={(draft) => void saveDraft(draft)}
        />
      ) : null}
    </div>
  );
}

function PublicMaterialLibrary(props: {
  activeType: MaterialType;
  allMaterials: Material[];
  categories: MaterialCategory[];
  categoryId: number | null;
  uncategorizedOnly: boolean;
  loading: boolean;
  materials: Material[];
  searchText: string;
  selected: Material | null;
  selectedId: number | null;
  onAddCategory: () => void;
  onSearchChange: (value: string) => void;
  onScopeChange: (scope: MaterialScope) => void;
  onCategoryChange: (id: number | null) => void;
  onUncategorizedChange: () => void;
  onTypeChange: (type: MaterialType) => void;
  onSelect: (id: number) => void;
  onCopy: () => void;
  onDelete: () => void;
  onEdit: () => void;
}) {
  const typeCategories = props.categories.filter((item) => item.material_type === props.activeType);
  return (
    <div className="material-public-layout">
      <aside className="material-category-panel">
        <header>
          <div className="material-scope-switch" role="tablist" aria-label="素材作用域">
            <button aria-selected="true" className="selected" onClick={() => props.onScopeChange('public')} role="tab" type="button">公共素材</button>
            <button aria-selected="false" onClick={() => props.onScopeChange('project')} role="tab" type="button">工程素材</button>
          </div>
        </header>
        <nav aria-label="素材固定分类">
          {materialTypes.map(({ icon: Icon, key, label }) => (
            <button className={props.activeType === key ? 'selected' : ''} key={key} onClick={() => props.onTypeChange(key)} type="button">
              <Icon size={16} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="material-custom-category-heading">
          <span>{typeLabel(props.activeType)}分类</span>
        </div>
        <nav aria-label="素材分类筛选">
          <button className={props.categoryId === null && !props.uncategorizedOnly ? 'selected' : ''} onClick={() => props.onCategoryChange(null)} type="button">
            <LibraryBig size={16} /><span>全部{typeLabel(props.activeType)}</span><small>{props.allMaterials.length}</small>
          </button>
          <button className={props.uncategorizedOnly ? 'selected' : ''} onClick={props.onUncategorizedChange} type="button">
            <Folder size={16} /><span>未分类</span><small>{props.allMaterials.filter((item) => item.categories.length === 0).length}</small>
          </button>
        </nav>
        <div className="material-custom-category-heading material-user-category-heading">
          <span>我的分类</span>
          <button aria-label="新增分类" onClick={props.onAddCategory} type="button"><FolderPlus size={14} /></button>
        </div>
        <nav aria-label="用户分类">
          {typeCategories.map((category) => (
            <button className={props.categoryId === category.id ? 'selected' : ''} key={category.id} onClick={() => props.onCategoryChange(category.id)} type="button">
              <Folder size={16} /><span>{category.name}</span><small>{category.material_count}</small>
            </button>
          ))}
          {typeCategories.length === 0 ? <p className="material-category-empty">暂无自定义分类</p> : null}
        </nav>
      </aside>
      <main className="material-card-shelf">
        <header>
          <label className="search-field material-library-search">
            <Search size={15} /><span className="sr-only">搜索素材</span>
            <input placeholder="搜索名称、摘要或分类" type="search" value={props.searchText} onChange={(event) => props.onSearchChange(event.target.value)} />
          </label>
        </header>
        {props.loading ? <MaterialEmpty text="正在读取素材库…" /> : props.materials.length ? (
          <div className="material-card-grid">
            {props.materials.map((material) => (
              <button className={`material-library-card ${props.selectedId === material.id ? 'selected' : ''}`} key={material.id} onClick={() => props.onSelect(material.id)} type="button">
                <div className="material-card-title"><strong>{material.name}</strong><span>v{material.version}</span></div>
                <p>{material.description || contentSummary(material.content)}</p>
                <div className="material-card-facts">
                  <span>{dimensionCount(material.content)} 个维度</span>
                  <span>{formatDate(material.updated_at)}</span>
                </div>
                <div className="material-card-tags">
                  {(material.categories.length ? material.categories : [typeLabel(material.material_type)]).slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}
                </div>
              </button>
            ))}
          </div>
        ) : <MaterialEmpty text="当前分类还没有素材，可导入 JSON 或使用 AI 提取。" />}
      </main>
      <aside className="material-inspector">
        {props.selected ? (
          <>
            <header><strong>{props.selected.name}</strong><span>{typeLabel(props.selected.material_type)}</span></header>
            <div className="material-inspector-scroll">
              <section><h3>内容摘要</h3><p>{props.selected.description || contentSummary(props.selected.content)}</p></section>
              <section><h3>结构维度</h3><StructuredPreview value={props.selected.content} /></section>
              <section><h3>来源</h3><p>{sourceLabel(props.selected)}</p></section>
              <section><h3>版本</h3><p>v{props.selected.version} · {formatDate(props.selected.updated_at)}</p></section>
            </div>
            <footer className="library-detail-footer">
              <SecondaryButton onClick={props.onCopy}><Copy size={14} />复制到工程</SecondaryButton>
              <SecondaryButton onClick={props.onEdit}><Pencil size={14} />打开编辑器</SecondaryButton>
            </footer>
          </>
        ) : <MaterialEmpty text="选择一张卡片查看详情。" />}
      </aside>
    </div>
  );
}

function ProjectMaterialTimeline(props: {
  hiddenLanes: Set<MaterialType>;
  loading: boolean;
  materials: Material[];
  onSelect: (id: number) => void;
  onToggleLane: (type: MaterialType) => void;
}) {
  const visibleTypes = materialTypes.filter((item) => !props.hiddenLanes.has(item.key));
  const nodes = useMemo(() => {
    const grouped = new Map<string, { start: number | null; end: number | null; materials: Material[] }>();
    for (const material of props.materials) {
      const key = `${material.timeline_start_chapter ?? 'pending'}:${material.timeline_end_chapter ?? 'pending'}`;
      const node = grouped.get(key) ?? { start: material.timeline_start_chapter, end: material.timeline_end_chapter, materials: [] };
      node.materials.push(material);
      grouped.set(key, node);
    }
    return [...grouped.values()].sort((left, right) => (left.start ?? Number.MAX_SAFE_INTEGER) - (right.start ?? Number.MAX_SAFE_INTEGER));
  }, [props.materials]);
  return (
    <div className="material-timeline-shell">
      <div className="material-lane-controls">
        <span>显示轨道</span>
        {materialTypes.map((type) => (
          <label key={type.key}>
            <input checked={!props.hiddenLanes.has(type.key)} onChange={() => props.onToggleLane(type.key)} type="checkbox" />
            {type.label}
          </label>
        ))}
      </div>
      <div className="material-timeline">
        <header className={`material-timeline-row material-timeline-heading lanes-${visibleTypes.length}`}>
          <div>时间节点</div>
          {visibleTypes.map((item) => <div key={item.key}>{item.label}</div>)}
        </header>
        {props.loading ? <MaterialEmpty text="正在读取工程时间线…" /> : nodes.length ? nodes.map((node, index) => (
          <div className={`material-timeline-row lanes-${visibleTypes.length}`} key={`${node.start}-${node.end}-${index}`}>
            <div className="material-time-node">
              <i />
              <strong>{chapterRange(node.start, node.end)}</strong>
              <span>{node.start === null ? '待定位素材' : `叙事节点 ${index + 1}`}</span>
            </div>
            {visibleTypes.map((type) => {
              const laneItems = node.materials.filter((item) => item.material_type === type.key);
              return (
                <div className="material-timeline-lane" key={type.key}>
                  {laneItems.length ? laneItems.map((material) => (
                    <button className="material-timeline-card" key={material.id} onClick={() => props.onSelect(material.id)} type="button">
                      <strong>{material.name}</strong>
                      <p>{material.description || contentSummary(material.content)}</p>
                      <span>关联 {chapterRange(material.timeline_start_chapter, material.timeline_end_chapter)} <ChevronRight size={13} /></span>
                    </button>
                  )) : <span className="material-lane-empty">尚未提取</span>}
                </div>
              );
            })}
          </div>
        )) : <MaterialEmpty text="工程尚无素材。使用 AI 提取后会按原文叙事顺序排列在这里。" />}
      </div>
    </div>
  );
}

function ExtractDialog(props: {
  busy: boolean;
  defaultProjectId: number | null;
  defaultType: MaterialType;
  documents: LibraryDocument[];
  projects: Project[];
  scope: MaterialScope;
  onClose: () => void;
  onExtract: (payload: {
    material_type: MaterialType;
    name: string | null;
    detail_level: StyleDetailLevel;
    sample_text?: string | null;
    source_project_id?: number | null;
    source_document_id?: number | null;
    scope: MaterialScope;
    project_id: number | null;
  }) => void;
}) {
  const [type, setType] = useState(props.defaultType);
  const [source, setSource] = useState<ExtractSource>('paste');
  const [name, setName] = useState('');
  const [detail, setDetail] = useState<StyleDetailLevel>('standard');
  const [text, setText] = useState('');
  const [sourceProjectId, setSourceProjectId] = useState<number | null>(props.defaultProjectId ?? props.projects[0]?.id ?? null);
  const [documentId, setDocumentId] = useState<number | null>(props.documents[0]?.id ?? null);
  const sourceReady = source === 'paste' ? Boolean(text.trim()) : source === 'project' ? sourceProjectId !== null : documentId !== null;
  return (
    <div className="material-dialog-backdrop" role="presentation">
      <section aria-modal="true" className="material-dialog" role="dialog">
        <header><div><span>AI 提取</span><h2>选择提取目标和文字来源</h2></div><button className="icon-button" disabled={props.busy} onClick={props.onClose} type="button"><X size={18} /></button></header>
        <div className="material-extract-type-grid">
          {materialTypes.map(({ icon: Icon, key, label }) => (
            <button className={type === key ? 'selected' : ''} key={key} onClick={() => setType(key)} type="button"><Icon size={18} /><strong>{label}</strong><span>{typeDescription(key)}</span></button>
          ))}
        </div>
        <div className="material-form-grid">
          <label><span className="form-label">建议名称（可留空）</span><input className="form-input" value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label><span className="form-label">细节等级</span><select className="form-input" value={detail} onChange={(event) => setDetail(event.target.value as StyleDetailLevel)}><option value="brief">简要</option><option value="standard">标准</option><option value="detailed">详细</option></select></label>
        </div>
        <div className="material-source-tabs">
          <button className={source === 'paste' ? 'selected' : ''} onClick={() => setSource('paste')} type="button">粘贴文本</button>
          <button className={source === 'project' ? 'selected' : ''} onClick={() => setSource('project')} type="button">工程内容</button>
          <button className={source === 'document' ? 'selected' : ''} onClick={() => setSource('document')} type="button">文档库</button>
        </div>
        {source === 'paste' ? <textarea className="material-source-textarea" placeholder={`粘贴需要提取${typeLabel(type)}的文字…`} value={text} onChange={(event) => setText(event.target.value)} /> : null}
        {source === 'project' ? <select className="form-input" value={sourceProjectId ?? ''} onChange={(event) => setSourceProjectId(Number(event.target.value) || null)}>{props.projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select> : null}
        {source === 'document' ? <select className="form-input" value={documentId ?? ''} onChange={(event) => setDocumentId(Number(event.target.value) || null)}>{props.documents.map((document) => <option key={document.id} value={document.id}>{document.title}</option>)}</select> : null}
        <footer><SecondaryButton disabled={props.busy} onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || !sourceReady} onClick={() => props.onExtract({
          material_type: type,
          name: name.trim() || null,
          detail_level: detail,
          sample_text: source === 'paste' ? text : null,
          source_project_id: source === 'project' ? sourceProjectId : null,
          source_document_id: source === 'document' ? documentId : null,
          scope: props.scope,
          project_id: props.scope === 'project' ? props.defaultProjectId : null,
        })}><Sparkles size={16} />开始提取</PrimaryButton></footer>
      </section>
    </div>
  );
}

function ImportDialog(props: {
  busy: boolean;
  defaultProjectId: number | null;
  defaultType: MaterialType;
  scope: MaterialScope;
  onClose: () => void;
  onImport: (raw: string, type: MaterialType) => void;
}) {
  const [type, setType] = useState(props.defaultType);
  const [raw, setRaw] = useState('');
  return (
    <div className="material-dialog-backdrop" role="presentation">
      <section aria-modal="true" className="material-dialog compact" role="dialog">
        <header><div><span>JSON 导入</span><h2>导入结构化素材</h2></div><button className="icon-button" onClick={props.onClose} type="button"><X size={18} /></button></header>
        <label><span className="form-label">素材类型</span><select className="form-input" value={type} onChange={(event) => setType(event.target.value as MaterialType)}>{materialTypes.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
        <textarea className="material-source-textarea" placeholder='{"name":"遗迹探索","description":"...","content":{}}' value={raw} onChange={(event) => setRaw(event.target.value)} />
        <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || !raw.trim() || (props.scope === 'project' && props.defaultProjectId === null)} onClick={() => props.onImport(raw, type)}><FileJson size={16} />导入 JSON</PrimaryButton></footer>
      </section>
    </div>
  );
}

function MaterialEditor(props: {
  busy: boolean;
  material: Material;
  onClose: () => void;
  onCopy: () => void;
  onDelete: () => void;
  onSave: (draft: MaterialDraft) => void;
}) {
  const [draft, setDraft] = useState<MaterialDraft>(() => ({
    name: props.material.name,
    description: props.material.description,
    detail_level: props.material.detail_level,
    contentText: JSON.stringify(props.material.content, null, 2),
    timeline_start_chapter: props.material.timeline_start_chapter?.toString() ?? '',
    timeline_end_chapter: props.material.timeline_end_chapter?.toString() ?? '',
  }));
  return (
    <div className="material-editor-backdrop" role="presentation">
      <section aria-modal="true" className="material-editor" role="dialog">
        <header>
          <div><span>{props.material.scope === 'public' ? '公共素材' : props.material.project_name}</span><h2>{props.material.name}</h2></div>
          <div><SecondaryButton onClick={props.onCopy}><Copy size={14} />生成副本</SecondaryButton><button className="icon-button" onClick={props.onClose} type="button"><X size={18} /></button></div>
        </header>
        <div className="material-editor-tabs"><button className="selected" type="button">结构内容</button><button disabled type="button">来源与版本</button></div>
        <div className="material-editor-content">
          <div className="material-editor-main">
            <div className="material-form-grid">
              <label><span className="form-label">名称</span><input className="form-input" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
              <label><span className="form-label">细节等级</span><select className="form-input" value={draft.detail_level} onChange={(event) => setDraft({ ...draft, detail_level: event.target.value as StyleDetailLevel })}><option value="brief">简要</option><option value="standard">标准</option><option value="detailed">详细</option></select></label>
            </div>
            <label><span className="form-label">摘要</span><textarea className="material-description-input" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
            <div className="material-visual-sections">
              {Object.entries(props.material.content).map(([key, value]) => <section key={key}><h3>{humanizeKey(key)}</h3><StructuredPreview value={value} /></section>)}
            </div>
          </div>
          <aside>
            {props.material.scope === 'project' ? (
              <section><h3>叙事位置</h3><div className="material-form-grid"><label><span className="form-label">起始章节</span><input className="form-input" min={1} type="number" value={draft.timeline_start_chapter} onChange={(event) => setDraft({ ...draft, timeline_start_chapter: event.target.value })} /></label><label><span className="form-label">结束章节</span><input className="form-input" min={1} type="number" value={draft.timeline_end_chapter} onChange={(event) => setDraft({ ...draft, timeline_end_chapter: event.target.value })} /></label></div></section>
            ) : null}
            <details><summary>高级 JSON</summary><p>用于导入、导出及修正复杂嵌套结构。</p><textarea className="material-json-editor" value={draft.contentText} onChange={(event) => setDraft({ ...draft, contentText: event.target.value })} /></details>
          </aside>
        </div>
        <footer><DangerButton disabled={props.busy} onClick={props.onDelete}><Trash2 size={15} />删除</DangerButton><div><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || !draft.name.trim()} onClick={() => props.onSave(draft)}>保存全部</PrimaryButton></div></footer>
      </section>
    </div>
  );
}

function StructuredPreview({ value }: { value: unknown }) {
  if (Array.isArray(value)) return <div className="material-structured-list">{value.map((item, index) => <div key={index}>{isObject(item) ? <StructuredPreview value={item} /> : String(item)}</div>)}</div>;
  if (isObject(value)) return <dl className="material-structured-definitions">{Object.entries(value).slice(0, 8).map(([key, item]) => <div key={key}><dt>{humanizeKey(key)}</dt><dd>{Array.isArray(item) ? item.map(String).join('、') : isObject(item) ? `${Object.keys(item).length} 个字段` : String(item ?? '—')}</dd></div>)}</dl>;
  return <p>{String(value ?? '—')}</p>;
}

function MaterialEmpty({ text }: { text: string }) {
  return <div className="material-empty"><Boxes size={24} /><span>{text}</span></div>;
}

function typeLabel(type: MaterialType) {
  return materialTypes.find((item) => item.key === type)?.label ?? type;
}

function typeDescription(type: MaterialType) {
  if (type === 'outline') return '整部作品的整体结构';
  if (type === 'plot_skeleton') return '可复用的经典剧情模式';
  return '可插入场景的原子素材';
}

function contentSummary(content: Record<string, unknown>) {
  const first = Object.values(content).find((value) => typeof value === 'string' && value.trim());
  return typeof first === 'string' ? first : `${Object.keys(content).slice(0, 3).map(humanizeKey).join('、') || '结构化内容'}`;
}

function dimensionCount(content: Record<string, unknown>) {
  return Object.keys(content).length;
}

function sourceLabel(material: Material) {
  if (material.source_material_id) return `副本来源 #${material.source_material_id} · v${material.source_version ?? 1}`;
  const type = String(material.source_metadata.source_type ?? '');
  if (type === 'project') return `工程：${String(material.source_metadata.source_project_name ?? '')}`;
  if (type === 'document_library') return `文档库：${String(material.source_metadata.source_document_title ?? '')}`;
  if (type === 'paste') return '粘贴文本 AI 提取';
  return material.import_metadata.migrated_from ? '旧版大纲迁移' : '手动导入';
}

function chapterRange(start: number | null, end: number | null) {
  if (start === null) return '待定位';
  return end && end !== start ? `第 ${start}–${end} 章` : `第 ${start} 章`;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN');
}

function humanizeKey(key: string) {
  const labels: Record<string, string> = {
    story_scope: '故事范围',
    volumes_or_phases: '分卷与阶段',
    major_plot_beats: '关键剧情节点',
    causal_chain: '因果链',
    character_progression: '人物进展',
    timeline: '时间线',
    unresolved_hooks: '未解线索',
    applicable_scenarios: '适用场景',
    prerequisites: '前置条件',
    participants_and_roles: '参与者与角色',
    stages: '发展阶段',
    turning_points: '转折',
    climax: '高潮',
    outcomes: '结果',
    reusable_variants: '可复用变体',
    snippet_kind: '素材类别',
    trigger: '触发条件',
    actions: '动作',
    sensory_description: '感官描写',
    effect_or_power: '效果与威力',
    cost: '代价',
    constraints: '限制',
  };
  return labels[key] ?? key.split('_').join(' ');
}

function parseJsonObject(value: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value);
  if (!isObject(parsed)) throw new Error('JSON 顶层必须是对象。');
  return parsed;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isDetailLevel(value: unknown): value is StyleDetailLevel {
  return value === 'brief' || value === 'standard' || value === 'detailed';
}

function positiveNumber(value: string) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

function numberOrNull(value: unknown) {
  return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : null;
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}
