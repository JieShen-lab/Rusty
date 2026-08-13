import { useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import {
  getCharacterExtractionSettings,
  getModels,
  previewCharacterExtraction,
  resetCharacterExtractionSettings,
  updateCharacterExtractionSettings,
} from '../api/client';
import type {
  CharacterDimensionDefinition,
  CharacterDraft,
  CharacterExtractionSettings,
  ModelConfig,
} from '../api/types';
import { LibraryDialog } from './LibraryPrimitives';
import { PrimaryButton } from './PrimaryButton';
import { SecondaryButton } from './SecondaryButton';

export type CharacterExtractionLaunch = {
  selectedText: string;
  sourceMetadata?: Record<string, unknown>;
};

export function CharacterAIExtractionDialog({
  initialLaunch,
  onClose,
  onDraft,
}: {
  initialLaunch?: CharacterExtractionLaunch | null;
  onClose: () => void;
  onDraft: (draft: CharacterDraft) => void;
}) {
  const [name, setName] = useState('');
  const [sourceText, setSourceText] = useState(initialLaunch?.selectedText ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function extract() {
    if (!name.trim() || !sourceText.trim()) return;
    setBusy(true);
    setError('');
    try {
      const preview = await previewCharacterExtraction({
        target_character_name: name.trim(),
        source_text: sourceText,
        source_metadata: initialLaunch?.sourceMetadata ?? { source_type: 'paste' },
      });
      onDraft(preview.character);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <LibraryDialog
      className="character-ai-dialog"
      footer={<><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !name.trim() || !sourceText.trim()} onClick={() => void extract()}>开始提取</PrimaryButton></>}
      onClose={onClose}
      subtitle="一次只提取一个明确指定的人物"
      title="AI 新建角色"
    >
      {error ? <div className="inline-alert error" role="alert">{error}</div> : null}
      <div className="character-ai-form">
        <label><span>角色名称 *</span><input autoFocus maxLength={120} onChange={(event) => setName(event.target.value)} placeholder="例如：林彻" value={name} /></label>
        <label><span>来源文本</span><textarea onChange={(event) => setSourceText(event.target.value)} rows={14} value={sourceText} /></label>
      </div>
    </LibraryDialog>
  );
}

export function CharacterExtractionSettingsDialog({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<CharacterExtractionSettings | null>(null);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [systemPromptOpen, setSystemPromptOpen] = useState(false);
  const [newDimensionOpen, setNewDimensionOpen] = useState(false);

  useEffect(() => {
    void Promise.all([getCharacterExtractionSettings(), getModels()])
      .then(([value, modelItems]) => { setSettings(value); setModels(modelItems); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const payload = useMemo(() => settings ? {
    model_id: settings.model_id,
    detail_level: settings.detail_level,
    generate_tags: settings.generate_tags,
    custom_requirements: settings.custom_requirements,
    system_prompt: settings.system_prompt,
    dimensions: settings.dimensions,
  } : null, [settings]);

  async function save() {
    if (!payload) return;
    setBusy(true);
    setError('');
    try { setSettings(await updateCharacterExtractionSettings(payload)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  function updateDimension(index: number, patch: Partial<CharacterDimensionDefinition>) {
    if (!settings) return;
    setSettings({ ...settings, dimensions: settings.dimensions.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) });
  }

  function moveDimension(index: number, offset: number) {
    if (!settings) return;
    const target = index + offset;
    if (target < 0 || target >= settings.dimensions.length) return;
    const dimensions = [...settings.dimensions];
    [dimensions[index], dimensions[target]] = [dimensions[target], dimensions[index]];
    setSettings({ ...settings, dimensions: dimensions.map((item, sort_order) => ({ ...item, sort_order })) });
  }

  return (
    <>
      <LibraryDialog
        className="character-settings-dialog"
        footer={<><SecondaryButton disabled={busy} onClick={async () => setSettings(await resetCharacterExtractionSettings())}>恢复默认</SecondaryButton><SecondaryButton disabled={busy} onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={busy || !settings} onClick={() => void save()}>保存设置</PrimaryButton></>}
        onClose={onClose}
        title="角色提取设置"
      >
        {error ? <div className="inline-alert error" role="alert">{error}</div> : null}
        {settings ? <div className="character-settings-content">
          <div className="character-settings-topline">
            <label><span>默认模型</span><select onChange={(event) => setSettings({ ...settings, model_id: event.target.value ? Number(event.target.value) : null })} value={settings.model_id ?? ''}><option value="">系统默认模型</option>{models.map((model) => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select></label>
            <label><span>默认细化程度</span><select onChange={(event) => setSettings({ ...settings, detail_level: event.target.value as CharacterExtractionSettings['detail_level'] })} value={settings.detail_level}><option value="brief">brief</option><option value="standard">standard</option><option value="detailed">detailed</option></select></label>
            <div className="character-system-prompt-control"><span>系统提示词</span><SecondaryButton onClick={() => setSystemPromptOpen(true)}>编辑</SecondaryButton></div>
          </div>
          <section className="character-settings-section">
            <div className="character-section-heading"><h3>生成维度</h3><SecondaryButton onClick={() => setNewDimensionOpen(true)}><Plus size={14} />添加维度</SecondaryButton></div>
            <div className="character-dimension-list">{settings.dimensions.map((dimension, index) => <div className={`character-dimension-row ${dimension.enabled ? '' : 'disabled'}`} key={dimension.id}>
              <label className="character-dimension-toggle"><input checked={dimension.enabled} onChange={(event) => updateDimension(index, { enabled: event.target.checked })} type="checkbox" /><span>{dimension.label}</span></label>
              <small>{dimension.instruction || '无附加提取说明'}</small>
              <button aria-label="上移维度" disabled={index === 0} onClick={() => moveDimension(index, -1)} type="button"><ArrowUp size={14} /></button>
              <button aria-label="下移维度" disabled={index === settings.dimensions.length - 1} onClick={() => moveDimension(index, 1)} type="button"><ArrowDown size={14} /></button>
              {!dimension.is_default ? <button aria-label="删除维度" className="danger" onClick={() => setSettings({ ...settings, dimensions: settings.dimensions.filter((_, itemIndex) => itemIndex !== index) })} type="button"><Trash2 size={14} /></button> : <span className="character-dimension-default">默认</span>}
            </div>)}</div>
          </section>
          <label className="dialog-stacked-field"><span>自定义附加分析要求</span><textarea onChange={(event) => setSettings({ ...settings, custom_requirements: event.target.value })} rows={4} value={settings.custom_requirements} /></label>
          <details className="character-prompt-preview"><summary>查看 Prompt 预览</summary><pre>{settings.prompt_preview}</pre></details>
        </div> : <p>正在读取设置…</p>}
      </LibraryDialog>
      {systemPromptOpen && settings ? <SystemPromptDialog onClose={() => setSystemPromptOpen(false)} onSave={(system_prompt) => { setSettings({ ...settings, system_prompt }); setSystemPromptOpen(false); }} value={settings.system_prompt} /> : null}
      {newDimensionOpen && settings ? <NewDimensionDialog onClose={() => setNewDimensionOpen(false)} onSave={(dimension) => { setSettings({ ...settings, dimensions: [...settings.dimensions, dimension] }); setNewDimensionOpen(false); }} sortOrder={settings.dimensions.length} /> : null}
    </>
  );
}

function SystemPromptDialog({ onClose, onSave, value }: { onClose: () => void; onSave: (value: string) => void; value: string }) {
  const [draft, setDraft] = useState(value);
  return <LibraryDialog footer={<><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={!draft.trim()} onClick={() => onSave(draft)}>保存</PrimaryButton></>} onClose={onClose} title="编辑系统提示词"><textarea className="character-system-prompt-editor" onChange={(event) => setDraft(event.target.value)} rows={16} value={draft} /></LibraryDialog>;
}

function NewDimensionDialog({ onClose, onSave, sortOrder }: { onClose: () => void; onSave: (value: CharacterDimensionDefinition) => void; sortOrder: number }) {
  const [label, setLabel] = useState('');
  const [instruction, setInstruction] = useState('');
  return <LibraryDialog footer={<><SecondaryButton onClick={onClose}>取消</SecondaryButton><PrimaryButton disabled={!label.trim()} onClick={() => onSave({ id: `custom_${crypto.randomUUID()}`, label: label.trim(), instruction: instruction.trim(), sort_order: sortOrder, enabled: true, is_default: false })}>添加</PrimaryButton></>} onClose={onClose} title="添加生成维度"><div className="character-ai-form"><label><span>维度名称</span><input autoFocus onChange={(event) => setLabel(event.target.value)} placeholder="例如：宗教信仰" value={label} /></label><label><span>提取说明</span><textarea onChange={(event) => setInstruction(event.target.value)} placeholder="只提取原文明确体现的信息；没有证据时留空。" rows={6} value={instruction} /></label></div></LibraryDialog>;
}
