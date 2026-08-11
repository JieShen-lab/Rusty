import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  Check,
  ClipboardCheck,
  Cpu,
  Eye,
  FilePenLine,
  FileText,
  FolderOpen,
  MessageSquareText,
  Scissors,
  Search,
  Upload,
  Wifi,
} from 'lucide-react';
import {
  createProject,
  getPromptDefinitions,
  getModels,
  previewProject,
  testModel,
} from '../api/client';
import type {
  ChapterSplitOptions,
  ModelConfig,
  PreviewResponse,
  ProjectKind,
  PromptDefinition,
} from '../api/types';

type Props = { onNavigate: (path: string) => void };
type WizardStep = 'purpose' | 'import' | 'split' | 'preview' | 'model' | 'prompt' | 'confirm';
type SplitMode = ChapterSplitOptions['mode'];

const FLOW_STEPS: Array<{ key: Exclude<WizardStep, 'purpose'>; label: string; hint: string; icon: ReactNode }> = [
  { key: 'import', label: '导入文件', hint: '选择源文件与工作目录', icon: <Upload size={17} /> },
  { key: 'split', label: '章节拆分', hint: '配置章节识别规则', icon: <Scissors size={17} /> },
  { key: 'preview', label: '预览信息', hint: '确认章节与元数据', icon: <Eye size={17} /> },
  { key: 'model', label: '模型配置', hint: '选择 AI 推理引擎', icon: <Cpu size={17} /> },
  { key: 'prompt', label: '总提示词', hint: '填入当前工程实际使用的规则', icon: <MessageSquareText size={17} /> },
  { key: 'confirm', label: '确认创建', hint: '检查并启动工程', icon: <ClipboardCheck size={17} /> },
];

