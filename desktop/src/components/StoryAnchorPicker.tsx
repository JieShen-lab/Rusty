import { useEffect, useMemo, useState } from 'react';
import {
  getChapterScenes,
  getChapterStorySkeleton,
} from '../api/client';
import {
  getRewriteVersionAnchors,
  getRewriteVersionSkeleton,
  previewStoryAnchor,
} from '../api/workflowClient';
import type {
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
  | 'skeleton_node';

export function StoryAnchorPicker({
  allowDocumentEnd = false,
  chapters,
  label,
  onChange,
  projectId,
  source = { kind: 'original' },
  sourceVersionId = null,
  value,
}: {
  allowDocumentEnd?: boolean;
  chapters: Chapter[];
  label: string;
  onChange: (anchor: StoryAnchor) => void;
  projectId: number;
  source?: ChapterSourceSelection;
  sourceVersionId?: number | null;
  value: StoryAnchor;
}) {
  const [chapterId, setChapterId] = useState(value.chapter_id ?? chapters[0]?.id ?? null);
  const [anchorType, setAnchorType] = useState<OriginalAnchorType>(
    value.anchor_type.startsWith('branch_') || value.anchor_type === 'text_offset' || (value.anchor_type === 'document_end' && !allowDocumentEnd)
      ? 'chapter_end'
      : value.anchor_type as OriginalAnchorType,
  );
  const [sceneId, setSceneId] = useState(value.scene_id ?? null);
  const [nodeId, setNodeId] = useState(value.node_id ?? '');
  const [side, setSide] = useState<'before' | 'after'>(value.side === 'before' ? 'before' : 'after');
  const [scenes, setScenes] = useState<SceneRecord[]>([]);
  const [skeleton, setSkeleton] = useState<PreferredStorySkeleton | null>(null);
  const [error, setError] = useState('');
  const [segments, setSegments] = useState<RewriteSemanticSegment[]>([]);
  const [preview, setPreview] = useState<StoryAnchorPreview | null>(null);

  useEffect(() => {
    if (!allowDocumentEnd && value.anchor_type === 'document_end') setAnchorType('chapter_end');
  }, [allowDocumentEnd, value.anchor_type]);

  useEffect(() => {
    if (!chapterId) return;
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
  }, [chapterId, sourceVersionId]);

  useEffect(() => {
    const versionFields = sourceVersionId == null
      ? {}
      : { source_version_id: sourceVersionId };
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
    } else if (chapterId) onChange({ anchor_type: anchorType, chapter_id: chapterId, ...versionFields });
  }, [anchorType, chapterId, nodeId, onChange, sceneId, side, skeleton, sourceVersionId]);

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

  return (
    <fieldset className="story-anchor-picker">
      <legend>{label}</legend>
        <label>章节<select aria-label={`${label}章节`} onChange={(event) => setChapterId(Number(event.target.value))} value={chapterId ?? ''}>{chapters.map((chapter) => <option key={chapter.id} value={chapter.id}>{chapter.title}</option>)}</select></label>
        <label>节点类型<select aria-label={`${label}节点类型`} onChange={(event) => setAnchorType(event.target.value as OriginalAnchorType)} value={anchorType}>{allowDocumentEnd ? <option value="document_end">原文末尾</option> : null}<option value="chapter_start">章节开始</option><option value="chapter_end">章节结束</option><option value="scene_start">场景开始</option><option value="scene_end">场景结束</option><option value="skeleton_node">细纲事件</option></select></label>
        {anchorType === 'scene_start' || anchorType === 'scene_end' ? <label>场景<select aria-label={`${label}场景`} onChange={(event) => setSceneId(Number(event.target.value))} value={sceneId ?? ''}>{scenes.map((scene) => <option key={scene.id} value={scene.id}>{scene.title || `场景 ${scene.scene_index}`}</option>)}</select></label> : null}
        {anchorType === 'skeleton_node' ? <><label>事件<select aria-label={`${label}细纲事件`} onChange={(event) => setNodeId(event.target.value)} value={nodeId}>{visibleNodes.map((node) => <option key={node.id} value={node.id}>{node.summary}</option>)}</select></label><label>位置<select onChange={(event) => setSide(event.target.value as typeof side)} value={side}><option value="before">事件之前</option><option value="after">事件之后</option></select></label></> : null}
      <button onClick={() => void loadPreview()} type="button">预览位置</button>
      {preview ? <aside aria-label={`${label}锚点预览`}><p>将在这里开始：</p><blockquote>{preview.text_excerpt}</blockquote>{preview.mapping_method === 'semantic' && preview.confidence < 0.8 ? <p>位置识别不确定，请确认附近正文是否正确。</p> : null}</aside> : null}
      {error ? <p role="alert">{error}</p> : null}
    </fieldset>
  );
}
