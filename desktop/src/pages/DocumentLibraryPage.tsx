import { useEffect, useRef, useState } from 'react';
import type { DragEvent, ReactNode } from 'react';
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
  Sparkles,
  Star,
  Trash2,
  WandSparkles,
  X,
} from 'lucide-react';
import {
  activateLibraryDocumentRevision,
  assignDocumentCategory,
  cleanupLibraryDocument,
  createDocumentCategory,
  createDocumentProcessingTemplate,
  deleteLibraryDocument,
  exportLibraryDocument,
  getDocumentCategories,
  getDocumentLibrarySettings,
  getDocumentProcessingTemplates,
  getLibraryDocumentChapters,
  getLibraryDocumentContent,
  getLibraryDocumentRevisions,
  getLibraryDocuments,
  importLibraryDocument,
  migrateDocumentLibrary,
  reorderLibraryDocumentChapters,
  updateLibraryDocument,
} from '../api/client';
import type {
  DocumentCategory,
  DocumentProcessingSettings,
  DocumentProcessingTemplate,
  LibraryDocument,
  LibraryDocumentChapter,
  LibraryDocumentContent,
  LibraryDocumentRevision,
} from '../api/types';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

type ProcessingTab = 'chapters' | 'cleanup' | 'reference';
type ReferenceScope = 'book' | 'chapters' | 'paragraphs';

const systemCategories = [
  { key: 'all', label: '全部文档', icon: LibraryBig },
  { key: 'favorite', label: '收藏', icon: Star },
  { key: 'project', label: '工程分类', icon: FolderOpen },
  { key: 'recent', label: '最近导入', icon: Clock3 },
  { key: 'uncategorized', label: '未分类', icon: Folder },
] as const;

const palettes = ['indigo', 'terracotta', 'jade', 'slate', 'ochre', 'plum', 'bluegray'] as const;

const fallbackSettings: DocumentProcessingSettings = {
  chapter_pattern: '^\\s*(第[一二三四五六七八九十百千万零〇两0-9]+[章节卷集部篇回].*|[0-9]+[、.． ].*)\\s*$',
  chapter_indent: 0,
  paragraph_indent: 2,
  blank_lines: 1,
  trim_whitespace: true,
};

