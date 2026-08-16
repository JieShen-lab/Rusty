import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { DragEvent, MouseEvent, ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowDownToLine,
  ArrowUpToLine,
  BookOpenText,
  ChevronRight,
  Clock3,
  Combine,
  Download,
  FileInput,
  Folder,
  FolderOpen,
  FolderPlus,
  LibraryBig,
  Plus,
  Pencil,
  Save,
  Search,
  Scissors,
  Settings2,
  Trash2,
  WandSparkles,
  X,
} from 'lucide-react';
import {
  activateLibraryDocumentRevision,
  assignDocumentTag,
  cleanupLibraryDocumentWithAI,
  createDocumentCategory,
  createDocumentTag,
  createLibraryDocumentChapter,
  deleteDocumentCategory,
  deleteLibraryDocument,
  exportLibraryDocument,
  getDocumentTags,
  getDocumentCategories,
  getDocumentLibrarySettings,
  getLibraryDocumentDirectory,
  getLibraryDocumentContent,
  getLibraryDocumentRevisions,
  getLibraryDocuments,
  importLibraryDocument,
  migrateDocumentLibrary,
  mergeLibraryDocuments,
  reorderLibraryDocumentChapters,
  previewAIDocumentSplit,
  applyAIDocumentSplit,
  splitLibraryDocumentChapterAtCursor,
  commitLibraryDocumentDraft,
  getLibraryDocumentDraft,
  saveLibraryDocumentDraft,
  renameDocumentCategory,
  renameLibraryDocumentVolume,
  updateLibraryDocument,
} from '../api/client';
import type {
  DocumentCategory,
  LibraryDocument,
  LibraryDocumentChapter,
  LibraryDocumentContent,
  LibraryDocumentRevision,
  LibraryDocumentDraft,
  LibraryDocumentDirectory,
  LibraryDocumentVolume,
  ResourceTag,
  AISplitProposal,
} from '../api/types';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { DangerButton } from '../components/DangerButton';
import { LibraryContextMenu, LibraryDetailSection, LibraryDialog, LibraryDivider, LibraryResourceCard, LibraryResourceGrid, LibrarySidebarSectionTitle, LibraryTagChip } from '../components/LibraryPrimitives';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

type DocumentAction = 'merge' | 'create-chapter' | 'split';
type SaveStatus = 'clean' | 'dirty' | 'saving' | 'saved' | 'error';

const systemFilters = [
  { key: 'all', label: '全部文档', icon: LibraryBig },
  { key: 'project', label: '工程文档', icon: FolderOpen },
  { key: 'recent', label: '最近导入', icon: Clock3 },
  { key: 'untagged', label: '无标签', icon: Folder },
] as const;
type SystemFilter = typeof systemFilters[number]['key'];

const palettes = ['indigo', 'terracotta', 'jade', 'slate', 'ochre', 'plum', 'bluegray'] as const;

