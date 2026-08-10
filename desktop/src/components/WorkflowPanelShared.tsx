import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import { getCanonChangeRun, reviewCanonPatch } from '../api/workflowClient';
import type {
  CanonChangeRun,
  ChapterRewriteVersion,
  ChapterSourceSelection,
  PlotGenerationRun,
  SeamProposal,
} from '../api/types';


export function SeamReview({
  onConfirm,
  seams = [],
}: {
  onConfirm?: (seams: SeamProposal[]) => void;
  seams?: SeamProposal[];
}) {
  const [items, setItems] = useState(seams);
  useEffect(() => setItems(seams), [seams]);
  return (
    <section className="seam-review wide" aria-label="接缝审查">
      <h3>接缝审查</h3>
      {items.length === 0 ? <p>尚未生成接缝提议。</p> : items.map((seam, index) => <article key={seam.id ?? index}><strong>{seam.seam_kind === 'entry' ? '进入接缝' : '回接接缝'}</strong><p>原文：{seam.original_text}</p><label>建议修改<textarea onChange={(event) => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, proposed_text: event.target.value } : item))} value={seam.proposed_text} /></label><p>{seam.reason}</p><button onClick={() => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: 'confirmed' } : item))} type="button">确认</button><button onClick={() => setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: 'rejected' } : item))} type="button">拒绝</button><span>{seam.status}</span></article>)}
      {items.length ? <button disabled={items.some((item) => item.status === 'draft')} onClick={() => onConfirm?.(items)} type="button">提交接缝审查</button> : null}
    </section>
  );
}

export function RewriteVersionHistory({
  onSelectSource,
  onUseCurrent,
  onUseOriginal,
  onView,
  selectedSource,
  versions,
  viewedVersion,
}: {
  onSelectSource: (version: ChapterRewriteVersion) => void;
  onUseCurrent: () => void;
  onUseOriginal: () => void;
  onView: (version: ChapterRewriteVersion) => void;
  selectedSource: ChapterSourceSelection;
  versions: ChapterRewriteVersion[];
  viewedVersion: ChapterRewriteVersion | null;
}) {
  return (
    <section className="rewrite-version-history" aria-label="rewrite versions">
      <h3>&#27491;&#25991;&#29256;&#26412;</h3>
      <p>Source: {selectedSource.kind === 'rewrite_version' ? `v${selectedSource.version_id}` : selectedSource.kind}</p>
      <button onClick={onUseCurrent} type="button">&#24403;&#21069;&#29256;&#26412;</button>
      <button onClick={onUseOriginal} type="button">&#21407;&#22987;&#22522;&#32447;</button>
      {versions.length === 0 ? <p>No rewrite versions.</p> : (
        <ul>
          {versions.map((version) => (
            <li key={version.id}>
              <button onClick={() => onView(version)} type="button">
                v{version.version} · {version.source_operation} · parent {version.parent_version_id ?? 'original'}
                {version.is_current ? ' · current' : ''}
              </button>
              <button onClick={() => onSelectSource(version)} type="button">
                &#22522;&#20110;&#27492;&#29256;&#26412;&#21019;&#24314;&#26032;&#25805;&#20316;
              </button>
              <time>{version.created_at}</time>
            </li>
          ))}
        </ul>
      )}
      {viewedVersion ? <pre>{viewedVersion.rewritten_text}</pre> : null}
    </section>
  );
}

export function CanonPatchReview({ onChange, run }: { onChange: (run: CanonChangeRun) => void; run: CanonChangeRun }) {
  async function decide(patchId: number, decision: 'accepted' | 'rejected' | 'skipped', replacementText?: string) {
    await reviewCanonPatch(patchId, { decision, replacement_text: replacementText ?? null });
    onChange(await getCanonChangeRun(run.id));
  }
  const groups = run.patches.reduce<Record<string, typeof run.patches>>((result, patch) => {
    (result[patch.impact_type] ??= []).push(patch);
    return result;
  }, {});
  return <section className="canon-patch-review wide" aria-label="设定变更影响列表">{Object.entries(groups).map(([impactType, patches]) => <div key={impactType}><h3>{impactType}</h3>{patches.map((patch) => <article key={patch.id}><p>{patch.original_text}</p><textarea defaultValue={patch.replacement_text} onBlur={(event) => { if (event.target.value !== patch.replacement_text) void reviewCanonPatch(patch.id, { decision: 'edited', replacement_text: event.target.value }).then(() => getCanonChangeRun(run.id)).then(onChange); }} /><small>{patch.reason} · {Math.round(patch.confidence * 100)}%</small><button onClick={() => void decide(patch.id, 'accepted')} type="button">接受</button><button onClick={() => void decide(patch.id, 'rejected')} type="button">拒绝</button><button onClick={() => void decide(patch.id, 'skipped')} type="button">跳过</button><span>{patch.status}</span></article>)}</div>)}</section>;
}

export function RunStatus({ run }: { run: { id: number; status: string; stage?: string } }) {
  return <p className="wide" role="status">运行 #{run.id} · {run.stage ? `${run.stage} · ` : ''}{run.status}</p>;
}

export function RunHistory<T extends { id: number; status: string }>({
  label,
  onSelect,
  runs,
}: {
  label: string;
  onSelect: (run: T) => void;
  runs: T[];
}) {
  return (
    <section className="wide" aria-label={label}>
      <h3>历史运行</h3>
      {runs.length === 0 ? <p>暂无历史运行。</p> : (
        <ul>{runs.map((run) => <li key={run.id}><button onClick={() => onSelect(run)} type="button">运行 #{run.id} · {run.status}</button></li>)}</ul>
      )}
    </section>
  );
}

export function plannedSceneCount(run: PlotGenerationRun): number {
  const chapters = Array.isArray(run.scene_plan.chapters) ? run.scene_plan.chapters : [];
  return chapters.reduce((count, chapter) => {
    if (!chapter || typeof chapter !== 'object') return count;
    const scenes = (chapter as { scenes?: unknown }).scenes;
    return count + (Array.isArray(scenes) ? scenes.length : 0);
  }, 0);
}

export function parseIds(value: string): number[] {
  return value.split(',').map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0);
}

export function seamReviews(seams: SeamProposal[]) {
  return seams.map((seam) => {
    if (!seam.id || seam.status === 'draft') throw new Error('所有接缝必须先确认或拒绝。');
    return {
      seam_id: seam.id,
      decision: seam.status,
      proposed_text: seam.proposed_text,
    };
  });
}

export function OperationButton({ active, icon, label, onClick }: { active: boolean; icon: ReactNode; label: string; onClick: () => void }) {
  return <button aria-pressed={active} className={active ? 'active' : ''} onClick={onClick} type="button">{icon}<strong>{label}</strong></button>;
}
