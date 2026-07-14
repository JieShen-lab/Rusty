import { useState } from 'react';
import { BookOpenText, FilePenLine, FolderOpen, Wand2 } from 'lucide-react';
import { createProject, previewProject } from '../api/client';
import type { PreviewResponse, ProjectPurpose } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';

type Props = {
  onNavigate: (path: string) => void;
};

const purposes: Array<{
  value: ProjectPurpose;
  title: string;
  description: string;
  steps: string;
  icon: typeof FilePenLine;
}> = [
  {
    value: 'rewrite',
    title: '改写项目',
    description: '保留原文结构，按章节总结、识别并改写。',
    steps: '原文 · 总结 · 识别 · 改写 · 导出',
    icon: FilePenLine,
  },
  {
    value: 'summary',
    title: '总结项目',
    description: '只生成章节总结与全书汇总，不进入改写。',
    steps: '原文 · 章节总结 · 全书汇总',
    icon: BookOpenText,
  },
];

export function NewProjectPage({ onNavigate }: Props) {
  const [purpose, setPurpose] = useState<ProjectPurpose>('rewrite');
  const [sourcePath, setSourcePath] = useState('');
  const [workspacePath, setWorkspacePath] = useState('');
  const [projectName, setProjectName] = useState('');
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function selectFile() {
    const selected = await window.rustyDesktop?.selectBookFile?.();
    if (selected) setSourcePath(selected);
  }

  async function handlePreview() {
    setBusy(true);
    setError(null);
    try {
      const result = await previewProject(sourcePath, workspacePath);
      setPreview(result);
      setProjectName(result.title);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(preview.preview_token, projectName, workspacePath, purpose);
      onNavigate(`/workspace/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <TopBar title="新建项目" subtitle="先确定项目目的，再导入本地书籍。创建后两套流程彼此独立。" />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}

      <section className="mb-5" aria-labelledby="purpose-heading">
        <div className="mb-3 flex items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-full border border-white/15 text-xs font-bold text-white">1</span>
          <h2 className="text-lg font-semibold text-white" id="purpose-heading">选择项目目的</h2>
        </div>
        <div className="grid max-w-[920px] grid-cols-2 gap-3 max-md:grid-cols-1">
          {purposes.map(({ value, title, description, steps, icon: Icon }) => {
            const selected = purpose === value;
            return (
              <button
                aria-pressed={selected}
                className={`purpose-option ${selected ? 'purpose-option-selected' : ''}`}
                key={value}
                onClick={() => setPurpose(value)}
                type="button"
              >
                <span className="purpose-icon"><Icon size={22} /></span>
                <span className="min-w-0 text-left">
                  <span className="block text-base font-semibold text-white">{title}</span>
                  <span className="mt-1 block text-sm text-[var(--text-muted)]">{description}</span>
                  <span className="mt-2 block text-xs text-[var(--accent-blue)]">{steps}</span>
                </span>
                <span className="purpose-radio" />
              </button>
            );
          })}
        </div>
      </section>

      <div className="mb-3 flex items-center gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-full border border-white/15 text-xs font-bold text-white">2</span>
        <h2 className="text-lg font-semibold text-white">导入本地书籍</h2>
      </div>
      <div className="grid grid-cols-[minmax(360px,0.85fr)_minmax(440px,1.15fr)] gap-5 max-xl:grid-cols-1">
        <GlassCard strong>
          <label className="form-label">电子书路径</label>
          <div className="mb-4 flex gap-2">
            <input className="form-input" value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="D:\\Novel\\book.txt" />
            <SecondaryButton aria-label="选择电子书" className="shrink-0" onClick={selectFile} type="button">
              <FolderOpen size={16} />
              选择文件
            </SecondaryButton>
          </div>
          <label className="form-label">工作目录（可选）</label>
          <input className="form-input mb-4" value={workspacePath} onChange={(event) => setWorkspacePath(event.target.value)} placeholder="留空则使用源文件所在目录" />
          <label className="form-label">项目名称</label>
          <input className="form-input mb-6" value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="预览后自动填入书名" />
          <div className="flex flex-wrap justify-end gap-3">
            <SecondaryButton disabled={!sourcePath || busy} onClick={handlePreview}>
              <Wand2 size={16} />
              预览
            </SecondaryButton>
            <PrimaryButton disabled={!preview || busy} onClick={handleCreate}>创建{purpose === 'summary' ? '总结' : '改写'}项目</PrimaryButton>
          </div>
        </GlassCard>

        <GlassCard title="解析预览" strong>
          {preview ? (
            <div>
              <div className="grid grid-cols-4 gap-3 max-xl:grid-cols-2">
                <PreviewMetric label="书名" value={preview.title} />
                <PreviewMetric label="作者" value={preview.author || '未知'} />
                <PreviewMetric label="章节" value={preview.total_chapters} />
                <PreviewMetric label="字数" value={preview.total_words.toLocaleString()} />
              </div>
              <div className="mt-5 max-h-[300px] space-y-2 overflow-auto pr-1">
                {preview.chapters.map((chapter) => (
                  <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-sm" key={chapter.index}>
                    <span className="truncate text-white">#{chapter.index} {chapter.title}</span>
                    <span className="shrink-0 text-[var(--text-muted)]">{chapter.word_count.toLocaleString()} 字</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState title="尚未预览" description="选择 TXT / EPUB / DOCX 后先执行预览，确认章节识别结果。" />
          )}
        </GlassCard>
      </div>
    </div>
  );
}

function PreviewMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
      <p className="text-xs text-[var(--text-soft)]">{label}</p>
      <p className="mt-1.5 truncate font-semibold text-white">{value}</p>
    </div>
  );
}
