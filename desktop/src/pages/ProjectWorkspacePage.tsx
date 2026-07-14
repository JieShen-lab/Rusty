import { useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, Download, FileText, Pause, Play, RefreshCcw, Save, Sparkles, Trash2 } from 'lucide-react';
import {
  bindProjectCharacter,
  bindProjectOutline,
  bindProjectStyle,
  detectScene,
  exportEpub,
  exportTxt,
  getChapters,
  getCharacterCards,
  getOutlineTemplates,
  getProject,
  getProjectCharacters,
  getProjectChapter,
  getProjectExportPlan,
  getProjectOutline,
  getProjectStyle,
  getStyleTemplates,
  pauseProjectPipeline,
  retryChapterStage,
  rewriteChapter,
  runProjectPipeline,
  saveChapterRewrite,
  saveProjectExportPlan,
  summarizeChapter,
  unbindProjectCharacter,
} from '../api/client';
import type { Chapter, ChapterDetail, CharacterCard, ExportPlanItem, OutlineTemplate, PipelineRunResult, ProjectDetail, StyleTemplate } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { GlassCard } from '../components/GlassCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StageStepper } from '../components/StageStepper';
import { StatusPill, statusVariant } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

type Props = {
  projectId?: number;
  onNavigate: (path: string) => void;
};

const stages = ['书籍拆分', '内容总结', '识别待处理', 'AI 改写', '合并输出'];

