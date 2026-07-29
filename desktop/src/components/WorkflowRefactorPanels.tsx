import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { GitBranch, GitFork, ListTree, Plus, RefreshCw, Settings2 } from 'lucide-react';
import { createStoryBranch, deleteStoryBranch, getStoryBranches } from '../api/client';
import type { StoryBranch } from '../api/types';

type Operation = 'plot_generation' | 'prose_rewrite' | 'canon_change';

export function RewriteOperationPanel() {
  const [operation, setOperation] = useState<Operation>('plot_generation');
  return (
    <section className="workflow-operation-panel" aria-label="改写操作">
      <header><div><span>改写工程</span><h2>选择本次写作操作</h2></div></header>
      <div className="workflow-operation-grid">
        <OperationButton active={operation === 'plot_generation'} icon={<Plus size={18} />} label="增加剧情" onClick={() => setOperation('plot_generation')} />
        <OperationButton active={operation === 'prose_rewrite'} icon={<RefreshCw size={18} />} label="重写正文" onClick={() => setOperation('prose_rewrite')} />
        <OperationButton active={operation === 'canon_change'} icon={<Settings2 size={18} />} label="修改设定" onClick={() => setOperation('canon_change')} />
      </div>
      {operation === 'plot_generation' ? <div className="operation-fields"><label>起点<select><option>选择章节、场景或细纲节点</option></select></label><label>回接点<select><option>选择后续回接节点</option></select></label><label className="wide">新增剧情目标<textarea placeholder="描述要增加的事件、人物目标与限制" /></label><label>人物<input placeholder="选择人物" /></label><label>素材<input placeholder="选择剧情骨架素材" /></label><label>风格<input placeholder="选择风格参考" /></label></div> : null}
      {operation === 'prose_rewrite' ? <div className="operation-fields"><label>范围<select><option>当前场景</option></select></label><label>源细纲<select><option>已确认版本</option></select></label><label className="wide">锁定内容<input value="事件、顺序、结果、因果、起止状态" readOnly /></label><label>目标风格<input placeholder="选择或描述新风格" /></label></div> : null}
      {operation === 'canon_change' ? <div className="operation-fields"><label>旧设定<input placeholder="例如：左臂受伤" /></label><label>新设定<input placeholder="例如：腿部受伤" /></label><label>生效点<select><option>选择章节或场景</option></select></label><label>扫描范围<select><option>当前路线后续</option></select></label><CanonPatchReview /></div> : null}
    </section>
  );
}

export function BranchWorkspacePanel({ defaultChapterId, projectId, projectName }: { defaultChapterId?: number; projectId: number; projectName: string }) {
  const [mode, setMode] = useState<'open_continuation' | 'fork' | 'fork_and_rejoin'>('open_continuation');
  const [branches, setBranches] = useState<StoryBranch[]>([]);
  const [currentBranchId, setCurrentBranchId] = useState<number | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    void getStoryBranches(projectId)
      .then((items) => {
        setBranches(items);
        setError('');
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '无法读取分支'));
  }, [projectId]);
  async function createBranch() {
    try {
      const created = await createStoryBranch(projectId, {
        name: `分支 ${String.fromCharCode(65 + branches.length)}`,
        branch_mode: mode,
        parent_branch_id: currentBranchId,
        start_anchor: mode === 'open_continuation' ? { anchor_type: 'document_end' } : { anchor_type: 'chapter_end', chapter_id: defaultChapterId },
        return_anchor: mode === 'fork_and_rejoin' ? { anchor_type: 'chapter_end', chapter_id: defaultChapterId } : null,
      });
      setBranches((items) => [...items, created]);
      setCurrentBranchId(created.id);
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建分支失败');
    }
  }
  async function removeCurrentBranch() {
    if (currentBranchId === null) return;
    try {
      await deleteStoryBranch(currentBranchId);
      setBranches((items) => items.filter((item) => item.id !== currentBranchId));
      setCurrentBranchId(null);
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除分支失败');
    }
  }
  const currentBranch = branches.find((branch) => branch.id === currentBranchId) ?? null;
  return (
    <div className="branch-workspace">
      <header><div><span>扩写工程</span><h1>{projectName}</h1><p>新路线与原始基线独立保存，可从原文或已有分支继续派生。</p></div></header>
      <div className="branch-action-grid" aria-label="扩写入口">
        <OperationButton active={mode === 'open_continuation'} icon={<GitBranch size={18} />} label="从原文末尾续写" onClick={() => setMode('open_continuation')} />
        <OperationButton active={mode === 'fork'} icon={<GitFork size={18} />} label="从指定节点建立分支" onClick={() => setMode('fork')} />
        <OperationButton active={mode === 'fork_and_rejoin'} icon={<ListTree size={18} />} label="建立分支并接回原文" onClick={() => setMode('fork_and_rejoin')} />
      </div>
      <div className="branch-layout">
        <aside aria-label="分支树"><h2>分支树</h2><ul><li><button onClick={() => setCurrentBranchId(null)} type="button">原文</button></li>{branches.map((branch) => <li key={branch.id}><button aria-current={branch.id === currentBranchId ? 'true' : undefined} onClick={() => setCurrentBranchId(branch.id)} type="button">{branch.parent_branch_id ? '  └─ ' : '└─ '}{branch.name}</button></li>)}</ul><button className="button secondary" onClick={() => void createBranch()} type="button">创建子分支</button>{currentBranch ? <button className="button ghost" onClick={() => void removeCurrentBranch()} type="button">删除未使用分支</button> : null}</aside>
        <main><h2>{mode === 'open_continuation' ? '末尾续写' : mode === 'fork' ? '节点分支' : '分支回接'}</h2>{error ? <p role="alert">{error}</p> : null}{currentBranch ? <div className="branch-current-details"><span>当前：{currentBranch.name}</span><span>父分支：{currentBranch.parent_branch_id ?? '原文'}</span><span>模式：{currentBranch.branch_mode}</span><button type="button">比较分支与原始路线</button></div> : null}<div className="operation-fields"><label>起点<select><option>{mode === 'open_continuation' ? '文档末尾' : '选择章节、场景或细纲节点'}</option></select></label>{mode === 'fork_and_rejoin' ? <label>回接点<select><option>选择原文回接节点</option></select></label> : null}<label className="wide">剧情目标<textarea placeholder="描述新路线" /></label></div><button className="button primary" onClick={() => void createBranch()} type="button">创建分支</button><ModularSkeletonEditor /></main>
      </div>
    </div>
  );
}