export function DocumentLibraryPage() {
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [categories, setCategories] = useState<DocumentCategory[]>([]);
  const [libraryPath, setLibraryPath] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [processingTab, setProcessingTab] = useState<ProcessingTab>('chapters');
  const [processingBusy, setProcessingBusy] = useState(false);
  const [templates, setTemplates] = useState<DocumentProcessingTemplate[]>([]);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [templateName, setTemplateName] = useState('自定义排版');
  const [templateSettings, setTemplateSettings] = useState<DocumentProcessingSettings>(fallbackSettings);
  const [revisions, setRevisions] = useState<LibraryDocumentRevision[]>([]);
  const [chapters, setChapters] = useState<LibraryDocumentChapter[]>([]);
  const [documentContent, setDocumentContent] = useState<LibraryDocumentContent | null>(null);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [referenceScope, setReferenceScope] = useState<ReferenceScope>('book');
  const [exportOpen, setExportOpen] = useState(false);
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);
  const [categoryName, setCategoryName] = useState('');
  const [editingMetadata, setEditingMetadata] = useState<'title' | 'author' | null>(null);
  const [metadataTitle, setMetadataTitle] = useState('');
  const [metadataAuthor, setMetadataAuthor] = useState('');

  const query = searchText.trim().toLocaleLowerCase();
  const userCategories = categories.filter((category) => category.name !== '工程');
  const visibleDocuments = documents.filter((document, index) => (
    matchesCategory(document, activeCategory, index)
    && (!query || `${document.title} ${document.author ?? ''} ${document.source_filename}`.toLocaleLowerCase().includes(query))
  ));
  const selectedDocument = documents.find((document) => document.id === selectedId) ?? null;

  useAutoDismiss(message, setMessage);
  useAutoDismiss(error, setError, 5200);

  useEffect(() => {
    setMetadataTitle(selectedDocument?.title ?? '');
    setMetadataAuthor(selectedDocument?.author ?? '');
    setEditingMetadata(null);
  }, [selectedDocument?.id]);

  async function loadLibrary(preferredId?: number | null) {
    setError(null);
    try {
      const [documentItems, categoryItems, settings] = await Promise.all([
        getLibraryDocuments(),
        getDocumentCategories(),
        getDocumentLibrarySettings(),
      ]);
      setDocuments(documentItems);
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

  async function addCategory() {
    const name = categoryName.trim();
    if (!name) return;
    await runBusy(async () => {
      const created = await createDocumentCategory(name);
      setCategories((current) => [...current, created]);
      setCategoryName('');
      setCategoryDialogOpen(false);
      setMessage(`已创建分类“${created.name}”。`);
    });
  }

  async function toggleCategory(category: DocumentCategory, selected: boolean) {
    if (!selectedDocument) return;
    await runBusy(async () => {
      await assignDocumentCategory(selectedDocument.id, category.id, selected);
      await loadLibrary(selectedDocument.id);
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

  async function openProcessing(tab: ProcessingTab = 'chapters', targetDocument: LibraryDocument | null = selectedDocument) {
    if (!targetDocument) return;
    setSelectedId(targetDocument.id);
    setProcessingTab(tab);
    setWorkspaceOpen(true);
    setProcessingBusy(true);
    setError(null);
    try {
      const [templateItems, revisionItems, chapterItems] = await Promise.all([
        getDocumentProcessingTemplates(),
        getLibraryDocumentRevisions(targetDocument.id),
        getLibraryDocumentChapters(targetDocument.id),
      ]);
      const firstChapterId = chapterItems[0]?.id ?? null;
      const content = await getLibraryDocumentContent(targetDocument.id, firstChapterId);
      setTemplates(templateItems);
      setRevisions(revisionItems);
      setChapters(chapterItems);
      setSelectedChapterId(firstChapterId);
      setDocumentContent(content);
      const defaultTemplate = templateItems.find((template) => template.is_default) ?? templateItems[0];
      if (defaultTemplate) {
        setTemplateId(defaultTemplate.id);
        setTemplateSettings(defaultTemplate.settings);
      }
    } catch (err) {
      setError(errorMessage(err));
      setWorkspaceOpen(false);
    } finally {
      setProcessingBusy(false);
    }
  }

  async function reorderChapters(draggedId: number, targetId: number) {
    if (!selectedDocument || draggedId === targetId) return;
    const previous = chapters;
    const reordered = [...chapters];
    const fromIndex = reordered.findIndex((chapter) => chapter.id === draggedId);
    const toIndex = reordered.findIndex((chapter) => chapter.id === targetId);
    if (fromIndex < 0 || toIndex < 0) return;
    const [moved] = reordered.splice(fromIndex, 1);
    reordered.splice(toIndex, 0, moved);
    setChapters(reordered.map((chapter, index) => ({ ...chapter, index: index + 1 })));
    try {
      const saved = await reorderLibraryDocumentChapters(
        selectedDocument.id,
        reordered.map((chapter) => chapter.id),
      );
      setChapters(saved);
      setMessage('章节顺序已保存。');
    } catch (err) {
      setChapters(previous);
      setError(errorMessage(err));
    }
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

  function showReservedAction(label: string) {
    setMessage(`${label}入口已放入文档工作区，处理逻辑将在下一步接入。`);
  }

  async function showDocumentContent(chapterId: number | null) {
    if (!selectedDocument) return;
    setProcessingBusy(true);
    setError(null);
    try {
      const content = await getLibraryDocumentContent(selectedDocument.id, chapterId);
      setSelectedChapterId(chapterId);
      setDocumentContent(content);
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
      setMessage('文字清理模板已保存。');
    });
  }

  async function applyProcessingTemplate() {
    if (!selectedDocument || !templateId) return;
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
      const [revisionItems, chapterItems] = await Promise.all([
        getLibraryDocumentRevisions(selectedDocument.id),
        getLibraryDocumentChapters(selectedDocument.id),
      ]);
      setRevisions(revisionItems);
      setChapters(chapterItems);
      setSelectedChapterId(null);
      setDocumentContent(await getLibraryDocumentContent(selectedDocument.id));
      setMessage(result.created ? `已生成版本 ${result.revision.revision_number}。` : '当前版本已经符合模板。');
    });
  }

  async function restoreRevision(revisionId: number) {
    if (!selectedDocument) return;
    await runProcessing(async () => {
      await activateLibraryDocumentRevision(selectedDocument.id, revisionId);
      await loadLibrary(selectedDocument.id);
      setChapters(await getLibraryDocumentChapters(selectedDocument.id));
      setSelectedChapterId(null);
      setDocumentContent(await getLibraryDocumentContent(selectedDocument.id));
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

  function categoryCount(category: string) {
    return documents.filter((document, index) => matchesCategory(document, category, index)).length;
  }

  if (workspaceOpen && selectedDocument) {
    return (
      <div className="project-workbench document-workbench">
        <header className="workbench-toolbar">
          <div className="project-heading">
            <button className="button ghost workbench-back-button" onClick={() => setWorkspaceOpen(false)} type="button">
              <ArrowLeft size={16} />返回文档库
            </button>
          </div>
          <div className="chapter-heading">
            <div>
              <strong>{selectedDocument.title}</strong>
              <span className="chapter-meta">
                <span>{formatNumber(selectedDocument.word_count)} 字</span>
                <span>共 {selectedDocument.chapter_count} 章</span>
                <span>本地保存<i className="status-dot" /></span>
              </span>
            </div>
          </div>
          <div className="toolbar-actions">
            <button className="button ghost" onClick={() => setExportOpen(true)} type="button"><Download size={16} />导出</button>
          </div>
        </header>
        <div className="workbench-feedback">
          {error ? <div className="inline-alert error workbench-alert" role="alert"><span>{error}</span></div> : null}
          {message ? <div className="inline-alert success workbench-alert" role="status"><span>{message}</span></div> : null}
        </div>
        <DocumentWorkspace
          chapters={chapters}
          content={documentContent}
          document={selectedDocument}
          onApply={() => void applyProcessingTemplate()}
          onContentChange={(chapterId) => void showDocumentContent(chapterId)}
          onExport={() => setExportOpen(true)}
          onReservedAction={showReservedAction}
          onRestore={(revisionId) => void restoreRevision(revisionId)}
          onReorder={(draggedId, targetId) => void reorderChapters(draggedId, targetId)}
          onSaveTemplate={() => void saveProcessingTemplate()}
          onSelectTemplate={selectTemplate}
          onSettingsChange={setTemplateSettings}
          onTabChange={setProcessingTab}
          onTemplateNameChange={setTemplateName}
          processingBusy={processingBusy}
          referenceScope={referenceScope}
          revisions={revisions}
          selectedChapterId={selectedChapterId}
          selectedTab={processingTab}
          setReferenceScope={setReferenceScope}
          templateId={templateId}
          templateName={templateName}
          templateSettings={templateSettings}
          templates={templates}
        />
        {exportOpen ? <ExportDialog busy={busy} document={selectedDocument} onClose={() => setExportOpen(false)} onExport={(format) => void exportDocument(format)} /> : null}
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
        <aside className="document-category-panel">
          <header>
            <h2>文档分类</h2>
          </header>
          <nav aria-label="文档分类">
            {systemCategories.map(({ icon: Icon, key, label }) => (
              <CategoryButton active={activeCategory === key} count={categoryCount(key)} icon={<Icon size={16} />} key={key} label={label} onClick={() => setActiveCategory(key)} />
            ))}
            <div className="document-category-heading">
              <span>我的分类</span>
              <button aria-label="新增分类" className="document-add-category" disabled={busy} onClick={() => setCategoryDialogOpen(true)} title="新增分类" type="button"><FolderPlus size={15} /></button>
            </div>
            {userCategories.length ? userCategories.map((category) => {
              const key = `category:${category.name}`;
              return <CategoryButton active={activeCategory === key} count={category.document_count} icon={<Folder size={16} />} key={category.id} label={category.name} onClick={() => setActiveCategory(key)} />;
            }) : <p className="document-category-empty">暂无自定义分类</p>}
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
                  <div className="document-detail-heading"><span>所在分类</span></div>
                  {userCategories.length ? (
                    <div className="document-category-checks">
                      {userCategories.map((category) => (
                        <button
                          aria-pressed={selectedDocument.categories.includes(category.name)}
                          className={selectedDocument.categories.includes(category.name) ? 'selected' : ''}
                          key={category.id}
                          type="button"
                            disabled={busy}
                          onClick={() => void toggleCategory(category, !selectedDocument.categories.includes(category.name))}
                        >
                          {category.name}
                        </button>
                      ))}
                    </div>
                  ) : <button className="document-inline-action" onClick={() => setCategoryDialogOpen(true)} type="button"><FolderPlus size={14} />创建第一个分类</button>}
                </section>
                <section className="document-library-location">
                  <div title={libraryPath}>{libraryPath || '正在读取目录…'}</div>
                </section>
              </div>
              <footer className="library-detail-footer">
                <SecondaryButton onClick={() => void deleteDocument()}><Trash2 size={15} />删除</SecondaryButton>
                <SecondaryButton onClick={() => setExportOpen(true)}><Download size={15} />导出</SecondaryButton>
              </footer>
            </>
          ) : <ShelfMessage title="选择一本书查看详情" />}
        </aside>
      </div>

      {exportOpen && selectedDocument ? <ExportDialog busy={busy} document={selectedDocument} onClose={() => setExportOpen(false)} onExport={(format) => void exportDocument(format)} /> : null}
      {categoryDialogOpen ? (
        <CategoryDialog
          busy={busy}
          name={categoryName}
          onChange={setCategoryName}
          onClose={() => { setCategoryDialogOpen(false); setCategoryName(''); }}
          onSubmit={() => void addCategory()}
        />
      ) : null}
    </div>
  );
}

type DocumentWorkspaceProps = {
  chapters: LibraryDocumentChapter[];
  content: LibraryDocumentContent | null;
  document: LibraryDocument;
  onApply: () => void;
  onContentChange: (chapterId: number | null) => void;
  onExport: () => void;
  onReorder: (draggedId: number, targetId: number) => void;
  onReservedAction: (label: string) => void;
  onRestore: (revisionId: number) => void;
  onSaveTemplate: () => void;
  onSelectTemplate: (templateId: number) => void;
  onSettingsChange: (settings: DocumentProcessingSettings) => void;
  onTabChange: (tab: ProcessingTab) => void;
  onTemplateNameChange: (name: string) => void;
  processingBusy: boolean;
  referenceScope: ReferenceScope;
  revisions: LibraryDocumentRevision[];
  selectedTab: ProcessingTab;
  selectedChapterId: number | null;
  setReferenceScope: (scope: ReferenceScope) => void;
  templateId: number | null;
  templateName: string;
  templateSettings: DocumentProcessingSettings;
  templates: DocumentProcessingTemplate[];
};

function DocumentWorkspace(props: DocumentWorkspaceProps) {
  const { document, processingBusy, selectedTab } = props;
  return (
    <div className="workbench-grid document-workspace-layout">
      <WorkspaceChapterNav
        chapters={props.chapters}
        onContentChange={props.onContentChange}
        onReorder={props.onReorder}
        selectedChapterId={props.selectedChapterId}
      />
      <main className="workspace-center document-workspace-main">
        <div className="document-workspace-content">
          {selectedTab === 'chapters' ? (
            <TextPreview
              content={props.content}
              loading={processingBusy}
              words={props.chapters.find((chapter) => chapter.id === props.selectedChapterId)?.word_count ?? document.word_count}
            />
          ) : null}
          {selectedTab === 'cleanup' ? <CleanupPanel {...props} /> : null}
          {selectedTab === 'reference' ? <ReferencePanel scope={props.referenceScope} setScope={props.setReferenceScope} /> : null}
        </div>
        {selectedTab === 'cleanup' ? (
          <footer>
            <PrimaryButton disabled={processingBusy || !props.templateId} onClick={props.onApply}>
              <WandSparkles size={16} />{processingBusy ? '处理中…' : '应用并生成新版本'}
            </PrimaryButton>
          </footer>
        ) : null}
      </main>
      <aside className="workbench-inspector document-workspace-inspector">
        <div className="document-workspace-info">
          <section>
            <h3>{document.title}</h3>
            <p>{document.author || '未知作者'}</p>
          </section>
          <section className="document-workspace-stats">
            <div><strong>{formatNumber(document.word_count)}</strong><span>总字数</span></div>
            <div><strong>{document.chapter_count}</strong><span>章节数</span></div>
          </section>
        </div>
        <div className="document-workspace-actions">
          <header><span>文档处理</span><small>选择操作</small></header>
          <div className="inspector-action-area">
            <button className="button secondary full" onClick={() => props.onReservedAction('合并文档')} type="button"><Combine size={16} />合并文档</button>
            <button className="button secondary full" onClick={() => props.onReservedAction('新增章节')} type="button"><Plus size={16} />新增章节</button>
            <button className={`button secondary full ${selectedTab === 'cleanup' ? 'selected' : ''}`} onClick={() => props.onTabChange('cleanup')} type="button"><WandSparkles size={16} />文字清理</button>
            <button className="button secondary full" onClick={() => props.onReservedAction('正则分章')} type="button"><Scissors size={16} />正则分章</button>
            <button className="button secondary full" onClick={() => props.onReservedAction('AI 分章')} type="button"><Sparkles size={16} />AI 分章</button>
            <button className={`button secondary full ${selectedTab === 'reference' ? 'selected' : ''}`} onClick={() => props.onTabChange('reference')} type="button"><BookOpenText size={16} />引用范围</button>
          </div>
          <SecondaryButton onClick={props.onExport}><Download size={15} />导出文档</SecondaryButton>
        </div>
      </aside>
    </div>
  );
}

function WorkspaceChapterNav({
  chapters,
  onContentChange,
  onReorder,
  selectedChapterId,
}: {
  chapters: LibraryDocumentChapter[];
  onContentChange: (chapterId: number | null) => void;
  onReorder: (draggedId: number, targetId: number) => void;
  selectedChapterId: number | null;
}) {
  const listRef = useRef<HTMLElement>(null);

  function startDrag(event: DragEvent<HTMLButtonElement>, chapterId: number) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(chapterId));
  }

  function dropChapter(event: DragEvent<HTMLButtonElement>, targetId: number) {
    event.preventDefault();
    const draggedId = Number(event.dataTransfer.getData('text/plain'));
    if (Number.isFinite(draggedId)) onReorder(draggedId, targetId);
  }

  return (
    <aside className="chapter-binder document-workspace-chapters">
      <div className="binder-heading"><h2>章节目录</h2><span>共 {chapters.length} 章</span></div>
      <nav className="chapter-list" ref={listRef}>
        {chapters.map((chapter) => (
          <button
            aria-current={selectedChapterId === chapter.id ? 'page' : undefined}
            className={`chapter-row draggable ${selectedChapterId === chapter.id ? 'selected' : ''}`}
            draggable
            key={chapter.id}
            onClick={() => onContentChange(chapter.id)}
            onDragOver={(event) => event.preventDefault()}
            onDragStart={(event) => startDrag(event, chapter.id)}
            onDrop={(event) => dropChapter(event, chapter.id)}
            type="button"
          >
            <span className="chapter-number">{chapter.index}</span>
            <span className="chapter-name" title={chapter.title}>{chapter.title}</span>
            <span className="chapter-state">{formatNumber(chapter.word_count)} 字</span>
          </button>
        ))}
        {chapters.length === 0 ? <div className="compact-empty">文档中没有章节。</div> : null}
      </nav>
      <div className="binder-footer">
        <button onClick={() => listRef.current?.scrollTo({ behavior: 'smooth', top: 0 })} type="button"><ArrowUpToLine size={14} />回到顶部</button>
        <button onClick={() => listRef.current?.scrollTo({ behavior: 'smooth', top: listRef.current.scrollHeight })} type="button"><ArrowDownToLine size={14} />回到底部</button>
      </div>
    </aside>
  );
}

function TextPreview({ content, loading, words }: { content: LibraryDocumentContent | null; loading: boolean; words: number }) {
  return (
    <section aria-busy={loading} className="manuscript-pane document-workspace-text">
      <header><h2>原文</h2><span>{formatNumber(words)} 字</span></header>
      <div className="manuscript-text">{loading && !content ? '正在读取正文…' : content?.text || '当前文档没有可显示的正文。'}</div>
    </section>
  );
}

function CleanupPanel(props: DocumentWorkspaceProps) {
  const settings = props.templateSettings;
  return (
    <div className="document-cleanup-grid">
      <div className="document-processing-settings">
        <label><span className="form-label">清理模板</span><select className="form-input" value={props.templateId ?? ''} onChange={(event) => props.onSelectTemplate(Number(event.target.value))}>{props.templates.map((template) => <option key={template.id} value={template.id}>{template.name}{template.is_default ? '（默认）' : ''}</option>)}</select></label>
        <div className="document-processing-number-grid">
          <NumberField label="章节缩进" value={settings.chapter_indent} onChange={(value) => props.onSettingsChange({ ...settings, chapter_indent: value })} />
          <NumberField label="段落首行缩进" value={settings.paragraph_indent} onChange={(value) => props.onSettingsChange({ ...settings, paragraph_indent: value })} />
          <NumberField label="段落间空行" max={3} value={settings.blank_lines} onChange={(value) => props.onSettingsChange({ ...settings, blank_lines: value })} />
        </div>
        <label><span className="form-label">章节标题正则</span><textarea className="document-processing-regex" value={settings.chapter_pattern} onChange={(event) => props.onSettingsChange({ ...settings, chapter_pattern: event.target.value })} /></label>
        <label className="document-processing-toggle"><input checked={settings.trim_whitespace} onChange={(event) => props.onSettingsChange({ ...settings, trim_whitespace: event.target.checked })} type="checkbox" />清除每行多余的前后空白</label>
        <div className="document-processing-save-template"><input className="form-input" value={props.templateName} onChange={(event) => props.onTemplateNameChange(event.target.value)} /><SecondaryButton disabled={props.processingBusy || !props.templateName.trim()} onClick={props.onSaveTemplate}><Save size={15} />另存模板</SecondaryButton></div>
      </div>
      <div className="document-processing-preview">
        <span className="form-label">排版预览</span><pre>{formatPreview(settings)}</pre>
        <div className="document-revision-list">
          <div className="document-detail-heading"><span>版本记录</span><small>{props.revisions.length} 个版本</small></div>
          {props.revisions.map((revision) => (
            <div key={revision.id}><span>版本 {revision.revision_number} · {revision.revision_type === 'import' ? '导入版' : '文字清理'}</span><button disabled={props.processingBusy || revision.storage_path === props.document.storage_path} onClick={() => props.onRestore(revision.id)} type="button">{revision.storage_path === props.document.storage_path ? '当前' : '切换'}</button></div>
          ))}
        </div>
      </div>
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

function CategoryDialog({
  busy,
  name,
  onChange,
  onClose,
  onSubmit,
}: {
  busy: boolean;
  name: string;
  onChange: (name: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="document-processing-backdrop" role="presentation">
      <form
        aria-labelledby="document-category-title"
        aria-modal="true"
        className="document-category-dialog"
        onSubmit={(event) => { event.preventDefault(); onSubmit(); }}
        role="dialog"
      >
        <header>
          <div><span>文档分类</span><h2 id="document-category-title">创建新分类</h2></div>
          <button aria-label="关闭分类窗口" className="icon-button" onClick={onClose} type="button"><X size={17} /></button>
        </header>
        <label><span className="form-label">分类名称</span><input autoFocus className="form-input" maxLength={80} onChange={(event) => onChange(event.target.value)} placeholder="例如：写作参考" value={name} /></label>
        <footer><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !name.trim()} type="submit">创建分类</PrimaryButton></footer>
      </form>
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

function CategoryButton({ active, count, icon, label, onClick }: { active: boolean; count: number; icon: ReactNode; label: string; onClick: () => void }) {
  return <button aria-current={active ? 'page' : undefined} className={`document-category-item ${active ? 'selected' : ''}`} onClick={onClick} type="button">{icon}<span>{label}</span><small>{count}</small></button>;
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

function matchesCategory(document: LibraryDocument, category: string, index: number) {
  if (category === 'all') return true;
  if (category === 'recent') return index < 5;
  if (category === 'favorite') return document.favorite;
  if (category === 'project') return document.categories.includes('工程');
  if (category === 'uncategorized') return document.categories.length === 0;
  return category.startsWith('category:') && document.categories.includes(category.slice('category:'.length));
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