export function DocumentLibraryPage({ onNavigate }: { onNavigate: (path: string, state?: unknown) => void }) {
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [tags, setTags] = useState<ResourceTag[]>([]);
  const [categories, setCategories] = useState<DocumentCategory[]>([]);
  const [libraryPath, setLibraryPath] = useState('');
  const [systemFilter, setSystemFilter] = useState<SystemFilter>('all');
  const [activeCategoryId, setActiveCategoryId] = useState<number | null>(null);
  const [activeTagIds, setActiveTagIds] = useState<number[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [processingBusy, setProcessingBusy] = useState(false);
  const [revisions, setRevisions] = useState<LibraryDocumentRevision[]>([]);
  const [chapters, setChapters] = useState<LibraryDocumentChapter[]>([]);
  const [volumes, setVolumes] = useState<LibraryDocumentVolume[]>([]);
  const [documentContent, setDocumentContent] = useState<LibraryDocumentContent | null>(null);
  const [documentDraft, setDocumentDraft] = useState<LibraryDocumentDraft | null>(null);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [resourceManager, setResourceManager] = useState<'tag' | null>(null);
  const [categoryCreateOpen, setCategoryCreateOpen] = useState(false);
  const [categoryContextMenu, setCategoryContextMenu] = useState<{ category: DocumentCategory; x: number; y: number } | null>(null);
  const [categoryRename, setCategoryRename] = useState<DocumentCategory | null>(null);
  const [editingMetadata, setEditingMetadata] = useState<'title' | 'author' | null>(null);
  const [metadataTitle, setMetadataTitle] = useState('');
  const [metadataAuthor, setMetadataAuthor] = useState('');
  const [actionDialog, setActionDialog] = useState<DocumentAction | null>(null);
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const [revisionsOpen, setRevisionsOpen] = useState(false);
  const [editorDirty, setEditorDirty] = useState(false);
  const editorControllerRef = useRef<DocumentEditorController | null>(null);

  const query = searchText.trim().toLocaleLowerCase();
  const systemDocuments = useMemo(
    () => documentsForSystemFilter(documents, systemFilter),
    [documents, systemFilter],
  );
  const activeTagNames = useMemo(() => {
    const selectedIds = new Set(activeTagIds);
    return tags.filter((tag) => selectedIds.has(tag.id)).map((tag) => tag.name);
  }, [activeTagIds, tags]);
  const visibleDocuments = useMemo(
    () => systemDocuments.filter((document) => (
      (activeCategoryId == null || document.category_ids.includes(activeCategoryId))
      && activeTagNames.every((tagName) => document.tags.includes(tagName))
      && (!query || `${document.title} ${document.author ?? ''} ${document.source_filename}`.toLocaleLowerCase().includes(query))
    )),
    [activeCategoryId, activeTagNames, query, systemDocuments],
  );
  const selectedDocument = documents.find((document) => document.id === selectedId) ?? null;

  useAutoDismiss(message, setMessage);
  useAutoDismiss(error, setError, 5200);

  useEffect(() => {
    setMetadataTitle(selectedDocument?.title ?? '');
    setMetadataAuthor(selectedDocument?.author ?? '');
    setEditingMetadata(null);
  }, [selectedDocument?.id]);

  useEffect(() => {
    if (workspaceOpen || visibleDocuments.some((document) => document.id === selectedId)) return;
    setSelectedId(visibleDocuments[0]?.id ?? null);
  }, [systemFilter, activeCategoryId, activeTagIds, query, visibleDocuments, workspaceOpen]);

  async function loadLibrary(preferredId?: number | null) {
    setError(null);
    try {
      const [documentItems, tagItems, categoryItems, settings] = await Promise.all([
        getLibraryDocuments(),
        getDocumentTags(),
        getDocumentCategories(),
        getDocumentLibrarySettings(),
      ]);
      setDocuments(documentItems);
      setTags(tagItems);
      setCategories(categoryItems);
      setLibraryPath(settings.storage_path);
      const nextId = preferredId !== undefined ? preferredId : selectedId;
      setSelectedId(documentItems.some((document) => document.id === nextId) ? nextId : documentItems[0]?.id ?? null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadLibrary();
  }, []);

  function applyDirectory(directory: LibraryDocumentDirectory): LibraryDocumentChapter[] {
    const allChapters = [
      ...directory.unassigned_chapters,
      ...directory.volumes.flatMap((volume) => volume.chapters),
    ].sort((left, right) => left.index - right.index);
    setVolumes(directory.volumes);
    setChapters(allChapters);
    return allChapters;
  }

  async function importDocument() {
    const sourcePath = await window.rustyDesktop?.selectLibraryDocumentFile?.();
    if (!sourcePath) return;
    await runBusy(async () => {
      const result = await importLibraryDocument(sourcePath);
      setMessage(result.created ? '文档已导入。' : '相同内容已存在，已定位到原文档。');
      await loadLibrary(result.document.id);
    });
  }

  async function migrateLibraryDirectory() {
    const targetPath = await window.rustyDesktop?.selectDocumentLibraryDirectory?.();
    if (!targetPath || targetPath === libraryPath) return;
    if (!window.confirm(`将全部文档版本迁移到：\n${targetPath}\n\n确认继续？`)) return;
    await runBusy(async () => {
      const settings = await migrateDocumentLibrary(targetPath);
      setLibraryPath(settings.storage_path);
      await loadLibrary(selectedId);
      setMessage('文档目录迁移完成。');
    });
  }

  async function createManagedResource(kind: 'category' | 'tag', name: string) {
    await runBusy(async () => {
      const created = kind === 'category'
        ? await createDocumentCategory(name)
        : await createDocumentTag(name);
      if (kind === 'category') {
        setCategories((current) => [...current, created as DocumentCategory]);
        setCategoryCreateOpen(false);
      } else {
        setTags((current) => [...current, created as ResourceTag]);
        if (selectedDocument) {
          await assignDocumentTag(selectedDocument.id, created.id, true);
          await loadLibrary(selectedDocument.id);
        }
      }
      setMessage(`已创建${kind === 'category' ? '分类' : '标签'}“${created.name}”。`);
    }, false);
  }

  async function renameCategory(category: DocumentCategory, name: string) {
    if (name === category.name) {
      setCategoryRename(null);
      return;
    }
    await runBusy(async () => {
      const renamed = await renameDocumentCategory(category.id, name);
      setCategories((current) => current.map((item) => item.id === renamed.id ? renamed : item));
      setCategoryRename(null);
      setMessage(`已重命名分类为“${renamed.name}”。`);
    }, false);
  }

  async function removeCategory(category: DocumentCategory) {
    if (!window.confirm(`确认删除分类“${category.name}”？文档本身不会被删除。`)) return;
    await runBusy(async () => {
      await deleteDocumentCategory(category.id);
      if (activeCategoryId === category.id) setActiveCategoryId(null);
      setCategories((current) => current.filter((item) => item.id !== category.id));
      setMessage(`已删除分类“${category.name}”。`);
    }, false);
  }

  async function toggleDocumentTag(tagId: number, selected: boolean) {
    if (!selectedDocument) return;
    await runBusy(async () => {
      await assignDocumentTag(selectedDocument.id, tagId, selected);
      await loadLibrary(selectedDocument.id);
      setMessage(selected ? '标签已关联。' : '标签关联已移除。');
    }, false);
  }

  function beginMetadataEdit(field: 'title' | 'author') {
    if (!selectedDocument) return;
    setMetadataTitle(selectedDocument.title);
    setMetadataAuthor(selectedDocument.author ?? '');
    setEditingMetadata(field);
  }

  async function saveMetadata() {
    if (!selectedDocument || !metadataTitle.trim()) {
      setError('文档名称不能为空。');
      return;
    }
    const originalId = selectedDocument.id;
    setEditingMetadata(null);
    await runBusy(async () => {
      const saved = await updateLibraryDocument(
        originalId,
        metadataTitle.trim(),
        metadataAuthor.trim() || null,
      );
      await loadLibrary(saved.id);
      setMessage('文档信息已保存，封面同步更新。');
    }, false);
  }

  async function saveWorkspaceMetadata(title: string, author: string) {
    if (!selectedDocument || !title.trim()) {
      setError('文档名称不能为空。');
      return;
    }
    await runBusy(async () => {
      const saved = await updateLibraryDocument(
        selectedDocument.id,
        title.trim(),
        author.trim() || null,
      );
      setDocuments((current) => current.map((item) => item.id === saved.id ? saved : item));
      setMetadataTitle(saved.title);
      setMetadataAuthor(saved.author ?? '');
      setMessage('书名和作者已同步保存。');
    }, false);
  }

  async function openProcessing(
    targetDocument: LibraryDocument | null = selectedDocument,
  ): Promise<boolean> {
    if (!targetDocument) return false;
    if (workspaceOpen && !(await flushEditorDraft(`切换到“${targetDocument.title}”`))) return false;
    setSelectedId(targetDocument.id);
    setWorkspaceOpen(true);
    setProcessingBusy(true);
    setError(null);
    try {
      const [revisionItems, directory] = await Promise.all([
        getLibraryDocumentRevisions(targetDocument.id),
        getLibraryDocumentDirectory(targetDocument.id),
      ]);
      const chapterItems = applyDirectory(directory);
      const firstChapterId = chapterItems[0]?.id ?? null;
      const [content, draft] = await Promise.all([
        getLibraryDocumentContent(targetDocument.id, firstChapterId),
        getLibraryDocumentDraft(targetDocument.id, firstChapterId),
      ]);
      setRevisions(revisionItems);
      setSelectedChapterId(firstChapterId);
      setDocumentContent(content);
      setDocumentDraft(draft);
      return true;
    } catch (err) {
      setError(errorMessage(err));
      setWorkspaceOpen(false);
      return false;
    } finally {
      setProcessingBusy(false);
    }
  }

  async function reorderChapters(
    draggedId: number,
    targetId: number | null,
    targetVolumeId: number | null,
  ) {
    if (!selectedDocument || draggedId === targetId) return;
    const previous = chapters;
    const reordered = [...chapters];
    const fromIndex = reordered.findIndex((chapter) => chapter.id === draggedId);
    if (fromIndex < 0) return;
    const [moved] = reordered.splice(fromIndex, 1);
    const targetIndex = targetId == null
      ? reordered.reduce(
        (last, chapter, index) => chapter.volume_id === targetVolumeId ? index + 1 : last,
        reordered.length,
      )
      : reordered.findIndex((chapter) => chapter.id === targetId);
    if (targetIndex < 0) return;
    reordered.splice(targetIndex, 0, { ...moved, volume_id: targetVolumeId });
    setChapters(reordered.map((chapter, index) => ({ ...chapter, index: index + 1 })));
    try {
      const saved = await reorderLibraryDocumentChapters(
        selectedDocument.id,
        reordered.map((chapter) => chapter.id),
        { [draggedId]: targetVolumeId },
      );
      setChapters(saved);
      setMessage('章节顺序已保存。');
    } catch (err) {
      setChapters(previous);
      setError(errorMessage(err));
    }
  }

  async function renameVolume(volumeId: number, title: string) {
    if (!selectedDocument || !title.trim()) return;
    if (!(await flushEditorDraft('修改卷标题'))) return;
    await runProcessing(async () => {
      const result = await renameLibraryDocumentVolume(
        selectedDocument.id,
        volumeId,
        title.trim(),
      );
      await refreshWorkspaceDocument(result.document, null);
      setMessage('卷标题已保存为新版本。');
    });
  }

  async function deleteDocument(document: LibraryDocument | null = selectedDocument) {
    if (!document) return;
    if (!window.confirm(`确定从文档库删除“${document.title}”吗？\n\n已保存的原始文件暂时保留，避免误删。`)) return;
    await runBusy(async () => {
      await deleteLibraryDocument(document.id);
      setWorkspaceOpen(false);
      setSelectedId(null);
      await loadLibrary(null);
      setMessage(`已删除“${document.title}”。`);
    });
  }

  async function handleDocumentAction(action: DocumentAction) {
    if (!selectedDocument) return;
    const labels: Record<DocumentAction, string> = {
      merge: '合并文档',
      'create-chapter': '新增章节',
      split: '分章',
    };
    if (!(await flushEditorDraft(labels[action]))) return;
    setActionDialog(action);
  }

  async function saveCurrentDraft(title: string, text: string): Promise<LibraryDocumentDraft> {
    if (!selectedDocument || !documentContent) throw new Error('当前没有可保存的文档内容。');
    return saveLibraryDocumentDraft(
      selectedDocument.id,
      documentContent.revision_id,
      title,
      text,
      documentContent.chapter_id,
    );
  }

  async function commitCurrentDraft(): Promise<boolean> {
    if (!selectedDocument || !documentContent) return false;
    try {
      const selectedIndex = chapters.find((chapter) => chapter.id === documentContent.chapter_id)?.index ?? null;
      const result = await commitLibraryDocumentDraft(selectedDocument.id, documentContent.chapter_id);
      const [revisionItems, directory] = await Promise.all([
        getLibraryDocumentRevisions(selectedDocument.id),
        getLibraryDocumentDirectory(selectedDocument.id),
      ]);
      const chapterItems = applyDirectory(directory);
      const chapterId = selectedIndex == null
        ? null
        : chapterItems.find((chapter) => chapter.index === selectedIndex)?.id ?? chapterItems[0]?.id ?? null;
      const [content, draft] = await Promise.all([
        getLibraryDocumentContent(selectedDocument.id, chapterId),
        getLibraryDocumentDraft(selectedDocument.id, chapterId),
      ]);
      setDocuments((current) => current.map((item) => item.id === result.document.id ? result.document : item));
      setRevisions(revisionItems);
      setSelectedChapterId(chapterId);
      setDocumentContent(content);
      setDocumentDraft(draft);
      setEditorDirty(false);
      setMessage('正文已保存为新版本。');
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    }
  }

  async function saveSelection(
    kind: 'scene' | 'plot' | 'character',
    text: string,
    startOffset: number,
    endOffset: number,
  ) {
    if (!documentContent) return;
    const selected = text.trim();
    if (!selected) return;
    if (selected.length > 50000) {
      setError('选区不能超过 50,000 字符。');
      return;
    }
    if (kind === 'character') {
      const chapter = chapters.find((item) => item.id === documentContent.chapter_id);
      const volume = volumes.find((item) => item.id === chapter?.volume_id);
      onNavigate('/characters', {
        characterExtraction: {
          selectedText: selected,
          sourceMetadata: {
            source_kind: 'document',
            source_type: 'document',
            document_id: documentContent.document_id,
            revision_id: documentContent.revision_id,
            volume_id: volume?.id ?? null,
            chapter_id: documentContent.chapter_id,
            start_offset: startOffset,
            end_offset: endOffset,
            document_title: selectedDocument?.title ?? '',
            volume_title: volume?.title ?? '',
            chapter_title: chapter ? chapterDisplayTitle(chapter) : '',
          },
        },
      });
      return;
    }
    const chapter = chapters.find((item) => item.id === documentContent.chapter_id);
    const volume = volumes.find((item) => item.id === chapter?.volume_id);
    onNavigate('/materials', {
      materialExtraction: {
        materialType: kind === 'plot' ? 'plot_skeleton' : 'author_style',
        taskType: kind === 'scene' ? 'author_style_extraction' : undefined,
        selectedText: selected,
        sourceMetadata: {
          source_kind: 'document_selection',
          source_type: 'document',
          document_id: documentContent.document_id,
          revision_id: documentContent.revision_id,
          volume_id: volume?.id ?? null,
          chapter_id: documentContent.chapter_id,
          start_offset: startOffset,
          end_offset: endOffset,
          document_title: selectedDocument?.title ?? '',
          volume_title: volume?.title ?? '',
          chapter_title: chapter ? chapterDisplayTitle(chapter) : '',
        },
      },
    });
  }

  async function showDocumentContent(chapterId: number | null) {
    if (!selectedDocument) return;
    if (!(await flushEditorDraft('切换章节'))) return;
    setProcessingBusy(true);
    setError(null);
    try {
      const [content, draft] = await Promise.all([
        getLibraryDocumentContent(selectedDocument.id, chapterId),
        getLibraryDocumentDraft(selectedDocument.id, chapterId),
      ]);
      setSelectedChapterId(chapterId);
      setDocumentContent(content);
      setDocumentDraft(draft);
      setEditorDirty(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setProcessingBusy(false);
    }
  }

  async function applyPromptCleanup(prompt: string) {
    if (!selectedDocument) return;
    if (!(await flushEditorDraft('文字整理'))) return;
    await runProcessing(async () => {
      if (editorDirty || documentDraft) {
        await commitLibraryDocumentDraft(selectedDocument.id, selectedChapterId);
      }
      const result = await cleanupLibraryDocumentWithAI(selectedDocument.id, selectedChapterId, prompt);
      await loadLibrary(selectedDocument.id);
      const [revisionItems, directory] = await Promise.all([
        getLibraryDocumentRevisions(selectedDocument.id),
        getLibraryDocumentDirectory(selectedDocument.id),
      ]);
      const chapterItems = applyDirectory(directory);
      setRevisions(revisionItems);
      const resolvedChapterId = chapterItems.find((chapter) => chapter.index === chapters.find((chapter) => chapter.id === selectedChapterId)?.index)?.id ?? chapterItems[0]?.id ?? null;
      setSelectedChapterId(resolvedChapterId);
      setDocumentContent(await getLibraryDocumentContent(selectedDocument.id, resolvedChapterId));
      setDocumentDraft(null);
      setCleanupOpen(false);
      setMessage(`已生成文字整理版本 ${result.revision.revision_number}。`);
    });
  }

  async function restoreRevision(revisionId: number) {
    if (!selectedDocument) return;
    if (!(await flushEditorDraft('恢复旧版本'))) return;
    await runProcessing(async () => {
      await activateLibraryDocumentRevision(selectedDocument.id, revisionId);
      await loadLibrary(selectedDocument.id);
      applyDirectory(await getLibraryDocumentDirectory(selectedDocument.id));
      setSelectedChapterId(null);
      setDocumentContent(await getLibraryDocumentContent(selectedDocument.id));
      setDocumentDraft(await getLibraryDocumentDraft(selectedDocument.id));
      setMessage('已切换到所选文档版本。');
    });
  }

  async function exportDocument(format: 'txt' | 'epub') {
    if (!selectedDocument) return;
    const outputPath = await window.rustyDesktop?.selectDocumentExportPath?.(format, selectedDocument.title);
    if (!outputPath) return;
    await runBusy(async () => {
      const result = await exportLibraryDocument(selectedDocument.id, format, outputPath);
      setExportOpen(false);
      setMessage(`已导出到 ${result.output_path}`);
    });
  }

  async function runBusy(action: () => Promise<void>, clearMessage = true) {
    setBusy(true);
    setError(null);
    if (clearMessage) setMessage(null);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function runProcessing(action: () => Promise<void>) {
    setProcessingBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setProcessingBusy(false);
    }
  }

  function filterCount(filter: SystemFilter) {
    return documentsForSystemFilter(documents, filter).length;
  }

  function categoryCount(categoryId: number) {
    return systemDocuments.filter((document) => document.category_ids.includes(categoryId)).length;
  }

  async function flushEditorDraft(actionLabel: string): Promise<boolean> {
    const controller = editorControllerRef.current;
    if (!controller) return true;
    const saved = await controller.flushDraft();
    if (!saved) {
      setError(`无法执行“${actionLabel}”：当前草稿未能保存，请解决保存错误后重试。`);
    }
    return saved;
  }

  async function refreshWorkspaceDocument(
    document: LibraryDocument,
    chapterId: number | null,
  ): Promise<void> {
    const [revisionItems, directory] = await Promise.all([
      getLibraryDocumentRevisions(document.id),
      getLibraryDocumentDirectory(document.id),
    ]);
    const chapterItems = applyDirectory(directory);
    const resolvedChapterId = chapterId != null && chapterItems.some((item) => item.id === chapterId)
      ? chapterId
      : chapterItems[0]?.id ?? null;
    const [content, draft] = await Promise.all([
      getLibraryDocumentContent(document.id, resolvedChapterId),
      getLibraryDocumentDraft(document.id, resolvedChapterId),
    ]);
    setDocuments((current) => current.map((item) => item.id === document.id ? document : item));
    setRevisions(revisionItems);
    setSelectedChapterId(resolvedChapterId);
    setDocumentContent(content);
    setDocumentDraft(draft);
    setEditorDirty(false);
  }

  if (workspaceOpen && selectedDocument) {
    return (
      <div className="project-workbench document-workbench">
        <header className="workbench-toolbar">
          <div className="project-heading">
            <button className="button ghost workbench-back-button" onClick={() => { void flushEditorDraft('关闭工作台').then((saved) => { if (saved) setWorkspaceOpen(false); }); }} type="button">
              <ArrowLeft size={16} />返回文档库
            </button>
          </div>
          <div className="chapter-heading">
            <div>
              <strong>{selectedDocument.title}</strong>
            </div>
          </div>
          <div className="toolbar-actions" />
        </header>
        <div className="workbench-feedback">
          {error ? <div className="inline-alert error workbench-alert" role="alert"><span>{error}</span></div> : null}
          {message ? <div className="inline-alert success workbench-alert" role="status"><span>{message}</span></div> : null}
        </div>
        <DocumentWorkspace
          ref={editorControllerRef}
          chapters={chapters}
          volumes={volumes}
          content={documentContent}
          draft={documentDraft}
          document={selectedDocument}
          onContentChange={(chapterId) => void showDocumentContent(chapterId)}
          onExport={() => { void flushEditorDraft('导出文档').then((saved) => { if (saved) setExportOpen(true); }); }}
          onDocumentAction={(action) => void handleDocumentAction(action)}
          onOpenCleanup={() => { void flushEditorDraft('文字整理').then((saved) => { if (saved) setCleanupOpen(true); }); }}
          onOpenRevisions={() => { void flushEditorDraft('版本记录').then((saved) => { if (saved) setRevisionsOpen(true); }); }}
          onUpdateMetadata={saveWorkspaceMetadata}
          onSaveDraft={saveCurrentDraft}
          onCommitDraft={commitCurrentDraft}
          onDirtyChange={setEditorDirty}
          onDraftSaved={setDocumentDraft}
          onTitlePreview={(title) => {
            if (selectedChapterId == null) return;
            setChapters((current) => current.map((chapter) => (
              chapter.id === selectedChapterId ? { ...chapter, title } : chapter
            )));
          }}
          onSelectionResource={(kind, text, startOffset, endOffset) => void saveSelection(kind, text, startOffset, endOffset)}
          onRenameVolume={(volumeId, title) => void renameVolume(volumeId, title)}
          onReorder={(draggedId, targetId, targetVolumeId) => void reorderChapters(draggedId, targetId, targetVolumeId)}
          processingBusy={processingBusy}
          selectedChapterId={selectedChapterId}
          readOnly={selectedDocument.is_project_document}
        />
        {cleanupOpen ? (
          <CleanupDialog
            busy={processingBusy}
            onApply={(prompt) => void applyPromptCleanup(prompt)}
            onClose={() => setCleanupOpen(false)}
          />
        ) : null}
        {revisionsOpen ? (
          <RevisionHistoryDialog
            busy={processingBusy}
            document={selectedDocument}
            onClose={() => setRevisionsOpen(false)}
            onRestore={(revisionId) => void restoreRevision(revisionId).then(() => setRevisionsOpen(false))}
            readOnly={selectedDocument.is_project_document}
            revisions={revisions}
          />
        ) : null}
        {exportOpen ? <ExportDialog busy={busy} document={selectedDocument} onClose={() => setExportOpen(false)} onExport={(format) => void exportDocument(format)} /> : null}
        {actionDialog ? (
          <DocumentActionDialog
            action={actionDialog}
            busy={busy}
            chapters={chapters}
            currentChapterId={selectedChapterId}
            currentBodyLength={documentDraft?.text.length ?? documentContent?.body_text.length ?? 0}
            cursorOffset={editorControllerRef.current?.getCursorOffset() ?? null}
            currentDocument={selectedDocument}
            documents={documents}
            onClose={() => setActionDialog(null)}
            onCreateChapter={async (title, text, position, anchorChapterId) => {
              await runBusy(async () => {
                const result = await createLibraryDocumentChapter(
                  selectedDocument.id,
                  title,
                  text,
                  position,
                  anchorChapterId,
                );
                setActionDialog(null);
                await refreshWorkspaceDocument(result.document, result.created_chapter_id);
                setMessage('新增章节已写入新版本。');
              });
            }}
            onMerge={async (ids, title) => {
              await runBusy(async () => {
                const merged = await mergeLibraryDocuments(ids, title);
                setActionDialog(null);
                setWorkspaceOpen(false);
                await loadLibrary(merged.id);
                setMessage('合并文档已创建，源文档未修改。');
              });
            }}
            onCursorSplit={async (nextTitle, cursorOffset) => {
              if (selectedChapterId == null) return;
              await runBusy(async () => {
                const result = await splitLibraryDocumentChapterAtCursor(
                  selectedDocument.id,
                  selectedChapterId,
                  cursorOffset,
                  nextTitle,
                );
                setActionDialog(null);
                await refreshWorkspaceDocument(result.document, result.created_chapter_id);
                setMessage('已在光标位置分章并生成新版本。');
              });
            }}
            onAIPreview={(prompt) => {
              if (selectedChapterId == null) return Promise.reject(new Error('请先选择一个章节。'));
              return previewAIDocumentSplit(selectedDocument.id, selectedChapterId, prompt);
            }}
            onAIApply={async (proposal) => {
              await runBusy(async () => {
                const result = await applyAIDocumentSplit(selectedDocument.id, proposal.proposal_id, proposal.chapters);
                const currentIndex = chapters.find((chapter) => chapter.id === selectedChapterId)?.index ?? 1;
                setActionDialog(null);
                await refreshWorkspaceDocument(
                  { ...selectedDocument, chapter_count: result.chapters.length },
                  result.chapters.find((chapter) => chapter.index === currentIndex)?.id ?? result.chapters[0]?.id ?? null,
                );
                setMessage('AI 分章已应用为新文档版本。');
              });
            }}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div className="document-library-page">
      <TopBar
        title="文档库"
        actions={(
          <>
            <SecondaryButton disabled={busy || !window.rustyDesktop?.selectDocumentLibraryDirectory} onClick={() => void migrateLibraryDirectory()}>
              <Settings2 size={16} />修改目录
            </SecondaryButton>
            <PrimaryButton disabled={busy || !window.rustyDesktop?.selectLibraryDocumentFile} onClick={() => void importDocument()}>
              <FileInput size={16} />{busy ? '处理中…' : '导入文档'}
            </PrimaryButton>
          </>
        )}
      />

      {error ? <div className="inline-alert error document-library-alert" role="alert">{error}</div> : null}
      {message ? <div className="inline-alert success document-library-alert" role="status">{message}</div> : null}

      <div className="document-library-layout">
        <aside className="document-tag-panel">
          <header>
            <h2>文档筛选</h2>
          </header>
          <nav aria-label="文档筛选">
            {systemFilters.map(({ icon: Icon, key, label }) => (
              <TagFilterButton active={systemFilter === key} count={filterCount(key)} icon={<Icon size={16} />} key={key} label={label} onClick={() => {
                setSystemFilter(key);
              }} />
            ))}
            <LibraryDivider />
            <LibrarySidebarSectionTitle action={<button aria-label="新建文档分类" className="document-add-tag" disabled={busy} onClick={() => setCategoryCreateOpen(true)} title="新建分类" type="button"><Plus size={15} /></button>}>我的分类</LibrarySidebarSectionTitle>
            {categories.length ? categories.map((category) => (
              <TagFilterButton
                active={activeCategoryId === category.id}
                count={categoryCount(category.id)}
                icon={<Folder size={16} />}
                key={category.id}
                label={category.name}
                onClick={() => setActiveCategoryId(activeCategoryId === category.id ? null : category.id)}
                onContextMenu={(event) => {
                  event.preventDefault();
                  setCategoryContextMenu({ category, x: event.clientX, y: event.clientY });
                }}
              />
            )) : <p className="document-tag-empty">暂无自定义分类</p>}
          </nav>
        </aside>

        <main className="document-shelf-panel">
          <header>
            <div className="document-shelf-tools">
              <label className="search-field document-search">
                <Search size={15} /><span className="sr-only">搜索文档</span>
                <input onChange={(event) => setSearchText(event.target.value)} placeholder="搜索标题或作者" type="search" value={searchText} />
              </label>
            </div>
          </header>
          {loading ? <ShelfMessage title="正在读取文档库…" /> : visibleDocuments.length ? (
            <div className="document-shelf-scroll">
              <LibraryResourceGrid>
                {visibleDocuments.map((document) => (
                  <LibraryResourceCard
                    ariaLabel={`${document.title}，${document.author || '未知作者'}`}
                    key={document.id}
                    onClick={() => setSelectedId(document.id)}
                    onDoubleClick={() => void openProcessing(document)}
                    selected={selectedDocument?.id === document.id}
                  >
                    <DefaultBookCover document={document} />
                  </LibraryResourceCard>
                ))}
              </LibraryResourceGrid>
            </div>
          ) : documents.length === 0 ? (
            <ShelfMessage action={<PrimaryButton disabled={busy} onClick={() => void importDocument()}><FileInput size={16} />导入第一本文档</PrimaryButton>} title="文档库还是空的" />
          ) : <ShelfMessage title="没有匹配的文档" />}
        </main>

        <aside className="document-detail-panel">
          <header>
            <h2>文档详情</h2>
          </header>
          {selectedDocument ? (
            <>
              <div className="document-detail-scroll">
                <section className="document-detail-identity">
                  <div>
                    {editingMetadata === 'title' ? (
                      <input
                        autoFocus
                        className="document-metadata-input title"
                        onBlur={() => void saveMetadata()}
                        onChange={(event) => setMetadataTitle(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') event.currentTarget.blur();
                          if (event.key === 'Escape') setEditingMetadata(null);
                        }}
                        value={metadataTitle}
                      />
                    ) : (
                      <button className="document-editable-title" onClick={() => beginMetadataEdit('title')} title="点击修改文档名称" type="button">
                        {selectedDocument.title}
                      </button>
                    )}
                    {editingMetadata === 'author' ? (
                      <input
                        autoFocus
                        className="document-metadata-input author"
                        onBlur={() => void saveMetadata()}
                        onChange={(event) => setMetadataAuthor(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') event.currentTarget.blur();
                          if (event.key === 'Escape') setEditingMetadata(null);
                        }}
                        placeholder="未知作者"
                        value={metadataAuthor}
                      />
                    ) : (
                      <button className="document-editable-author" onClick={() => beginMetadataEdit('author')} title="点击修改作者" type="button">
                        {selectedDocument.author || '未知作者'}
                      </button>
                    )}
                  </div>
                </section>
                <section className="document-detail-metadata">
                  <Definition label="导入时间" value={formatDate(selectedDocument.created_at)} />
                  <Definition label="保存格式" value="UTF-8 TXT" />
                  <Definition label="文件大小" value={formatBytes(selectedDocument.stored_size_bytes)} />
                  <Definition label="章节" value={selectedDocument.chapter_count ? `${selectedDocument.chapter_count} 章` : '尚未识别'} />
                  <Definition label="字数" value={formatNumber(selectedDocument.word_count)} />
                </section>
                <LibraryDetailSection action={<button aria-label="管理当前文档标签" className="document-inline-plus" onClick={() => setResourceManager('tag')} type="button"><Plus size={14} /></button>} title="标签">
                  {selectedDocument.tags.length ? (
                    <div className="document-tag-checks">
                      {tags.filter((tag) => selectedDocument.tags.includes(tag.name)).map((tag) => (
                        <LibraryTagChip
                          active={activeTagIds.includes(tag.id)}
                          key={tag.id}
                          onClick={() => setActiveTagIds((current) => (
                            current.includes(tag.id)
                              ? current.filter((id) => id !== tag.id)
                              : [...current, tag.id]
                          ))}
                        >
                          {tag.name}
                        </LibraryTagChip>
                      ))}
                    </div>
                  ) : <p className="document-resource-empty">未设置标签</p>}
                </LibraryDetailSection>
              </div>
              <section className="document-library-location">
                <span>文档库存储目录</span>
                <div title={libraryPath}>{libraryPath || '正在读取目录…'}</div>
              </section>
              <footer className="library-detail-footer">
                <SecondaryButton onClick={() => setExportOpen(true)}><Download size={15} />导出文档</SecondaryButton>
                <DangerButton onClick={() => void deleteDocument()}><Trash2 size={15} />删除</DangerButton>
              </footer>
            </>
          ) : <ShelfMessage title="选择一本书查看详情" />}
        </aside>
      </div>

      {exportOpen && selectedDocument ? <ExportDialog busy={busy} document={selectedDocument} onClose={() => setExportOpen(false)} onExport={(format) => void exportDocument(format)} /> : null}
      {resourceManager ? (
        <ResourceAssignmentDialog
          busy={busy}
          document={selectedDocument}
          items={tags}
          onClose={() => setResourceManager(null)}
          onCreate={(name) => void createManagedResource('tag', name)}
          onToggle={(tagId, selected) => void toggleDocumentTag(tagId, selected)}
        />
      ) : null}
      {categoryCreateOpen ? (
        <DocumentCategoryNameDialog
          busy={busy}
          category={null}
          onClose={() => setCategoryCreateOpen(false)}
          onSave={(name) => void createManagedResource('category', name)}
        />
      ) : null}
      {categoryContextMenu ? (
        <LibraryContextMenu
          actions={[
            { icon: <Pencil size={14} />, label: '重命名', onSelect: () => setCategoryRename(categoryContextMenu.category) },
            { danger: true, icon: <Trash2 size={14} />, label: '删除分类', onSelect: () => void removeCategory(categoryContextMenu.category) },
          ]}
          label={`${categoryContextMenu.category.name} 分类操作`}
          onClose={() => setCategoryContextMenu(null)}
          x={categoryContextMenu.x}
          y={categoryContextMenu.y}
        />
      ) : null}
      {categoryRename ? (
        <DocumentCategoryNameDialog
          busy={busy}
          category={categoryRename}
          onClose={() => setCategoryRename(null)}
          onSave={(name) => void renameCategory(categoryRename, name)}
        />
      ) : null}
    </div>
  );
}

type DocumentWorkspaceProps = {
  chapters: LibraryDocumentChapter[];
  volumes: LibraryDocumentVolume[];
  content: LibraryDocumentContent | null;
  draft: LibraryDocumentDraft | null;
  document: LibraryDocument;
  onContentChange: (chapterId: number | null) => void;
  onExport: () => void;
  onReorder: (draggedId: number, targetId: number | null, targetVolumeId: number | null) => void;
  onRenameVolume: (volumeId: number, title: string) => void;
  onDocumentAction: (action: DocumentAction) => void;
  onOpenCleanup: () => void;
  onOpenRevisions: () => void;
  onUpdateMetadata: (title: string, author: string) => Promise<void>;
  onSaveDraft: (title: string, text: string) => Promise<LibraryDocumentDraft>;
  onCommitDraft: () => Promise<boolean>;
  onDraftSaved: (draft: LibraryDocumentDraft) => void;
  onDirtyChange: (dirty: boolean) => void;
  onTitlePreview: (title: string) => void;
  onSelectionResource: (kind: 'scene' | 'plot' | 'character', text: string, startOffset: number, endOffset: number) => void;
  processingBusy: boolean;
  readOnly: boolean;
  selectedChapterId: number | null;
};

type DocumentEditorController = {
  flushDraft: () => Promise<boolean>;
  getCursorOffset: () => number | null;
};

const DocumentWorkspace = forwardRef<DocumentEditorController, DocumentWorkspaceProps>(function DocumentWorkspace(props, ref) {
  const { document, processingBusy } = props;
  const editorRef = useRef<DocumentEditorController | null>(null);
  const selectedChapter = props.chapters.find((chapter) => chapter.id === props.selectedChapterId) ?? null;
  const [liveCount, setLiveCount] = useState(selectedChapter?.word_count ?? document.word_count);
  const [saveInfo, setSaveInfo] = useState<{ status: SaveStatus; savedAt: string }>({ status: 'clean', savedAt: '' });
  const [metadataTitle, setMetadataTitle] = useState(document.title);
  const [metadataAuthor, setMetadataAuthor] = useState(document.author ?? '');
  const handleSaveStatusChange = useCallback((status: SaveStatus, savedAt: string) => {
    setSaveInfo((current) => current.status === status && current.savedAt === savedAt
      ? current
      : { status, savedAt });
  }, []);

  useEffect(() => {
    setLiveCount(selectedChapter?.word_count ?? document.word_count);
  }, [document.word_count, selectedChapter?.id, selectedChapter?.word_count]);

  useEffect(() => {
    setMetadataTitle(document.title);
    setMetadataAuthor(document.author ?? '');
  }, [document.author, document.title]);

  useImperativeHandle(ref, () => ({
    flushDraft: () => editorRef.current?.flushDraft() ?? Promise.resolve(true),
    getCursorOffset: () => editorRef.current?.getCursorOffset() ?? null,
  }), []);

  const liveTotal = selectedChapter
    ? Math.max(0, document.word_count - selectedChapter.word_count + liveCount)
    : liveCount;

  return (
    <div className="workbench-grid document-workspace-layout">
      <WorkspaceChapterNav
        chapters={props.chapters}
        liveChapterId={props.selectedChapterId}
        liveWordCount={liveCount}
        onContentChange={props.onContentChange}
        onRenameVolume={props.onRenameVolume}
        onReorder={props.onReorder}
        selectedChapterId={props.selectedChapterId}
        readOnly={props.readOnly}
        volumes={props.volumes}
      />
      <main className="workspace-center document-workspace-main">
        <div className="document-workspace-content">
          <EditableTextPreview
            content={props.content}
            draft={props.draft}
            chapterIndex={selectedChapter?.index ?? null}
            loading={processingBusy}
            onCommit={props.onCommitDraft}
            onDirtyChange={props.onDirtyChange}
            onDraftSaved={props.onDraftSaved}
            onLiveCountChange={setLiveCount}
            onSaveDraft={props.onSaveDraft}
            onSaveStatusChange={handleSaveStatusChange}
            onSelectionResource={props.onSelectionResource}
            onTitlePreview={props.onTitlePreview}
            readOnly={props.readOnly}
            ref={editorRef}
          />
        </div>
      </main>
      <aside className="workbench-inspector document-workspace-inspector">
        <div className="document-workspace-info">
          <section>
            <label className="document-workspace-metadata"><span>书名</span><input aria-label="书名" onBlur={() => { if (!props.readOnly) void props.onUpdateMetadata(metadataTitle, metadataAuthor); }} onChange={(event) => setMetadataTitle(event.target.value)} readOnly={props.readOnly} value={metadataTitle} /></label>
            <label className="document-workspace-metadata"><span>作者</span><input aria-label="作者" onBlur={() => { if (!props.readOnly) void props.onUpdateMetadata(metadataTitle, metadataAuthor); }} onChange={(event) => setMetadataAuthor(event.target.value)} placeholder="未知作者" readOnly={props.readOnly} value={metadataAuthor} /></label>
          </section>
          <section className="document-workspace-stats">
            <div><strong>{formatNumber(liveTotal)}</strong><span>全文字数</span></div>
            <div><strong>{formatNumber(liveCount)}</strong><span>{selectedChapter ? '当前章节' : '当前正文'}</span></div>
            <div><strong>{document.chapter_count}</strong><span>章节数</span></div>
            <div><strong>{formatDateTime(document.updated_at)}</strong><span>修改时间</span></div>
            <div><strong>{saveStatusLabel(saveInfo.status, saveInfo.savedAt)}</strong><span>保存状态</span></div>
          </section>
        </div>
        <div className="document-workspace-actions">
          <div className="document-workspace-action-scroll">
            {!props.readOnly ? <div className="inspector-action-area">
              <button className="button secondary full" onClick={() => props.onDocumentAction('merge')} type="button"><Combine size={16} />合并文档</button>
              <button className="button secondary full" onClick={() => props.onDocumentAction('create-chapter')} type="button"><Plus size={16} />新增章节</button>
              <button className="button secondary full" onClick={() => props.onDocumentAction('split')} type="button"><Scissors size={16} />分章</button>
              <button className="button secondary full" onClick={props.onOpenCleanup} type="button"><WandSparkles size={16} />文字整理</button>
              <button className="button secondary full" onClick={props.onOpenRevisions} type="button"><Clock3 size={16} />版本记录</button>
            </div> : <div className="inspector-action-area"><div className="document-readonly-note">工程文档由工程保存结果同步，此处为只读工作区。</div><button className="button secondary full" onClick={props.onOpenRevisions} type="button"><Clock3 size={16} />版本记录</button></div>}
          </div>
          <SecondaryButton onClick={props.onExport}><Download size={15} />导出文档</SecondaryButton>
        </div>
      </aside>
    </div>
  );
});

function WorkspaceChapterNav({
  chapters,
  liveChapterId,
  liveWordCount,
  onContentChange,
  onRenameVolume,
  onReorder,
  selectedChapterId,
  readOnly,
  volumes,
}: {
  chapters: LibraryDocumentChapter[];
  liveChapterId: number | null;
  liveWordCount: number;
  onContentChange: (chapterId: number | null) => void;
  onRenameVolume: (volumeId: number, title: string) => void;
  onReorder: (draggedId: number, targetId: number | null, targetVolumeId: number | null) => void;
  selectedChapterId: number | null;
  readOnly: boolean;
  volumes: LibraryDocumentVolume[];
}) {
  const listRef = useRef<HTMLElement>(null);
  const [collapsed, setCollapsed] = useState<Set<number>>(() => new Set());

  function startDrag(event: DragEvent<HTMLButtonElement>, chapterId: number) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(chapterId));
  }

  function dropChapter(
    event: DragEvent<HTMLElement>,
    targetId: number | null,
    volumeId: number | null,
  ) {
    event.preventDefault();
    const draggedId = Number(event.dataTransfer.getData('text/plain'));
    if (Number.isFinite(draggedId)) onReorder(draggedId, targetId, volumeId);
  }

  const unassigned = chapters.filter((chapter) => chapter.volume_id == null);
  const directoryItems: Array<
    | { kind: 'chapter'; sort: number; chapter: LibraryDocumentChapter }
    | { kind: 'volume'; sort: number; volume: LibraryDocumentVolume }
  > = [
    ...unassigned.map((chapter) => ({ kind: 'chapter' as const, sort: chapter.index, chapter })),
    ...volumes.map((volume) => ({
      kind: 'volume' as const,
      sort: Math.min(
        ...chapters.filter((chapter) => chapter.volume_id === volume.id).map((chapter) => chapter.index),
        Number.MAX_SAFE_INTEGER - volumes.length + volume.index,
      ),
      volume,
    })),
  ].sort((left, right) => left.sort - right.sort);
  const renderChapter = (chapter: LibraryDocumentChapter) => (
    <button
      aria-current={selectedChapterId === chapter.id ? 'page' : undefined}
      className={`chapter-row draggable ${selectedChapterId === chapter.id ? 'selected' : ''}`}
      draggable={!readOnly}
      key={chapter.id}
      onClick={() => onContentChange(chapter.id)}
      onDragOver={(event) => { if (!readOnly) event.preventDefault(); }}
      onDragStart={(event) => { if (!readOnly) startDrag(event, chapter.id); }}
      onDrop={(event) => { if (!readOnly) dropChapter(event, chapter.id, chapter.volume_id); }}
      type="button"
    >
      <span className="chapter-number">{chapterOrdinal(chapter.index)}</span>
      <span className="chapter-name" title={chapter.title || '未命名'}>{chapter.title || '未命名'}</span>
      <span className="chapter-state">{formatNumber(chapter.id === liveChapterId ? liveWordCount : chapter.word_count)} 字</span>
    </button>
  );

  return (
    <aside className="chapter-binder document-workspace-chapters">
      <div className="binder-heading"><h2>章节目录</h2><span>共 {chapters.length} 章</span></div>
      <nav className="chapter-list" ref={listRef}>
        {directoryItems.map((item) => {
          if (item.kind === 'chapter') return renderChapter(item.chapter);
          const volume = item.volume;
          const volumeChapters = chapters.filter((chapter) => chapter.volume_id === volume.id);
          const isCollapsed = collapsed.has(volume.id);
          return (
            <section className="document-volume-group" key={volume.id}>
              <div
                className="document-volume-row"
                onDragOver={(event) => { if (!readOnly) event.preventDefault(); }}
                onDrop={(event) => { if (!readOnly) dropChapter(event, null, volume.id); }}
              >
                <button
                  aria-expanded={!isCollapsed}
                  className="document-volume-toggle"
                  onClick={() => setCollapsed((current) => {
                    const next = new Set(current);
                    if (next.has(volume.id)) next.delete(volume.id);
                    else next.add(volume.id);
                    return next;
                  })}
                  type="button"
                >
                  <ChevronRight className={isCollapsed ? '' : 'expanded'} size={15} />
                </button>
                <input
                  aria-label={`卷标题：${volume.title}`}
                  defaultValue={volume.title}
                  readOnly={readOnly}
                  onBlur={(event) => {
                    if (event.target.value.trim() && event.target.value.trim() !== volume.title) {
                      onRenameVolume(volume.id, event.target.value);
                    }
                  }}
                />
                <span>{formatNumber(volume.word_count)} 字</span>
              </div>
              {!isCollapsed ? <div className="document-volume-chapters">{volumeChapters.map(renderChapter)}</div> : null}
            </section>
          );
        })}
        {chapters.length === 0 ? <div className="compact-empty">文档中没有章节。</div> : null}
      </nav>
      <div className="binder-footer">
        <button onClick={() => listRef.current?.scrollTo({ behavior: 'smooth', top: 0 })} type="button"><ArrowUpToLine size={14} />回到顶部</button>
        <button onClick={() => listRef.current?.scrollTo({ behavior: 'smooth', top: listRef.current.scrollHeight })} type="button"><ArrowDownToLine size={14} />回到底部</button>
      </div>
    </aside>
  );
}

const EditableTextPreview = forwardRef<DocumentEditorController, {
  chapterIndex: number | null;
  content: LibraryDocumentContent | null;
  draft: LibraryDocumentDraft | null;
  loading: boolean;
  onCommit: () => Promise<boolean>;
  onDirtyChange: (dirty: boolean) => void;
  onDraftSaved: (draft: LibraryDocumentDraft) => void;
  onLiveCountChange: (count: number) => void;
  onSaveDraft: (title: string, text: string) => Promise<LibraryDocumentDraft>;
  onSaveStatusChange: (status: SaveStatus, savedAt: string) => void;
  onSelectionResource: (kind: 'scene' | 'plot' | 'character', text: string, startOffset: number, endOffset: number) => void;
  onTitlePreview: (title: string) => void;
  readOnly: boolean;
}>(function EditableTextPreview({
  chapterIndex,
  content,
  draft,
  loading,
  onCommit,
  onDirtyChange,
  onDraftSaved,
  onLiveCountChange,
  onSaveDraft,
  onSaveStatusChange,
  onSelectionResource,
  onTitlePreview,
  readOnly,
}, ref) {
  const initialText = draft?.text ?? content?.body_text ?? '';
  const initialTitle = draft?.title ?? content?.title ?? '';
  const [text, setText] = useState(initialText);
  const [title, setTitle] = useState(initialTitle);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>(draft ? 'saved' : 'clean');
  const [savedAt, setSavedAt] = useState(draft?.updated_at ?? '');
  const [menu, setMenu] = useState<{ x: number; y: number; text: string; startOffset: number; endOffset: number } | null>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const mountedRef = useRef(true);
  const saveStatusRef = useRef<SaveStatus>(saveStatus);
  const textRef = useRef(text);
  const titleRef = useRef(title);
  const persistedSignatureRef = useRef(draft ? draftSignature(initialTitle, initialText) : '');
  const requestSequenceRef = useRef(0);
  const saveQueueRef = useRef<Promise<boolean>>(Promise.resolve(true));
  const callbacksRef = useRef({ onCommit, onDirtyChange, onDraftSaved, onLiveCountChange, onSaveDraft, onTitlePreview });

  textRef.current = text;
  titleRef.current = title;
  saveStatusRef.current = saveStatus;
  callbacksRef.current = { onCommit, onDirtyChange, onDraftSaved, onLiveCountChange, onSaveDraft, onTitlePreview };

  useEffect(() => {
    const nextText = draft?.text ?? content?.body_text ?? '';
    const nextTitle = draft?.title ?? content?.title ?? '';
    setText(nextText);
    setTitle(nextTitle);
    setSaveStatus(draft ? 'saved' : 'clean');
    setSavedAt(draft?.updated_at ?? '');
    persistedSignatureRef.current = draft ? draftSignature(nextTitle, nextText) : '';
    onDirtyChange(false);
    onLiveCountChange(countTextUnits(nextText));
    setMenu(null);
  }, [content?.revision_id, content?.chapter_id, draft?.id]);

  useEffect(() => {
    onSaveStatusChange(saveStatus, savedAt);
  }, [onSaveStatusChange, saveStatus, savedAt]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (!['dirty', 'saving', 'error'].includes(saveStatus)) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [saveStatus]);

  useEffect(() => {
    if (!menu) return;
    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (event.button === 0 && !menuRef.current?.contains(event.target as Node)) setMenu(null);
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setMenu(null);
    };
    const closeMenu = () => setMenu(null);
    const editor = editorRef.current;
    window.addEventListener('pointerdown', closeOnOutsidePointer, true);
    window.addEventListener('keydown', closeOnEscape);
    window.addEventListener('resize', closeMenu);
    editor?.addEventListener('scroll', closeMenu, { passive: true });
    return () => {
      window.removeEventListener('pointerdown', closeOnOutsidePointer, true);
      window.removeEventListener('keydown', closeOnEscape);
      window.removeEventListener('resize', closeMenu);
      editor?.removeEventListener('scroll', closeMenu);
    };
  }, [menu]);

  const queueDraftSave = useCallback((snapshotTitle: string, snapshotText: string): Promise<boolean> => {
    const signature = draftSignature(snapshotTitle, snapshotText);
    if (signature === persistedSignatureRef.current) return saveQueueRef.current;
    const sequence = ++requestSequenceRef.current;
    const task = saveQueueRef.current.then(async () => {
      if (mountedRef.current && sequence === requestSequenceRef.current) setSaveStatus('saving');
      try {
        const saved = await callbacksRef.current.onSaveDraft(snapshotTitle, snapshotText);
        persistedSignatureRef.current = signature;
        if (mountedRef.current && sequence === requestSequenceRef.current) {
          setSaveStatus('saved');
          setSavedAt(saved.updated_at);
          callbacksRef.current.onDirtyChange(false);
          callbacksRef.current.onDraftSaved(saved);
        }
        return true;
      } catch {
        if (mountedRef.current && sequence === requestSequenceRef.current) {
          setSaveStatus('error');
          callbacksRef.current.onDirtyChange(true);
        }
        return false;
      }
    });
    saveQueueRef.current = task;
    return task;
  }, []);

  const flushDraft = useCallback(async (): Promise<boolean> => {
    if (saveStatusRef.current === 'clean') return saveQueueRef.current;
    const signature = draftSignature(titleRef.current, textRef.current);
    if (signature === persistedSignatureRef.current) return saveQueueRef.current;
    return queueDraftSave(titleRef.current, textRef.current);
  }, [queueDraftSave]);

  useEffect(() => {
    if (saveStatus !== 'dirty') return undefined;
    const timer = window.setTimeout(() => {
      void queueDraftSave(titleRef.current, textRef.current);
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [saveStatus, text, title, queueDraftSave]);

  function markDirty() {
    setSaveStatus('dirty');
    callbacksRef.current.onDirtyChange(true);
  }

  useImperativeHandle(ref, () => ({
    flushDraft: readOnly ? () => Promise.resolve(true) : flushDraft,
    getCursorOffset: () => editorRef.current?.selectionStart ?? null,
  }), [flushDraft, readOnly]);

  function openMenu(event: MouseEvent<HTMLTextAreaElement>) {
    const target = event.currentTarget;
    const rawSelection = target.value.slice(target.selectionStart, target.selectionEnd);
    const selected = rawSelection.trim();
    if (!selected) {
      setMenu(null);
      return;
    }
    event.preventDefault();
    const leadingWhitespace = rawSelection.length - rawSelection.trimStart().length;
    const startOffset = (content?.body_start_offset ?? 0) + target.selectionStart + leadingWhitespace;
    setMenu({
      x: event.clientX,
      y: event.clientY,
      text: selected,
      startOffset,
      endOffset: startOffset + selected.length,
    });
  }

  return (
    <section aria-busy={loading} className="manuscript-pane document-workspace-text editable-manuscript">
      <header className="document-editor-heading">
        <span aria-hidden="true" className="document-editor-heading-spacer" />
        <label className="document-editor-title">
          {chapterIndex != null ? <strong>{chapterOrdinal(chapterIndex)}</strong> : null}
          <input
            aria-label={content?.chapter_id == null ? '文档标题' : '章节标题'}
            disabled={loading || !content}
            onChange={(event) => {
              setTitle(event.target.value);
              callbacksRef.current.onTitlePreview(event.target.value);
              callbacksRef.current.onLiveCountChange(
                countTextUnits(textRef.current),
              );
              markDirty();
            }}
            placeholder={content?.chapter_id == null ? '文档标题' : '未命名'}
            style={{ width: `${Math.min(40, Math.max(6, Array.from(title || '未命名').length + 1))}em` }}
            value={title}
          />
        </label>
        {!readOnly ? <button
          className="button secondary"
          disabled={saveStatus === 'clean' || saveStatus === 'saving' || loading || !content || (content.chapter_id == null && !title.trim())}
          onClick={() => {
            void flushDraft().then(async (saved) => {
              if (!saved) return;
              if (!(await onCommit()) && mountedRef.current) setSaveStatus('error');
            });
          }}
          type="button"
        ><Save size={15} />保存</button> : <span className="document-readonly-badge">只读</span>}
      </header>
      <textarea
        className="manuscript-editor"
        disabled={loading || !content}
        readOnly={readOnly}
        onChange={(event) => {
          const nextText = event.target.value;
          setText(nextText);
          callbacksRef.current.onLiveCountChange(
            countTextUnits(nextText),
          );
          markDirty();
        }}
        onContextMenu={openMenu}
        ref={editorRef}
        value={loading && !content ? '正在读取正文…' : text}
      />
      {menu ? (
        <div className="selection-resource-menu" ref={menuRef} style={{ left: menu.x, top: menu.y }}>
          <button onClick={() => { onSelectionResource('plot', menu.text, menu.startOffset, menu.endOffset); setMenu(null); }} type="button">添加为剧情骨架来源</button>
          <button onClick={() => { onSelectionResource('scene', menu.text, menu.startOffset, menu.endOffset); setMenu(null); }} type="button">添加为作者风格来源</button>
          <button onClick={() => { onSelectionResource('character', menu.text, menu.startOffset, menu.endOffset); setMenu(null); }} type="button">提取角色卡</button>
        </div>
      ) : null}
    </section>
  );
});

const DEFAULT_CLEANUP_PROMPT = '只整理空白、段落、标点间距和明显排版问题。禁止改剧情、改写句子、添加内容、删除有效正文，也不要改变人物、设定和事实。';
const DEFAULT_SPLIT_PROMPT = '请根据当前章节内容划分自然、连续的章节边界并拟定简洁标题。不得改写、补充、删除或重复原文。';

function CleanupDialog(props: {
  busy: boolean;
  onApply: (prompt: string) => void;
  onClose: () => void;
}) {
  const [preset, setPreset] = useState('default');
  const [prompt, setPrompt] = useState(DEFAULT_CLEANUP_PROMPT);
  return (
    <div className="document-processing-backdrop" role="presentation">
      <section aria-modal="true" className="document-modal document-cleanup-dialog" role="dialog">
        <header><h2>文字整理</h2><button aria-label="关闭文字整理" className="icon-button" onClick={props.onClose} type="button"><X size={17} /></button></header>
        <div className="document-modal-body document-cleanup-body">
          <label className="document-modal-row"><span>整理提示词</span><select className="form-input" value={preset} onChange={(event) => { setPreset(event.target.value); setPrompt(DEFAULT_CLEANUP_PROMPT); }}><option value="default">默认文字整理</option></select></label>
          <label className="document-modal-stack"><span>具体要求</span><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label>
        </div>
        <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || !prompt.trim()} onClick={() => props.onApply(prompt.trim())}><WandSparkles size={16} />应用并生成新版本</PrimaryButton></footer>
      </section>
    </div>
  );
}

function RevisionHistoryDialog(props: {
  busy: boolean;
  document: LibraryDocument;
  onClose: () => void;
  onRestore: (revisionId: number) => void;
  readOnly: boolean;
  revisions: LibraryDocumentRevision[];
}) {
  const currentRevision = props.revisions.find((revision) => revision.storage_path === props.document.storage_path) ?? props.revisions[0];
  const historical = props.revisions.filter((revision) => revision.id !== currentRevision?.id);
  const renderRevision = (revision: LibraryDocumentRevision, current: boolean) => (
    <div key={revision.id}>
      <span>版本 {revision.revision_number} · {revisionLabel(revision.revision_type)} · {formatDateTime(revision.created_at)}</span>
      <button disabled={props.busy || props.readOnly || current} onClick={() => { if (window.confirm('恢复后会切换当前文档版本，确定继续吗？')) props.onRestore(revision.id); }} type="button">{current ? '当前' : props.readOnly ? '只读' : '恢复'}</button>
    </div>
  );
  return (
    <div className="document-processing-backdrop" role="presentation">
      <section aria-modal="true" className="document-modal document-revision-dialog" role="dialog">
        <header><h2>版本记录</h2><button aria-label="关闭版本记录" className="icon-button" onClick={props.onClose} type="button"><X size={17} /></button></header>
        <div className="document-revision-list">
          <h3>当前版本</h3>
          {currentRevision ? renderRevision(currentRevision, true) : null}
          <h3>历史版本</h3>
          {historical.length ? historical.map((revision) => renderRevision(revision, false)) : <p className="document-resource-empty">暂无历史版本</p>}
        </div>
        <footer><SecondaryButton onClick={props.onClose}>关闭</SecondaryButton></footer>
      </section>
    </div>
  );
}

function DocumentActionDialog(props: {
  action: DocumentAction;
  busy: boolean;
  chapters: LibraryDocumentChapter[];
  currentChapterId: number | null;
  currentBodyLength: number;
  cursorOffset: number | null;
  currentDocument: LibraryDocument;
  documents: LibraryDocument[];
  onClose: () => void;
  onCreateChapter: (title: string, text: string, position: 'before' | 'after', anchorChapterId: number | null) => void;
  onCursorSplit: (nextTitle: string, cursorOffset: number) => void;
  onMerge: (ids: number[], title: string) => void;
  onAIPreview: (prompt: string) => Promise<AISplitProposal>;
  onAIApply: (proposal: AISplitProposal) => void;
}) {
  const [title, setTitle] = useState(props.action === 'merge' ? `${props.currentDocument.title} 合并本` : '');
  const [text, setText] = useState('');
  const [positionMode, setPositionMode] = useState<'before-current' | 'after-current' | 'after-index'>(props.currentChapterId ? 'after-current' : 'after-index');
  const [anchorIndex, setAnchorIndex] = useState(props.chapters.at(-1)?.index ?? 1);
  const [splitTab, setSplitTab] = useState<'cursor' | 'ai'>('cursor');
  const [selected, setSelected] = useState<number[]>([]);
  const [splitPrompt, setSplitPrompt] = useState(DEFAULT_SPLIT_PROMPT);
  const [localError, setLocalError] = useState('');
  async function applyAI() {
    try { props.onAIApply(await props.onAIPreview(splitPrompt)); setLocalError(''); } catch (reason) { setLocalError(errorMessage(reason)); }
  }
  function moveDocument(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= selected.length) return;
    const next = [...selected];
    [next[index], next[target]] = [next[target], next[index]];
    setSelected(next);
  }
  const heading = props.action === 'merge' ? '合并文档' : props.action === 'create-chapter' ? '新增章节' : '分章';
  const currentChapter = props.chapters.find((chapter) => chapter.id === props.currentChapterId) ?? props.chapters.at(-1) ?? null;
  const indexedAnchor = props.chapters.find((chapter) => chapter.index === anchorIndex) ?? null;
  const createPosition = positionMode === 'before-current' ? 'before' : 'after';
  const createAnchor = positionMode === 'after-index' ? indexedAnchor : currentChapter;
  return (
    <div className="document-processing-backdrop" role="presentation">
      <section className={`document-modal document-action-dialog action-${props.action}`} role="dialog" aria-modal="true">
        <header><h2>{heading}</h2><button aria-label={`关闭${heading}`} className="icon-button" onClick={props.onClose} type="button"><X size={17} /></button></header>
        {props.action === 'merge' ? (
          <>
            <div className="document-modal-body">
              <label className="document-modal-row"><span>新文档标题</span><input className="form-input" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
              <div className="document-merge-columns">
                <section><h3>可添加文档</h3><div className="document-merge-list">{props.documents.filter((document) => document.id !== props.currentDocument.id).map((document) => <div key={document.id}><span>{document.title}{document.is_project_document ? <small className="document-project-inline-badge">工程</small> : null}</span><button className="button secondary compact" disabled={selected.includes(document.id)} onClick={() => setSelected((current) => [...current, document.id])} type="button">添加</button></div>)}</div></section>
                <section><h3>已选择</h3><div className="document-merge-list document-merge-order">{selected.map((id, index) => <div key={id}><span>{index + 1}. {props.documents.find((item) => item.id === id)?.title}</span><span className="document-merge-controls"><button aria-label="上移" disabled={index === 0} onClick={() => moveDocument(index, -1)} type="button">↑</button><button aria-label="下移" disabled={index === selected.length - 1} onClick={() => moveDocument(index, 1)} type="button">↓</button><button onClick={() => setSelected((current) => current.filter((item) => item !== id))} type="button">移除</button></span></div>)}</div></section>
              </div>
            </div>
            <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || selected.length < 1 || !title.trim()} onClick={() => props.onMerge([props.currentDocument.id, ...selected], title.trim())}>创建新文档</PrimaryButton></footer>
          </>
        ) : null}
        {props.action === 'create-chapter' ? (
          <>
            <div className="document-modal-body document-create-chapter-body">
              <label className="document-modal-row"><span>章节标题</span><input className="form-input" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
              <label className="document-modal-row"><span>插入位置</span><select value={positionMode} onChange={(event) => setPositionMode(event.target.value as typeof positionMode)}><option value="before-current">本章之前</option><option value="after-current">本章之后</option><option value="after-index">指定章节之后</option></select></label>
              {positionMode === 'after-index' ? <label className="document-modal-row"><span>指定章节</span><select aria-label="指定章节" value={anchorIndex} onChange={(event) => setAnchorIndex(Number(event.target.value))}>{props.chapters.map((chapter) => <option key={chapter.id} value={chapter.index}>{chapterDisplayTitle(chapter)}</option>)}</select></label> : <p className="document-action-anchor">锚点：{currentChapter ? chapterDisplayTitle(currentChapter) : '当前文档暂无章节'}</p>}
              <label className="document-modal-stack document-chapter-text"><span>正文</span><textarea value={text} onChange={(event) => setText(event.target.value)} /></label>
            </div>
            <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || (props.chapters.length > 0 && !createAnchor)} onClick={() => props.onCreateChapter(title.trim(), text, createPosition, createAnchor?.id ?? null)}>保存为新版本</PrimaryButton></footer>
          </>
        ) : null}
        {props.action === 'split' ? (
          <>
            <div className="document-modal-body document-split-body">
              <div className="document-split-tabs"><button className={splitTab === 'cursor' ? 'selected' : ''} onClick={() => setSplitTab('cursor')} type="button">光标处分章</button><button className={splitTab === 'ai' ? 'selected' : ''} onClick={() => setSplitTab('ai')} type="button">AI 分章</button></div>
              {splitTab === 'cursor' ? <><label className="document-modal-row"><span>下一章标题</span><input className="form-input" value={title} onChange={(event) => setTitle(event.target.value)} /></label><p className="document-cursor-position">当前分割位置：{props.cursorOffset == null ? '请先在正文中放置光标' : `第 ${props.cursorOffset} 字`}</p></> : <label className="document-modal-stack"><span>分章要求</span><textarea value={splitPrompt} onChange={(event) => setSplitPrompt(event.target.value)} /></label>}
            </div>
            <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton>{splitTab === 'cursor' ? <PrimaryButton disabled={props.busy || !title.trim() || props.cursorOffset == null || props.cursorOffset <= 0 || props.cursorOffset >= props.currentBodyLength} onClick={() => props.onCursorSplit(title.trim(), props.cursorOffset!)}>分章</PrimaryButton> : <PrimaryButton disabled={props.busy || !splitPrompt.trim()} onClick={() => void applyAI()}>AI 分章</PrimaryButton>}</footer>
          </>
        ) : null}
        {localError ? <div className="inline-alert error" role="alert">{localError}</div> : null}
      </section>
    </div>
  );
}

function DocumentCategoryNameDialog({
  busy,
  category,
  onClose,
  onSave,
}: {
  busy: boolean;
  category: DocumentCategory | null;
  onClose: () => void;
  onSave: (name: string) => void;
}) {
  const [name, setName] = useState(category?.name ?? '');
  const normalizedName = name.trim();
  return (
    <LibraryDialog
      className="document-category-name-dialog"
      footer={<><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !normalizedName} onClick={() => onSave(normalizedName)}>{category ? '保存' : '新建'}</PrimaryButton></>}
      onClose={onClose}
      title={category ? '重命名分类' : '新建分类'}
    >
      <label className="library-name-field"><span>分类名称</span><input autoFocus className="form-input" maxLength={40} onChange={(event) => setName(event.target.value)} value={name} /></label>
    </LibraryDialog>
  );
}

function ResourceAssignmentDialog({
  busy,
  document,
  items,
  onClose,
  onCreate,
  onToggle,
}: {
  busy: boolean;
  document: LibraryDocument | null;
  items: ResourceTag[];
  onClose: () => void;
  onCreate: (name: string) => void;
  onToggle: (tagId: number, selected: boolean) => void;
}) {
  const [selectedIds, setSelectedIds] = useState<number[]>(() => items.filter((item) => document?.tags.includes(item.name)).map((item) => item.id));
  const [name, setName] = useState('');
  useEffect(() => {
    setSelectedIds(items.filter((item) => document?.tags.includes(item.name)).map((item) => item.id));
  }, [document?.tags, items]);
  return (
    <div className="document-processing-backdrop" role="presentation">
      <section
        aria-labelledby="document-resource-title"
        aria-modal="true"
        className="document-modal document-resource-dialog"
        role="dialog"
      >
        <header>
          <h2 id="document-resource-title">管理标签</h2>
          <button aria-label="关闭标签窗口" className="icon-button" onClick={onClose} type="button"><X size={17} /></button>
        </header>
        <div className="document-resource-options">
          {document ? items.map((item) => (
            <label key={item.id}>
              <input
                checked={selectedIds.includes(item.id)}
                disabled={busy}
                onChange={(event) => {
                  const selected = event.target.checked;
                  setSelectedIds((current) => selected ? [...current, item.id] : current.filter((id) => id !== item.id));
                  onToggle(item.id, selected);
                }}
                type="checkbox"
              />
              <span>{item.name}</span>
            </label>
          )) : <p>请先选择文档。</p>}
          {document && !items.length ? <p>尚无可用标签。</p> : null}
        </div>
        <form className="document-resource-create" onSubmit={(event) => { event.preventDefault(); if (name.trim()) { onCreate(name.trim()); setName(''); } }}>
          <input className="form-input" maxLength={40} onChange={(event) => setName(event.target.value)} placeholder="新标签名称" value={name} />
          <SecondaryButton disabled={busy || !name.trim()} type="submit"><Plus size={14} />新建</SecondaryButton>
        </form>
        <footer><SecondaryButton onClick={onClose}>关闭</SecondaryButton></footer>
      </section>
    </div>
  );
}

function ExportDialog({
  busy,
  document,
  onClose,
  onExport,
}: {
  busy: boolean;
  document: LibraryDocument;
  onClose: () => void;
  onExport: (format: 'txt' | 'epub') => void;
}) {
  return (
    <div className="document-processing-backdrop" role="presentation">
      <section aria-labelledby="document-export-title" aria-modal="true" className="document-export-dialog" role="dialog">
        <header>
          <div><span>导出文档</span><h2 id="document-export-title">{document.title}</h2></div>
          <button aria-label="关闭导出" className="icon-button" onClick={onClose} type="button"><X size={17} /></button>
        </header>
        <div className="document-export-options">
          <button disabled={busy} onClick={() => onExport('txt')} type="button"><strong>TXT</strong><span>UTF-8 文本，按当前章节顺序导出</span><ChevronRight size={16} /></button>
          <button disabled={busy} onClick={() => onExport('epub')} type="button"><strong>EPUB</strong><span>生成带目录的电子书</span><ChevronRight size={16} /></button>
        </div>
      </section>
    </div>
  );
}

function TagFilterButton({ active, count, icon, label, onClick, onContextMenu }: { active: boolean; count: number; icon: ReactNode; label: string; onClick: () => void; onContextMenu?: (event: MouseEvent<HTMLButtonElement>) => void }) {
  return <button aria-current={active ? 'page' : undefined} className={`document-tag-item ${active ? 'selected' : ''}`} onClick={onClick} onContextMenu={onContextMenu} type="button">{icon}<span>{label}</span><small>{count}</small></button>;
}

function DefaultBookCover({ compact = false, document }: { compact?: boolean; document: LibraryDocument }) {
  const palette = palettes[(document.id - 1) % palettes.length];
  return <span className={`default-book-cover palette-${palette} ${compact ? 'compact' : ''}`}><span className="default-book-spine" />{document.is_project_document ? <span className="document-project-marker">工程</span> : null}<strong>{document.title}</strong><span className="default-book-author">{document.author || '未知作者'}</span></span>;
}

function Definition({ label, value }: { label: string; value: string }) {
  return <div className="document-definition"><span>{label}</span><strong title={value}>{value}</strong></div>;
}

function ShelfMessage({ action, title }: { action?: ReactNode; title: string }) {
  return <div className="document-shelf-empty"><LibraryBig size={28} /><strong>{title}</strong>{action ? <div className="document-shelf-empty-action">{action}</div> : null}</div>;
}

function documentsForSystemFilter(
  documents: LibraryDocument[],
  filter: SystemFilter,
): LibraryDocument[] {
  if (filter === 'project') return documents.filter((document) => document.is_project_document);
  if (filter === 'recent') {
    return documents.filter((document) => !document.is_project_document)
      .sort((left, right) => right.created_at.localeCompare(left.created_at) || right.id - left.id)
      .slice(0, 5);
  }
  if (filter === 'untagged') {
    return documents.filter((document) => document.tags.length === 0);
  }
  return documents;
}

function chapterOrdinal(index: number): string {
  const digits = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
  if (index < 10) return `第${digits[index]}章`;
  if (index < 20) return `第十${index === 10 ? '' : digits[index % 10]}章`;
  if (index < 100) return `第${digits[Math.floor(index / 10)]}十${index % 10 ? digits[index % 10] : ''}章`;
  return `第${index}章`;
}

function chapterDisplayTitle(chapter: Pick<LibraryDocumentChapter, 'index' | 'title'>): string {
  return `${chapterOrdinal(chapter.index)}${chapter.title ? ` ${chapter.title}` : ''}`;
}

function formatDateTime(value: string): string {
  if (!value) return '—';
  const parsed = new Date(value.includes('T') ? value : `${value.replace(' ', 'T')}Z`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false });
}

