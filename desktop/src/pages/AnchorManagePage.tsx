import { useEffect, useState } from 'react';
import { ChevronDown, Plus, Save, Search, Sparkles, Trash2, X } from 'lucide-react';
import {
  createCharacterCard,
  createOutlineTemplate,
  deleteCharacterCard,
  deleteOutlineTemplate,
  extractCharacterCards,
  extractOutlineTemplate,
  getCharacterCards,
  getLibraryDocuments,
  getOutlineTemplates,
  getProjects,
  updateCharacterCard,
  updateOutlineTemplate,
} from '../api/client';
import type { CharacterCard, CharacterCardWrite, LibraryDocument, OutlineTemplate, OutlineTemplateWrite, Project, StyleDetailLevel } from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { EmptyState } from '../components/EmptyState';
import { SurfaceCard } from '../components/SurfaceCard';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { StatusPill } from '../components/StatusPill';
import { TopBar } from '../components/TopBar';

const emptyOutline: OutlineTemplateWrite = {
  name: '',
  description: '',
  detail_level: 'standard',
  outline: {},
  anchor_prompt: '',
  source_metadata: {},
  import_metadata: {},
};

const emptyCharacter: CharacterCardWrite = {
  name: '',
  aliases: [],
  description: '',
  priority: 50,
  is_main: false,
  relationship_notes: '',
  personality: '',
  speech_style: '',
  action_constraints: '',
  anti_ooc_rules: '',
  profile: {},
  source_metadata: {},
  import_metadata: {},
};

type AnchorSection = 'outlines' | 'characters';
type Props = {
  section: AnchorSection;
  onNavigate: (path: string) => void;
};
type CharacterField = 'description' | 'relationship_notes' | 'personality' | 'speech_style' | 'action_constraints' | 'anti_ooc_rules';

const characterTabs: Array<[string, CharacterField]> = [
  ['描述', 'description'],
  ['关系', 'relationship_notes'],
  ['性格', 'personality'],
  ['语气', 'speech_style'],
  ['动作约束', 'action_constraints'],
  ['防 OOC', 'anti_ooc_rules'],
];

