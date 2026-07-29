import { useEffect, useMemo, useState } from 'react';
import { Check, FileText, Plus, Settings2, Tag, X } from 'lucide-react';
import {
  applyCharacterExtraction,
  getCharacterExtractionSettings,
  getModels,
  previewCharacterExtraction,
  resetCharacterExtractionSettings,
  updateCharacterExtractionSettings,
} from '../api/client';
import type {
  CharacterCategory,
  CharacterExtractionCandidate,
  CharacterExtractionSettings,
  CharacterProjectSummary,
  ResourceTag,
} from '../api/types';
import { LibraryDialog } from './LibraryPrimitives';
import { PrimaryButton } from './PrimaryButton';
import { SecondaryButton } from './SecondaryButton';

export type CharacterExtractionLaunch = {
  selectedText: string;
  sourceMetadata: Record<string, unknown>;
};

export function CharacterCreateDialog({
  categories,
  initialLaunch,
  initialProjectId,
  onClose,
  onCreated,
  onManual,
  projects,
  tags,
}: {
  categories: CharacterCategory[];
  initialLaunch?: CharacterExtractionLaunch | null;
  initialProjectId: number | null;
  onClose: () => void;
  onCreated: (cardIds: number[], scope: 'public' | 'project', projectId: number | null) => void;
  onManual: () => void;
  projects: CharacterProjectSummary[];
  tags: ResourceTag[];
}) {
  const [mode, setMode] = useState<'manual' | 'extract'>(initialLaunch ? 'extract' : 'manual');
  const [text, setText] = useState(initialLaunch?.selectedText ?? '');
  const [targetName, setTargetName] = useState('');
  const [scope, setScope] = useState<'public' | 'project'>(initialProjectId ? 'project' : 'public');
  const [projectId, setProjectId] = useState<number | null>(initialProjectId);
  const [categoryIds, setCategoryIds] = useState<number[]>([]);
  const [previewToken, setPreviewToken] = useState('');
  const [sourceSummaryLabel, setSourceSummaryLabel] = useState('');
  const [candidates, setCandidates] = useState<CharacterExtractionCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resultMessage, setResultMessage] = useState('');

  async function generatePreview() {
    if (!text.trim()) {
      setError('请粘贴文本、载入文件或从文档选区进入。');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await previewCharacterExtraction({
        sample_text: text,
        name: targetName.trim() || null,
        source_metadata: initialLaunch?.sourceMetadata ?? {},
      });
      setPreviewToken(result.preview_token);
      setSourceSummaryLabel(result.source_summary.label);
      // Suggestions are deliberately not confirmed until the user clicks them.
      setCandidates(result.candidates.map((candidate) => ({ ...candidate, confirmed_tags: [] })));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function applyPreview() {
    const selected = candidates.filter((candidate) => candidate.selected);
    if (!selected.length) {
      setError('请至少选择一个候选角色。');
      return;
    }
    if (selected.some((candidate) => !candidate.name.trim())) {
      setError('候选角色名称不能为空。');
      return;
    }
    if (scope === 'project' && projectId === null) {
      setError('请选择目标工程。');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await applyCharacterExtraction({
        preview_token: previewToken,
        candidates: candidates.map((candidate) => ({
          ...candidate,
          confirmed_tags: candidate.confirmed_tags ?? [],
        })),
        selected_candidate_ids: selected.map((candidate) => candidate.candidate_id),
        scope,
        project_id: scope === 'project' ? projectId : null,
        category_ids: scope === 'public' ? categoryIds : [],
      });
      const ids = result.created.flatMap((item) => item.card_id === null ? [] : [item.card_id]);
      if (result.errors.length || ids.length !== selected.length) {
        setError(
          result.errors.map((item) => item.error).filter(Boolean).join('；')
          || '角色创建未全部成功，请修改候选后重试。',
        );
        return;
      }
      setResultMessage(`已创建 ${ids.length} 个角色。`);
      onCreated(ids, scope, scope === 'project' ? projectId : null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function updateCandidate(candidateId: string, patch: Partial<CharacterExtractionCandidate>) {
    setCandidates((current) => current.map((candidate) => (
      candidate.candidate_id === candidateId ? { ...candidate, ...patch } : candidate
    )));
  }

  return (
    <LibraryDialog
      bodyClassName="character-create-dialog-body"
      className="character-create-dialog"
      footer={(
        <>
          <SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton>
          {mode === 'manual' ? (
            <PrimaryButton disabled={busy} onClick={onManual}><Plus size={15} />进入手动编辑</PrimaryButton>
          ) : previewToken ? (
            <PrimaryButton disabled={busy} onClick={() => void applyPreview()}><Check size={15} />确认创建</PrimaryButton>
          ) : (
            <PrimaryButton disabled={busy || !text.trim()} onClick={() => void generatePreview()}>生成候选角色</PrimaryButton>
          )}
        </>
      )}
      onClose={onClose}
      subtitle="统一新建入口"
      title="新建角色"
    >
      <div className="character-create-tabs" role="tablist">
        <button aria-selected={mode === 'manual'} onClick={() => setMode('manual')} role="tab" type="button">手动创建</button>
        <button aria-selected={mode === 'extract'} onClick={() => setMode('extract')} role="tab" type="button">从文本提取</button>
      </div>
      {error ? <div className="inline-alert error" role="alert">{error}</div> : null}
      {resultMessage ? <div className="inline-alert success">{resultMessage}</div> : null}
      {mode === 'manual' ? (
        <div className="character-mode-intro">
          <Plus size={22} />
          <strong>直接填写角色资料</strong>
          <p>不调用 AI，也不依赖模型配置。手动创建的角色默认标记为“未分析”。</p>
        </div>
      ) : (
        <>
          {!previewToken ? (
            <div className="character-extract-source">
              <div className="character-source-options" aria-label="来源方式">
                <span className="selected"><FileText size={14} />粘贴文本</span>
                <label>
                  <FileText size={14} />文件
                  <input
                    accept=".txt,.md,text/plain,text/markdown"
                    hidden
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) void file.text().then((value) => {
                        if (value.length > 50000) {
                          setError('来源文本不能超过 50,000 字符。');
                          return;
                        }
                        setText(value);
                      });
                    }}
                    type="file"
                  />
                </label>
                {initialLaunch ? <span className="selected">文档选区</span> : null}
              </div>
              <label><span>目标角色名（可选）</span><input onChange={(event) => setTargetName(event.target.value)} placeholder="留空时提取所有证据充分的人物" value={targetName} /></label>
              <label><span>来源文本</span><textarea maxLength={50000} onChange={(event) => setText(event.target.value)} rows={10} value={text} /></label>
              <ScopeFields
                categoryIds={categoryIds}
                categories={categories}
                projectId={projectId}
                projects={projects}
                scope={scope}
                setCategoryIds={setCategoryIds}
                setProjectId={setProjectId}
                setScope={setScope}
              />
            </div>
          ) : (
            <div className="character-candidate-list">
              <header><strong>候选角色</strong><span>确认前不会写入角色库；标签建议也需逐个确认。</span></header>
              <div className="inline-alert" role="status">来源：{sourceSummaryLabel}</div>
              {candidates.map((candidate) => (
                <CandidateEditor
                  candidate={candidate}
                  key={candidate.candidate_id}
                  onChange={(patch) => updateCandidate(candidate.candidate_id, patch)}
                  tags={tags}
                />
              ))}
              <ScopeFields
                categoryIds={categoryIds}
                categories={categories}
                projectId={projectId}
                projects={projects}
                scope={scope}
                setCategoryIds={setCategoryIds}
                setProjectId={setProjectId}
                setScope={setScope}
              />
              <SecondaryButton onClick={() => { setPreviewToken(''); setCandidates([]); }}>返回修改来源文本</SecondaryButton>
            </div>
          )}
        </>
      )}
    </LibraryDialog>
  );
}

function CandidateEditor({
  candidate,
  onChange,
  tags,
}: {
  candidate: CharacterExtractionCandidate;
  onChange: (patch: Partial<CharacterExtractionCandidate>) => void;
  tags: ResourceTag[];
}) {
  const [newTag, setNewTag] = useState('');
  const confirmed = candidate.confirmed_tags ?? [];
  const tagOptions = useMemo(
    () => Array.from(new Set([...candidate.suggested_tags, ...tags.map((tag) => tag.name)])),
    [candidate.suggested_tags, tags],
  );
  return (
    <article className={`character-candidate ${candidate.selected ? '' : 'disabled'}`}>
      <header>
        <label><input checked={candidate.selected} onChange={(event) => onChange({ selected: event.target.checked })} type="checkbox" />选择候选</label>
        <small>{candidate.evidence_summary || '模型未返回证据摘要'}</small>
      </header>
      <div className="character-candidate-fields">
        <label><span>角色名称</span><input onChange={(event) => onChange({ name: event.target.value })} value={candidate.name} /></label>
        <label><span>身份</span><input onChange={(event) => onChange({ identity: event.target.value })} value={candidate.identity} /></label>
        <label><span>年龄</span><input onChange={(event) => onChange({ age: event.target.value })} value={candidate.age} /></label>
        <label><span>别名</span><input onChange={(event) => onChange({ aliases: event.target.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) })} value={candidate.aliases.join('、')} /></label>
        <label className="wide"><span>简介</span><textarea onChange={(event) => onChange({ description: event.target.value })} rows={2} value={candidate.description} /></label>
        <label className="wide"><span>设定</span><textarea onChange={(event) => onChange({ setting_text: event.target.value })} rows={2} value={candidate.setting_text} /></label>
        <label className="wide"><span>人物关系</span><textarea onChange={(event) => onChange({ relationship_notes: event.target.value })} rows={2} value={candidate.relationship_notes} /></label>
        <label><span>性格</span><textarea onChange={(event) => onChange({ personality: event.target.value })} rows={2} value={candidate.personality} /></label>
        <label><span>语言风格</span><textarea onChange={(event) => onChange({ speech_style: event.target.value })} rows={2} value={candidate.speech_style} /></label>
        <label><span>动作约束</span><textarea onChange={(event) => onChange({ action_constraints: event.target.value })} rows={2} value={candidate.action_constraints} /></label>
        <label><span>反 OOC 规则</span><textarea onChange={(event) => onChange({ anti_ooc_rules: event.target.value })} rows={2} value={candidate.anti_ooc_rules} /></label>
      </div>
      <div className="candidate-tags">
        <span><Tag size={13} />确认标签</span>
        <div>
          {tagOptions.map((name) => {
            const active = confirmed.includes(name);
            return (
              <button
                aria-pressed={active}
                className={active ? 'selected' : ''}
                key={name}
                onClick={() => onChange({ confirmed_tags: active ? confirmed.filter((item) => item !== name) : [...confirmed, name] })}
                type="button"
              >
                {name}{active ? <X size={11} /> : <Plus size={11} />}
              </button>
            );
          })}
        </div>
        <div className="character-inline-create">
          <input maxLength={40} onChange={(event) => setNewTag(event.target.value)} placeholder="添加新标签" value={newTag} />
          <SecondaryButton
            disabled={!newTag.trim()}
            onClick={() => {
              const name = newTag.trim();
              if (!confirmed.some((item) => item.toLocaleLowerCase() === name.toLocaleLowerCase())) {
                onChange({ confirmed_tags: [...confirmed, name] });
              }
              setNewTag('');
            }}
          ><Plus size={13} />添加</SecondaryButton>
        </div>
      </div>
    </article>
  );
}

