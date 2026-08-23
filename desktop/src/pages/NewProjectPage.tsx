import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ClipboardCheck,
  Cpu,
  Eye,
  FilePenLine,
  FileText,
  FolderOpen,
  Scissors,
  Upload,
  Wifi,
} from 'lucide-react';
import {
  createProject,
  getModels,
  previewProject,
  testModel,
} from '../api/client';
import type {
  ChapterSplitOptions,
  ModelConfig,
  PreviewResponse,
} from '../api/types';

type Props = { onNavigate: (path: string) => void };
type WizardStep = 'import' | 'split' | 'preview' | 'model' | 'confirm';
type SplitMode = ChapterSplitOptions['mode'];

const FLOW_STEPS: Array<{ key: WizardStep; label: string; icon: ReactNode }> = [
  { key: 'import', label: '导入文件', icon: <Upload size={17} /> },
  { key: 'split', label: '章节拆分', icon: <Scissors size={17} /> },
  { key: 'preview', label: '预览信息', icon: <Eye size={17} /> },
  { key: 'model', label: '模型配置', icon: <Cpu size={17} /> },
  { key: 'confirm', label: '确认创建', icon: <ClipboardCheck size={17} /> },
];

export function NewProjectPage({ onNavigate }: Props) {
  const [step, setStep] = useState<WizardStep>('import');
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
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getModels()
      .then((modelItems) => {
        setModels(modelItems);
        setModelId(modelItems.find((item) => item.is_default)?.id ?? modelItems[0]?.id ?? null);
      })
      .catch((reason) => setError(messageOf(reason)));
  }, []);

  const sourceFormat = sourcePath.split('.').pop()?.toLowerCase() ?? '';
  const directoryPickerAvailable = typeof window.rustyDesktop?.selectWorkspaceDirectory === 'function';
  const selectedModel = models.find((item) => item.id === modelId) ?? null;

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
      setError('当前环境无法打开目录选择器，请手动输入工作目录。');
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
    if (!preview || !modelId) return;
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(
        preview.preview_token,
        projectName,
        workspacePath,
        modelId,
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
    if (step === 'import') {
      onNavigate('/library');
      return;
    }
    const index = FLOW_STEPS.findIndex((item) => item.key === step);
    setStep(index <= 0 ? 'import' : FLOW_STEPS[index - 1].key);
  }

  async function next() {
    setError(null);
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
    if (step === 'import') return Boolean(sourcePath && workspacePath);
    if (step === 'split') {
      if (sourceFormat !== 'txt') return true;
      if (splitMode === 'regex') return Boolean(customRegex.trim());
      return Boolean(titleSuffixes.trim());
    }
    if (step === 'preview') return Boolean(preview && preview.total_chapters > 0 && projectName.trim());
    if (step === 'model') return modelId !== null;
    return Boolean(preview && modelId && projectName.trim());
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
              const complete = index < currentIndex;
              const active = item.key === step;
              return (
                <li className={`${active ? 'active' : ''} ${complete ? 'complete' : ''}`} key={item.key}>
                  <span>{complete ? <Check size={16} /> : index + 1}</span>
                  <div><strong>{item.label}</strong></div>
                </li>
              );
            })}
          </ol>
        </aside>

        <main className="wizard-content">
          {step === 'import' ? (
            <WizardSection title="导入文件">
              <div className="import-dropzone">
                <Upload size={34} />
                <strong>{sourcePath ? fileNameOf(sourcePath) : '选择 TXT、EPUB 或 DOCX 文件'}</strong>
                {sourcePath ? <small>{sourcePath}</small> : null}
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
            <WizardSection title="配置章节拆分规则">
              {sourceFormat !== 'txt' ? (
                <div className="wizard-empty-panel">
                  <FileText size={30} />
                  <strong>{sourceFormat.toUpperCase()} 自动拆分</strong>
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
            <WizardSection title="预览信息">
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
            <WizardSection title="模型配置">
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

          {step === 'confirm' && preview ? (
            <WizardSection title="确认配置">
              <div className="confirm-grid">
                <ConfirmItem label="工程类型" value="小说创作工程" />
                <ConfirmItem label="工程名称" value={projectName} />
                <ConfirmItem label="书名" value={preview.title} />
                <ConfirmItem label="规模" value={`${preview.total_chapters} 章 · ${preview.total_words.toLocaleString()} 字`} />
                <ConfirmItem label="章节拆分" value={splitModeLabel(preview.split_mode)} />
                <ConfirmItem label="AI 模型" value={selectedModel?.display_name || '未选择'} />
                <ConfirmItem label="系统提示词" value="使用全局系统提示词" />
                <ConfirmItem label="源文件" value={sourcePath} wide />
                <ConfirmItem label="工作目录" value={workspacePath} wide />
              </div>
            </WizardSection>
          ) : null}
        </main>
      </div>

      <footer className="setup-actions wizard-actions">
        <button className="button secondary" onClick={previous} type="button"><ArrowLeft size={17} />{step === 'import' ? '取消' : '上一步'}</button>
        <button className="button primary wide" disabled={!canContinue} onClick={() => void next()} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); event.stopPropagation(); } }} type="button">{primaryLabel}<ArrowRight size={17} /></button>
      </footer>
    </div>
  );
}

function WizardSection({ children, title }: { children: ReactNode; title: string }) {
  return <section className="wizard-section"><header><h2>{title}</h2></header>{children}</section>;
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