export function AnchorManagePage({ onNavigate, section }: Props) {
  const [outlines, setOutlines] = useState<OutlineTemplate[]>([]);
  const [characters, setCharacters] = useState<CharacterCard[]>([]);
  const [selectedOutlineId, setSelectedOutlineId] = useState<number | null>(null);
  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(null);
  const [outlineForm, setOutlineForm] = useState<OutlineTemplateWrite>(emptyOutline);
  const [outlineText, setOutlineText] = useState('{}');
  const [characterForm, setCharacterForm] = useState<CharacterCardWrite>(emptyCharacter);
  const [characterAliases, setCharacterAliases] = useState('');
  const [characterProfileText, setCharacterProfileText] = useState('{}');
  const [characterField, setCharacterField] = useState<CharacterField>('description');
  const [extractMode, setExtractMode] = useState<'paste' | 'project' | 'document'>('paste');
  const [extractName, setExtractName] = useState('');
  const [extractDetailLevel, setExtractDetailLevel] = useState<StyleDetailLevel>('standard');
  const [extractSampleText, setExtractSampleText] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [characterScope, setCharacterScope] = useState<'public' | 'project'>('public');
  const [characterProjectId, setCharacterProjectId] = useState<number | null>(null);
  const [extractSourceProjectId, setExtractSourceProjectId] = useState<number | null>(null);
  const [extractSourceDocumentId, setExtractSourceDocumentId] = useState<number | null>(null);
  const [characterSearch, setCharacterSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [extractOpen, setExtractOpen] = useState(false);

  function fillOutline(template: OutlineTemplate) {
    setOutlineForm({
      name: template.name,
      description: template.description,
      detail_level: template.detail_level,
      outline: template.outline,
      anchor_prompt: template.anchor_prompt,
      source_metadata: template.source_metadata,
      import_metadata: template.import_metadata,
    });
    setOutlineText(JSON.stringify(template.outline, null, 2));
  }

  function fillCharacter(card: CharacterCard) {
    setCharacterForm({
      name: card.name,
      aliases: card.aliases,
      description: card.description,
      priority: card.priority,
      is_main: card.is_main,
      relationship_notes: card.relationship_notes,
      personality: card.personality,
      speech_style: card.speech_style,
      action_constraints: card.action_constraints,
      anti_ooc_rules: card.anti_ooc_rules,
      profile: card.profile,
      source_metadata: card.source_metadata,
      import_metadata: card.import_metadata,
    });
    setCharacterAliases(card.aliases.join(', '));
    setCharacterProfileText(JSON.stringify(card.profile, null, 2));
  }

  async function loadAnchors(nextOutlineId?: number | null, nextCharacterId?: number | null) {
    setError(null);
    try {
      const [outlineItems, projectItems, documentItems] = await Promise.all([
        getOutlineTemplates(),
        getProjects(),
        getLibraryDocuments(),
      ]);
      const nextProjectId = characterProjectId ?? projectItems[0]?.id ?? null;
      const characterItems = await getCharacterCards(
        characterScope,
        characterScope === 'project' ? nextProjectId : null,
      );
      setOutlines(outlineItems);
      setCharacters(characterItems);
      setProjects(projectItems);
      setDocuments(documentItems);
      setCharacterProjectId(nextProjectId);
      setExtractSourceProjectId((current) => current ?? nextProjectId);
      setExtractSourceDocumentId((current) => current ?? documentItems[0]?.id ?? null);

      const outlineId = nextOutlineId ?? selectedOutlineId ?? outlineItems[0]?.id ?? null;
      setSelectedOutlineId(outlineId);
      const selectedOutline = outlineItems.find((item) => item.id === outlineId);
      if (selectedOutline) fillOutline(selectedOutline);

      const characterId = nextCharacterId ?? selectedCharacterId ?? characterItems[0]?.id ?? null;
      setSelectedCharacterId(characterId);
      const selectedCharacter = characterItems.find((item) => item.id === characterId);
      if (selectedCharacter) fillCharacter(selectedCharacter);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    loadAnchors(null, null);
  }, [characterScope, characterProjectId]);

  function newOutline() {
    setSelectedOutlineId(null);
    setOutlineForm(emptyOutline);
    setOutlineText('{}');
    setMessage(null);
  }

  function newCharacter() {
    setSelectedCharacterId(null);
    setCharacterForm(emptyCharacter);
    setCharacterAliases('');
    setCharacterProfileText('{}');
    setMessage(null);
  }

  async function saveOutline() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const parsed = parseJsonObject(outlineText, '大纲 JSON');
      const payload = { ...outlineForm, outline: parsed };
      const saved = selectedOutlineId ? await updateOutlineTemplate(selectedOutlineId, payload) : await createOutlineTemplate(payload);
      setMessage('大纲模板已保存。');
      await loadAnchors(saved.id, selectedCharacterId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeOutline() {
    if (!selectedOutlineId || !window.confirm('确认删除当前大纲模板？')) return;
    setBusy(true);
    setError(null);
    try {
      await deleteOutlineTemplate(selectedOutlineId);
      setMessage('大纲模板已删除。');
      setSelectedOutlineId(null);
      setOutlineForm(emptyOutline);
      await loadAnchors(null, selectedCharacterId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveCharacter() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const profile = parseJsonObject(characterProfileText, '角色结构 JSON');
      const aliases = characterAliases
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      const payload = {
        ...characterForm,
        aliases,
        profile,
        scope: characterScope,
        project_id: characterScope === 'project' ? characterProjectId : null,
      };
      const saved = selectedCharacterId ? await updateCharacterCard(selectedCharacterId, payload) : await createCharacterCard(payload);
      setMessage('角色卡已保存。');
      await loadAnchors(selectedOutlineId, saved.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeCharacter() {
    if (!selectedCharacterId || !window.confirm('确认删除当前角色卡？')) return;
    setBusy(true);
    setError(null);
    try {
      await deleteCharacterCard(selectedCharacterId);
      setMessage('角色卡已删除。');
      setSelectedCharacterId(null);
      setCharacterForm(emptyCharacter);
      await loadAnchors(selectedOutlineId, null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function extractOutline() {
    if (!extractName.trim()) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const outline = await extractOutlineTemplate({
        name: extractName,
        detail_level: extractDetailLevel,
        sample_text: extractMode === 'paste' ? extractSampleText : null,
        source_path: null,
      });
      setMessage('AI 大纲模板已生成。');
      setExtractSampleText('');
      await loadAnchors(outline.id, selectedCharacterId);
      setExtractOpen(false);
      onNavigate('/outlines');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function extractCharacters() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await extractCharacterCards({
        name: extractName || null,
        detail_level: extractDetailLevel,
        sample_text: extractMode === 'paste' ? extractSampleText : null,
        source_project_id: extractMode === 'project' ? extractSourceProjectId : null,
        source_document_id: extractMode === 'document' ? extractSourceDocumentId : null,
        scope: characterScope,
        project_id: characterScope === 'project' ? characterProjectId : null,
      });
      const first = result.character_cards[0];
      setMessage(`AI 角色卡已生成：${result.character_cards.length} 张。`);
      setExtractSampleText('');
      await loadAnchors(selectedOutlineId, first?.id ?? selectedCharacterId);
      setExtractOpen(false);
      onNavigate('/characters');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="anchor-manage-page">
      <TopBar
        actions={(
          <PrimaryButton onClick={() => {
            setError(null);
            setMessage(null);
            setExtractOpen(true);
          }}>
            <Sparkles size={16} />
            AI 抽取
          </PrimaryButton>
        )}
        title={section === 'outlines' ? '剧情大纲' : '角色卡'}
      />
      {error && <SurfaceCard className="mb-5 border-rose-300/25 text-rose-100">后端错误：{error}</SurfaceCard>}
      {message && <SurfaceCard className="mb-5 border-emerald-300/25 text-emerald-100">{message}</SurfaceCard>}

      {extractOpen ? (
        <div
          className="anchor-extract-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target && !busy) setExtractOpen(false);
          }}
          role="presentation"
        >
          <section aria-labelledby="anchor-extract-title" aria-modal="true" className="anchor-extract-dialog" role="dialog">
            <header>
              <div>
                <span>AI EXTRACTION</span>
                <h2 id="anchor-extract-title">{section === 'outlines' ? 'AI 抽取剧情大纲' : 'AI 抽取角色卡'}</h2>
              </div>
              <button aria-label="关闭 AI 抽取窗口" className="icon-button" disabled={busy} onClick={() => setExtractOpen(false)} type="button">
                <X size={18} />
              </button>
            </header>

            {error ? <div className="inline-alert error">后端错误：{error}</div> : null}
            <div className="anchor-extract-fields">
              <label>
                <span className="form-label">{section === 'outlines' ? '大纲模板名' : '角色卡名称（可留空）'}</span>
                <input autoFocus className="form-input" value={extractName} onChange={(event) => setExtractName(event.target.value)} />
              </label>
              <label>
                <span className="form-label">细节等级</span>
                <select className="form-input" value={extractDetailLevel} onChange={(event) => setExtractDetailLevel(event.target.value as StyleDetailLevel)}>
                  <option value="brief">brief</option>
                  <option value="standard">standard</option>
                  <option value="detailed">detailed</option>
                </select>
              </label>
              <label>
                <span className="form-label">来源</span>
                <select className="form-input" value={extractMode} onChange={(event) => setExtractMode(event.target.value as 'paste' | 'project' | 'document')}>
                  <option value="paste">粘贴文本</option>
                  <option value="project">工程内容</option>
                  <option value="document">文档库</option>
                </select>
              </label>
            </div>

            {extractMode === 'paste' ? (
              <textarea
                className="anchor-extract-textarea"
                placeholder={section === 'outlines' ? '粘贴用于抽取剧情大纲的样本文字。' : '粘贴用于抽取角色卡的样本文字。'}
                value={extractSampleText}
                onChange={(event) => setExtractSampleText(event.target.value)}
              />
            ) : extractMode === 'project' ? (
              <select className="form-input" value={extractSourceProjectId ?? ''} onChange={(event) => setExtractSourceProjectId(Number(event.target.value) || null)}>
                {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
              </select>
            ) : (
              <select className="form-input" value={extractSourceDocumentId ?? ''} onChange={(event) => setExtractSourceDocumentId(Number(event.target.value) || null)}>
                {documents.map((document) => <option key={document.id} value={document.id}>{document.title}</option>)}
              </select>
            )}

            <footer>
              <SecondaryButton disabled={busy} onClick={() => setExtractOpen(false)}>取消</SecondaryButton>
              {section === 'outlines' ? (
                <PrimaryButton
                  disabled={busy || !extractName.trim() || (extractMode === 'paste' ? !extractSampleText.trim() : false)}
                  onClick={extractOutline}
                >
                  <Sparkles size={16} />
                  生成大纲模板
                </PrimaryButton>
              ) : (
                <PrimaryButton disabled={busy || (extractMode === 'paste' ? !extractSampleText.trim() : extractMode === 'project' ? extractSourceProjectId === null : extractSourceDocumentId === null)} onClick={extractCharacters}>
                  <Sparkles size={16} />
                  生成角色卡
                </PrimaryButton>
              )}
            </footer>
          </section>
        </div>
      ) : null}

      {section === 'outlines' ? (
        <div className="grid grid-cols-[360px_1fr] gap-5 max-lg:grid-cols-1">
          <SurfaceCard title="大纲列表">
            <SecondaryButton className="mb-4 w-full" onClick={newOutline}>
              <Plus size={16} />
              新建大纲模板
            </SecondaryButton>
            {outlines.length === 0 ? (
              <EmptyState title="尚未创建大纲模板" description="先录入固定剧情节点，再在工程中绑定。" />
            ) : (
              <div className="space-y-3">
                {outlines.map((template) => (
                  <button
                    className={`w-full cursor-pointer rounded-2xl border p-4 text-left transition ${selectedOutlineId === template.id ? 'border-sky-300/30 bg-sky-300/12' : 'border-white/10 bg-white/[0.04] hover:bg-white/[0.08]'}`}
                    key={template.id}
                    onClick={() => {
                      setSelectedOutlineId(template.id);
                      fillOutline(template);
                    }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-white">{template.name}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">{template.description || '无描述'}</p>
                      </div>
                      <StatusPill variant="info">{template.detail_level}</StatusPill>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </SurfaceCard>

          <SurfaceCard title={selectedOutlineId ? '编辑大纲模板' : '新建大纲模板'}>
            <div className="mb-4 grid grid-cols-[1fr_180px] gap-3 max-md:grid-cols-1">
              <label>
                <span className="form-label">名称</span>
                <input className="form-input" value={outlineForm.name} onChange={(event) => setOutlineForm({ ...outlineForm, name: event.target.value })} />
              </label>
              <label>
                <span className="form-label">细节等级</span>
                <select className="form-input" value={outlineForm.detail_level} onChange={(event) => setOutlineForm({ ...outlineForm, detail_level: event.target.value as StyleDetailLevel })}>
                  <option value="brief">brief</option>
                  <option value="standard">standard</option>
                  <option value="detailed">detailed</option>
                </select>
              </label>
            </div>
            <label>
              <span className="form-label">描述</span>
              <input className="form-input" value={outlineForm.description} onChange={(event) => setOutlineForm({ ...outlineForm, description: event.target.value })} />
            </label>
            <div className="mt-4 grid grid-cols-2 gap-4 max-xl:grid-cols-1">
              <label>
                <span className="form-label">剧情锚点提示词</span>
                <textarea className="chapter-text min-h-[360px] w-full resize-y rounded-3xl border border-white/10 bg-slate-950/35 p-5 text-sm leading-7 text-slate-100 outline-none" value={outlineForm.anchor_prompt} onChange={(event) => setOutlineForm({ ...outlineForm, anchor_prompt: event.target.value })} />
              </label>
              <label>
                <span className="form-label">结构化大纲 JSON</span>
                <textarea className="chapter-text min-h-[360px] w-full resize-y rounded-3xl border border-white/10 bg-slate-950/35 p-5 font-mono text-xs leading-6 text-slate-100 outline-none" value={outlineText} onChange={(event) => setOutlineText(event.target.value)} />
              </label>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <PrimaryButton disabled={busy} onClick={saveOutline}>
                <Save size={16} />
                保存
              </PrimaryButton>
              <DangerButton disabled={busy || !selectedOutlineId} onClick={removeOutline}>
                <Trash2 size={16} />
                删除
              </DangerButton>
            </div>
          </SurfaceCard>
        </div>
      ) : (
        <div className="character-library-workspace">
          <div className="character-library-command">
            <div className="material-scope-switch" role="tablist" aria-label="角色卡作用域">
              <button className={characterScope === 'public' ? 'selected' : ''} onClick={() => setCharacterScope('public')} role="tab" type="button">公共角色</button>
              <button className={characterScope === 'project' ? 'selected' : ''} onClick={() => setCharacterScope('project')} role="tab" type="button">工程角色</button>
            </div>
            {characterScope === 'project' ? (
              <label className="material-project-select">
                <select value={characterProjectId ?? ''} onChange={(event) => setCharacterProjectId(Number(event.target.value) || null)}>
                  {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                </select>
                <ChevronDown size={14} />
              </label>
            ) : null}
            <label className="search-field character-search">
              <Search size={15} /><input placeholder="搜索角色名、别名或描述" type="search" value={characterSearch} onChange={(event) => setCharacterSearch(event.target.value)} />
            </label>
            <SecondaryButton onClick={newCharacter}><Plus size={16} />新建角色卡</SecondaryButton>
          </div>
          <div className="character-library-layout">
          <SurfaceCard title={`${characterScope === 'public' ? '公共角色' : '工程角色'} · ${characters.length} 张`}>
            {characters.length === 0 ? (
              <EmptyState title="尚未创建角色卡" description="角色卡可绑定到项目，改写时按出现角色自动注入。" />
            ) : (
              <div className="character-card-grid">
                {characters.filter((card) => {
                  const query = characterSearch.trim().toLocaleLowerCase();
                  return !query || `${card.name} ${card.aliases.join(' ')} ${card.description}`.toLocaleLowerCase().includes(query);
                }).map((card) => (
                  <button
                    className={`character-library-card ${selectedCharacterId === card.id ? 'selected' : ''}`}
                    key={card.id}
                    onClick={() => {
                      setSelectedCharacterId(card.id);
                      fillCharacter(card);
                    }}
                  >
                    <div className="character-card-heading">
                      <div><strong>{card.name}</strong><span>{card.aliases.join('、') || '无别名'}</span></div>
                      <StatusPill variant={card.is_main || card.priority >= 80 ? 'warning' : 'info'}>{card.priority}</StatusPill>
                    </div>
                    <p>{card.description || card.personality || '尚未填写角色描述。'}</p>
                    <div className="character-card-meta"><span>{card.is_main ? '主角 / 常驻' : '普通角色'}</span><span>v{card.version}</span></div>
                  </button>
                ))}
              </div>
            )}
          </SurfaceCard>

          <SurfaceCard title={selectedCharacterId ? '编辑角色卡' : '新建角色卡'}>
            <div className="mb-4 grid grid-cols-[1fr_1fr_130px] gap-3 max-xl:grid-cols-1">
              <label>
                <span className="form-label">角色名</span>
                <input className="form-input" value={characterForm.name} onChange={(event) => setCharacterForm({ ...characterForm, name: event.target.value })} />
              </label>
              <label>
                <span className="form-label">别名，逗号分隔</span>
                <input className="form-input" value={characterAliases} onChange={(event) => setCharacterAliases(event.target.value)} />
              </label>
              <label>
                <span className="form-label">优先级</span>
                <input className="form-input" min={0} max={100} type="number" value={characterForm.priority} onChange={(event) => setCharacterForm({ ...characterForm, priority: Number(event.target.value) || 0 })} />
              </label>
            </div>
            <label className="mb-4 flex items-center gap-3 text-sm text-[var(--text-muted)]">
              <input checked={characterForm.is_main} onChange={(event) => setCharacterForm({ ...characterForm, is_main: event.target.checked })} type="checkbox" />
              主角或常驻角色，改写时默认注入
            </label>
            <div className="mb-4 flex flex-wrap gap-2">
              {characterTabs.map(([label, key]) => (
                <button className={tabButtonClass(characterField === key)} key={key} onClick={() => setCharacterField(key)}>
                  {label}
                </button>
              ))}
            </div>
            <textarea
              className="chapter-text min-h-[260px] w-full resize-y rounded-3xl border border-white/10 bg-slate-950/35 p-5 text-sm leading-7 text-slate-100 outline-none"
              value={characterForm[characterField]}
              onChange={(event) => setCharacterForm({ ...characterForm, [characterField]: event.target.value })}
            />
            <label className="mt-4 block">
              <span className="form-label">结构化角色 JSON</span>
              <textarea className="chapter-text min-h-[180px] w-full resize-y rounded-3xl border border-white/10 bg-slate-950/35 p-5 font-mono text-xs leading-6 text-slate-100 outline-none" value={characterProfileText} onChange={(event) => setCharacterProfileText(event.target.value)} />
            </label>
            <div className="mt-6 flex flex-wrap gap-3">
              <PrimaryButton disabled={busy} onClick={saveCharacter}>
                <Save size={16} />
                保存
              </PrimaryButton>
              <DangerButton disabled={busy || !selectedCharacterId} onClick={removeCharacter}>
                <Trash2 size={16} />
                删除
              </DangerButton>
            </div>
          </SurfaceCard>
          </div>
        </div>
      )}
    </div>
  );
}

function parseJsonObject(text: string, label: string): Record<string, unknown> {
  const value = text.trim() ? JSON.parse(text) : {};
  if (!value || Array.isArray(value) || typeof value !== 'object') {
    throw new Error(`${label} 必须是对象。`);
  }
  return value as Record<string, unknown>;
}

function tabButtonClass(active: boolean) {
  return `rounded-full border px-3 py-1 text-xs ${active ? 'border-sky-300/30 bg-sky-300/15 text-white' : 'border-white/10 bg-white/5 text-[var(--text-muted)]'}`;
}
