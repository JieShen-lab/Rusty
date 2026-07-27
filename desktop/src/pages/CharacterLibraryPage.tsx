import { useEffect, useMemo, useState } from 'react';
import {
  ArrowRightLeft,
  ChevronDown,
  Copy,
  FolderOpen,
  Pencil,
  Plus,
  Save,
  Search,
  Sparkles,
  Trash2,
  Upload,
  UserRound,
  Users,
  X,
} from 'lucide-react';
import {
  copyCharacterCard,
  createCharacterCard,
  deleteCharacterCard,
  extractCharacterCards,
  getCharacterCards,
  getLibraryDocuments,
  getProjects,
  importCharacterCard,
  updateCharacterCard,
} from '../api/client';
import type {
  CharacterCard,
  CharacterCardWrite,
  LibraryDocument,
  Project,
  StyleDetailLevel,
} from '../api/types';
import { DangerButton } from '../components/DangerButton';
import { EmptyState } from '../components/EmptyState';
import { PrimaryButton } from '../components/PrimaryButton';
import { SecondaryButton } from '../components/SecondaryButton';
import { TopBar } from '../components/TopBar';
import { useAutoDismiss } from '../hooks/useAutoDismiss';

type Scope = 'public' | 'project';
type SourceMode = 'paste' | 'project' | 'document';
type ProfileEntry = { key: string; value: string };