export function NewProjectPage({ onNavigate }: Props) {
  const [step, setStep] = useState<WizardStep>('import');
  const [purpose, setPurpose] = useState<ProjectKind | null>('rewrite');
  const [sourcePath, setSourcePath] = useState('');
  const [workspacePath, setWorkspacePath] = useState('');
  const [projectName, setProjectName] = useState('');
  const [preview, setPreview] = useState<PreviewResponse | null>(null);

  const [splitMode, setSplitMode] = useState<SplitMode>('simple');
  const [linePrefix, setLinePrefix] = useState('第');
  const [numberStyle, setNumberStyle] = useState<'mixed' | 'arabic' | 'chinese'>('mixed');
  const [titleSuffixes, setTitleSuffixes] = useState('章|回|节|卷|集|部|篇');
  const [extraTitleRegex, setExtraTitleRegex] = useState('^(序|楔子|前言|后记|尾声|番外|终章|最终章).*$');
  const [customRegex, setCustomRegex] = useState('^\\s*(第[零〇一二三四五六七八九十百千万两0-9]+[章回节卷集部篇].*)\\s*$');

  const [models, setModels] = useState<ModelConfig[]>([]);
  const [modelId, setModelId] = useState<number | null>(null);
  const [modelTestMessage, setModelTestMessage] = useState<string | null>(null);
  const [masterPrompts, setMasterPrompts] = useState<PromptDefinition[]>([]);
  const [masterPromptId, setMasterPromptId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([getModels(), getPromptDefinitions()])
      .then(([modelItems, promptItems]) => {
        setModels(modelItems);
        setModelId(modelItems.find((item) => item.is_default)?.id ?? modelItems[0]?.id ?? null);
        const masters = promptItems.filter((item) => item.kind === 'master');
        setMasterPrompts(masters);
        setMasterPromptId(masters.find((item) => item.is_default)?.id ?? masters[0]?.id ?? null);
      })
      .catch((reason) => setError(messageOf(reason)));
  }, []);

  const sourceFormat = sourcePath.split('.').pop()?.toLowerCase() ?? '';
  const directoryPickerAvailable = typeof window.rustyDesktop?.selectWorkspaceDirectory === 'function';
  const selectedModel = models.find((item) => item.id === modelId) ?? null;
  const visiblePrompts = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const source = masterPrompts;
    return normalized
      ? source.filter((item) => `${item.name} ${item.description}`.toLowerCase().includes(normalized))
      : source;
  }, [masterPrompts, query]);
  const selectedPrompt = masterPrompts.find((item) => item.id === masterPromptId);

  function resetPreview() {
    setPreview(null);
    setError(null);
  }

  async function chooseFile() {
    const selected = await window.rustyDesktop?.selectBookFile?.();
    if (selected) {
      setSourcePath(selected);
      setProjectName('');
      resetPreview();
    }
  }

  async function chooseWorkspace() {
    const picker = window.rustyDesktop?.selectWorkspaceDirectory;
    if (!picker) {
      setError('当前窗口仍在使用旧版桌面桥接。请完全退出 Rusty 后重新打开；重启前也可以手动输入工作目录。');
      return;
    }
    setError(null);
    try {
      const selected = await picker();
      if (selected) {
        setWorkspacePath(selected);
        resetPreview();
      }
    } catch (reason) {
      setError(`无法打开目录选择窗口：${messageOf(reason)}`);
    }
  }

  function splitOptions(): ChapterSplitOptions {
    if (sourceFormat !== 'txt') return { mode: 'auto' };
    if (splitMode === 'simple') {
      return {
        mode: 'simple',
        line_prefix: linePrefix,
        number_style: numberStyle,
        title_suffixes: titleSuffixes.split('|').map((item) => item.trim()).filter(Boolean),
        extra_title_regex: extraTitleRegex.trim() || null,
      };
    }
    if (splitMode === 'regex') return { mode: 'regex', custom_regex: customRegex.trim() };
    return { mode: 'auto' };
  }

  async function generatePreview() {
    setBusy(true);
    setError(null);
    try {
      const result = await previewProject(sourcePath, workspacePath, splitOptions());
      setPreview(result);
      setProjectName((current) => current || result.title);
      setStep('preview');
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function testSelectedModel() {
    if (!modelId) return;
    setBusy(true);
    setError(null);
    setModelTestMessage(null);
    try {
      const result = await testModel(modelId);
      setModelTestMessage(result.ok ? `连接成功：${result.message}` : `连接失败：${result.message}`);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!preview || !selectedPrompt || !purpose || !modelId) return;
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(
        preview.preview_token,
        projectName,
        workspacePath,
        purpose,
        null,
        null,
        modelId,
        masterPromptId,
      );
      onNavigate(`/workspace/${project.id}`);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  function previous() {
    setError(null);
    if (step === 'purpose' || step === 'import') {
      onNavigate('/library');
      return;
    }
    const index = FLOW_STEPS.findIndex((item) => item.key === step);
    setStep(index <= 0 ? 'purpose' : FLOW_STEPS[index - 1].key);
  }

  async function next() {
    setError(null);
    if (step === 'purpose') {
      if (purpose) setStep('import');
      return;
    }
    if (step === 'import') {
      setStep('split');
      return;
    }
    if (step === 'split') {
      await generatePreview();
      return;
    }
    const index = FLOW_STEPS.findIndex((item) => item.key === step);
    if (step === 'confirm') {
      await create();
    } else if (index >= 0 && index + 1 < FLOW_STEPS.length) {
      setStep(FLOW_STEPS[index + 1].key);
    }
  }

  const canContinue = (() => {
    if (busy) return false;
    if (step === 'purpose') return purpose !== null;
    if (step === 'import') return Boolean(sourcePath && workspacePath);
    if (step === 'split') {
      if (sourceFormat !== 'txt') return true;
      if (splitMode === 'regex') return Boolean(customRegex.trim());
      return Boolean(titleSuffixes.trim());
    }
    if (step === 'preview') return Boolean(preview && preview.total_chapters > 0 && projectName.trim());
    if (step === 'model') return modelId !== null;
    if (step === 'prompt') return selectedPrompt !== undefined;
    return Boolean(preview && selectedPrompt && modelId && projectName.trim());
  })();

  const primaryLabel = step === 'confirm'
    ? (busy ? '正在创建…' : '开始创建')
    : step === 'split'
      ? (busy ? '正在拆分…' : '拆分并预览')
      : '下一步';

  return (
    <div className="setup-page wizard-page">
      <header className="setup-header wizard-header">
        <div>
          <h1>新建工程</h1>
          <p>普通小说创作工程 · 按步骤完成导入与配置</p>
        </div>
        <span className="wizard-purpose-badge">小说创作工程</span>
      </header>

      {error ? <div className="inline-alert error" role="alert">{error}</div> : null}

      <div className="wizard-frame">
        <aside className="wizard-sidebar" aria-label="创建工程步骤">
          <div className="wizard-sidebar-title">
            <FilePenLine size={20} />
            <strong>小说创作工程</strong>
          </div>
          <ol>
            {FLOW_STEPS.map((item, index) => {
              const currentIndex = FLOW_STEPS.findIndex((candidate) => candidate.key === step);
              const complete = step !== 'purpose' && index < currentIndex;
              const active = item.key === step;
              return (
                <li className={`${active ? 'active' : ''} ${complete ? 'complete' : ''}`} key={item.key}>
                  <span>{complete ? <Check size={16} /> : index + 1}</span>
                  <div><strong>{item.label}</strong><small>{item.hint}</small></div>
                </li>
              );
            })}
          </ol>
        </aside>

        <main className="wizard-content">
          {step === 'purpose' ? (
            <WizardSection title="选择工程类型" description="选择后才会释放导入文件步骤。">
              <div className="purpose-choice-grid">
                <PurposeOption
                  active={purpose === 'rewrite'}
                  description="基于项目设定、人物卡和提示词逐章改写正文。"
                  icon={<FilePenLine size={26} />}
                  onClick={() => setPurpose('rewrite')}
                  title="改写工程"
                />
                <PurposeOption
                  active={purpose === 'branch'}
                  description="从原文末尾或任意节点派生新路线，原始文本始终保持不变。"
                  icon={<BookOpenText size={26} />}
                  onClick={() => setPurpose('branch')}
                  title="扩写工程"
                />
              </div>
            </WizardSection>
          ) : null}

          {step === 'import' ? (
            <WizardSection title="导入文件" description="源文件和工作目录都确认后才能继续。">
              <div className="import-dropzone">
                <Upload size={34} />
                <strong>{sourcePath ? fileNameOf(sourcePath) : '选择 TXT、EPUB 或 DOCX 文件'}</strong>
                <small>{sourcePath || '点击按钮选择本地电子书文件'}</small>
                <button className="button secondary" onClick={() => void chooseFile()} type="button">
                  <FolderOpen size={17} />选择文件
                </button>
              </div>
              <label className="field-label" htmlFor="workspace-path">工作目录</label>
              <div className="path-picker">
                <input
                  className="text-input"
                  id="workspace-path"
                  readOnly={directoryPickerAvailable}
                  value={workspacePath}
                  onChange={(event) => { setWorkspacePath(event.target.value); resetPreview(); }}
                  placeholder={directoryPickerAvailable ? '请选择工作目录' : '输入目录，或重启 Rusty 启用目录选择'}
                />
                <button className="button secondary" onClick={() => void chooseWorkspace()} type="button">
                  <FolderOpen size={17} />选择目录
                </button>
              </div>
            </WizardSection>
          ) : null}

          {step === 'split' ? (
            <WizardSection title="配置章节拆分规则" description={sourceFormat === 'txt' ? '选择一种方式，把原文识别成一章一章。' : '该格式使用文档自身的章节结构。'}>
              {sourceFormat !== 'txt' ? (
                <div className="wizard-empty-panel">
                  <FileText size={30} />
                  <strong>{sourceFormat.toUpperCase()} 自动拆分</strong>
                  <p>Rusty 将读取文档标题层级和元数据，不需要配置 TXT 正则。</p>
                </div>
              ) : (
                <>
                  <div className="split-mode-tabs" role="radiogroup" aria-label="章节拆分方式">
                    <SplitModeButton active={splitMode === 'simple'} label="简易规则" onClick={() => { setSplitMode('simple'); resetPreview(); }} />
                    <SplitModeButton active={splitMode === 'regex'} label="正则表达式" onClick={() => { setSplitMode('regex'); resetPreview(); }} />
                  </div>
                  {splitMode === 'simple' ? (
                    <div className="split-form-grid">
                      <label><span>行首标识</span><input className="text-input" value={linePrefix} onChange={(event) => { setLinePrefix(event.target.value); resetPreview(); }} /></label>
                      <label><span>数字类型</span><select className="text-input" value={numberStyle} onChange={(event) => { setNumberStyle(event.target.value as typeof numberStyle); resetPreview(); }}><option value="mixed">中文与阿拉伯数字</option><option value="chinese">仅中文数字</option><option value="arabic">仅阿拉伯数字</option></select></label>
                      <label className="span-two"><span>章节单位（使用 | 分隔）</span><input className="text-input" value={titleSuffixes} onChange={(event) => { setTitleSuffixes(event.target.value); resetPreview(); }} /></label>
                      <label className="span-two"><span>附加标题规则</span><input className="text-input mono" value={extraTitleRegex} onChange={(event) => { setExtraTitleRegex(event.target.value); resetPreview(); }} /></label>
                    </div>
                  ) : null}
                  {splitMode === 'regex' ? (
                    <label className="split-regex-field"><span>章节标题正则表达式</span><textarea className="text-area mono" value={customRegex} onChange={(event) => { setCustomRegex(event.target.value); resetPreview(); }} /></label>
                  ) : null}
                </>
              )}
            </WizardSection>
          ) : null}

          {step === 'preview' && preview ? (
            <WizardSection title="预览信息" description="确认书籍元数据和章节边界。">
              <div className="preview-facts">
                <Fact label="识别书名" value={preview.title} />
                <Fact label="文件格式" value={preview.source_format.toUpperCase()} />
                <Fact label="章节总数" value={`${preview.total_chapters} 章`} />
                <Fact label="总字数" value={preview.total_words.toLocaleString()} />
              </div>
              <label className="field-label" htmlFor="project-name">工程名称</label>
              <input className="text-input" id="project-name" value={projectName} onChange={(event) => setProjectName(event.target.value)} />
              <div className="chapter-preview wizard-chapter-preview">
                <div className="section-heading"><strong>章节预览</strong><span>共 {preview.total_chapters} 章</span></div>
                <div className="chapter-preview-list">
                  {preview.chapters.map((chapter) => (
                    <div className="chapter-preview-row" key={`${chapter.index}-${chapter.title}`}>
                      <span>{chapter.index}</span><strong title={chapter.title}>{chapter.title}</strong><small>{chapter.word_count.toLocaleString()} 字</small>
                    </div>
                  ))}
                </div>
              </div>
            </WizardSection>
          ) : null}

          {step === 'model' ? (
            <WizardSection title="模型配置" description="选择本工程后续处理使用的 AI 模型。">
              <div className="wizard-model-list">
                {models.map((model) => (
                  <button className={`wizard-choice-card ${model.id === modelId ? 'selected' : ''}`} key={model.id} onClick={() => { setModelId(model.id); setModelTestMessage(null); }} type="button">
                    <span className="radio-mark" />
                    <span><strong>{model.display_name}</strong><small>{model.model_name} · {model.base_url}</small></span>
                    <em>{model.is_default ? '默认' : model.has_api_key ? '已配置密钥' : '未保存密钥'}</em>
                  </button>
                ))}
                {!models.length ? <div className="compact-empty">还没有模型配置，请先到模型管理中新建。</div> : null}
              </div>
              <div className="wizard-inline-actions">
                <button className="button secondary" disabled={!modelId || busy} onClick={() => void testSelectedModel()} type="button"><Wifi size={17} />测试连接</button>
                <button className="button secondary" onClick={() => onNavigate('/models')} type="button">模型管理</button>
                {modelTestMessage ? <span>{modelTestMessage}</span> : null}
              </div>
            </WizardSection>
          ) : null}

          {step === 'prompt' ? (
            <WizardSection title="选择总提示词" description="所选内容会复制到工程中，之后可独立编辑，不与提示词库同步。">
              <div className="search-field"><Search size={16} /><input aria-label="搜索提示词" placeholder="搜索名称或说明" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
              <div className="prompt-choice-list wizard-prompt-list">
                {visiblePrompts.map((item) => {
                  const selected = item.id === masterPromptId;
                  return (
                    <button className={`prompt-choice ${selected ? 'selected' : ''}`} key={item.id} onClick={() => setMasterPromptId(item.id)} type="button">
                      <span className="radio-mark" /><span><strong>{item.name}</strong><small>{item.description || '暂无说明'}</small></span>{item.is_default ? <em>默认</em> : null}
                    </button>
                  );
                })}
                {!visiblePrompts.length ? <div className="compact-empty">还没有适用于该工程类型的提示词。</div> : null}
              </div>
            </WizardSection>
          ) : null}

          {step === 'confirm' && preview ? (
            <WizardSection title="确认配置" description="检查无误后创建工程。">
              <div className="confirm-grid">
                <ConfirmItem label="工程类型" value="小说创作工程" />
                <ConfirmItem label="工程名称" value={projectName} />
                <ConfirmItem label="书名" value={preview.title} />
                <ConfirmItem label="规模" value={`${preview.total_chapters} 章 · ${preview.total_words.toLocaleString()} 字`} />
                <ConfirmItem label="章节拆分" value={splitModeLabel(preview.split_mode)} />
                <ConfirmItem label="AI 模型" value={selectedModel?.display_name || '未选择'} />
                <ConfirmItem label="总提示词" value={selectedPrompt?.name || '未选择'} />
                <ConfirmItem label="源文件" value={sourcePath} wide />
                <ConfirmItem label="工作目录" value={workspacePath} wide />
              </div>
            </WizardSection>
          ) : null}
        </main>
      </div>

      <footer className="setup-actions wizard-actions">
        <button className="button secondary" onClick={previous} type="button"><ArrowLeft size={17} />{step === 'purpose' ? '取消' : '上一步'}</button>
        <span>{footerHint(step, preview)}</span>
        <button className="button primary wide" disabled={!canContinue} onClick={() => void next()} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); event.stopPropagation(); } }} type="button">{primaryLabel}<ArrowRight size={17} /></button>
      </footer>
    </div>
  );
}

