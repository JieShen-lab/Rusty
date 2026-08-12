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
  assignDocumentCategory,
  assignDocumentTag,
  cleanupLibraryDocument,
  createDocumentCategory,
  createDocumentTag,
  createLibraryDocumentChapter,
  createDocumentProcessingTemplate,
  deleteLibraryDocument,
  exportLibraryDocument,
  getDocumentTags,
  getDocumentCategories,
  getDocumentLibrarySettings,
  getDocumentProcessingTemplates,
  getLibraryDocumentDirectory,
  getLibraryDocumentContent,
  getLibraryDocumentRevisions,
  getLibraryDocuments,
  importLibraryDocument,
  migrateDocumentLibrary,
  mergeLibraryDocuments,
  previewRegexSplit,
  reorderLibraryDocumentChapters,
  applyRegexSplit,
  markLibraryDocumentChapter,
  previewAIDocumentSplit,
  applyAIDocumentSplit,
  commitLibraryDocumentDraft,
  getLibraryDocumentDraft,
  saveLibraryDocumentDraft,
  renameLibraryDocumentVolume,
  updateLibraryDocument,
} from '../api/client';
import type {
  DocumentProcessingSettings,
  DocumentProcessingTemplate,
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
  SplitPreview,
} from '../api/types';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { DangerButton } from '../components/DangerButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

type ProcessingTab = 'chapters' | 'cleanup' | 'reference';
type DocumentAction = 'merge' | 'create-chapter' | 'split';
type ReferenceScope = 'book' | 'chapters' | 'paragraphs';
type SaveStatus = 'clean' | 'dirty' | 'saving' | 'saved' | 'error';

const systemFilters = [
  { key: 'all', label: '全部文档', icon: LibraryBig },
  { key: 'project', label: '工程文档', icon: FolderOpen },
  { key: 'recent', label: '最近导入', icon: Clock3 },
  { key: 'untagged', label: '无标签', icon: Folder },
] as const;
type SystemFilter = typeof systemFilters[number]['key'];

const palettes = ['indigo', 'terracotta', 'jade', 'slate', 'ochre', 'plum', 'bluegray'] as const;

const fallbackSettings: DocumentProcessingSettings = {
  chapter_pattern: '^\\s*(第[一二三四五六七八九十百千万零〇两0-9]+[章节卷集部篇回].*|[0-9]+[、.． ].*)\\s*$',
  chapter_indent: 0,
  paragraph_indent: 2,
  blank_lines: 1,
  trim_whitespace: true,
};