export function LegacyExtractPanel({ onCreateNew, onExport, projectName }: { onCreateNew: () => void; onExport: () => void; projectName: string }) {
  return <div className="legacy-extract-panel"><span>旧版兼容</span><h1>{projectName}</h1><p>此项目属于旧版分析工程。<br />可以查看和导出已有分析结果，<br />或基于原文创建新的改写工程或扩写工程。</p><div><button className="button secondary" onClick={onExport} type="button">导出已有分析</button><button className="button primary" onClick={onCreateNew} type="button">基于此项目创建新工程</button></div><small>当前工作区只读，旧提取主流程已停用。</small></div>;
}

export function ModularSkeletonEditor() {
  const [nodes, setNodes] = useState([{ id: 'event-1', summary: '新事件节点', locked: false }]);
  function reorder(from: number, to: number) {
    setNodes((items) => {
      const next = [...items];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  }
  return <section className="modular-skeleton-editor" aria-label="模块化细纲编辑器"><header><div><span>模块化细纲</span><h3>事件链</h3></div><button className="button secondary" onClick={() => setNodes((items) => [...items, { id: `event-${items.length + 1}`, summary: '新事件节点', locked: false }])} type="button">插入事件</button></header>{nodes.map((node, index) => <article draggable key={node.id} onDragOver={(event) => event.preventDefault()} onDragStart={(event) => event.dataTransfer.setData('text/plain', String(index))} onDrop={(event) => reorder(Number(event.dataTransfer.getData('text/plain')), index)}><span className="drag-handle" aria-label="拖拽排序">⠿</span><strong>{index + 1}</strong><input aria-label={`事件 ${index + 1}`} onChange={(event) => setNodes((items) => items.map((item) => item.id === node.id ? { ...item, summary: event.target.value } : item))} value={node.summary} /><label><input checked={node.locked} onChange={(event) => setNodes((items) => items.map((item) => item.id === node.id ? { ...item, locked: event.target.checked } : item))} type="checkbox" />锁定</label><button aria-label={`删除事件 ${index + 1}`} disabled={node.locked} onClick={() => setNodes((items) => items.filter((item) => item.id !== node.id))} type="button">删除</button><small>来源 · 因果关系</small></article>)}<div className="skeleton-module-grid">{['人物状态', '时间与地点', '物品变化', '知识变化', '关系变化', '伏笔', '未解决线索', '开始状态', '结束状态', '插入点', '回接条件'].map((label) => <button key={label} type="button">{label}</button>)}</div></section>;
}

export function SeamReview() {
  const [status, setStatus] = useState('待确认');
  return <section className="seam-review" aria-label="接缝审查"><h3>接缝审查</h3><div><strong>原文</strong><p>人物进入院子。</p></div><div><strong>建议修改</strong><textarea defaultValue="人物进入院子，墙后忽然传来脚步声。" /></div><p>修改原因：为新增剧情建立自然进入接缝。影响范围：当前句。</p><footer><button onClick={() => setStatus('已确认')} type="button">确认</button><button onClick={() => setStatus('已拒绝')} type="button">拒绝</button><button onClick={() => setStatus('已恢复原文')} type="button">恢复原文</button><span>{status}</span></footer></section>;
}

function CanonPatchReview() {
  const [accepted, setAccepted] = useState(true);
  return <section className="canon-patch-review wide" aria-label="设定变更影响列表"><h3>动作后果</h3><label><input checked={accepted} onChange={(event) => setAccepted(event.target.checked)} type="checkbox" />无法抬剑 → 腿伤令他难以站稳</label><h3>治疗</h3><label><input type="checkbox" />剪开衣袖 → 剪开裤腿</label></section>;
}

function OperationButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return <button aria-pressed={active} className={active ? 'active' : ''} onClick={onClick} type="button">{icon}<strong>{label}</strong></button>;
}
