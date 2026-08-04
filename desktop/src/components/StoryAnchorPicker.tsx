import { useEffect, useMemo, useState } from 'react';
import { getBranchChapters, getChapterScenes, getChapterStorySkeleton } from '../api/client';
import type {
  BranchChapterRecord,
  Chapter,
  PreferredStorySkeleton,
  SceneRecord,
  StoryAnchor,
} from '../api/types';

type OriginalAnchorType =
  | 'document_end'
  | 'chapter_start'
  | 'chapter_end'
  | 'scene_start'
  | 'scene_end'
  | 'skeleton_node'
  | 'text_offset';

export function StoryAnchorPicker({
  allowDocumentEnd = false,
  chapters,
  label,
  onChange,
  parentBranchId = null,
  value,
}: {
  allowDocumentEnd?: boolean;
  chapters: Chapter[];
  label: string;
  onChange: (anchor: StoryAnchor) => void;
  parentBranchId?: number | null;
  value: StoryAnchor;
}) {
  const [sourceKind, setSourceKind] = useState<'original' | 'branch'>(
    value.anchor_type.startsWith('branch_') ? 'branch' : 'original',
  );
  const [chapterId, setChapterId] = useState(value.chapter_id ?? chapters[0]?.id ?? null);
  const [anchorType, setAnchorType] = useState<OriginalAnchorType>(
    value.anchor_type.startsWith('branch_') || (value.anchor_type === 'document_end' && !allowDocumentEnd)
      ? 'chapter_end'
      : value.anchor_type as OriginalAnchorType,
  );
  const [sceneId, setSceneId] = useState(value.scene_id ?? null);
  const [nodeId, setNodeId] = useState(value.node_id ?? '');
  const [textOffset, setTextOffset] = useState(value.text_offset ?? 0);
  const [side, setSide] = useState<'before' | 'after'>(value.side === 'before' ? 'before' : 'after');
  const [scenes, setScenes] = useState<SceneRecord[]>([]);
  const [skeleton, setSkeleton] = useState<PreferredStorySkeleton | null>(null);
  const [branchChapters, setBranchChapters] = useState<BranchChapterRecord[]>([]);
  const [branchTarget, setBranchTarget] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!allowDocumentEnd && value.anchor_type === 'document_end') setAnchorType('chapter_end');
  }, [allowDocumentEnd, value.anchor_type]);

  useEffect(() => {
    if (!chapterId || sourceKind !== 'original') return;
    let active = true;
    Promise.all([
      getChapterScenes(chapterId),
      getChapterStorySkeleton(chapterId).catch(() => null),
    ]).then(([loadedScenes, loadedSkeleton]) => {
      if (!active) return;
      setScenes(loadedScenes);
      setSkeleton(loadedSkeleton);
      setSceneId((current) => current && loadedScenes.some((item) => item.id === current)
        ? current
        : loadedScenes[0]?.id ?? null);
      const firstNode = loadedSkeleton?.structured?.event_nodes[0]?.id ?? '';
      setNodeId((current) => current || firstNode);
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '无法读取锚点数据'));
    return () => { active = false; };
  }, [chapterId, sourceKind]);

  useEffect(() => {
    if (!parentBranchId) {
      setSourceKind('original');
      setBranchChapters([]);
      return;
    }
    let active = true;
    getBranchChapters(parentBranchId).then((loaded) => {
      if (!active) return;
      setBranchChapters(loaded);
      const lastChapter = loaded.at(-1);
      const lastScene = lastChapter?.scenes.at(-1);
      const target = lastScene ? `scene:${lastScene.id}` : lastChapter ? `chapter:${lastChapter.id}` : '';
      setBranchTarget(target);
      if (target) setSourceKind('branch');
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '无法读取父分支内容'));
    return () => { active = false; };
  }, [parentBranchId]);

  const branchOptions = useMemo(() => branchChapters.flatMap((chapter) => [
    { label: `章节：${chapter.title}`, value: `chapter:${chapter.id}` },
    ...chapter.scenes.map((scene) => ({
      label: `场景：${chapter.title} / ${scene.title || `场景 ${scene.scene_index}`}`,
      value: `scene:${scene.id}`,
    })),
  ]), [branchChapters]);

  useEffect(() => {
    if (sourceKind === 'branch' && branchTarget) {
      const [kind, rawId] = branchTarget.split(':');
      const id = Number(rawId);
      if (kind === 'scene') {
        const scene = branchChapters.flatMap((chapter) => chapter.scenes).find((item) => item.id === id);
        if (scene) onChange({
          anchor_type: 'branch_scene',
          branch_scene_id: scene.id,
          source_version_id: scene.version_id,
          side,
        });
      } else {
        const chapter = branchChapters.find((item) => item.id === id);
        if (chapter) onChange({
          anchor_type: 'branch_chapter',
          branch_chapter_id: chapter.id,
          source_version_id: chapter.version_id,
          side,
        });
      }
      return;
    }
    if (anchorType === 'document_end') onChange({ anchor_type: 'document_end' });
    else if (anchorType === 'scene_start' || anchorType === 'scene_end') {
      if (sceneId) onChange({ anchor_type: anchorType, scene_id: sceneId });
    } else if (anchorType === 'skeleton_node') {
      if (skeleton?.version_id && nodeId) onChange({
        anchor_type: 'skeleton_node',
        skeleton_version_id: skeleton.version_id,
        node_id: nodeId,
        side,
      });
    } else if (anchorType === 'text_offset') {
      if (chapterId) onChange({ anchor_type: 'text_offset', chapter_id: chapterId, text_offset: textOffset, side });
    } else if (chapterId) onChange({ anchor_type: anchorType, chapter_id: chapterId });
  }, [anchorType, branchChapters, branchTarget, chapterId, nodeId, onChange, sceneId, side, skeleton, sourceKind, textOffset]);

  const selectedChapter = chapters.find((chapter) => chapter.id === chapterId);
  return (
    <fieldset className="story-anchor-picker">
      <legend>{label}</legend>
      {parentBranchId ? <label>来源<select aria-label={`${label}来源`} onChange={(event) => setSourceKind(event.target.value as typeof sourceKind)} value={sourceKind}><option value="original">原文</option><option disabled={!branchOptions.length} value="branch">当前分支</option></select></label> : null}
      {sourceKind === 'branch' ? <>
        <label>父分支节点<select aria-label={`${label}父分支节点`} onChange={(event) => setBranchTarget(event.target.value)} value={branchTarget}>{branchOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>位置<select aria-label={`${label}位置`} onChange={(event) => setSide(event.target.value as typeof side)} value={side}><option value="before">之前</option><option value="after">之后</option></select></label>
      </> : <>
        <label>章节<select aria-label={`${label}章节`} onChange={(event) => setChapterId(Number(event.target.value))} value={chapterId ?? ''}>{chapters.map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.title}</option>)}</select></label>
        <label>节点类型<select aria-label={`${label}节点类型`} onChange={(event) => setAnchorType(event.target.value as OriginalAnchorType)} value={anchorType}>{allowDocumentEnd ? <option value="document_end">原文末尾</option> : null}<option value="chapter_start">章节开始</option><option value="chapter_end">章节结束</option><option value="scene_start">场景开始</option><option value="scene_end">场景结束</option><option value="skeleton_node">细纲事件</option><option value="text_offset">正文文本位置</option></select></label>
        {anchorType === 'scene_start' || anchorType === 'scene_end' ? <label>场景<select aria-label={`${label}场景`} onChange={(event) => setSceneId(Number(event.target.value))} value={sceneId ?? ''}>{scenes.map((scene) => <option key={scene.id} value={scene.id}>{scene.title || `场景 ${scene.scene_index}`}</option>)}</select></label> : null}
        {anchorType === 'skeleton_node' ? <><label>事件<select aria-label={`${label}细纲事件`} onChange={(event) => setNodeId(event.target.value)} value={nodeId}>{skeleton?.structured?.event_nodes.map((node) => <option key={node.id} value={node.id}>{node.summary}</option>)}</select></label><label>位置<select onChange={(event) => setSide(event.target.value as typeof side)} value={side}><option value="before">事件之前</option><option value="after">事件之后</option></select></label></> : null}
        {anchorType === 'text_offset' ? <><label>字符位置<input max={selectedChapter?.original_text.length ?? 0} min={0} onChange={(event) => setTextOffset(Number(event.target.value))} type="number" value={textOffset} /></label><label>位置<select onChange={(event) => setSide(event.target.value as typeof side)} value={side}><option value="before">位置之前</option><option value="after">位置之后</option></select></label></> : null}
      </>}
      {error ? <p role="alert">{error}</p> : null}
    </fieldset>
  );
}