export function DocumentLibraryPage({ onNavigate }: { onNavigate: (path: string, state?: unknown) => void }) {
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [tags, setTags] = useState<ResourceTag[]>([]);
  const [categories, setCategories] = useState<DocumentCategory[]>([]);
  const [libraryPath, setLibraryPath] = useState('');
  const [systemFilter, setSystemFilter] = useState<SystemFilter>('all');
  const [activeCategoryId, setActiveCategoryId] = useState<number | null>(null);
  const [activeTagId, setActiveTagId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [processingBusy, setProcessingBusy] = useState(false);
  const [templates, setTemplates] = useState<DocumentProcessingTemplate[]>([]);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [templateName, setTemplateName] = useState('自定义排版');
  const [templateSettings, setTemplateSettings] = useState<DocumentProcessingSettings>(fallbackSettings);
  const [revisions, setRevisions] = useState<LibraryDocumentRevision[]>([]);
  const [chapters, setChapters] = useState<LibraryDocumentChapter[]>([]);
  const [volumes, setVolumes] = useState<LibraryDocumentVolume[]>([]);
  const [documentContent, setDocumentContent] = useState<LibraryDocumentContent | null>(null);
  const [documentDraft, setDocumentDraft] = useState<LibraryDocumentDraft | null>(null);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [resourceManager, setResourceManager] = useState<'category' | 'tag' | null>(null);
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
  const activeTag = tags.find((tag) => tag.id === activeTagId) ?? null;
  const visibleDocuments = useMemo(
    () => systemDocuments.filter((document) => (
      (activeCategoryId == null || document.category_ids.includes(activeCategoryId))
      && (activeTag == null || document.tags.includes(activeTag.name))
      && (!query || `${document.title} ${document.author ?? ''} ${document.source_filename}`.toLocaleLowerCase().includes(query))
    )),
    [activeCategoryId, activeTag, query, systemDocuments],
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
  }, [systemFilter, activeCategoryId, activeTagId, query, visibleDocuments, workspaceOpen]);

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
      if (kind === 'category') setCategories((current) => [...current, created as DocumentCategory]);
      else setTags((current) => [...current, created as ResourceTag]);
      setMessage(`已创建${kind === 'category' ? '分类' : '标签'}“${created.name}”。`);
    }, false);
  }

  async function applyManagedResources(kind: 'category' | 'tag', selectedIds: number[]) {
    if (!selectedDocument) return;
    const currentIds = kind === 'category'
      ? selectedDocument.category_ids
      : tags.filter((tag) => selectedDocument.tags.includes(tag.name)).map((tag) => tag.id);
    const allIds = new Set([...currentIds, ...selectedIds]);
    await runBusy(async () => {
      await Promise.all([...allIds].map((id) => (
        kind === 'category'
          ? assignDocumentCategory(selectedDocument.id, id, selectedIds.includes(id))
          : assignDocumentTag(selectedDocument.id, id, selectedIds.includes(id))
      )));
      await loadLibrary(selectedDocument.id);
      setResourceManager(null);
      setMessage(`${kind === 'category' ? '分类' : '标签'}关联已保存。`);
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
    tab: ProcessingTab = 'chapters',
    targetDocument: LibraryDocument | null = selectedDocument,
  ): Promise<boolean> {
    if (!targetDocument) return false;
    if (workspaceOpen && !(await flushEditorDraft(`切换到“${targetDocument.title}”`))) return false;
    setSelectedId(targetDocument.id);
    setWorkspaceOpen(true);
    setProcessingBusy(true);
    setError(null);
    try {
      const [templateItems, revisionItems, directory] = await Promise.all([
        getDocumentProcessingTemplates(),
        getLibraryDocumentRevisions(targetDocument.id),
        getLibraryDocumentDirectory(targetDocument.id),
      ]);
      const chapterItems = applyDirectory(directory);
      const firstChapterId = chapterItems[0]?.id ?? null;
      const [content, draft] = await Promise.all([
        getLibraryDocumentContent(targetDocument.id, firstChapterId),
        getLibraryDocumentDraft(targetDocument.id, firstChapterId),
      ]);
      setTemplates(templateItems);
      setRevisions(revisionItems);
      setSelectedChapterId(firstChapterId);
      setDocumentContent(content);
      setDocumentDraft(draft);
      const defaultTemplate = templateItems.find((template) => template.is_default) ?? templateItems[0];
      if (defaultTemplate) {
        setTemplateId(defaultTemplate.id);
        setTemplateSettings(defaultTemplate.settings);
      }
      return true;
    } catch (err) {
      setError(errorMessage(err));
      setWorkspaceOpen(false);
      return false;
    } finally {
      setProcessingBusy(false);
    }
  }

  async function openAnalysisWorkspace() {
    if (await openProcessing('chapters')) setActionDialog('split');
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
      onNavigate('/characters', {
        characterExtraction: {
          selectedText: selected,
          sourceMetadata: {
            source_kind: 'document',
            source_type: 'document',
            document_id: documentContent.document_id,
            revision_id: documentContent.revision_id,
            chapter_id: documentContent.chapter_id,
            start_offset: startOffset,
            end_offset: endOffset,
            document_title: selectedDocument?.title ?? '',
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
        materialType: kind === 'plot' ? 'plot_skeleton' : 'scene_reference',
        taskType: kind === 'scene' ? 'source_text_to_scene_material' : undefined,
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

  function selectTemplate(nextTemplateId: number) {
    setTemplateId(nextTemplateId);
    const template = templates.find((item) => item.id === nextTemplateId);
    if (template) setTemplateSettings(template.settings);
  }

  async function saveProcessingTemplate() {
    await runProcessing(async () => {
      const saved = await createDocumentProcessingTemplate(templateName, templateSettings);
      setTemplates((current) => [...current, saved]);
      setTemplateId(saved.id);
      setMessage('文字整理模板已保存。');
    });
  }

  async function applyProcessingTemplate() {
    if (!selectedDocument || !templateId) return;
    if (!(await flushEditorDraft('应用文字整理模板'))) return;
    if (documentDraft) {
      setError('文字整理会生成新版本，请先点击正文标题栏的“保存”提交当前草稿。');
      return;
    }
    await runProcessing(async () => {
      const selectedTemplate = templates.find((template) => template.id === templateId);
      let effectiveTemplateId = templateId;
      if (!selectedTemplate || JSON.stringify(selectedTemplate.settings) !== JSON.stringify(templateSettings)) {
        const saved = await createDocumentProcessingTemplate(templateName, templateSettings);
        setTemplates((current) => [...current, saved]);
        setTemplateId(saved.id);
        effectiveTemplateId = saved.id;
      }
      const result = await cleanupLibraryDocument(selectedDocument.id, effectiveTemplateId);
      await loadLibrary(selectedDocument.id);
      const [revisionItems, directory] = await Promise.all([
        getLibraryDocumentRevisions(selectedDocument.id),
        getLibraryDocumentDirectory(selectedDocument.id),
      ]);
      const chapterItems = applyDirectory(directory);
      setRevisions(revisionItems);
      setSelectedChapterId(null);
      setDocumentContent(await getLibraryDocumentContent(selectedDocument.id));
      setDocumentDraft(null);
      setCleanupOpen(false);
      setMessage(result.created ? `已生成版本 ${result.revision.revision_number}。` : '当前版本已经符合模板。');
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
          <div className="toolbar-actions">
            <button className="button ghost" onClick={() => { void flushEditorDraft('导出文档').then((saved) => { if (saved) setExportOpen(true); }); }} type="button"><Download size={16} />导出</button>
          </div>
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
          onManualMark={async (startOffset, endOffset, title) => {
            if (!documentContent) return;
            await runBusy(async () => {
              const saved = await markLibraryDocumentChapter(selectedDocument.id, documentContent.revision_id, title, startOffset, endOffset);
              setChapters(saved);
              setMessage('手动章节区间已加入目录。');
            });
          }}
          onSelectionResource={(kind, text, startOffset, endOffset) => void saveSelection(kind, text, startOffset, endOffset)}
          onRenameVolume={(volumeId, title) => void renameVolume(volumeId, title)}
          onReorder={(draggedId, targetId, targetVolumeId) => void reorderChapters(draggedId, targetId, targetVolumeId)}
          processingBusy={processingBusy}
          selectedChapterId={selectedChapterId}
        />
        {cleanupOpen ? (
          <CleanupDialog
            busy={processingBusy}
            content={documentContent ? { ...documentContent, body_text: documentDraft?.text ?? documentContent.body_text } : null}
            onApply={() => void applyProcessingTemplate()}
            onClose={() => setCleanupOpen(false)}
            onSaveTemplate={() => void saveProcessingTemplate()}
            onSelectTemplate={selectTemplate}
            onSettingsChange={setTemplateSettings}
            onTemplateNameChange={setTemplateName}
            templateId={templateId}
            templateName={templateName}
            templateSettings={templateSettings}
            templates={templates}
          />
        ) : null}
        {revisionsOpen ? (
          <RevisionHistoryDialog
            busy={processingBusy}
            document={selectedDocument}
            onClose={() => setRevisionsOpen(false)}
            onRestore={(revisionId) => void restoreRevision(revisionId).then(() => setRevisionsOpen(false))}
            revisions={revisions}
          />
        ) : null}
        {exportOpen ? <ExportDialog busy={busy} document={selectedDocument} onClose={() => setExportOpen(false)} onExport={(format) => void exportDocument(format)} /> : null}
        {actionDialog ? (
          <DocumentActionDialog
            action={actionDialog}
            busy={busy}
            categories={categories}
            chapters={chapters}
            currentChapterId={selectedChapterId}
            currentDocument={selectedDocument}
            documents={documents}
            onClose={() => setActionDialog(null)}
            onManualSplit={() => {
              setActionDialog(null);
              editorControllerRef.current?.markBoundary();
            }}
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
            onRegexApply={async (pattern, preview) => {
              await runBusy(async () => {
                const saved = await applyRegexSplit(selectedDocument.id, pattern, preview.preview_token, preview.chapters);
                const updatedDocument = { ...selectedDocument, chapter_count: saved.length };
                await refreshWorkspaceDocument(updatedDocument, saved[0]?.id ?? null);
                setActionDialog(null);
                setMessage('正则分章已应用为新版本。');
              });
            }}
            onAIPreview={() => previewAIDocumentSplit(selectedDocument.id)}
            onAIApply={async (proposal) => {
              await runBusy(async () => {
                const result = await applyAIDocumentSplit(selectedDocument.id, proposal.proposal_id, proposal.chapters);
                setActionDialog(null);
                await refreshWorkspaceDocument(
                  { ...selectedDocument, chapter_count: result.chapters.length },
                  result.chapters[0]?.id ?? null,
                );
                setMessage('AI 分章已应用为新文档版本。');
              });
            }}
            onRegexPreview={(pattern) => previewRegexSplit(selectedDocument.id, pattern)}
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
                if (key === 'all') setActiveCategoryId(null);
              }} />
            ))}
            <div className="document-tag-heading">
              <span>我的分类</span>
              <button aria-label="管理分类" className="document-add-tag" disabled={busy} onClick={() => setResourceManager('category')} title="管理分类" type="button"><Plus size={15} /></button>
            </div>
            {categories.length ? categories.map((category) => (
              <TagFilterButton
                active={activeCategoryId === category.id}
                count={categoryCount(category.id)}
                icon={<Folder size={16} />}
                key={category.id}
                label={category.name}
                onClick={() => setActiveCategoryId(activeCategoryId === category.id ? null : category.id)}
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
              {activeTag ? (
                <div className="document-active-filters" aria-label="当前筛选条件">
                  {activeTag ? <button onClick={() => setActiveTagId(null)} type="button">标签：{activeTag.name}<X size={12} /></button> : null}
                </div>
              ) : null}
            </div>
          </header>
          {loading ? <ShelfMessage title="正在读取文档库…" /> : visibleDocuments.length ? (
            <div className="document-shelf-scroll">
              <div className="document-shelf-grid">
                {visibleDocuments.map((document) => (
                  <button
                    aria-label={`${document.title}，${document.author || '未知作者'}`}
                    aria-pressed={selectedDocument?.id === document.id}
                    className={`document-book ${selectedDocument?.id === document.id ? 'selected' : ''}`}
                    key={document.id}
                    onClick={() => setSelectedId(document.id)}
                    onDoubleClick={() => void openProcessing('chapters', document)}
                    type="button"
                  >
                    <DefaultBookCover document={document} />
                    {document.is_project_document ? <span className="document-project-marker">工程文档</span> : null}
                  </button>
                ))}
              </div>
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
                <section>
                  <div className="document-detail-heading"><span>分类</span><button aria-label="管理当前文档分类" className="document-inline-plus" onClick={() => setResourceManager('category')} type="button"><Plus size={14} /></button></div>
                  {selectedDocument.categories.length ? (
                    <div className="document-tag-checks">
                      {selectedDocument.category_ids.map((categoryId, index) => (
                        <button
                          aria-pressed={activeCategoryId === categoryId}
                          className={activeCategoryId === categoryId ? 'selected' : ''}
                          key={categoryId}
                          type="button"
                          onClick={() => setActiveCategoryId(categoryId)}
                        >
                          {selectedDocument.categories[index]}
                        </button>
                      ))}
                    </div>
                  ) : <p className="document-resource-empty">未设置分类</p>}
                </section>
                <section>
                  <div className="document-detail-heading"><span>标签</span><button aria-label="管理当前文档标签" className="document-inline-plus" onClick={() => setResourceManager('tag')} type="button"><Plus size={14} /></button></div>
                  {selectedDocument.tags.length ? (
                    <div className="document-tag-checks">
                      {tags.filter((tag) => selectedDocument.tags.includes(tag.name)).map((tag) => (
                        <button
                          aria-pressed={activeTagId === tag.id}
                          className={activeTagId === tag.id ? 'selected' : ''}
                          key={tag.id}
                          type="button"
                          onClick={() => setActiveTagId(tag.id)}
                        >
                          {tag.name}
                        </button>
                      ))}
                    </div>
                  ) : <p className="document-resource-empty">未设置标签</p>}
                </section>
              </div>
              <section className="document-library-location">
                <span>文档库存储目录</span>
                <div title={libraryPath}>{libraryPath || '正在读取目录…'}</div>
              </section>
              <footer className="library-detail-footer">
                <SecondaryButton onClick={() => void openProcessing('chapters')}><BookOpenText size={15} />编辑</SecondaryButton>
                <SecondaryButton onClick={() => void openAnalysisWorkspace()}><WandSparkles size={15} />AI 分析</SecondaryButton>
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
          items={resourceManager === 'category' ? categories : tags}
          kind={resourceManager}
          onApply={(selectedIds) => void applyManagedResources(resourceManager, selectedIds)}
          onClose={() => setResourceManager(null)}
          onCreate={(name) => void createManagedResource(resourceManager, name)}
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
  onManualMark: (startOffset: number, endOffset: number, title: string) => void;
  onSelectionResource: (kind: 'scene' | 'plot' | 'character', text: string, startOffset: number, endOffset: number) => void;
  processingBusy: boolean;
  selectedChapterId: number | null;
};

type DocumentEditorController = {
  flushDraft: () => Promise<boolean>;
  undo: () => void;
  redo: () => void;
  markBoundary: () => void;
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
    undo: () => editorRef.current?.undo(),
    redo: () => editorRef.current?.redo(),
    markBoundary: () => editorRef.current?.markBoundary(),
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
            onManualMark={props.onManualMark}
            onSaveDraft={props.onSaveDraft}
            onSaveStatusChange={handleSaveStatusChange}
            onSelectionResource={props.onSelectionResource}
            onTitlePreview={props.onTitlePreview}
            ref={editorRef}
          />
        </div>
      </main>
      <aside className="workbench-inspector document-workspace-inspector">
        <div className="document-workspace-info">
          <section>
            <label className="document-workspace-metadata"><span>书名</span><input aria-label="书名" onBlur={() => void props.onUpdateMetadata(metadataTitle, metadataAuthor)} onChange={(event) => setMetadataTitle(event.target.value)} value={metadataTitle} /></label>
            <label className="document-workspace-metadata"><span>作者</span><input aria-label="作者" onBlur={() => void props.onUpdateMetadata(metadataTitle, metadataAuthor)} onChange={(event) => setMetadataAuthor(event.target.value)} placeholder="未知作者" value={metadataAuthor} /></label>
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
            <div className="inspector-action-area">
              <button className="button secondary full" onClick={() => props.onDocumentAction('merge')} type="button"><Combine size={16} />合并文档</button>
              <button className="button secondary full" onClick={() => props.onDocumentAction('create-chapter')} type="button"><Plus size={16} />新增章节</button>
              <button className="button secondary full" onClick={() => props.onDocumentAction('split')} type="button"><Scissors size={16} />分章</button>
              <button className="button secondary full" onClick={props.onOpenCleanup} type="button"><WandSparkles size={16} />文字整理</button>
              <button className="button secondary full" onClick={props.onOpenRevisions} type="button"><Clock3 size={16} />版本记录</button>
            </div>
            <div className="inspector-action-area document-editor-commands">
              <button className="button secondary full" onClick={() => editorRef.current?.markBoundary()} type="button">标记章节</button>
              <button className="button secondary full" onClick={() => editorRef.current?.undo()} type="button">撤销</button>
              <button className="button secondary full" onClick={() => editorRef.current?.redo()} type="button">重做</button>
            </div>
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
  volumes,
}: {
  chapters: LibraryDocumentChapter[];
  liveChapterId: number | null;
  liveWordCount: number;
  onContentChange: (chapterId: number | null) => void;
  onRenameVolume: (volumeId: number, title: string) => void;
  onReorder: (draggedId: number, targetId: number | null, targetVolumeId: number | null) => void;
  selectedChapterId: number | null;
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
      draggable
      key={chapter.id}
      onClick={() => onContentChange(chapter.id)}
      onDragOver={(event) => event.preventDefault()}
      onDragStart={(event) => startDrag(event, chapter.id)}
      onDrop={(event) => dropChapter(event, chapter.id, chapter.volume_id)}
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
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => dropChapter(event, null, volume.id)}
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
  onManualMark: (startOffset: number, endOffset: number, title: string) => void;
  onSaveDraft: (title: string, text: string) => Promise<LibraryDocumentDraft>;
  onSaveStatusChange: (status: SaveStatus, savedAt: string) => void;
  onSelectionResource: (kind: 'scene' | 'plot' | 'character', text: string, startOffset: number, endOffset: number) => void;
  onTitlePreview: (title: string) => void;
}>(function EditableTextPreview({
  chapterIndex,
  content,
  draft,
  loading,
  onCommit,
  onDirtyChange,
  onDraftSaved,
  onLiveCountChange,
  onManualMark,
  onSaveDraft,
  onSaveStatusChange,
  onSelectionResource,
  onTitlePreview,
}, ref) {
  const initialText = draft?.text ?? content?.body_text ?? '';
  const initialTitle = draft?.title ?? content?.title ?? '';
  const [text, setText] = useState(initialText);
  const [title, setTitle] = useState(initialTitle);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>(draft ? 'saved' : 'clean');
  const [savedAt, setSavedAt] = useState(draft?.updated_at ?? '');
  const [menu, setMenu] = useState<{ x: number; y: number; text: string; startOffset: number; endOffset: number } | null>(null);
  const [markStart, setMarkStart] = useState<number | null>(null);
  const [markEnd, setMarkEnd] = useState<number | null>(null);
  const [markTitle, setMarkTitle] = useState('');
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
  const historyRef = useRef<Array<{ text: string; selectionStart: number; selectionEnd: number }>>([
    { text: initialText, selectionStart: 0, selectionEnd: 0 },
  ]);
  const historyIndexRef = useRef(0);
  const lastHistoryAtRef = useRef(0);

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
    historyRef.current = [{ text: nextText, selectionStart: 0, selectionEnd: 0 }];
    historyIndexRef.current = 0;
    onDirtyChange(false);
    onLiveCountChange(countTextUnits(nextText));
    setMarkStart(null);
    setMarkEnd(null);
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

  function restoreHistory(index: number) {
    const snapshot = historyRef.current[index];
    if (!snapshot) return;
    historyIndexRef.current = index;
    setText(snapshot.text);
    markDirty();
    callbacksRef.current.onLiveCountChange(
      countTextUnits(snapshot.text),
    );
    window.requestAnimationFrame(() => editorRef.current?.setSelectionRange(snapshot.selectionStart, snapshot.selectionEnd));
  }

  function undo() {
    restoreHistory(Math.max(0, historyIndexRef.current - 1));
  }

  function redo() {
    restoreHistory(Math.min(historyRef.current.length - 1, historyIndexRef.current + 1));
  }

  function recordText(nextText: string, selectionStart: number, selectionEnd: number) {
    const now = Date.now();
    const next = { text: nextText, selectionStart, selectionEnd };
    const history = historyRef.current.slice(0, historyIndexRef.current + 1);
    if (now - lastHistoryAtRef.current < 700 && history.length > 1) history[history.length - 1] = next;
    else history.push(next);
    if (history.length > 100) history.shift();
    historyRef.current = history;
    historyIndexRef.current = history.length - 1;
    lastHistoryAtRef.current = now;
  }

  function markBoundary() {
    const cursor = editorRef.current?.selectionStart;
    if (cursor == null || !content) return;
    const absolute = content.body_start_offset + cursor;
    if (markStart == null) {
      setMarkStart(absolute);
      return;
    }
    if (absolute <= markStart) return;
    setMarkTitle(content.title || '新章节');
    setMarkEnd(absolute);
  }

  useImperativeHandle(ref, () => ({ flushDraft, undo, redo, markBoundary }), [flushDraft]);

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
            value={title}
          />
        </label>
        <button
          className="button secondary"
          disabled={saveStatus === 'clean' || saveStatus === 'saving' || loading || !content || (content.chapter_id == null && !title.trim())}
          onClick={() => {
            void flushDraft().then(async (saved) => {
              if (!saved) return;
              if (!(await onCommit()) && mountedRef.current) setSaveStatus('error');
            });
          }}
          type="button"
        ><Save size={15} />保存</button>
      </header>
      <textarea
        className="manuscript-editor"
        disabled={loading || !content}
        onChange={(event) => {
          const nextText = event.target.value;
          recordText(nextText, event.target.selectionStart, event.target.selectionEnd);
          setText(nextText);
          callbacksRef.current.onLiveCountChange(
            countTextUnits(nextText),
          );
          markDirty();
        }}
        onContextMenu={openMenu}
        onKeyDown={(event) => {
          if (!(event.ctrlKey || event.metaKey)) return;
          const key = event.key.toLocaleLowerCase();
          if (key === 'z' && !event.shiftKey) { event.preventDefault(); undo(); }
          else if (key === 'y' || (key === 'z' && event.shiftKey)) { event.preventDefault(); redo(); }
        }}
        ref={editorRef}
        value={loading && !content ? '正在读取正文…' : text}
      />
      {menu ? (
        <div className="selection-resource-menu" ref={menuRef} style={{ left: menu.x, top: menu.y }}>
          <button onClick={() => { onSelectionResource('plot', menu.text, menu.startOffset, menu.endOffset); setMenu(null); }} type="button">添加为剧情骨架来源</button>
          <button onClick={() => { onSelectionResource('scene', menu.text, menu.startOffset, menu.endOffset); setMenu(null); }} type="button">添加为场景素材来源</button>
          <button onClick={() => { onSelectionResource('character', menu.text, menu.startOffset, menu.endOffset); setMenu(null); }} type="button">提取角色卡</button>
        </div>
      ) : null}
      {markStart != null && markEnd != null ? (
        <div className="library-confirm-panel" role="dialog" aria-label="章节标题">
          <label><span>章节标题</span><input autoFocus value={markTitle} onChange={(event) => setMarkTitle(event.target.value)} /></label>
          <div><button className="button secondary" onClick={() => { setMarkEnd(null); setMarkStart(null); }} type="button">取消</button><button className="button primary" disabled={!markTitle.trim()} onClick={() => { onManualMark(markStart, markEnd, markTitle.trim()); setMarkStart(null); setMarkEnd(null); }} type="button">确认章节</button></div>
        </div>
      ) : null}
    </section>
  );
});

function CleanupDialog(props: {
  busy: boolean;
  content: LibraryDocumentContent | null;
  onApply: () => void;
  onClose: () => void;
  onSaveTemplate: () => void;
  onSelectTemplate: (templateId: number) => void;
  onSettingsChange: (settings: DocumentProcessingSettings) => void;
  onTemplateNameChange: (name: string) => void;
  templateId: number | null;
  templateName: string;
  templateSettings: DocumentProcessingSettings;
  templates: DocumentProcessingTemplate[];
}) {
  const settings = props.templateSettings;
  return (
    <div className="document-processing-backdrop" role="presentation">
      <section aria-modal="true" className="document-cleanup-dialog" role="dialog">
        <header><div><span>文档处理</span><h2>文字整理</h2></div><button className="icon-button" onClick={props.onClose} type="button"><X size={17} /></button></header>
        <div className="document-cleanup-grid">
          <div className="document-processing-settings">
            <label><span className="form-label">整理模板</span><select className="form-input" value={props.templateId ?? ''} onChange={(event) => props.onSelectTemplate(Number(event.target.value))}>{props.templates.map((template) => <option key={template.id} value={template.id}>{template.name}{template.is_default ? '（默认）' : ''}</option>)}</select></label>
            <div className="document-processing-number-grid">
              <NumberField label="章节缩进" value={settings.chapter_indent} onChange={(value) => props.onSettingsChange({ ...settings, chapter_indent: value })} />
              <NumberField label="段落首行缩进" value={settings.paragraph_indent} onChange={(value) => props.onSettingsChange({ ...settings, paragraph_indent: value })} />
              <NumberField label="段落间空行" max={3} value={settings.blank_lines} onChange={(value) => props.onSettingsChange({ ...settings, blank_lines: value })} />
            </div>
            <label><span className="form-label">章节标题正则</span><textarea className="document-processing-regex" value={settings.chapter_pattern} onChange={(event) => props.onSettingsChange({ ...settings, chapter_pattern: event.target.value })} /></label>
            <label className="document-processing-toggle"><input checked={settings.trim_whitespace} onChange={(event) => props.onSettingsChange({ ...settings, trim_whitespace: event.target.checked })} type="checkbox" />清除每行多余的前后空白</label>
            <div className="document-processing-save-template"><input className="form-input" value={props.templateName} onChange={(event) => props.onTemplateNameChange(event.target.value)} /><SecondaryButton disabled={props.busy || !props.templateName.trim()} onClick={props.onSaveTemplate}><Save size={15} />另存模板</SecondaryButton></div>
          </div>
          <div className="document-processing-preview">
            <span className="form-label">处理后真实预览</span>
            <pre>{applyCleanupPreview(props.content?.body_text ?? '', settings)}</pre>
          </div>
        </div>
        <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || !props.templateId} onClick={props.onApply}><WandSparkles size={16} />应用并生成新版本</PrimaryButton></footer>
      </section>
    </div>
  );
}

function RevisionHistoryDialog(props: {
  busy: boolean;
  document: LibraryDocument;
  onClose: () => void;
  onRestore: (revisionId: number) => void;
  revisions: LibraryDocumentRevision[];
}) {
  return (
    <div className="document-processing-backdrop" role="presentation">
      <section aria-modal="true" className="document-tag-dialog document-revision-dialog" role="dialog">
        <header><div><span>文档版本</span><h2>版本记录</h2></div><button className="icon-button" onClick={props.onClose} type="button"><X size={17} /></button></header>
        <div className="document-revision-list">
          {props.revisions.map((revision) => (
            <div key={revision.id}>
              <span>版本 {revision.revision_number} · {revisionLabel(revision.revision_type)}</span>
              <button disabled={props.busy || revision.storage_path === props.document.storage_path} onClick={() => props.onRestore(revision.id)} type="button">{revision.storage_path === props.document.storage_path ? '当前' : '恢复'}</button>
            </div>
          ))}
        </div>
        <footer><SecondaryButton onClick={props.onClose}>关闭</SecondaryButton></footer>
      </section>
    </div>
  );
}

function ReferencePanel({ scope, setScope }: { scope: ReferenceScope; setScope: (scope: ReferenceScope) => void }) {
  const options: Array<[ReferenceScope, string, string]> = [
    ['book', '整本书', '引用当前文档的全部内容'],
    ['chapters', '特定章节', '从已识别章节中选择'],
    ['paragraphs', '选定段落', '进入正文后选择连续段落'],
  ];
  return (
    <section className="document-reference-panel">
      <header><h3>默认引用范围</h3><p>为工程、角色卡和剧情大纲预设选择范围。</p></header>
      <div>{options.map(([key, label, description]) => <button className={scope === key ? 'selected' : ''} key={key} onClick={() => setScope(key)} type="button"><BookOpenText size={18} /><span><strong>{label}</strong><small>{description}</small></span></button>)}</div>
    </section>
  );
}

function DocumentActionDialog(props: {
  action: DocumentAction;
  busy: boolean;
  categories: DocumentCategory[];
  chapters: LibraryDocumentChapter[];
  currentChapterId: number | null;
  currentDocument: LibraryDocument;
  documents: LibraryDocument[];
  onClose: () => void;
  onCreateChapter: (title: string, text: string, position: 'before' | 'after', anchorChapterId: number | null) => void;
  onManualSplit: () => void;
  onMerge: (ids: number[], title: string) => void;
  onRegexPreview: (pattern: string) => Promise<SplitPreview>;
  onRegexApply: (pattern: string, preview: SplitPreview) => void;
  onAIPreview: () => Promise<AISplitProposal>;
  onAIApply: (proposal: AISplitProposal) => void;
}) {
  const [title, setTitle] = useState(props.action === 'merge' ? `${props.currentDocument.title} 合并本` : '');
  const [text, setText] = useState('');
  const [positionMode, setPositionMode] = useState<'before-current' | 'after-current' | 'after-index'>(props.currentChapterId ? 'after-current' : 'after-index');
  const [anchorIndex, setAnchorIndex] = useState(props.chapters.at(-1)?.index ?? 1);
  const [splitTab, setSplitTab] = useState<'ai' | 'regex' | 'manual'>('ai');
  const [selected, setSelected] = useState<number[]>([props.currentDocument.id]);
  const [pattern, setPattern] = useState('^第.+[章节].*$');
  const [regexPreview, setRegexPreview] = useState<SplitPreview | null>(null);
  const [aiPreview, setAiPreview] = useState<AISplitProposal | null>(null);
  const [localError, setLocalError] = useState('');
  async function previewRegex() {
    try { setRegexPreview(await props.onRegexPreview(pattern)); setLocalError(''); } catch (reason) { setLocalError(errorMessage(reason)); }
  }
  async function previewAI() {
    try { setAiPreview(await props.onAIPreview()); setLocalError(''); } catch (reason) { setLocalError(errorMessage(reason)); }
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
      <section className="document-tag-dialog document-action-dialog" role="dialog" aria-modal="true">
        <header><div><span>文档处理</span><h2>{heading}</h2></div><button className="icon-button" onClick={props.onClose} type="button"><X size={17} /></button></header>
        {props.action === 'merge' ? (
          <>
            <label><span className="form-label">新文档标题</span><input className="form-input" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
            <div className="document-merge-list document-merge-category-tree">
              {[
                ...props.categories.map((category) => ({
                  id: `category-${category.id}`,
                  label: category.name,
                  documents: props.documents.filter((document) => document.category_ids.includes(category.id)),
                })),
                {
                  id: 'uncategorized',
                  label: '未分类',
                  documents: props.documents.filter((document) => document.category_ids.length === 0),
                },
              ].filter((group) => group.documents.length > 0).map((group) => (
                <section key={group.id}>
                  <h3><Folder size={14} />{group.label}</h3>
                  {group.documents.map((document) => (
                    <label key={`${group.id}-${document.id}`}>
                      <input
                        checked={selected.includes(document.id)}
                        disabled={document.id === props.currentDocument.id}
                        type="checkbox"
                        onChange={(event) => setSelected(
                          event.target.checked
                            ? [...new Set([...selected, document.id])]
                            : selected.filter((id) => id !== document.id),
                        )}
                      />
                      {document.title}
                    </label>
                  ))}
                </section>
              ))}
              <div className="document-merge-order">
              {selected.map((id, index) => <div key={id}><span>{index + 1}. {props.documents.find((item) => item.id === id)?.title}</span><button onClick={() => moveDocument(index, -1)} type="button">↑</button><button onClick={() => moveDocument(index, 1)} type="button">↓</button></div>)}
              </div>
            </div>
            <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || selected.length < 2 || !title.trim()} onClick={() => props.onMerge(selected, title.trim())}>创建新文档</PrimaryButton></footer>
          </>
        ) : null}
        {props.action === 'create-chapter' ? (
          <>
            <label><span className="form-label">章节标题</span><input className="form-input" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
            <label><span className="form-label">插入位置</span><select value={positionMode} onChange={(event) => setPositionMode(event.target.value as typeof positionMode)}><option value="before-current">本章之前</option><option value="after-current">本章之后</option><option value="after-index">插入到第几章之后</option></select></label>
            {positionMode === 'after-index' ? <label><span className="form-label">章节序号</span><input min={1} max={Math.max(1, props.chapters.length)} type="number" value={anchorIndex} onChange={(event) => setAnchorIndex(Number(event.target.value))} /><small>{indexedAnchor ? `匹配：${chapterDisplayTitle(indexedAnchor)}` : '没有匹配该章节序号'}</small></label> : <p className="document-action-anchor">锚点：{currentChapter ? chapterDisplayTitle(currentChapter) : '当前文档暂无章节'}</p>}
            <label><span className="form-label">正文</span><textarea value={text} onChange={(event) => setText(event.target.value)} /></label>
            <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || (props.chapters.length > 0 && !createAnchor)} onClick={() => props.onCreateChapter(title.trim(), text, createPosition, createAnchor?.id ?? null)}>保存为新版本</PrimaryButton></footer>
          </>
        ) : null}
        {props.action === 'split' ? (
          <>
            <div className="document-split-tabs">
              <button className={splitTab === 'ai' ? 'selected' : ''} onClick={() => setSplitTab('ai')} type="button">AI 识别</button>
              <button className={splitTab === 'regex' ? 'selected' : ''} onClick={() => setSplitTab('regex')} type="button">正则识别</button>
              <button className={splitTab === 'manual' ? 'selected' : ''} onClick={() => setSplitTab('manual')} type="button">手动标记</button>
            </div>
            {splitTab === 'regex' ? <>
              <label><span className="form-label">章节标题正则</span><textarea value={pattern} onChange={(event) => { setPattern(event.target.value); setRegexPreview(null); }} /></label>
              <SecondaryButton disabled={props.busy || !pattern} onClick={() => void previewRegex()}>生成候选</SecondaryButton>
              {regexPreview ? <EditableBoundaryPreview chapters={regexPreview.chapters} onChange={(chapters) => setRegexPreview({ ...regexPreview, chapters, chapter_count: chapters.length })} /> : null}
            </> : null}
            {splitTab === 'ai' ? <>
              {!aiPreview ? <SecondaryButton disabled={props.busy} onClick={() => void previewAI()}>调用模型生成候选</SecondaryButton> : (
              <div className="document-split-editor">
                {aiPreview.chapters.map((chapter, index) => (
                  <div key={index}>
                    <input aria-label={`第 ${index + 1} 章标题`} value={chapter.title} onChange={(event) => setAiPreview({ ...aiPreview, chapters: aiPreview.chapters.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item) })} />
                    <input aria-label={`第 ${index + 1} 章开始位置`} type="number" value={chapter.start_offset} onChange={(event) => setAiPreview({ ...aiPreview, chapters: aiPreview.chapters.map((item, itemIndex) => itemIndex === index ? { ...item, start_offset: Number(event.target.value) } : item) })} />
                    <input aria-label={`第 ${index + 1} 章结束位置`} type="number" value={chapter.end_offset} onChange={(event) => setAiPreview({ ...aiPreview, chapters: aiPreview.chapters.map((item, itemIndex) => itemIndex === index ? { ...item, end_offset: Number(event.target.value) } : item) })} />
                    <small>{chapter.reason}</small>
                  </div>
                ))}
              </div>
            )}
            </> : null}
            {splitTab === 'manual' ? <div className="document-manual-split-help"><p>返回正文后，使用右侧“标记章节”记录当前光标的起止位置。</p><SecondaryButton onClick={props.onManualSplit}>进入手动标记</SecondaryButton></div> : null}
            <footer><SecondaryButton onClick={props.onClose}>取消</SecondaryButton><PrimaryButton disabled={props.busy || (splitTab === 'ai' ? !aiPreview : splitTab === 'regex' ? !regexPreview : true)} onClick={() => { if (splitTab === 'ai' && aiPreview) props.onAIApply(aiPreview); if (splitTab === 'regex' && regexPreview) props.onRegexApply(pattern, regexPreview); }}>应用为新版本</PrimaryButton></footer>
          </>
        ) : null}
        {localError ? <div className="inline-alert error" role="alert">{localError}</div> : null}
      </section>
    </div>
  );
}

function EditableBoundaryPreview({ chapters, onChange }: { chapters: SplitPreview['chapters']; onChange: (chapters: SplitPreview['chapters']) => void }) {
  return (
    <div className="document-split-editor">
      {chapters.map((chapter, index) => (
        <div key={`${chapter.start_offset}-${index}`}>
          <input aria-label={`第 ${index + 1} 章标题`} value={chapter.title} onChange={(event) => onChange(chapters.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item))} />
          <input aria-label={`第 ${index + 1} 章开始位置`} type="number" value={chapter.start_offset} onChange={(event) => onChange(chapters.map((item, itemIndex) => itemIndex === index ? { ...item, start_offset: Number(event.target.value) } : item))} />
          <input aria-label={`第 ${index + 1} 章结束位置`} type="number" value={chapter.end_offset} onChange={(event) => onChange(chapters.map((item, itemIndex) => itemIndex === index ? { ...item, end_offset: Number(event.target.value) } : item))} />
          <small>{chapter.end_offset - chapter.start_offset} 字符 · {chapter.word_count} 字</small>
        </div>
      ))}
      <ChapterBoundaryPreview chapters={chapters} count={chapters.length} />
    </div>
  );
}

function ChapterBoundaryPreview({ chapters, count }: { chapters: Array<{ title: string; start_offset: number; end_offset: number; word_count: number }>; count: number }) {
  const ordered = [...chapters].sort((left, right) => left.start_offset - right.start_offset);
  const gaps = ordered.flatMap((chapter, index) => {
    const expected = index === 0 ? 0 : ordered[index - 1].end_offset;
    return chapter.start_offset > expected ? [`${expected}–${chapter.start_offset}`] : [];
  });
  return <div className="document-split-preview"><strong>匹配章节：{count}</strong>{chapters.map((chapter, index) => <div key={`${chapter.start_offset}-${index}`}><span>{chapter.title}</span><small>{chapter.start_offset}–{chapter.end_offset} · {chapter.word_count} 字</small></div>)}<p>{gaps.length ? `未匹配区间：${gaps.join('、')}` : '未匹配开头或中间内容：无；尾部由最后一章终点标识。'}</p></div>;
}

function ResourceAssignmentDialog({
  busy,
  document,
  items,
  kind,
  onApply,
  onClose,
  onCreate,
}: {
  busy: boolean;
  document: LibraryDocument | null;
  items: Array<DocumentCategory | ResourceTag>;
  kind: 'category' | 'tag';
  onApply: (selectedIds: number[]) => void;
  onClose: () => void;
  onCreate: (name: string) => void;
}) {
  const initialSelected = kind === 'category'
    ? document?.category_ids ?? []
    : items.filter((item) => document?.tags.includes(item.name)).map((item) => item.id);
  const [selectedIds, setSelectedIds] = useState<number[]>(initialSelected);
  const [name, setName] = useState('');
  const label = kind === 'category' ? '分类' : '标签';
  return (
    <div className="document-processing-backdrop" role="presentation">
      <section
        aria-labelledby="document-resource-title"
        aria-modal="true"
        className="document-tag-dialog document-resource-dialog"
        role="dialog"
      >
        <header>
          <div><span>文档{label}</span><h2 id="document-resource-title">管理{label}</h2></div>
          <button aria-label={`关闭${label}窗口`} className="icon-button" onClick={onClose} type="button"><X size={17} /></button>
        </header>
        <div className="document-resource-options">
          {document ? items.map((item) => (
            <label key={item.id}>
              <input
                checked={selectedIds.includes(item.id)}
                disabled={busy}
                onChange={(event) => setSelectedIds((current) => (
                  event.target.checked
                    ? [...current, item.id]
                    : current.filter((id) => id !== item.id)
                ))}
                type="checkbox"
              />
              <span>{item.name}</span>
            </label>
          )) : <p>先创建分类；选择文档后可分配关联。</p>}
          {document && !items.length ? <p>尚无可用{label}。</p> : null}
        </div>
        <form className="document-resource-create" onSubmit={(event) => { event.preventDefault(); if (name.trim()) { onCreate(name.trim()); setName(''); } }}>
          <input className="form-input" maxLength={40} onChange={(event) => setName(event.target.value)} placeholder={`新${label}名称`} value={name} />
          <SecondaryButton disabled={busy || !name.trim()} type="submit"><Plus size={14} />新建</SecondaryButton>
        </form>
        <footer><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !document} onClick={() => onApply(selectedIds)}>保存关联</PrimaryButton></footer>
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

function TagFilterButton({ active, count, icon, label, onClick }: { active: boolean; count: number; icon: ReactNode; label: string; onClick: () => void }) {
  return <button aria-current={active ? 'page' : undefined} className={`document-tag-item ${active ? 'selected' : ''}`} onClick={onClick} type="button">{icon}<span>{label}</span><small>{count}</small></button>;
}

function DefaultBookCover({ compact = false, document }: { compact?: boolean; document: LibraryDocument }) {
  const palette = palettes[(document.id - 1) % palettes.length];
  return <span className={`default-book-cover palette-${palette} ${compact ? 'compact' : ''}`}><span className="default-book-spine" /><strong>{document.title}</strong><span className="default-book-author">{document.author || '未知作者'}</span></span>;
}

function Definition({ label, value }: { label: string; value: string }) {
  return <div className="document-definition"><span>{label}</span><strong title={value}>{value}</strong></div>;
}

function ShelfMessage({ action, title }: { action?: ReactNode; title: string }) {
  return <div className="document-shelf-empty"><LibraryBig size={28} /><strong>{title}</strong>{action ? <div className="document-shelf-empty-action">{action}</div> : null}</div>;
}

function NumberField({ label, max = 8, onChange, value }: { label: string; max?: number; onChange: (value: number) => void; value: number }) {
  return <label><span className="form-label">{label}</span><input className="form-input" max={max} min={0} onChange={(event) => onChange(Number(event.target.value))} type="number" value={value} /></label>;
}

function documentsForSystemFilter(
  documents: LibraryDocument[],
  filter: SystemFilter,
): LibraryDocument[] {
  if (filter === 'project') return documents.filter((document) => document.is_project_document);
  if (filter === 'recent') {
    return [...documents]
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
  if (revisionType === 'split_regex') return '正则分章';
  return '文字整理';
}

function statusLabel(status: string) {
  if (status === 'imported') return '已导入';
  if (status === 'processed') return '已处理';
  return status;
}

function formatPreview(settings: DocumentProcessingSettings) {
  const chapterIndent = '　'.repeat(settings.chapter_indent);
  const paragraphIndent = '　'.repeat(settings.paragraph_indent);
  const separator = '\n'.repeat(settings.blank_lines + 1);
  return `${chapterIndent}第一章　风起${separator}${paragraphIndent}这是正文的第一段。${separator}${paragraphIndent}这是正文的第二段。`;
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

function applyCleanupPreview(text: string, settings: DocumentProcessingSettings): string {
  let chapterPattern: RegExp | null = null;
  try {
    chapterPattern = new RegExp(settings.chapter_pattern);
  } catch {
    chapterPattern = null;
  }
  const lines = text.replace(/\r\n?/g, '\n').split('\n').flatMap((rawLine) => {
    const line = settings.trim_whitespace ? rawLine.trim() : rawLine;
    if (!line) return [];
    const indent = chapterPattern?.test(line) ? settings.chapter_indent : settings.paragraph_indent;
    return `${'　'.repeat(indent)}${settings.trim_whitespace ? line.trimStart() : line}`;
  });
  return lines.join('\n'.repeat(settings.blank_lines + 1));
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
