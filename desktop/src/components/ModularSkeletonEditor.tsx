import { useEffect, useState } from 'react';
import type { StructuredEventNode, StructuredSkeleton, WorkflowObject } from '../api/types';

type SkeletonListKey = Exclude<{
  [K in keyof StructuredSkeleton]: StructuredSkeleton[K] extends unknown[] ? K : never
}[keyof StructuredSkeleton], 'event_nodes' | 'source_references'>;
type SkeletonItem = Record<string, unknown>;
type ItemField = { key: string; label: string; kind?: 'event' };

const modules: Array<{ key: SkeletonListKey; label: string; fields: ItemField[] }> = [
  { key: 'causal_links', label: '因果关系', fields: [{ key: 'source_id', label: '原因事件', kind: 'event' }, { key: 'target_id', label: '结果事件', kind: 'event' }, { key: 'relation', label: '关系' }] },
  { key: 'character_state_changes', label: '人物状态变化', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'character_id', label: '人物' }, { key: 'attribute', label: '属性' }, { key: 'before', label: '变化前' }, { key: 'after', label: '变化后' }] },
  { key: 'location_changes', label: '地点变化', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'character_id', label: '人物' }, { key: 'from', label: '原地点' }, { key: 'to', label: '新地点' }] },
  { key: 'time_changes', label: '时间变化', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'from', label: '原时间' }, { key: 'to', label: '新时间' }] },
  { key: 'object_changes', label: '物品变化', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'object_id', label: '物品' }, { key: 'change', label: '变化' }] },
  { key: 'knowledge_changes', label: '知识变化', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'character_id', label: '人物' }, { key: 'fact', label: '事实' }, { key: 'before', label: '变化前' }, { key: 'after', label: '变化后' }] },
  { key: 'relationship_changes', label: '关系变化', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'source_character_id', label: '人物 A' }, { key: 'target_character_id', label: '人物 B' }, { key: 'change', label: '变化' }] },
  { key: 'foreshadowing', label: '伏笔', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'summary', label: '内容' }, { key: 'status', label: '状态' }] },
  { key: 'open_threads', label: '未解决线索', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'summary', label: '内容' }, { key: 'status', label: '状态' }] },
  { key: 'resolved_threads', label: '已解决线索', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'summary', label: '内容' }, { key: 'resolution', label: '解决方式' }] },
  { key: 'editable_points', label: '可编辑点', fields: [{ key: 'event_id', label: '关联事件', kind: 'event' }, { key: 'description', label: '说明' }] },
];

export type SkeletonVersionInfo = {
  version: number;
  status: 'draft' | 'confirmed';
  previousVersion?: number | null;
};

export function ModularSkeletonEditor({
  onChange,
  onConfirm,
  skeleton,
  versionInfo,
}: {
  onChange?: (value: StructuredSkeleton) => void;
  onConfirm?: (value: StructuredSkeleton) => void;
  skeleton: StructuredSkeleton;
  versionInfo?: SkeletonVersionInfo | null;
}) {
  const [current, setCurrent] = useState(skeleton);
  useEffect(() => setCurrent(skeleton), [skeleton]);
  function update(value: StructuredSkeleton) { setCurrent(value); onChange?.(value); }
  function updateList(key: SkeletonListKey, items: SkeletonItem[]) {
    update({ ...current, [key]: items } as StructuredSkeleton);
  }
  function reorder(from: number, to: number) {
    const nodes = [...current.event_nodes];
    const [moved] = nodes.splice(from, 1);
    nodes.splice(to, 0, moved);
    update({ ...current, event_nodes: nodes.map((node, index) => ({ ...node, order: index + 1 })) });
  }
  return (
    <section className="modular-skeleton-editor wide" aria-label="模块化细纲编辑器">
      <header>
        <div><span>模块化细纲</span><h3>结构化版本</h3></div>
        {versionInfo ? <p aria-label="细纲版本信息">当前版本 v{versionInfo.version} · {versionInfo.status === 'confirmed' ? '已确认' : '草稿'} · 上一版本 {versionInfo.previousVersion ? `v${versionInfo.previousVersion}` : '无'}</p> : null}
      </header>
      <EventNodeEditor nodes={current.event_nodes} onChange={(event_nodes) => update({ ...current, event_nodes })} onReorder={reorder} />
      {modules.map((module) => (
        <RecordListEditor
          eventNodes={current.event_nodes}
          fields={module.fields}
          items={(current[module.key] as SkeletonItem[]) ?? []}
          key={module.key}
          label={module.label}
          onChange={(items) => updateList(module.key, items)}
        />
      ))}
      <StateConstraintEditor label="开始状态" onChange={(required_start_state) => update({ ...current, required_start_state })} value={current.required_start_state} />
      <StateConstraintEditor label="结束状态 / 回接条件" onChange={(required_end_state) => update({ ...current, required_end_state })} value={current.required_end_state} />
      <SourceReferenceViewer items={(current.source_references as SkeletonItem[]) ?? []} />
      {onConfirm ? <button className="button primary" onClick={() => onConfirm(current)} type="button">确认目标细纲</button> : null}
    </section>
  );
}

