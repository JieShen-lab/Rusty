import { useState } from 'react';
import { FolderOpen, Wand2 } from 'lucide-react';
import { createProject, previewProject } from '../api/client';
import type { PreviewResponse } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';

declare global {
  interface Window {
    rustyDesktop?: {
      platform: string;
      versions: Record<string, string>;
      selectBookFile: () => Promise<string | null>;
    };
  }
}

type Props = {
  onNavigate: (path: string) => void;
};

export function NewProjectPage({ onNavigate }: Props) {
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
      const project = await createProject(preview.preview_token, projectName, workspacePath);
      onNavigate(`/workspace/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <TopBar title="新建工程" subtitle="UI-R2 最小闭环：本地路径预览 -> 创建工程 -> 进入创作台" />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      <div className="grid grid-cols-[420px_1fr] gap-5 max-xl:grid-cols-1">
        <GlassCard title="导入文件" eyebrow="Local Preview" strong>
          <p className="mb-5 text-sm leading-6 text-[var(--text-muted)]">
            UI-R2 使用本地 FastAPI 预览路径。Electron 文件选择可用时会自动填入路径；浏览器直开时可手动输入本机绝对路径。
          </p>
          <label className="form-label">电子书路径</label>
          <div className="mb-4 flex gap-2">
            <input className="form-input" value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="D:\\Novel\\book.txt" />
            <SecondaryButton onClick={selectFile} type="button">
              <FolderOpen size={16} />
            </SecondaryButton>
          </div>
          <label className="form-label">工作目录（可选）</label>
          <input className="form-input mb-4" value={workspacePath} onChange={(event) => setWorkspacePath(event.target.value)} placeholder="留空则使用源文件所在目录" />
          <label className="form-label">项目名称</label>
          <input className="form-input mb-6" value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="预览后自动填入书名" />
          <div className="flex flex-wrap gap-3">
            <SecondaryButton disabled={!sourcePath || busy} onClick={handlePreview}>
              <Wand2 size={16} />
              预览
            </SecondaryButton>
            <PrimaryButton disabled={!preview || busy} onClick={handleCreate}>创建工程</PrimaryButton>
          </div>
        </GlassCard>

        <GlassCard title="解析预览" eyebrow="Preview" strong>
          {preview ? (
            <div>
              <div className="grid grid-cols-4 gap-3 max-xl:grid-cols-2">
                <PreviewMetric label="书名" value={preview.title} />
                <PreviewMetric label="作者" value={preview.author || '未知'} />
                <PreviewMetric label="章节" value={preview.total_chapters} />
                <PreviewMetric label="字数" value={preview.total_words.toLocaleString()} />
              </div>
              <div className="mt-6 space-y-2">
                {preview.chapters.map((chapter) => (
                  <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.04] p-3 text-sm" key={chapter.index}>
                    <span className="text-white">#{chapter.index} {chapter.title}</span>
                    <span className="text-[var(--text-muted)]">{chapter.word_count.toLocaleString()} 字</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState title="尚未预览" description="选择 TXT / EPUB / DOCX 后先执行预览，确认元数据与章节识别结果。" />
          )}
        </GlassCard>
      </div>
    </div>
  );
}

function PreviewMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
      <p className="text-xs text-[var(--text-soft)]">{label}</p>
      <p className="mt-2 truncate font-semibold text-white">{value}</p>
    </div>
  );
}