function ScopeFields({
  categories,
  categoryIds,
  projectId,
  projects,
  scope,
  setCategoryIds,
  setProjectId,
  setScope,
}: {
  categories: CharacterCategory[];
  categoryIds: number[];
  projectId: number | null;
  projects: CharacterProjectSummary[];
  scope: 'public' | 'project';
  setCategoryIds: (ids: number[]) => void;
  setProjectId: (id: number | null) => void;
  setScope: (scope: 'public' | 'project') => void;
}) {
  return (
    <fieldset className="character-extract-target">
      <legend>创建范围</legend>
      <label><input checked={scope === 'public'} onChange={() => setScope('public')} type="radio" />公共角色</label>
      <label><input checked={scope === 'project'} onChange={() => setScope('project')} type="radio" />工程角色</label>
      {scope === 'project' ? (
        <select onChange={(event) => setProjectId(event.target.value ? Number(event.target.value) : null)} value={projectId ?? ''}>
          <option value="">选择工程</option>
          {projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.project_name}</option>)}
        </select>
      ) : (
        <div className="candidate-tags">
          <span>我的分类（可选）</span>
          <div>{categories.map((category) => (
            <button
              aria-pressed={categoryIds.includes(category.id)}
              className={categoryIds.includes(category.id) ? 'selected' : ''}
              key={category.id}
              onClick={() => setCategoryIds(categoryIds.includes(category.id) ? categoryIds.filter((id) => id !== category.id) : [...categoryIds, category.id])}
              type="button"
            >{category.name}</button>
          ))}</div>
        </div>
      )}
    </fieldset>
  );
}

