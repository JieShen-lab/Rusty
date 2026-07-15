import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { BookOpenText, FilePenLine, FileText, FolderOpen, Search } from 'lucide-react';
import { createProject, getAnalysisPrompts, getPrompts, previewProject } from '../api/client';
import type { AnalysisPromptTemplate, PreviewResponse, ProjectPurpose, PromptTemplate } from '../api/types';

type Props = { onNavigate: (path: string) => void };

export function NewProjectPage({ onNavigate }: Props) {
  const [purpose, setPurpose] = useState<ProjectPurpose>('rewrite');
  const [sourcePath, setSourcePath] = useState('');
  const [workspacePath, setWorkspacePath] = useState('');
  const [projectName, setProjectName] = useState('');
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [rewritePrompts, setRewritePrompts] = useState<PromptTemplate[]>([]);
  const [analysisPrompts, setAnalysisPrompts] = useState<AnalysisPromptTemplate[]>([]);
  const [rewritePromptId, setRewritePromptId] = useState<number | null>(null);
  const [analysisPromptId, setAnalysisPromptId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([getPrompts(), getAnalysisPrompts()])
      .then(([rewriteItems, analysisItems]) => {
        setRewritePrompts(rewriteItems);
        setAnalysisPrompts(analysisItems);
        setRewritePromptId(rewriteItems.find((item) => item.is_default)?.id ?? rewriteItems[0]?.id ?? null);
        setAnalysisPromptId(analysisItems.find((item) => item.is_default)?.id ?? analysisItems[0]?.id ?? null);
      })
      .catch((reason) => setError(messageOf(reason)));
  }, []);

  const visiblePrompts = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const source = purpose === 'rewrite' ? rewritePrompts : analysisPrompts;
    return normalized
      ? source.filter((item) => `${item.name} ${item.description}`.toLowerCase().includes(normalized))
      : source;
  }, [analysisPrompts, purpose, query, rewritePrompts]);

  const selectedPrompt = purpose === 'rewrite'
    ? rewritePrompts.find((item) => item.id === rewritePromptId)
    : analysisPrompts.find((item) => item.id === analysisPromptId);

  async function chooseFile() {
    const selected = await window.rustyDesktop?.selectBookFile?.();
    if (selected) {
      setSourcePath(selected);
      setPreview(null);
    }
  }

  async function previewFile() {
    if (!sourcePath) return;
    setBusy(true);
    setError(null);
    try {
      const result = await previewProject(sourcePath, workspacePath);
      setPreview(result);
      setProjectName((current) => current || result.title);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!preview || !selectedPrompt) return;
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(
        preview.preview_token,
        projectName,
        workspacePath,
        purpose,
        purpose === 'rewrite' ? rewritePromptId : null,
        purpose === 'extract' ? analysisPromptId : null,
      );
      onNavigate(`/workspace/${project.id}`);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="setup-page">
      <header className="setup-header">
        <div><h1>新建工程</h1><p>选择用途、确认分章结果，再绑定本次工作需要的提示词。</p></div>
        <div className="setup-steps" aria-label="创建工程步骤"><span className="active">1 工程类型</span><span>2 文件预览</span><span>3 提示词与设置</span></div>
      </header>

      {error ? <div className="inline-alert error" role="alert">{error}</div> : null}

      <div className="setup-grid">
        <section className="setup-column purpose-column" aria-labelledby="purpose-title">
          <ColumnTitle index="1" title="选择工程类型" subtitle="本次工程最终要产出什么" id="purpose-title" />
          <PurposeOption
            active={purpose === 'rewrite'}
            description="逐章提取剧情和人物，修改骨架后生成改写稿。"
            icon={<FilePenLine size={24} />}
            onClick={() => setPurpose('rewrite')}
            title="改写工程"
          />
          <PurposeOption
            active={purpose === 'extract'}
            description="逐章分析范文风格，归纳并导出改写提示词。"
            icon={<BookOpenText size={24} />}
            onClick={() => setPurpose('extract')}
            title="提取工程"
          />
          <div className="purpose-flow">
            <strong>{purpose === 'rewrite' ? '改写流程' : '提取流程'}</strong>
            <p>{purpose === 'rewrite' ? '拆分 → 剧情与人物 → 目标骨架 → 改写对照 → 导出' : '拆分 → 章节分析 → 人工审查 → 全书归纳 → JSON'}</p>
          </div>
        </section>

        <section className="setup-column preview-column" aria-labelledby="preview-title">
          <ColumnTitle index="2" title="导入文件与预览" subtitle="系统会解析 TXT、EPUB 或 DOCX" id="preview-title" />
          <label className="field-label" htmlFor="source-path">源文件</label>
          <div className="file-row">
            <input className="text-input" id="source-path" placeholder="请选择本地文件" value={sourcePath} onChange={(event) => { setSourcePath(event.target.value); setPreview(null); }} />
            <button className="button secondary" onClick={() => void chooseFile()} type="button"><FolderOpen size={17} />浏览</button>
            <button className="button secondary" disabled={!sourcePath || busy} onClick={() => void previewFile()} type="button">预览</button>
          </div>

          {preview ? (
            <>
              <div className="preview-facts">
                <Fact label="识别书名" value={preview.title} />
                <Fact label="文件格式" value={preview.source_format.toUpperCase()} />
                <Fact label="章节总数" value={`${preview.total_chapters} 章`} />
                <Fact label="总字数" value={preview.total_words.toLocaleString()} />
              </div>
              <div className="chapter-preview">
                <div className="section-heading"><strong>章节预览</strong><span>共 {preview.total_chapters} 章</span></div>
                <div className="chapter-preview-list">
                  {preview.chapters.map((chapter) => (
                    <div className="chapter-preview-row" key={`${chapter.index}-${chapter.title}`}>
                      <span>{chapter.index}</span><strong title={chapter.title}>{chapter.title}</strong><small>{chapter.word_count.toLocaleString()} 字</small>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="setup-empty"><FileText size={28} /><strong>等待文件预览</strong><p>预览后才能创建工程并确认分章结果。</p></div>
          )}
        </section>

        <section className="setup-column prompt-column" aria-labelledby="prompt-title">
          <ColumnTitle index="3" title={purpose === 'rewrite' ? '选择改写提示词' : '选择分析提示词'} subtitle={purpose === 'rewrite' ? '决定如何识别与改写' : '决定提取哪些风格规律'} id="prompt-title" />
          <div className="search-field"><Search size={16} /><input aria-label="搜索提示词" placeholder="搜索名称或说明" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
          <div className="prompt-choice-list">
            {visiblePrompts.map((item) => {
              const selected = purpose === 'rewrite' ? item.id === rewritePromptId : item.id === analysisPromptId;
              return (
                <button
                  aria-pressed={selected}
                  className={`prompt-choice ${selected ? 'selected' : ''}`}
                  key={item.id}
                  onClick={() => purpose === 'rewrite' ? setRewritePromptId(item.id) : setAnalysisPromptId(item.id)}
                  type="button"
                >
                  <span className="radio-mark" /><span><strong>{item.name}</strong><small>{item.description || '暂无说明'}</small></span>{item.is_default ? <em>默认</em> : null}
                </button>
              );
            })}
            {visiblePrompts.length === 0 ? <div className="compact-empty">还没有可用模板，请先到提示词管理中新建。</div> : null}
          </div>
          {selectedPrompt ? <div className="selected-prompt-summary"><span>已选择</span><strong>{selectedPrompt.name}</strong><p>{selectedPrompt.description || '可在提示词管理中查看和编辑完整内容。'}</p></div> : null}

          <label className="field-label" htmlFor="project-name">工程名称</label>
          <input className="text-input" id="project-name" value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="预览后自动填入" />
          <label className="field-label field-gap" htmlFor="workspace-path">输出文件夹</label>
          <input className="text-input" id="workspace-path" value={workspacePath} onChange={(event) => setWorkspacePath(event.target.value)} placeholder="留空则使用源文件所在目录" />
        </section>
      </div>

      <footer className="setup-actions">
        <span>{preview ? `已识别 ${preview.total_chapters} 章 · ${preview.total_words.toLocaleString()} 字` : '请先导入并预览文件'}</span>
        <div><button className="button secondary wide" onClick={() => onNavigate('/home')} type="button">取消</button><button className="button primary wide" disabled={!preview || !selectedPrompt || busy} onClick={() => void create()} type="button">{busy ? '正在创建…' : '创建工程'}</button></div>
      </footer>
    </div>
  );
}

function ColumnTitle({ id, index, subtitle, title }: { id: string; index: string; subtitle: string; title: string }) {
  return <div className="column-title"><span>{index}</span><div><h2 id={id}>{title}</h2><p>{subtitle}</p></div></div>;
}

function PurposeOption({ active, description, icon, onClick, title }: { active: boolean; description: string; icon: ReactNode; onClick: () => void; title: string }) {
  return <button aria-pressed={active} className={`purpose-card ${active ? 'selected' : ''}`} onClick={onClick} type="button"><span className="purpose-icon">{icon}</span><span><strong>{title}</strong><small>{description}</small></span><span className="radio-mark" /></button>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><small>{label}</small><strong>{value}</strong></div>;
}

function messageOf(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