const EMPTY_FORM: CharacterCardWrite = {
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

const FIELD_SECTIONS: Array<{
  key: keyof Pick<
    CharacterCardWrite,
    'description' | 'relationship_notes' | 'personality' | 'speech_style' | 'action_constraints' | 'anti_ooc_rules'
  >;
  label: string;
  placeholder: string;
}> = [
  { key: 'description', label: '人物描述', placeholder: '身份、外貌、经历和当前处境。' },
  { key: 'relationship_notes', label: '关系', placeholder: '与其他角色的关系、立场与变化。' },
  { key: 'personality', label: '性格', placeholder: '核心性格、情绪触发点、价值取向。' },
  { key: 'speech_style', label: '语言风格', placeholder: '措辞、语气、口头禅与表达习惯。' },
  { key: 'action_constraints', label: '动作约束', placeholder: '擅长或避免的行为、战斗和决策方式。' },
  { key: 'anti_ooc_rules', label: '防 OOC', placeholder: '角色绝不会做的事，以及必须保持的一致性。' },
];

export function CharacterLibraryPage() {
  const initialScope = new URLSearchParams(window.location.search).get('scope') === 'project' ? 'project' : 'public';
  const [scope, setScope] = useState<Scope>(initialScope);
  const [projects, setProjects] = useState<Project[]>([]);
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [cards, setCards] = useState<CharacterCard[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState<CharacterCardWrite>(EMPTY_FORM);
  const [aliases, setAliases] = useState('');
  const [profileEntries, setProfileEntries] = useState<ProfileEntry[]>([]);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<'all' | 'main' | 'support'>('all');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(
    () => new URLSearchParams(window.location.search).get('edit') === '1',
  );
  const [extractOpen, setExtractOpen] = useState(
    () => new URLSearchParams(window.location.search).get('extract') === '1',
  );
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [copyProjectId, setCopyProjectId] = useState<number | null>(null);

  const [extractSource, setExtractSource] = useState<SourceMode>('paste');
  const [extractText, setExtractText] = useState('');
  const [extractTargetName, setExtractTargetName] = useState('');
  const [extractDetail, setExtractDetail] = useState<StyleDetailLevel>('standard');
  const [extractDestination, setExtractDestination] = useState<Scope>(initialScope);
  const [extractProjectId, setExtractProjectId] = useState<number | null>(null);
  const [sourceProjectId, setSourceProjectId] = useState<number | null>(null);
  const [sourceDocumentId, setSourceDocumentId] = useState<number | null>(null);

  const selected = cards.find((card) => card.id === selectedId) ?? null;
  const filteredCards = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return cards.filter((card) => {
      const matchesRole = roleFilter === 'all' || (roleFilter === 'main' ? card.is_main : !card.is_main);
      const matchesSearch = !query || `${card.name} ${card.aliases.join(' ')} ${card.description}`.toLocaleLowerCase().includes(query);
      return matchesRole && matchesSearch;
    });
  }, [cards, roleFilter, search]);

  useAutoDismiss(message, setMessage);
  useAutoDismiss(error, setError, 5200);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getProjects(), getLibraryDocuments()])
      .then(([projectItems, documentItems]) => {
        if (cancelled) return;
        const firstProjectId = projectItems[0]?.id ?? null;
        setProjects(projectItems);
        setDocuments(documentItems);
        setProjectId((current) => current ?? firstProjectId);
        setCopyProjectId((current) => current ?? firstProjectId);
        setExtractProjectId((current) => current ?? firstProjectId);
        setSourceProjectId((current) => current ?? firstProjectId);
        setSourceDocumentId((current) => current ?? documentItems[0]?.id ?? null);
      })
      .catch((reason) => {
        if (!cancelled) setError(errorMessage(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (scope === 'project' && projectId === null) {
      setCards([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getCharacterCards(scope, scope === 'project' ? projectId : null)
      .then((items) => {
        if (cancelled) return;
        setCards(items);
        const next = items.find((item) => item.id === selectedId) ?? items[0] ?? null;
        if (next) {
          selectCard(next);
        } else {
          beginCreate();
        }
      })
      .catch((reason) => {
        if (!cancelled) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scope, projectId]);

  function selectCard(card: CharacterCard) {
    setSelectedId(card.id);
    setForm({
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
      scope: card.scope,
      project_id: card.project_id,
    });
    setAliases(card.aliases.join('、'));
    setProfileEntries(profileToEntries(card.profile));
    setMessage(null);
  }

  function beginCreate() {
    setSelectedId(null);
    setForm({
      ...EMPTY_FORM,
      scope,
      project_id: scope === 'project' ? projectId : null,
    });
    setAliases('');
    setProfileEntries([]);
    setMessage(null);
    setEditorOpen(true);
  }

  function openEditor(card: CharacterCard) {
    selectCard(card);
    setEditorOpen(true);
  }

  async function reload(preferredId?: number | null) {
    const items = await getCharacterCards(scope, scope === 'project' ? projectId : null);
    setCards(items);
    const next = items.find((item) => item.id === preferredId) ?? items[0] ?? null;
    if (next) selectCard(next);
    else beginCreate();
  }

  async function save() {
    if (!form.name.trim()) {
      setError('请填写角色名。');
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const payload = buildPayload(form, aliases, profileEntries, scope, projectId);
      const saved = selectedId
        ? await updateCharacterCard(selectedId, payload)
        : await createCharacterCard(payload);
      await reload(saved.id);
      setMessage(selectedId ? '角色卡已保存。' : '角色卡已创建。');
      setEditorOpen(false);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selectedId || !window.confirm('确认删除当前角色卡？')) return;
    setBusy(true);
    setError(null);
    try {
      await deleteCharacterCard(selectedId);
      await reload(null);
      setMessage('角色卡已删除。');
      setEditorOpen(false);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function copyCard() {
    if (!selectedId) return;
    const targetScope: Scope = scope === 'public' ? 'project' : 'public';
    if (targetScope === 'project' && copyProjectId === null) {
      setError('请选择目标工程。');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await copyCharacterCard(selectedId, targetScope, targetScope === 'project' ? copyProjectId : null);
      setMessage(targetScope === 'project' ? '已生成可独立修改的工程角色副本。' : '已生成可独立修改的公共角色副本。');
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function importJson() {
    setBusy(true);
    setError(null);
    try {
      const parsed = JSON.parse(importText) as Record<string, unknown>;
      const source = (
        parsed.character_card && typeof parsed.character_card === 'object'
          ? parsed.character_card
          : parsed
      ) as Partial<CharacterCardWrite>;
      if (!source.name || typeof source.name !== 'string') throw new Error('JSON 中缺少角色名 name。');
      const payload: CharacterCardWrite = {
        ...EMPTY_FORM,
        ...source,
        aliases: Array.isArray(source.aliases) ? source.aliases.map(String) : [],
        profile: source.profile && typeof source.profile === 'object' && !Array.isArray(source.profile) ? source.profile : {},
        source_metadata: source.source_metadata ?? {},
        import_metadata: source.import_metadata ?? {},
        scope,
        project_id: scope === 'project' ? projectId : null,
      };
      const saved = await importCharacterCard(payload);
      setImportOpen(false);
      setImportText('');
      await reload(saved.id);
      setMessage('角色卡已从 JSON 导入。');
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function extract() {
    setBusy(true);
    setError(null);
    try {
      const result = await extractCharacterCards({
        name: extractTargetName.trim() || null,
        detail_level: extractDetail,
        sample_text: extractSource === 'paste' ? extractText : null,
        source_project_id: extractSource === 'project' ? sourceProjectId : null,
        source_document_id: extractSource === 'document' ? sourceDocumentId : null,
        scope: extractDestination,
        project_id: extractDestination === 'project' ? extractProjectId : null,
      });
      const first = result.character_cards[0] ?? null;
      setExtractOpen(false);
      setExtractText('');
      if (extractDestination === scope && (scope === 'public' || extractProjectId === projectId)) {
        await reload(first?.id ?? null);
      }
      setMessage(`AI 已生成 ${result.character_cards.length} 张角色卡。`);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const sourceReady =
    extractSource === 'paste'
      ? Boolean(extractText.trim())
      : extractSource === 'project'
        ? sourceProjectId !== null
        : sourceDocumentId !== null;
  const destinationReady = extractDestination === 'public' || extractProjectId !== null;

  return (
    <div className="character-page character-library-page">
      <TopBar
        title="角色卡"
        actions={(
          <>
            <SecondaryButton onClick={() => setImportOpen(true)}>
              <Upload size={16} />导入角色卡
            </SecondaryButton>
            <PrimaryButton onClick={() => setExtractOpen(true)}>
              <Sparkles size={16} />AI 智能提取
            </PrimaryButton>
          </>
        )}
      />

      {error ? <div className="inline-alert error">{error}<button onClick={() => setError(null)} type="button"><X size={14} /></button></div> : null}
      {message ? <div className="inline-alert success">{message}</div> : null}

      <div className="document-library-layout character-browser-layout">
        <aside className="document-category-panel">
          <nav aria-label="角色卡分类">
            <button className={`document-category-item ${scope === 'public' ? 'selected' : ''}`} onClick={() => { setScope('public'); setRoleFilter('all'); }} type="button">
              <Users size={16} /><span>公共角色</span>
            </button>
            <button className={`document-category-item ${scope === 'project' ? 'selected' : ''}`} onClick={() => { setScope('project'); setRoleFilter('all'); }} type="button">
              <FolderOpen size={16} /><span>工程角色</span>
            </button>
            {scope === 'public' ? (
              <>
                <div className="document-category-heading"><span>角色分类</span></div>
                <button className={`document-category-item ${roleFilter === 'all' ? 'selected' : ''}`} onClick={() => setRoleFilter('all')} type="button"><UserRound size={15} /><span>全部角色</span><small>{cards.length}</small></button>
                <button className={`document-category-item ${roleFilter === 'main' ? 'selected' : ''}`} onClick={() => setRoleFilter('main')} type="button"><UserRound size={15} /><span>主角 / 常驻</span><small>{cards.filter((card) => card.is_main).length}</small></button>
                <button className={`document-category-item ${roleFilter === 'support' ? 'selected' : ''}`} onClick={() => setRoleFilter('support')} type="button"><UserRound size={15} /><span>配角</span><small>{cards.filter((card) => !card.is_main).length}</small></button>
              </>
            ) : null}
            {scope === 'project' ? (
              <>
                <div className="document-category-heading"><span>选择工程</span></div>
                {projects.map((project) => (
                  <button className={`document-category-item ${projectId === project.id ? 'selected' : ''}`} key={project.id} onClick={() => setProjectId(project.id)} type="button">
                    <FolderOpen size={15} /><span>{project.name}</span>
                  </button>
                ))}
              </>
            ) : null}
          </nav>
        </aside>

        <main className="document-shelf-panel character-browser-shelf">
          <header>
            <div className="document-shelf-tools">
              <label className="search-field document-search">
                <Search size={15} /><span className="sr-only">搜索角色卡</span>
                <input onChange={(event) => setSearch(event.target.value)} placeholder="搜索角色名或别名" type="search" value={search} />
              </label>
              <button aria-label="新建角色卡" className="icon-button" onClick={beginCreate} title="新建角色卡" type="button"><Plus size={17} /></button>
            </div>
          </header>
          {loading ? <div className="character-loading">正在读取角色卡…</div> : filteredCards.length ? (
            <div className="document-shelf-scroll">
              <div className="character-card-grid document-character-grid">
                {filteredCards.map((card) => (
                  <button
                    aria-label={`${card.name}，双击编辑`}
                    aria-pressed={selectedId === card.id}
                    className={`character-library-card ${selectedId === card.id ? 'selected' : ''}`}
                    key={card.id}
                    onClick={() => selectCard(card)}
                    onDoubleClick={() => openEditor(card)}
                    title="双击编辑角色卡"
                    type="button"
                  >
                    <div className="character-card-heading">
                      <div><strong>{card.name}</strong><span>{card.aliases.join('、') || '暂无别名'}</span></div>
                      <span className={`character-role-mark ${card.is_main ? 'main' : ''}`}>{card.is_main ? '主角' : '配角'}</span>
                    </div>
                    <p>{card.description || card.personality || '尚未填写人物描述。'}</p>
                    <div className="character-card-signals"><span>优先级 {card.priority}</span><span>v{card.version}</span></div>
                    <div className="character-card-meta"><span>{card.source_character_card_id ? `副本 · 来源 #${card.source_character_card_id}` : card.scope === 'project' ? '工程创建' : '公共创建'}</span></div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState title={search ? '没有匹配的角色卡' : '还没有角色卡'} description={search ? '尝试更换关键词。' : '可手动新建、导入 JSON，或从文本中 AI 提取。'} />
          )}
        </main>

        <aside className="document-detail-panel character-detail-panel">
          <header>
            <h2>角色详情</h2>
          </header>
          {selected ? (
            <>
              <div className="document-detail-scroll">
                <section className="character-detail-identity">
                  <div className="character-detail-avatar"><UserRound size={30} /></div>
                  <div><h3>{selected.name}</h3><p>{selected.aliases.join('、') || '暂无别名'}</p><div className="document-detail-badges"><span>{selected.is_main ? '主角 / 常驻' : '配角'}</span><span>优先级 {selected.priority}</span></div></div>
                </section>
                <section className="document-detail-metadata">
                  <DetailDefinition label="作用域" value={selected.scope === 'public' ? '公共角色' : '工程角色'} />
                  <DetailDefinition label="版本" value={`v${selected.version}`} />
                  <DetailDefinition label="来源" value={selected.source_character_card_id ? `角色卡 #${selected.source_character_card_id} · v${selected.source_version}` : '本地创建'} />
                </section>
                <section><div className="document-detail-heading"><span>人物描述</span></div><p className="character-detail-copy">{selected.description || '暂无描述'}</p></section>
                <section><div className="document-detail-heading"><span>性格</span></div><p className="character-detail-copy">{selected.personality || '暂无记录'}</p></section>
                <section><div className="document-detail-heading"><span>关系</span></div><p className="character-detail-copy">{selected.relationship_notes || '暂无记录'}</p></section>
                {Object.keys(selected.profile).length ? <section><div className="document-detail-heading"><span>扩展维度</span></div><div>{Object.entries(selected.profile).map(([key, value]) => <DetailDefinition key={key} label={key} value={typeof value === 'string' ? value : JSON.stringify(value)} />)}</div></section> : null}
                <p className="character-double-click-hint">双击中间的角色卡进入编辑</p>
              </div>
              <footer className="library-detail-footer character-detail-footer">
                <SecondaryButton onClick={() => openEditor(selected)}><Pencil size={15} />编辑</SecondaryButton>
                <SecondaryButton disabled={busy || (scope === 'public' && copyProjectId === null)} onClick={copyCard}><ArrowRightLeft size={15} />{scope === 'public' ? '复制到工程' : '保存到公共库'}</SecondaryButton>
              </footer>
            </>
          ) : <EmptyState title="选择一张角色卡" description="单击查看详情，双击进入编辑。" />}
        </aside>
      </div>

      <div className="character-command">
        <div className="material-scope-switch" aria-label="角色卡作用域" role="tablist">
          <button className={scope === 'public' ? 'selected' : ''} onClick={() => setScope('public')} role="tab" type="button">公共角色</button>
          <button className={scope === 'project' ? 'selected' : ''} onClick={() => setScope('project')} role="tab" type="button">工程角色</button>
        </div>
        {scope === 'project' ? (
          <label className="material-project-select">
            <select aria-label="选择工程" value={projectId ?? ''} onChange={(event) => setProjectId(numberOrNull(event.target.value))}>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
            <ChevronDown size={14} />
          </label>
        ) : null}
        <label className="search-field character-search">
          <Search size={15} />
          <input onChange={(event) => setSearch(event.target.value)} placeholder="搜索角色名、别名或描述" type="search" value={search} />
        </label>
        <SecondaryButton onClick={beginCreate}><Plus size={16} />新建角色卡</SecondaryButton>
      </div>

      <div className={`character-workspace ${editorOpen ? 'editor-open' : ''}`}>
        <section className="character-shelf">
          <header>
            <div><strong>{scope === 'public' ? '公共角色' : '工程角色'}</strong><span>共 {filteredCards.length} 张</span></div>
          </header>
          {loading ? (
            <div className="character-loading">正在读取角色卡…</div>
          ) : filteredCards.length === 0 ? (
            <EmptyState
              title={search ? '没有匹配的角色卡' : '还没有角色卡'}
              description={search ? '尝试更换关键词。' : '可手动新建、导入 JSON，或从文本中 AI 提取。'}
            />
          ) : (
            <div className="character-card-grid">
              {filteredCards.map((card) => (
                <button
                  className={`character-library-card ${selectedId === card.id ? 'selected' : ''}`}
                  key={card.id}
                  onClick={() => selectCard(card)}
                  type="button"
                >
                  <div className="character-card-heading">
                    <div><strong>{card.name}</strong><span>{card.aliases.join('、') || '暂无别名'}</span></div>
                    <span className={`character-role-mark ${card.is_main ? 'main' : ''}`}>{card.is_main ? '主角' : '配角'}</span>
                  </div>
                  <p>{card.description || card.personality || '尚未填写人物描述。'}</p>
                  <div className="character-card-signals">
                    <span>优先级 {card.priority}</span><span>v{card.version}</span>
                  </div>
                  <div className="character-card-meta">
                    <span>{card.source_character_card_id ? `副本 · 来源 #${card.source_character_card_id}` : card.scope === 'project' ? '工程创建' : '公共创建'}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="character-editor">
          <header>
            <div>
              <span>{selected ? `${selected.scope === 'public' ? '公共角色' : '工程角色'} · v${selected.version}` : '手动创建'}</span>
              <h2>{selected ? selected.name : '新建角色卡'}</h2>
              {selected?.source_character_card_id ? <p>来自角色卡 #{selected.source_character_card_id} 的独立副本，源版本 v{selected.source_version}</p> : null}
            </div>
            <button aria-label="关闭编辑器" className="icon-button" disabled={busy} onClick={() => setEditorOpen(false)} type="button"><X size={18} /></button>
          </header>

          <div className="character-editor-scroll">
            <fieldset className="character-form-section">
              <legend>基础信息</legend>
              <div className="character-basic-grid">
                <label><span>角色名</span><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
                <label><span>别名</span><input placeholder="使用顿号或逗号分隔" value={aliases} onChange={(event) => setAliases(event.target.value)} /></label>
                <label><span>优先级</span><input max={100} min={0} type="number" value={form.priority} onChange={(event) => setForm({ ...form, priority: Number(event.target.value) || 0 })} /></label>
                <label><span>角色类型</span><select value={form.is_main ? 'main' : 'support'} onChange={(event) => setForm({ ...form, is_main: event.target.value === 'main' })}><option value="main">主角 / 常驻</option><option value="support">配角</option></select></label>
              </div>
            </fieldset>

            {FIELD_SECTIONS.map((section) => (
              <label className="character-form-section character-text-section" key={section.key}>
                <span>{section.label}</span>
                <textarea
                  placeholder={section.placeholder}
                  value={String(form[section.key] ?? '')}
                  onChange={(event) => setForm({ ...form, [section.key]: event.target.value })}
                />
              </label>
            ))}

            <fieldset className="character-form-section">
              <legend>扩展维度</legend>
              <div className="profile-entry-list">
                {profileEntries.map((entry, index) => (
                  <div className="profile-entry" key={`${index}-${entry.key}`}>
                    <input aria-label="维度名称" placeholder="维度，如：身份" value={entry.key} onChange={(event) => updateProfileEntry(index, 'key', event.target.value)} />
                    <input aria-label="维度内容" placeholder="内容" value={entry.value} onChange={(event) => updateProfileEntry(index, 'value', event.target.value)} />
                    <button aria-label="删除维度" onClick={() => setProfileEntries((items) => items.filter((_, itemIndex) => itemIndex !== index))} type="button"><Trash2 size={14} /></button>
                  </div>
                ))}
                <button className="profile-add" onClick={() => setProfileEntries((items) => [...items, { key: '', value: '' }])} type="button"><Plus size={14} />添加维度</button>
              </div>
            </fieldset>
          </div>

          <footer>
            <div>
              <PrimaryButton disabled={busy} onClick={save}><Save size={16} />保存</PrimaryButton>
              <DangerButton disabled={busy || !selectedId} onClick={remove}><Trash2 size={16} />删除</DangerButton>
            </div>
            {selectedId ? (
              <div className="character-copy-control">
                {scope === 'public' ? (
                  <label>
                    <select aria-label="复制到工程" value={copyProjectId ?? ''} onChange={(event) => setCopyProjectId(numberOrNull(event.target.value))}>
                      {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                    </select>
                    <ChevronDown size={13} />
                  </label>
                ) : null}
                <SecondaryButton disabled={busy || (scope === 'public' && copyProjectId === null)} onClick={copyCard}>
                  <ArrowRightLeft size={16} />{scope === 'public' ? '复制到工程' : '保存到公共库'}
                </SecondaryButton>
              </div>
            ) : null}
          </footer>
        </section>
      </div>

      {extractOpen ? (
        <div className="character-drawer-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && !busy && setExtractOpen(false)}>
          <aside aria-labelledby="character-extract-title" aria-modal="true" className="character-extract-drawer" role="dialog">
            <header><div><h2 id="character-extract-title">AI 智能提取</h2><p>从文本、工程原文或文档库中提取并生成角色卡。</p></div><button aria-label="关闭" disabled={busy} onClick={() => setExtractOpen(false)} type="button"><X size={18} /></button></header>
            <div className="character-drawer-scroll">
              <section>
                <h3>1. 选择提取来源</h3>
                <div className="character-source-tabs">
                  {([['paste', '粘贴文本'], ['project', '工程原文'], ['document', '文档库']] as Array<[SourceMode, string]>).map(([value, label]) => (
                    <button className={extractSource === value ? 'selected' : ''} key={value} onClick={() => setExtractSource(value)} type="button">{label}</button>
                  ))}
                </div>
                {extractSource === 'paste' ? (
                  <textarea className="character-source-text" placeholder="粘贴包含角色信息的文本…" value={extractText} onChange={(event) => setExtractText(event.target.value)} />
                ) : extractSource === 'project' ? (
                  <select className="form-input" value={sourceProjectId ?? ''} onChange={(event) => setSourceProjectId(numberOrNull(event.target.value))}>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select>
                ) : (
                  <select className="form-input" value={sourceDocumentId ?? ''} onChange={(event) => setSourceDocumentId(numberOrNull(event.target.value))}>{documents.map((document) => <option key={document.id} value={document.id}>{document.title}</option>)}</select>
                )}
              </section>
              <section><h3>2. 目标角色名（可选）</h3><input className="form-input" placeholder="留空则识别全部角色" value={extractTargetName} onChange={(event) => setExtractTargetName(event.target.value)} /></section>
              <section><h3>3. 提取详细度</h3><div className="character-radio-list">{([['brief', '精简（关键信息）'], ['standard', '标准（推荐）'], ['detailed', '详尽（更多细节）']] as Array<[StyleDetailLevel, string]>).map(([value, label]) => <label key={value}><input checked={extractDetail === value} name="detail" onChange={() => setExtractDetail(value)} type="radio" />{label}</label>)}</div></section>
              <section><h3>4. 保存位置</h3><div className="character-radio-list"><label><input checked={extractDestination === 'public'} name="destination" onChange={() => setExtractDestination('public')} type="radio" />公共角色</label><label><input checked={extractDestination === 'project'} name="destination" onChange={() => setExtractDestination('project')} type="radio" />工程角色</label></div>{extractDestination === 'project' ? <select className="form-input" value={extractProjectId ?? ''} onChange={(event) => setExtractProjectId(numberOrNull(event.target.value))}>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select> : null}</section>
            </div>
            <footer><PrimaryButton disabled={busy || !sourceReady || !destinationReady} onClick={extract}><Sparkles size={16} />开始提取</PrimaryButton><p>结果将自动生成角色卡，可继续手动编辑。</p></footer>
          </aside>
        </div>
      ) : null}

      {importOpen ? (
        <div className="anchor-extract-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && !busy && setImportOpen(false)}>
          <section aria-labelledby="character-import-title" aria-modal="true" className="anchor-extract-dialog character-import-dialog" role="dialog">
            <header><div><span>JSON IMPORT</span><h2 id="character-import-title">导入角色卡</h2></div><button aria-label="关闭" className="icon-button" disabled={busy} onClick={() => setImportOpen(false)} type="button"><X size={18} /></button></header>
            <p className="character-import-help">粘贴角色卡 JSON。导入后会在软件内转换成可视化字段，不需要直接维护 JSON。</p>
            <textarea className="anchor-extract-textarea" placeholder={'{"name":"角色名","aliases":[],"description":"…","profile":{"身份":"…"}}'} value={importText} onChange={(event) => setImportText(event.target.value)} />
            <footer><SecondaryButton disabled={busy} onClick={() => setImportOpen(false)}>取消</SecondaryButton><PrimaryButton disabled={busy || !importText.trim()} onClick={importJson}><Copy size={16} />导入</PrimaryButton></footer>
          </section>
        </div>
      ) : null}
    </div>
  );

  function updateProfileEntry(index: number, field: keyof ProfileEntry, value: string) {
    setProfileEntries((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item));
  }
}

function buildPayload(
  form: CharacterCardWrite,
  aliases: string,
  entries: ProfileEntry[],
  scope: Scope,
  projectId: number | null,
): CharacterCardWrite {
  const profile = Object.fromEntries(
    entries
      .map((entry) => [entry.key.trim(), entry.value.trim()] as const)
      .filter(([key]) => Boolean(key)),
  );
  return {
    ...form,
    name: form.name.trim(),
    aliases: aliases.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
    profile,
    scope,
    project_id: scope === 'project' ? projectId : null,
  };
}

function profileToEntries(profile: Record<string, unknown>): ProfileEntry[] {
  return Object.entries(profile).map(([key, value]) => ({
    key,
    value: typeof value === 'string' ? value : JSON.stringify(value, null, 0),
  }));
}

function numberOrNull(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

function DetailDefinition({ label, value }: { label: string; value: string }) {
  return <div className="document-definition"><span>{label}</span><strong title={value}>{value}</strong></div>;
}