export function ProjectWorkspacePage({ projectId, onNavigate }: Props) {
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null);
  const [activeStage, setActiveStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [styleTemplates, setStyleTemplates] = useState<StyleTemplate[]>([]);
  const [boundStyleId, setBoundStyleId] = useState<number | null>(null);
  const [outlineTemplates, setOutlineTemplates] = useState<OutlineTemplate[]>([]);
  const [boundOutlineId, setBoundOutlineId] = useState<number | null>(null);
  const [characterCards, setCharacterCards] = useState<CharacterCard[]>([]);
  const [boundCharacterIds, setBoundCharacterIds] = useState<number[]>([]);
  const [exportPlan, setExportPlan] = useState<ExportPlanItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [rewriteDraft, setRewriteDraft] = useState('');

  useEffect(() => {
    if (!projectId) return;
    setError(null);
    Promise.all([
      getProject(projectId),
      getChapters(projectId),
      getStyleTemplates(),
      getProjectStyle(projectId),
      getOutlineTemplates(),
      getProjectOutline(projectId),
      getCharacterCards(),
      getProjectCharacters(projectId),
      getProjectExportPlan(projectId),
    ])
      .then(([project, items, styles, styleBinding, outlines, outlineBinding, cards, characterBinding, plan]) => {
        setProjectDetail(project);
        setChapters(items);
        setStyleTemplates(styles);
        setBoundStyleId(styleBinding.style_template?.id ?? null);
        setOutlineTemplates(outlines);
        setBoundOutlineId(outlineBinding.outline_template?.id ?? null);
        setCharacterCards(cards);
        setBoundCharacterIds(characterBinding.character_cards.map((card) => card.id));
        setExportPlan(plan);
        setSelectedChapterId((current) => current ?? items[0]?.id ?? null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !selectedChapterId) return;
    getProjectChapter(projectId, selectedChapterId)
      .then((detail) => {
        setChapterDetail(detail);
        setRewriteDraft(detail.chapter.rewritten_text || '');
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [projectId, selectedChapterId]);

  if (!projectId) {
    return <EmptyState title="尚未选择项目" description="请先到作品库选择一个项目。" action={<PrimaryButton onClick={() => onNavigate('/library')}>前往作品库</PrimaryButton>} />;
  }

  const project = projectDetail?.project;
  const selected = chapterDetail?.chapter;
  const completed = project ? Math.round(project.progress * stages.length) : 0;

  async function handleExport(kind: 'txt' | 'epub') {
    if (!projectId) return;
    setExportMessage(null);
    try {
      const result = kind === 'txt' ? await exportTxt(projectId) : await exportEpub(projectId);
      setExportMessage(`已导出：${result.output_path}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function moveExportPlanItem(index: number, delta: -1 | 1) {
    setExportPlan((current) => {
      const nextIndex = index + delta;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next.map((item, itemIndex) => ({ ...item, export_order: itemIndex + 1 }));
    });
  }

  function updateExportPlanItem(chapterId: number, patch: Partial<ExportPlanItem>) {
    setExportPlan((current) => current.map((item) => (item.chapter_id === chapterId ? { ...item, ...patch } : item)));
  }

  async function handleSaveExportPlan() {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    setExportMessage(null);
    try {
      const saved = await saveProjectExportPlan(projectId, {
        items: exportPlan.map((item, index) => ({
          chapter_id: item.chapter_id,
          export_order: index + 1,
          export_title: item.export_title,
          include_in_export: item.include_in_export,
        })),
      });
      setExportPlan(saved);
      setExportMessage('导出章节设置已保存。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function reloadWorkspace(chapterId = selectedChapterId) {
    if (!projectId) return;
    const [project, items, styles, styleBinding, outlines, outlineBinding, cards, characterBinding, plan] = await Promise.all([
      getProject(projectId),
      getChapters(projectId),
      getStyleTemplates(),
      getProjectStyle(projectId),
      getOutlineTemplates(),
      getProjectOutline(projectId),
      getCharacterCards(),
      getProjectCharacters(projectId),
      getProjectExportPlan(projectId),
    ]);
    setProjectDetail(project);
    setChapters(items);
    setStyleTemplates(styles);
    setBoundStyleId(styleBinding.style_template?.id ?? null);
    setOutlineTemplates(outlines);
    setBoundOutlineId(outlineBinding.outline_template?.id ?? null);
    setCharacterCards(cards);
    setBoundCharacterIds(characterBinding.character_cards.map((card) => card.id));
    setExportPlan(plan);
    if (chapterId) {
      const detail = await getProjectChapter(projectId, chapterId);
      setChapterDetail(detail);
      setRewriteDraft(detail.chapter.rewritten_text || '');
    }
  }

  async function handleStyleBinding(value: string) {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const binding = await bindProjectStyle(projectId, value ? Number(value) : null);
      setBoundStyleId(binding.style_template?.id ?? null);
      setMessage(binding.style_template ? `已绑定风格模板：${binding.style_template.name}` : '已取消风格模板绑定。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleOutlineBinding(value: string) {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const binding = await bindProjectOutline(projectId, value ? Number(value) : null);
      setBoundOutlineId(binding.outline_template?.id ?? null);
      setMessage(binding.outline_template ? `已绑定剧情大纲：${binding.outline_template.name}` : '已取消剧情大纲绑定。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleCharacterBinding(cardId: number, checked: boolean) {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const binding = checked
        ? await bindProjectCharacter(projectId, cardId, boundCharacterIds.length + 1)
        : await unbindProjectCharacter(projectId, cardId);
      setBoundCharacterIds(binding.character_cards.map((card) => card.id));
      setMessage('项目角色卡绑定已更新。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runAction(label: string, action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await action();
      if (isPipelineRunResult(result)) {
        const summary = `流水线结果：成功 ${result.processed} 章，失败 ${result.failed} 章，保留原文 ${result.skipped} 章${result.paused ? '，已暂停' : ''}。`;
        if (result.failed > 0) {
          setError(`${summary} 请查看当前章节的错误信息。`);
        } else {
          setMessage(summary);
        }
        await reloadWorkspace();
        return;
      }
      const text = typeof result === 'object' && result && 'text' in result ? String((result as { text: string }).text) : '';
      setMessage(text ? `${label}完成：${text.slice(0, 160)}` : `${label}完成。`);
      await reloadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const selectedChapterIdForAction = selected?.id;

  return (
    <div>
      <TopBar
        title={project?.name ?? '创作台'}
        subtitle={project ? `${project.total_chapters} 章 · ${project.total_words.toLocaleString()} 字` : '读取项目中'}
        onRefresh={() => window.location.reload()}
      />
      {error && <GlassCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</GlassCard>}
      {message && <GlassCard className="mb-5 border-emerald-300/25 text-emerald-100">{message}</GlassCard>}
      <div className="mb-5">
        <StageStepper stages={stages} activeStage={activeStage} completedStages={Array.from({ length: completed }, (_, index) => index).filter((index) => index < activeStage)} />
      </div>
      <div className="grid grid-cols-[300px_1fr_280px] gap-5 max-2xl:grid-cols-[260px_1fr] max-lg:grid-cols-1">
        <GlassCard title="章节导航" strong className="max-h-[calc(100vh-190px)] overflow-auto">
          <p className="mb-4 text-sm text-[var(--text-muted)]">{chapters.length} 章 · {project?.completed_chapters ?? 0} 已完成</p>
          <div className="space-y-2">
            {chapters.map((chapter) => (
              <button
                className={`w-full cursor-pointer rounded-2xl border p-3 text-left transition ${selectedChapterId === chapter.id ? 'border-sky-300/30 bg-sky-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                key={chapter.id}
                onClick={() => setSelectedChapterId(chapter.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold text-white">{chapter.title}</span>
                  <StatusPill variant={statusVariant(chapter.status)}>{chapter.status}</StatusPill>
                </div>
                <p className="mt-1 text-xs text-[var(--text-soft)]">{chapter.word_count.toLocaleString()} 字</p>
              </button>
            ))}
          </div>
        </GlassCard>

        <GlassCard strong className="min-h-[640px]">
          <div className="mb-5 flex flex-wrap gap-2">
            {stages.map((stage, index) => (
              <button className={`rounded-full border px-3 py-1 text-xs ${activeStage === index ? 'border-sky-300/30 bg-sky-300/15 text-white' : 'border-white/10 bg-white/5 text-[var(--text-muted)]'}`} key={stage} onClick={() => setActiveStage(index)}>
                {stage}
              </button>
            ))}
          </div>
          {selected ? <StageContent activeStage={activeStage} detail={chapterDetail} rewriteDraft={rewriteDraft} setRewriteDraft={setRewriteDraft} /> : <EmptyState title="请选择章节" description="选择章节后可查看原文、总结、识别和改写结果。" />}
        </GlassCard>

        <aside className="space-y-5 max-2xl:col-span-2 max-lg:col-span-1">
          <GlassCard title="剧情大纲">
            {outlineTemplates.length === 0 ? (
              <p className="text-sm text-[var(--text-muted)]">尚未创建大纲模板。</p>
            ) : (
              <label>
                <span className="form-label">改写时固定剧情</span>
                <select className="form-input" disabled={busy} value={boundOutlineId ?? ''} onChange={(event) => handleOutlineBinding(event.target.value)}>
                  <option value="">不使用剧情大纲</option>
                  {outlineTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <p className="mt-3 text-xs leading-5 text-[var(--text-soft)]">大纲只进入 AI 改写阶段，用于保持剧情节点和因果关系。</p>
          </GlassCard>
          <GlassCard title="角色卡">
            {characterCards.length === 0 ? (
              <p className="text-sm text-[var(--text-muted)]">尚未创建角色卡。</p>
            ) : (
              <div className="space-y-3">
                {characterCards.map((card) => (
                  <label className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.04] p-3 text-sm text-[var(--text-muted)]" key={card.id}>
                    <input
                      checked={boundCharacterIds.includes(card.id)}
                      className="mt-1"
                      disabled={busy}
                      onChange={(event) => toggleCharacterBinding(card.id, event.target.checked)}
                      type="checkbox"
                    />
                    <span>
                      <span className="font-semibold text-white">{card.name}</span>
                      <span className="ml-2 text-xs text-[var(--text-soft)]">优先级 {card.priority}</span>
                      {card.aliases.length > 0 && <span className="mt-1 block text-xs text-[var(--text-soft)]">{card.aliases.join(', ')}</span>}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <p className="mt-3 text-xs leading-5 text-[var(--text-soft)]">主角/高优先级角色默认注入；普通角色按章节原文中姓名或别名命中注入。</p>
          </GlassCard>
          <GlassCard title="风格模板">
            {styleTemplates.length === 0 ? (
              <p className="text-sm text-[var(--text-muted)]">尚未创建风格模板。</p>
            ) : (
              <label>
                <span className="form-label">改写时使用</span>
                <select className="form-input" disabled={busy} value={boundStyleId ?? ''} onChange={(event) => handleStyleBinding(event.target.value)}>
                  <option value="">不使用风格模板</option>
                  {styleTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <p className="mt-3 text-xs leading-5 text-[var(--text-soft)]">风格模板只进入 AI 改写阶段，不影响总结和场景识别。</p>
          </GlassCard>
          <GlassCard title="项目操作">
            <div className="flex flex-col gap-3">
              <PrimaryButton disabled={busy} onClick={() => runAction('项目流水线', () => runProjectPipeline(projectId))}>
                <Play size={16} />
                运行项目流水线
              </PrimaryButton>
              <SecondaryButton disabled={busy} onClick={() => runAction('暂停项目', () => pauseProjectPipeline(projectId))}>
                <Pause size={16} />
                暂停项目
              </SecondaryButton>
            </div>
          </GlassCard>
          <GlassCard title="章节 AI">
            <div className="grid grid-cols-2 gap-3">
              <SecondaryButton disabled={busy || !selectedChapterIdForAction} onClick={() => selectedChapterIdForAction && runAction('总结章节', () => summarizeChapter(selectedChapterIdForAction))}>
                <Sparkles size={16} />
                总结
              </SecondaryButton>
              <SecondaryButton disabled={busy || !selectedChapterIdForAction} onClick={() => selectedChapterIdForAction && runAction('识别场景', () => detectScene(selectedChapterIdForAction))}>
                <Sparkles size={16} />
                识别
              </SecondaryButton>
              <SecondaryButton disabled={busy || !selectedChapterIdForAction} onClick={() => selectedChapterIdForAction && runAction('改写章节', () => rewriteChapter(selectedChapterIdForAction))}>
                <Sparkles size={16} />
                改写
              </SecondaryButton>
              <SecondaryButton disabled={busy || !selectedChapterIdForAction} onClick={() => selectedChapterIdForAction && runAction('重试改写', () => retryChapterStage(selectedChapterIdForAction, 'rewrite'))}>
                <RefreshCcw size={16} />
                重试
              </SecondaryButton>
            </div>
            <div className="mt-3 flex flex-col gap-3">
              <PrimaryButton disabled={busy || !selectedChapterIdForAction} onClick={() => selectedChapterIdForAction && runAction('保存改写', () => saveChapterRewrite(selectedChapterIdForAction, rewriteDraft))}>
                <Save size={16} />
                保存改写文本
              </PrimaryButton>
              <SecondaryButton disabled={busy || !selectedChapterIdForAction} onClick={() => selectedChapterIdForAction && runAction('清空改写', () => saveChapterRewrite(selectedChapterIdForAction, ''))}>
                <Trash2 size={16} />
                清空改写
              </SecondaryButton>
            </div>
          </GlassCard>
          <GlassCard title="项目统计">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Stat label="总字数" value={project?.total_words.toLocaleString() ?? '-'} />
              <Stat label="章节数" value={project?.total_chapters ?? '-'} />
              <Stat label="已完成" value={project?.completed_chapters ?? '-'} />
              <Stat label="总进度" value={project ? `${Math.round(project.progress * 100)}%` : '-'} />
            </div>
          </GlassCard>
          <GlassCard title="导出">
            <div className="flex flex-col gap-3">
              <PrimaryButton onClick={() => handleExport('txt')}>
                <Download size={16} />
                导出 TXT
              </PrimaryButton>
              <SecondaryButton onClick={() => handleExport('epub')}>
                <FileText size={16} />
                导出 EPUB
              </SecondaryButton>
            </div>
            {exportMessage && <p className="mt-4 break-all text-xs text-emerald-200">{exportMessage}</p>}
          </GlassCard>
          <GlassCard title="导出章节">
            {exportPlan.length === 0 ? (
              <p className="text-sm text-[var(--text-muted)]">暂无章节导出计划。</p>
            ) : (
              <div className="space-y-3">
                <div className="max-h-[360px] space-y-2 overflow-auto pr-1">
                  {exportPlan.map((item, index) => (
                    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3" key={item.chapter_id}>
                      <div className="mb-2 flex items-center gap-2">
                        <input
                          checked={item.include_in_export}
                          disabled={busy}
                          onChange={(event) => updateExportPlanItem(item.chapter_id, { include_in_export: event.target.checked })}
                          type="checkbox"
                        />
                        <span className="min-w-0 flex-1 truncate text-xs text-[var(--text-soft)]">
                          #{index + 1} · {exportSourceLabel(item.source_status)}
                        </span>
                        <button
                          className="rounded-full border border-white/10 bg-white/[0.05] p-1 text-white disabled:opacity-40"
                          disabled={busy || index === 0}
                          onClick={() => moveExportPlanItem(index, -1)}
                          title="上移"
                          type="button"
                        >
                          <ArrowUp size={14} />
                        </button>
                        <button
                          className="rounded-full border border-white/10 bg-white/[0.05] p-1 text-white disabled:opacity-40"
                          disabled={busy || index === exportPlan.length - 1}
                          onClick={() => moveExportPlanItem(index, 1)}
                          title="下移"
                          type="button"
                        >
                          <ArrowDown size={14} />
                        </button>
                      </div>
                      <input
                        className="form-input py-2 text-sm"
                        disabled={busy}
                        value={item.export_title}
                        onChange={(event) => updateExportPlanItem(item.chapter_id, { export_title: event.target.value })}
                      />
                    </div>
                  ))}
                </div>
                <PrimaryButton disabled={busy} onClick={handleSaveExportPlan}>
                  <Save size={16} />
                  保存导出设置
                </PrimaryButton>
              </div>
            )}
          </GlassCard>
          <GlassCard title="错误信息">
            {chapterDetail?.errors.length ? (
              <div className="space-y-2">
                {chapterDetail.errors.map((item) => (
                  <p className="rounded-xl border border-rose-300/20 bg-rose-400/10 p-3 text-xs text-rose-100" key={item.id}>
                    {item.stage}: {item.message}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">暂无错误。</p>
            )}
          </GlassCard>
        </aside>
      </div>
    </div>
  );
}

function isPipelineRunResult(result: unknown): result is PipelineRunResult {
  return Boolean(
    result &&
      typeof result === 'object' &&
      'processed' in result &&
      'failed' in result &&
      'skipped' in result &&
      'paused' in result,
  );
}

function StageContent({
  activeStage,
  detail,
  rewriteDraft,
  setRewriteDraft,
}: {
  activeStage: number;
  detail: ChapterDetail | null;
  rewriteDraft: string;
  setRewriteDraft: (value: string) => void;
}) {
  if (!detail) return null;
  const chapter = detail.chapter;
  const outputs = detail.ai_outputs;
  if (activeStage === 1) {
    return <TextPanel title="剧情概要" text={outputs.plot_summary || '暂无章节总结，请点击后续流水线入口生成总结。'} />;
  }
  if (activeStage === 2) {
    return (
      <TextPanel
        title="场景识别"
        text={outputs.needs_rewrite === null ? '暂无场景识别结果。' : `是否需要改写：${outputs.needs_rewrite ? '是' : '否'}\n标签：${outputs.scene_labels?.join(', ') || '无'}\n理由：${outputs.scene_reasoning || '无'}`}
      />
    );
  }
  if (activeStage === 3) {
    return (
      <div className="grid grid-cols-2 gap-4 max-xl:grid-cols-1">
        <TextPanel title="原文" text={chapter.original_text} />
        <div>
          <h2 className="mb-4 text-2xl font-bold text-white">改写文</h2>
          <textarea
            className="chapter-text min-h-[520px] w-full resize-y whitespace-pre-wrap rounded-3xl border border-white/10 bg-slate-950/35 p-5 text-sm leading-8 text-slate-100 outline-none"
            placeholder="暂无改写文本，可运行 AI 改写或手动输入后保存。"
            value={rewriteDraft}
            onChange={(event) => setRewriteDraft(event.target.value)}
          />
        </div>
      </div>
    );
  }
  if (activeStage === 4) {
    return <TextPanel title="合并输出" text="请使用右侧导出按钮生成 TXT / EPUB。UI-R2 暂不在前端合并全文。" />;
  }
  return <TextPanel title={`${chapter.title} · ${chapter.word_count.toLocaleString()} 字`} text={chapter.original_text} />;
}

function TextPanel({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <h2 className="mb-4 text-2xl font-bold text-white">{title}</h2>
      <pre className="chapter-text whitespace-pre-wrap rounded-3xl border border-white/10 bg-slate-950/35 p-5 text-sm leading-8 text-slate-100">{text}</pre>
    </div>
  );
}

function exportSourceLabel(status: ExportPlanItem['source_status']) {
  if (status === 'manual_rewrite') return '手动改写';
  if (status === 'ai_rewrite') return 'AI 改写';
  if (status === 'kept_original') return '保留原文';
  return '原文';
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
      <p className="text-xs text-[var(--text-soft)]">{label}</p>
      <p className="mt-1 font-semibold text-white">{value}</p>
    </div>
  );
}