export function CharacterExtractionSettingsDialog({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<CharacterExtractionSettings | null>(null);
  const [models, setModels] = useState<Array<{ id: number; display_name: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void Promise.all([getCharacterExtractionSettings(), getModels()])
      .then(([value, modelItems]) => {
        setSettings(value);
        setModels(modelItems);
      })
      .catch((reason) => setError(errorMessage(reason)));
  }, []);

  async function save() {
    if (!settings) return;
    setBusy(true);
    try {
      const { prompt_preview: _preview, ...payload } = settings;
      setSettings(await updateCharacterExtractionSettings(payload));
      onClose();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function restore() {
    setBusy(true);
    try {
      setSettings(await resetCharacterExtractionSettings());
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const toggles: Array<[keyof CharacterExtractionSettings, string]> = [
    ['extract_all_characters', '提取全部人物'],
    ['generate_tags', '生成标签建议'],
    ['generate_appearance', '生成外貌信息'],
    ['generate_relationships', '生成人物关系'],
    ['generate_personality', '生成性格'],
    ['generate_speech_style', '生成语言风格'],
    ['generate_action_constraints', '生成动作约束'],
    ['generate_anti_ooc_rules', '生成反 OOC 规则'],
    ['generate_abilities_background', '生成能力与背景'],
  ];

  return (
    <LibraryDialog
      className="character-settings-dialog"
      footer={<><SecondaryButton disabled={busy} onClick={() => void restore()}>恢复默认值</SecondaryButton><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !settings} onClick={() => void save()}>保存设置</PrimaryButton></>}
      onClose={onClose}
      subtitle="持久化到本地数据库"
      title="角色提取设置"
    >
      {error ? <div className="inline-alert error">{error}</div> : null}
      {settings ? (
        <div className="character-settings-form">
          <label><span>默认模型</span><select onChange={(event) => setSettings({ ...settings, model_id: event.target.value ? Number(event.target.value) : null })} value={settings.model_id ?? ''}><option value="">使用系统默认模型</option>{models.map((model) => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select></label>
          <label><span>默认细化程度</span><select onChange={(event) => setSettings({ ...settings, detail_level: event.target.value as CharacterExtractionSettings['detail_level'] })} value={settings.detail_level}><option value="brief">brief</option><option value="standard">standard</option><option value="detailed">detailed</option></select></label>
          <label><span>最大候选角色数</span><input max={20} min={1} onChange={(event) => setSettings({ ...settings, max_candidates: Number(event.target.value) })} type="number" value={settings.max_candidates} /></label>
          <fieldset><legend><Settings2 size={14} />生成维度</legend>{toggles.map(([key, label]) => <label key={key}><input checked={Boolean(settings[key])} onChange={(event) => setSettings({ ...settings, [key]: event.target.checked })} type="checkbox" />{label}</label>)}</fieldset>
          <label className="wide"><span>自定义附加分析要求</span><textarea onChange={(event) => setSettings({ ...settings, custom_requirements: event.target.value })} rows={3} value={settings.custom_requirements} /></label>
          <label className="wide"><span>系统提示词（高级）</span><textarea onChange={(event) => setSettings({ ...settings, system_prompt: event.target.value })} rows={7} value={settings.system_prompt} /></label>
          <details className="wide"><summary>查看 Prompt 预览</summary><pre>{settings.prompt_preview}</pre></details>
        </div>
      ) : <p>正在读取设置…</p>}
    </LibraryDialog>
  );
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}