function WizardSection({ children, description, title }: { children: ReactNode; description: string; title: string }) {
  return <section className="wizard-section"><header><h2>{title}</h2><p>{description}</p></header>{children}</section>;
}

function PurposeOption({ active, description, icon, onClick, title }: { active: boolean; description: string; icon: ReactNode; onClick: () => void; title: string }) {
  return <button aria-pressed={active} className={`purpose-card ${active ? 'selected' : ''}`} onClick={onClick} type="button"><span className="purpose-icon">{icon}</span><span><strong>{title}</strong><small>{description}</small></span><span className="radio-mark" /></button>;
}

function SplitModeButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return <button aria-checked={active} className={active ? 'active' : ''} onClick={onClick} role="radio" type="button"><span className="radio-mark" />{label}</button>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><small>{label}</small><strong>{value}</strong></div>;
}

function ConfirmItem({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return <div className={wide ? 'wide' : ''}><small>{label}</small><strong title={value}>{value}</strong></div>;
}

function footerHint(step: WizardStep, preview: PreviewResponse | null) {
  if (step === 'purpose') return '选择一种工程类型后继续';
  if (step === 'import') return '必须同时选择源文件和工作目录';
  if (step === 'split') return '拆分后进入章节预览';
  if (step === 'preview' && preview) return `已识别 ${preview.total_chapters} 章`;
  if (step === 'model') return '模型配置将用于后续工程处理';
  if (step === 'prompt') return '所选总提示词会复制到工程，不建立同步关系';
  return '创建后进入工程工作台';
}

function splitModeLabel(mode: string) {
  if (mode === 'simple') return '简易规则';
  if (mode === 'regex') return '正则表达式';
  if (mode === 'document') return '文档结构';
  return '自动规则';
}

function fileNameOf(path: string) {
  return path.split(/[\\/]/).pop() || path;
}

function messageOf(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}