function revisionLabel(revisionType: string) {
  if (revisionType === 'import') return '导入版';
  if (revisionType === 'manual_edit') return '手动编辑';
  if (revisionType === 'merge') return '合并';
  if (revisionType === 'split_ai') return 'AI 分章';
  if (revisionType === 'split_cursor') return '光标分章';
  if (revisionType === 'split_regex') return '正则分章';
  if (revisionType === 'project_sync') return '工程同步';
  if (revisionType === 'cleanup_ai') return '文字整理';
  return '文字整理';
}

function statusLabel(status: string) {
  if (status === 'imported') return '已导入';
  if (status === 'processed') return '已处理';
  return status;
}

function countTextUnits(text: string): number {
  return Array.from(text).reduce((count, character) => (/\s/u.test(character) ? count : count + 1), 0);
}

function draftSignature(title: string, text: string): string {
  return `${title}\u0000${text}`;
}

function saveStatusLabel(status: SaveStatus, savedAt: string): string {
  if (status === 'dirty') return '尚未保存草稿';
  if (status === 'saving') return '正在保存';
  if (status === 'error') return '草稿保存失败';
  if (status === 'saved') return savedAt ? `草稿已保存 ${formatDate(savedAt)}` : '草稿已保存';
  return '已保存';
}

function formatDate(value: string) {
  const parsed = new Date(value.replace(' ', 'T') + 'Z');
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false });
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
