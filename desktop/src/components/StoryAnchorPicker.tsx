import { useEffect, useMemo, useState } from 'react';
import {
  getBranchChapters,
  getChapterScenes,
  getChapterStorySkeleton,
  getRewriteVersionAnchors,
  getRewriteVersionSkeleton,
  previewStoryAnchor,
} from '../api/client';
import type {
  BranchChapterRecord,
  Chapter,
  PreferredStorySkeleton,
  SceneRecord,
  StoryAnchor,
  StoryAnchorPreview,
  ChapterSourceSelection,
  RewriteSemanticSegment,
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
  projectId,
  source = { kind: 'original' },
  sourceTextLength,
  sourceVersionId = null,
  value,
}: {
  allowDocumentEnd?: boolean;
  chapters: Chapter[];
  label: string;
  onChange: (anchor: StoryAnchor) => void;
  parentBranchId?: number | null;
  projectId: number;
  source?: ChapterSourceSelection;
  sourceTextLength?: number;
  sourceVersionId?: number | null;
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
  const [segments, setSegments] = useState<RewriteSemanticSegment[]>([]);
  const [preview, setPreview] = useState<StoryAnchorPreview | null>(null);

  useEffect(() => {
    if (!allowDocumentEnd && value.anchor_type === 'document_end') setAnchorType('chapter_end');
  }, [allowDocumentEnd, value.anchor_type]);

  useEffect(() => {
    if (!chapterId || sourceKind !== 'original') return;
    let active = true;
    Promise.all([
      getChapterScenes(chapterId),
      (sourceVersionId
        ? getRewriteVersionSkeleton(sourceVersionId).then((item): PreferredStorySkeleton => ({
            format: 'structured',
            skeleton_id: item.skeleton_id,
            version_id: item.skeleton_version_id,
            status: item.status === 'confirmed' ? 'confirmed' : 'draft',
            structured: item.structured,
          }))
        : getChapterStorySkeleton(chapterId)).catch(() => null),
      sourceVersionId ? getRewriteVersionAnchors(sourceVersionId) : Promise.resolve([]),
    ]).then(([loadedScenes, loadedSkeleton, loadedSegments]) => {
      if (!active) return;
      const mappedSceneIds = new Set(loadedSegments
        .filter((item) => item.segment_kind === 'scene' && !item.needs_remap)
        .map((item) => item.source_scene_id));
      const availableScenes = sourceVersionId
        ? loadedScenes.filter((item) => mappedSceneIds.has(item.id))
        : loadedScenes;
      setSegments(loadedSegments);
      setScenes(availableScenes);
      setSkeleton(loadedSkeleton);
      setSceneId((current) => current && availableScenes.some((item) => item.id === current)
        ? current
        : availableScenes[0]?.id ?? null);
      const mappedNodes = new Set(loadedSegments
        .filter((item) => item.segment_kind === 'event_node'
          && !item.needs_remap)
        .map((item) => item.node_id));
      const firstNode = loadedSkeleton?.structured?.event_nodes
        .find((item) => !sourceVersionId || mappedNodes.has(item.id))?.id ?? '';
      setNodeId((current) => current || firstNode);
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '无法读取锚点数据'));
    return () => { active = false; };
  }, [chapterId, sourceKind, sourceVersionId]);

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
      setSourceKind('branch');
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
    const versionFields = sourceVersionId == null
      ? {}
      : { source_version_id: sourceVersionId };
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
      if (sceneId) onChange({ anchor_type: anchorType, scene_id: sceneId, ...versionFields });
    } else if (anchorType === 'skeleton_node') {
      if (skeleton?.version_id && nodeId) onChange({
        anchor_type: 'skeleton_node',
        skeleton_version_id: skeleton.version_id,
        node_id: nodeId,
        side,
        ...versionFields,
      });
    } else if (anchorType === 'text_offset') {
      if (chapterId) onChange({ anchor_type: 'text_offset', chapter_id: chapterId, text_offset: textOffset, side, ...versionFields });
    } else if (chapterId) onChange({ anchor_type: anchorType, chapter_id: chapterId, ...versionFields });
  }, [anchorType, branchChapters, branchTarget, chapterId, nodeId, onChange, sceneId, side, skeleton, sourceKind, sourceVersionId, textOffset]);

  const visibleNodes = useMemo(() => {
    const nodes = skeleton?.structured?.event_nodes ?? [];
    if (!sourceVersionId) return nodes;
    const ids = new Set(segments
      .filter((item) => item.segment_kind === 'event_node'
        && !item.needs_remap)
      .map((item) => item.node_id));
    return nodes.filter((node) => ids.has(node.id));
  }, [segments, skeleton, sourceVersionId]);

  async function loadPreview() {
    setError('');
    try {
      setPreview(await previewStoryAnchor({ project_id: projectId, source, anchor: value }));
    } catch (reason) {
      setPreview(null);
      setError(reason instanceof Error ? reason.message : '无法预览锚点');
    }
  }

  const selectedChapter = chapters.find((chapter) => chapter.id === chapterId);
  return (
    <fieldset className="story-anchor-picker">
      <legend>{label}</legend>
      {parentBranchId ? <p>来源：父分支内容</p> : null}
      {sourceKind === 'branch' ? <>
        <label>父分支节点<select aria-label={`${label}父分支节点`} onChange={(event) => setBranchTarget(event.target.value)} value={branchTarget}>{branchOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>位置<select aria-label={`${label}位置`} onChange={(event) => setSide(event.target.value as typeof side)} value={side}><option value="before">之前</option><option value="after">之后</option></select></label>
      </> : <>
        <label>章节<select aria-label={`${label}章节`} onChange={(event) => setChapterId(Number(event.target.value))} value={chapterId ?? ''}>{chapters.map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.title}</option>)}</select></label>
        <label>节点类型<select aria-label={`${label}节点类型`} onChange={(event) => setAnchorType(event.target.value as OriginalAnchorType)} value={anchorType}>{allowDocumentEnd ? <option value="document_end">原文末尾</option> : null}<option value="chapter_start">章节开始</option><option value="chapter_end">章节结束</option><option value="scene_start">场景开始</option><option value="scene_end">场景结束</option><option value="skeleton_node">细纲事件</option><option value="text_offset">正文文本位置</option></select></label>
        {anchorType === 'scene_start' || anchorType === 'scene_end' ? <label>场景<select aria-label={`${label}场景`} onChange={(event) => setSceneId(Number(event.target.value))} value={sceneId ?? ''}>{scenes.map((scene) => <option key={scene.id} value={scene.id}>{scene.title || `场景 ${scene.scene_index}`}</option>)}</select></label> : null}
        {anchorType === 'skeleton_node' ? <><label>事件<select aria-label={`${label}细纲事件`} onChange={(event) => setNodeId(event.target.value)} value={nodeId}>{visibleNodes.map((node) => <option key={node.id} value={node.id}>{node.summary}</option>)}</select></label><label>位置<select onChange={(event) => setSide(event.target.value as typeof side)} value={side}><option value="before">事件之前</option><option value="after">事件之后</option></select></label></> : null}
        {anchorType === 'text_offset' ? <><label>字符位置<input max={sourceTextLength ?? selectedChapter?.original_text.length ?? 0} min={0} onChange={(event) => setTextOffset(Number(event.target.value))} type="number" value={textOffset} /></label><label>位置<select onChange={(event) => setSide(event.target.value as typeof side)} value={side}><option value="before">位置之前</option><option value="after">位置之后</option></select></label></> : null}
      </>}
      {sourceKind === 'original' ? <button onClick={() => void loadPreview()} type="button">预览锚点</button> : null}
      {preview ? <aside aria-label={`${label}锚点预览`}><p>位置：{preview.resolved_start}–{preview.resolved_end}</p><blockquote>{preview.text_excerpt}</blockquote><small>映射：{preview.mapping_method} / {Math.round(preview.confidence * 100)}%</small>{preview.mapping_method === 'semantic' && preview.confidence < 0.8 ? <p>此锚点位置由语义映射得到，建议确认。</p> : null}</aside> : null}
      {error ? <p role="alert">{error}</p> : null}
    </fieldset>
  );
}