function EventNodeEditor({ nodes, onChange, onReorder }: { nodes: StructuredEventNode[]; onChange: (nodes: StructuredEventNode[]) => void; onReorder: (from: number, to: number) => void }) {
  const edit = (id: string, value: Partial<StructuredEventNode>) => onChange(nodes.map((node) => node.id === id ? { ...node, ...value } : node));
  return <section aria-label="事件链编辑器"><header><h4>事件链</h4><button onClick={() => onChange([...nodes, emptyEvent(nodes.length + 1)])} type="button">插入事件</button></header>{nodes.map((node, index) => <article draggable key={node.id} onDragOver={(event) => event.preventDefault()} onDragStart={(event) => event.dataTransfer.setData('text/plain', String(index))} onDrop={(event) => onReorder(Number(event.dataTransfer.getData('text/plain')), index)}><span aria-label="拖拽排序">⋮</span><strong>{index + 1}</strong><label>摘要<input aria-label={`事件 ${index + 1}`} onChange={(event) => edit(node.id, { summary: event.target.value })} value={node.summary} /></label><label>类型<input onChange={(event) => edit(node.id, { event_type: event.target.value })} value={node.event_type} /></label><label>参与者<input onChange={(event) => edit(node.id, { participants: splitValues(event.target.value) })} value={node.participants.join(', ')} /></label><label>地点<input onChange={(event) => edit(node.id, { location: event.target.value })} value={node.location} /></label><label>时间状态<input onChange={(event) => edit(node.id, { time_state: { label: event.target.value } })} value={String(node.time_state.label ?? '')} /></label><label>原因事件<input onChange={(event) => edit(node.id, { causes: splitValues(event.target.value) })} value={node.causes.join(', ')} /></label><label>结果事件<input onChange={(event) => edit(node.id, { effects: splitValues(event.target.value) })} value={node.effects.join(', ')} /></label><label>动机<input onChange={(event) => edit(node.id, { motivation: event.target.value })} value={node.motivation ?? ''} /></label><label>知识变化<input onChange={(event) => edit(node.id, { knowledge_changes: splitValues(event.target.value) })} value={(node.knowledge_changes ?? []).join(', ')} /></label><label><input checked={node.locked} onChange={(event) => edit(node.id, { locked: event.target.checked })} type="checkbox" />锁定</label><button disabled={node.locked || nodes.length === 1} onClick={() => onChange(nodes.filter((item) => item.id !== node.id))} type="button">删除</button><small>来源范围：{formatValue(node.source_span)}</small></article>)}</section>;
}

function RecordListEditor({ eventNodes, fields, items, label, onChange }: { eventNodes: StructuredEventNode[]; fields: ItemField[]; items: SkeletonItem[]; label: string; onChange: (items: SkeletonItem[]) => void }) {
  const add = () => onChange([...items, Object.fromEntries(fields.map((field) => [field.key, field.kind === 'event' ? (eventNodes[0]?.id ?? '') : '']))]);
  const edit = (index: number, key: string, value: string) => onChange(items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  return <section aria-label={`${label}编辑器`}><header><h4>{label}</h4><button onClick={add} type="button">新增{label}</button></header>{items.length === 0 ? <p>暂无记录。</p> : items.map((item, index) => <article key={`${label}-${index}`}>{fields.map((field) => <label key={field.key}>{field.label}{field.kind === 'event' ? <select aria-label={`${label} ${index + 1} ${field.label}`} onChange={(event) => edit(index, field.key, event.target.value)} value={String(item[field.key] ?? '')}><option value="">未关联</option>{eventNodes.map((node) => <option key={node.id} value={node.id}>{node.order}. {node.summary || node.id}</option>)}</select> : <input aria-label={`${label} ${index + 1} ${field.label}`} onChange={(event) => edit(index, field.key, event.target.value)} value={formatScalar(item[field.key])} />}</label>)}<button onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))} type="button">删除</button></article>)}</section>;
}

