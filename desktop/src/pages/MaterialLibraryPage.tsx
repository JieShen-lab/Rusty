import { useEffect, useMemo, useState } from 'react';
import { Copy, MoreHorizontal, Pencil, Plus, Search, Sparkles, Tag, Trash2 } from 'lucide-react';
import {
  analyzeMaterial,
  copyMaterial,
  createMaterial,
  createMaterialTag,
  deleteMaterial,
  deleteMaterialTag,
  getMaterialTags,
  getMaterials,
  getProjects,
  updateMaterial,
} from '../api/client';
import type { AnalysisStatus, Material, MaterialScope, MaterialType, Project, ResourceTag } from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';

const materialTypes: Array<{ key: MaterialType; label: string }> = [
  { key: 'scene_reference', label: '场景素材' },
  { key: 'plot_skeleton', label: '剧情骨架' },
];

type Filter = 'all' | 'unanalyzed' | 'scene_reference' | 'plot_skeleton' | 'untagged';

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = materials.find((item) => item.id === selectedId) ?? materials[0] ?? null;
  const filtered = useMemo(() => materials.filter((item) => {
    const text = `${item.name} ${item.description} ${item.raw_text} ${item.tags.join(' ')}`.toLowerCase();
    return !query.trim() || text.includes(query.trim().toLowerCase());
  }), [materials, query]);

  async function load(preferredId?: number | null) {
    setBusy(true);
    setError(null);
    try {
      const [projectItems, tagItems] = await Promise.all([getProjects(), getMaterialTags()]);
      const nextProjectId = projectId ?? projectItems[0]?.id ?? null;
      const materialItems = await getMaterials({
        scope,
        project_id: scope === 'project' && nextProjectId ? nextProjectId : undefined,
        material_type: filter === 'scene_reference' || filter === 'plot_skeleton' ? filter : undefined,
        analysis_status: filter === 'unanalyzed' ? 'unanalyzed' : undefined,
        untagged: filter === 'untagged',
        tag_id: tagId ?? undefined,
      });
      setProjects(projectItems);
      setProjectId(nextProjectId);
      setTags(tagItems);
      setMaterials(materialItems);
      setSelectedId(preferredId ?? materialItems[0]?.id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, [scope, projectId, filter, tagId]);

  async function createBlank(type: MaterialType) {
    const name = window.prompt(type === 'scene_reference' ? '场景素材名称' : '剧情骨架名称');
    if (!name?.trim()) return;
    const created = await createMaterial({
      material_type: type,
      scope,
      project_id: scope === 'project' ? projectId : null,
      name: name.trim(),
      description: '',
      raw_text: '',
      content: {},
      analysis_status: 'analyzed',
      tag_ids: [],
    });
    await load(created.id);
    setEditing(created);
  }

  async function addTag() {
    const name = window.prompt('新增标签');
    if (!name?.trim()) return;
    const tag = await createMaterialTag(name);
    setTagId(tag.id);
    await load(selectedId);
  }

  async function removeTag(id: number) {
    if (!window.confirm('删除标签只会解除关联，不会删除素材。')) return;
    await deleteMaterialTag(id);
    if (tagId === id) setTagId(null);
    await load(selectedId);
  }

  async function copySelected(material: Material) {
    if (material.scope === 'public') {
      if (!projectId) {
        setError('请先选择目标工程。');
        return;
      }
      const copied = await copyMaterial(material.id, 'project', projectId);
      await load(copied.id);
      return;
    }
    if (!window.confirm('确认将该工程素材保存为新的公共素材副本？')) return;
    const copied = await copyMaterial(material.id, 'public', null);
    await load(copied.id);
  }

  async function runAnalyze(material: Material) {
    const raw = window.prompt('粘贴 AI 分析得到的 JSON 对象。失败不会覆盖已有内容。', JSON.stringify(material.content, null, 2));
    if (!raw) return;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const updated = await analyzeMaterial(material.id, parsed);
    await load(updated.id);
  }

  async function saveMaterial(material: Material, next: { name: string; description: string; raw_text: string; content: string; analysis_status: AnalysisStatus }) {
    const updated = await updateMaterial(material.id, {
      name: next.name,
      description: next.description,
      raw_text: next.raw_text,
      content: JSON.parse(next.content) as Record<string, unknown>,
      analysis_status: next.analysis_status,
      detail_level: material.detail_level,
      sort_order: material.sort_order,
    });
    setEditing(null);
    await load(updated.id);
  }

  return (
    <div className="resource-page">
      <TopBar title="素材库" actions={(
        <>
          <SecondaryButton disabled={busy} onClick={() => createBlank('scene_reference')}><Plus size={16} />场景素材</SecondaryButton>
          <PrimaryButton disabled={busy} onClick={() => createBlank('plot_skeleton')}><Plus size={16} />剧情骨架</PrimaryButton>
        </>
      )} />
      {error ? <div className="inline-alert error">{error}</div> : null}
      <div className="resource-layout">
        <aside className="resource-sidebar">
          <button className={scope === 'public' ? 'selected' : ''} onClick={() => { setScope('public'); setTagId(null); }}>公共素材</button>
          <button className={scope === 'project' ? 'selected' : ''} onClick={() => { setScope('project'); setTagId(null); }}>工程素材</button>
          {scope === 'project' ? (
            <select value={projectId ?? ''} onChange={(event) => setProjectId(Number(event.target.value) || null)}>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          ) : null}
          <hr />
          {[
            ['all', '全部'],
            ['unanalyzed', '未分析'],
            ['scene_reference', '场景素材'],
            ['plot_skeleton', '剧情骨架'],
            ['untagged', '无标签'],
          ].map(([key, label]) => (
            <button className={filter === key && tagId === null ? 'selected' : ''} key={key} onClick={() => { setFilter(key as Filter); setTagId(null); }}>{label}</button>
          ))}
          <div className="resource-sidebar-title"><span>我的标签</span><button onClick={addTag} type="button"><Plus size={14} /></button></div>
          {tags.map((item) => (
            <div className="resource-tag-row" key={item.id}>
              <button className={tagId === item.id ? 'selected' : ''} onClick={() => { setTagId(item.id); setFilter('all'); }}><Tag size={14} />{item.name}<small>{item.resource_count}</small></button>
              <button aria-label="删除标签" onClick={() => removeTag(item.id)} type="button"><Trash2 size={13} /></button>
            </div>
          ))}
        </aside>
        <main className="resource-main">
          <label className="search-field"><Search size={15} /><input placeholder="搜索名称、说明、原文或标签" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <div className="resource-card-grid">
            {filtered.map((material) => (
              <article className={`resource-card ${selectedId === material.id ? 'selected' : ''}`} key={material.id} onClick={() => setSelectedId(material.id)}>
                <header><strong>{material.name}</strong><span>{typeLabel(material.material_type)}</span></header>
                <p>{material.description || material.raw_text.slice(0, 96) || structuredSummary(material.content)}</p>
                <div className="resource-badges"><span>{material.analysis_status === 'unanalyzed' ? '未分析' : '已分析'}</span>{material.tags.slice(0, 3).map((tag) => <span key={tag}>{tag}</span>)}</div>
                <div className="resource-card-menu">
                  <button onClick={(event) => { event.stopPropagation(); setEditing(material); }} title="编辑" type="button"><Pencil size={15} /></button>
                  <button onClick={(event) => { event.stopPropagation(); copySelected(material); }} title={material.scope === 'public' ? '添加到工程' : '添加到公共素材'} type="button"><Copy size={15} /></button>
                  {material.analysis_status === 'unanalyzed' ? <button onClick={(event) => { event.stopPropagation(); runAnalyze(material); }} title="AI 分析" type="button"><Sparkles size={15} /></button> : null}
                  <button onClick={(event) => { event.stopPropagation(); if (window.confirm('确认删除素材？')) deleteMaterial(material.id).then(() => load(null)); }} title="删除" type="button"><MoreHorizontal size={15} /></button>
                </div>
              </article>
            ))}
          </div>
        </main>
        <aside className="resource-detail">
          {selected ? (
            <>
              <h2>{selected.name}</h2>
              <p>{typeLabel(selected.material_type)} · {selected.analysis_status === 'unanalyzed' ? '未分析' : '已分析'} · v{selected.version}</p>
              <section><h3>标签</h3><p>{selected.tags.length ? selected.tags.join(' / ') : '无标签'}</p></section>
              <section><h3>内容摘要</h3><p>{selected.description || selected.raw_text.slice(0, 200) || structuredSummary(selected.content)}</p></section>
              <section><h3>结构化内容</h3><pre>{JSON.stringify(selected.content, null, 2)}</pre></section>
              <section><h3>来源</h3><p>{selected.source_material_id ? `副本来源 #${selected.source_material_id}` : String(selected.source_metadata.source_kind ?? selected.source_metadata.source_type ?? '本地创建')}</p></section>
            </>
          ) : <p>选择一个素材查看详情。</p>}
        </aside>
      </div>
      {editing ? <MaterialEditor material={editing} onClose={() => setEditing(null)} onSave={saveMaterial} /> : null}
    </div>
  );
}

function MaterialEditor({ material, onClose, onSave }: {
  material: Material;
  onClose: () => void;
  onSave: (material: Material, next: { name: string; description: string; raw_text: string; content: string; analysis_status: AnalysisStatus }) => void;
}) {
  const [name, setName] = useState(material.name);
  const [description, setDescription] = useState(material.description);
  const [rawText, setRawText] = useState(material.raw_text);
  const [content, setContent] = useState(JSON.stringify(material.content, null, 2));
  const [status, setStatus] = useState<AnalysisStatus>(material.analysis_status);
  return (
    <div className="modal-backdrop">
      <section className="resource-editor" role="dialog" aria-modal="true">
        <header><h2>编辑素材</h2><p>类型只读：{typeLabel(material.material_type)}</p></header>
        <label>名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>说明<textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <label>分析状态<select value={status} onChange={(event) => setStatus(event.target.value as AnalysisStatus)}><option value="unanalyzed">未分析</option><option value="analyzed">已分析</option></select></label>
        <label>原始文字<textarea value={rawText} onChange={(event) => setRawText(event.target.value)} /></label>
        <label>结构化内容 JSON<textarea value={content} onChange={(event) => setContent(event.target.value)} /></label>
        <footer><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={!name.trim()} onClick={() => onSave(material, { name, description, raw_text: rawText, content, analysis_status: status })}>保存</PrimaryButton></footer>
      </section>
    </div>
  );
}

function typeLabel(type: MaterialType) {
  return materialTypes.find((item) => item.key === type)?.label ?? type;
}

function structuredSummary(content: Record<string, unknown>) {
  return Object.keys(content).length ? Object.keys(content).join(' / ') : '暂无结构化内容';
}