type ValueKind = 'text' | 'number' | 'boolean' | 'array' | 'object';
function StateConstraintEditor({ label, onChange, value }: { label: string; onChange: (value: WorkflowObject) => void; value: WorkflowObject }) {
  const entries = Object.entries(value);
  const rename = (oldKey: string, newKey: string) => { const next = { ...value }; const current = next[oldKey]; delete next[oldKey]; if (newKey) next[newKey] = current; onChange(next); };
  const setValue = (key: string, nextValue: unknown) => onChange({ ...value, [key]: nextValue });
  return <section aria-label={`${label}编辑器`}><header><h4>{label}</h4><button onClick={() => onChange({ ...value, [`字段${entries.length + 1}`]: '' })} type="button">增加字段</button></header>{entries.map(([key, item]) => { const kind = valueKind(item); return <article key={key}><label>字段<input aria-label={`${label}字段名`} onBlur={(event) => rename(key, event.target.value.trim())} defaultValue={key} /></label><label>类型<select aria-label={`${label} ${key} 类型`} onChange={(event) => setValue(key, defaultForKind(event.target.value as ValueKind))} value={kind}><option value="text">文本</option><option value="number">数字</option><option value="boolean">布尔值</option><option value="array">数组</option><option value="object">对象</option></select></label>{kind === 'boolean' ? <label>值<select aria-label={`${label} ${key}`} onChange={(event) => setValue(key, event.target.value === 'true')} value={String(item)}><option value="true">true</option><option value="false">false</option></select></label> : <label>值<input aria-label={`${label} ${key}`} onChange={(event) => setValue(key, parseTypedValue(kind, event.target.value))} value={formatTypedValue(kind, item)} /></label>}<button onClick={() => { const next = { ...value }; delete next[key]; onChange(next); }} type="button">删除</button></article>; })}</section>;
}

function SourceReferenceViewer({ items }: { items: SkeletonItem[] }) {
  return <section aria-label="来源引用"><header><h4>来源引用（只读）</h4></header>{items.length === 0 ? <p>暂无来源记录。</p> : items.map((item, index) => <article key={index}><dl>{Object.entries(item).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{formatValue(value)}</dd></div>)}</dl></article>)}</section>;
}

function emptyEvent(order: number): StructuredEventNode { return { id: crypto.randomUUID(), order, event_type: 'user_event', summary: '', participants: [], location: '', time_state: {}, causes: [], effects: [], motivation: '', knowledge_changes: [], locked: false, source_span: null, confidence: 1 }; }
function splitValues(value: string) { return value.split(',').map((item) => item.trim()).filter(Boolean); }
function formatScalar(value: unknown) { return typeof value === 'string' ? value : value == null ? '' : formatValue(value); }
function formatValue(value: unknown) { return typeof value === 'string' ? value : JSON.stringify(value); }
function valueKind(value: unknown): ValueKind { if (Array.isArray(value)) return 'array'; if (typeof value === 'number') return 'number'; if (typeof value === 'boolean') return 'boolean'; if (value && typeof value === 'object') return 'object'; return 'text'; }
function defaultForKind(kind: ValueKind): unknown { return kind === 'number' ? 0 : kind === 'boolean' ? false : kind === 'array' ? [] : kind === 'object' ? {} : ''; }
function formatTypedValue(kind: ValueKind, value: unknown) { if (kind === 'array') return (value as unknown[]).map(formatScalar).join(', '); if (kind === 'object') return Object.entries(value as WorkflowObject).map(([key, item]) => `${key}=${formatScalar(item)}`).join(', '); return String(value ?? ''); }
function parseTypedValue(kind: ValueKind, value: string): unknown { if (kind === 'number') return Number(value) || 0; if (kind === 'array') return splitValues(value); if (kind === 'object') return Object.fromEntries(splitValues(value).map((item) => { const [key, ...rest] = item.split('='); return [key.trim(), rest.join('=').trim()]; }).filter(([key]) => key)); return value; }
