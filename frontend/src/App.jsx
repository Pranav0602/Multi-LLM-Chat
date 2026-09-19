import React, { useEffect, useState } from 'react';
import { api } from './api';
import { TurnCard } from './components/TurnCard';

const ROLE_PRESETS = {
  'Lead Researcher':
    'You are the lead researcher. Analyze the research question carefully. Develop hypotheses. Explain your reasoning. Build upon useful arguments from previous researchers. Do not agree merely because another model proposed something. Identify uncertainty explicitly.',
  Skeptic:
    'You are the skeptical researcher. Critically examine previous responses. Look for unsupported assumptions, logical errors, incorrect facts, alternative explanations, missing evidence, overconfident conclusions. Do not criticize merely for criticism; accept well-supported arguments.',
  'Mathematical Analyst':
    'You are the mathematical analyst. Check mathematical reasoning rigorously. Derive important equations where useful. Check assumptions and limiting cases. Identify dimensional, algebraic and logical errors.',
  Synthesizer:
    'You are the synthesizer. Integrate the strongest arguments so far, resolve contradictions where possible, and state clearly what is established vs unresolved.',
  'Empirical Specialist':
    'You are the empirical specialist. Supply concrete domain mechanisms, equations, datasets, or scientific evidence. Ground abstract claims in verifiable facts.',
  Affirmative:
    'You are the affirmative proponent. Build the strongest case in favor of the thesis. Present structured arguments with evidence and preempt counter-arguments.',
  Negative:
    'You are the negative opponent. Rebut the affirmative case, present counter-positions with evidence, and expose weaknesses in opposing arguments.',
  'Cross-Examiner':
    'You are the cross-examiner. Probe both sides with critical questions, fact-check claims, and surface hidden assumptions.',
  Judge:
    'You are the neutral moderator and judge. Evaluate argument strength fairly, summarize debate points, and declare which side is currently stronger and why.',
  'System Architect':
    'You are the system architect. Design module structure, interfaces, data flow, and scalability. Propose concrete components and their responsibilities.',
  'Security Auditor':
    'You are the security and reliability auditor. Scan for vulnerabilities, race conditions, failure modes, and edge cases. Propose mitigations.',
  'Performance Specialist':
    'You are the performance specialist. Analyze latency, memory, throughput, and database query costs. Suggest measurable optimizations.',
  Reviewer:
    'You are the pragmatic reviewer. Ensure code readability, maintainability, and clear implementation steps. Keep solutions shippable.',
  'Visionary Ideator':
    'You are the visionary ideator. Generate bold, unconstrained creative concepts. Quantity and novelty first — no feasibility filter yet.',
  'User Advocate':
    'You are the customer and user advocate. Evaluate user friction, value proposition, and empathy. Represent the end-user voice.',
  'Pragmatic Realist':
    'You are the pragmatic realist. Evaluate feasibility, execution complexity, cost, and risks. Ground wild ideas in constraints.',
  'Product Strategist':
    'You are the product strategist. Create roadmap, prioritization, MVP specifications, and success metrics from the ideas so far.',
};

const CHAT_TYPES = {
  research: {
    label: '🔬 Research',
    roles: ['Lead Researcher', 'Skeptic', 'Empirical Specialist', 'Synthesizer'],
  },
  debate: {
    label: '⚔️ Debate',
    roles: ['Affirmative', 'Negative', 'Cross-Examiner', 'Judge'],
  },
  architecture: {
    label: '💻 Architecture',
    roles: ['System Architect', 'Security Auditor', 'Performance Specialist', 'Reviewer'],
  },
  brainstorm: {
    label: '💡 Brainstorm',
    roles: ['Visionary Ideator', 'User Advocate', 'Pragmatic Realist', 'Product Strategist'],
  },
  custom: { label: '🛠️ Custom', roles: [] },
};

const PROVIDER_SUGGESTIONS = {
  codecraft: { models: ['gemma-2-2b', 'muse-spark-1.1', 'gpt-5.6-sol'], baseUrl: 'https://codecraftapi.com/v1', keyHint: 'CODECRAFT_API_KEY (.env fallback)' },
  openai: { models: ['gpt-4o-mini', 'gpt-4o', 'o1-mini'], baseUrl: 'https://api.openai.com/v1', keyHint: 'OPENAI_API_KEY (.env fallback)' },
  anthropic: { models: ['claude-3-5-sonnet-latest', 'claude-3-5-haiku-latest'], baseUrl: 'https://api.anthropic.com', keyHint: 'ANTHROPIC_API_KEY (.env fallback)' },
  gemini: { models: ['gemini-1.5-flash', 'gemini-1.5-pro'], baseUrl: 'https://generativelanguage.googleapis.com', keyHint: 'GEMINI_API_KEY (.env fallback)' },
  openrouter: { models: ['openai/gpt-4o-mini', 'anthropic/claude-3.5-sonnet'], baseUrl: 'https://openrouter.ai/api/v1', keyHint: 'OPENROUTER_API_KEY (.env fallback)' },
  local: { models: ['llama3', 'mistral', 'phi3'], baseUrl: 'http://localhost:11434/v1', keyHint: 'No key needed (local server must be running)' },
};

export default function App() {
  const [groups, setGroups] = useState([]);
  const [activeGroup, setActiveGroup] = useState(null);
  const [groupModels, setGroupModels] = useState([]);
  const [allModels, setAllModels] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [activeConv, setActiveConv] = useState(null);
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState('Is dark energy actually real?');
  const [maxRounds, setMaxRounds] = useState(5);
  const [chatType, setChatType] = useState('research');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [newGroupName, setNewGroupName] = useState('');

  // Add-model state (plan §2)
  const [addTab, setAddTab] = useState('existing'); // existing | new
  const [existingModelId, setExistingModelId] = useState('');
  const [newModel, setNewModel] = useState({
    name: '',
    provider: 'codecraft',
    model_name: 'gemma-2-2b',
    system_prompt: ROLE_PRESETS['Lead Researcher'],
    api_key: '',
    base_url: '',
  });
  const [preset, setPreset] = useState('Lead Researcher');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [addDiag, setAddDiag] = useState(null); // {ok, message}

  // Role editor state: linkId -> {expanded, role, prompt}
  const [roleEdits, setRoleEdits] = useState({});

  const refreshGroups = async () => setGroups(await api.listGroups());
  const refreshModels = async () => setAllModels(await api.listModels());

  useEffect(() => {
    refreshGroups().catch((e) => setError(String(e)));
    refreshModels().catch((e) => setError(String(e)));
  }, []);

  const selectGroup = async (g) => {
    setActiveGroup(g);
    setActiveConv(null);
    setTurns([]);
    setTestResult(null);
    setAddDiag(null);
    setGroupModels(await api.listGroupModels(g.id));
  };

  const createGroup = async () => {
    if (!newGroupName.trim()) return;
    const g = await api.createGroup(newGroupName.trim(), '');
    setNewGroupName('');
    await refreshGroups();
    await selectGroup(g);
  };

  const createConversation = async () => {
    if (!activeGroup || !question.trim()) return;
    setBusy(true);
    setError('');
    try {
      const conv = await api.createConversation({
        group_id: activeGroup.id,
        title: question.slice(0, 120),
        original_prompt: question,
        max_rounds: Number(maxRounds) || 5,
        chat_type: chatType,
      });
      setActiveConv(conv);
      setConversations((c) => [conv, ...c]);
      setTurns([]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const reloadTurns = async (id) => {
    const t = await api.listTurns(id);
    setTurns(t);
    setActiveConv(await api.getConversation(id));
  };

  const run = async (fn) => {
    if (!activeConv) return;
    setBusy(true);
    setError('');
    try {
      await fn();
      await reloadTurns(activeConv.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  // ---- Turn order (plan §1) ----
  const sortedLinks = [...groupModels].sort((a, b) => a.turn_order - b.turn_order || a.id - b.id);
  const enabledLinks = sortedLinks.filter((l) => l.is_enabled);
  const nextLink =
    enabledLinks.length > 0 ? enabledLinks[(activeConv?.current_turn ?? 0) % enabledLinks.length] : null;

  const moveLink = async (linkId, dir) => {
    const ids = sortedLinks.map((l) => l.id);
    const idx = ids.indexOf(linkId);
    const j = idx + dir;
    if (idx < 0 || j < 0 || j >= ids.length) return;
    const swapped = [...ids];
    [swapped[idx], swapped[j]] = [swapped[j], swapped[idx]];
    setBusy(true);
    setError('');
    try {
      await api.reorderGroupModels(activeGroup.id, swapped);
      setGroupModels(await api.listGroupModels(activeGroup.id));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeLink = async (linkId) => {
    setBusy(true);
    setError('');
    try {
      await api.removeGroupModel(activeGroup.id, linkId);
      setGroupModels(await api.listGroupModels(activeGroup.id));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  // ---- Add model with diagnostics (plan §2) ----
  // Free-text platform: known keys give hints, but ANY custom name works
  // as long as an OpenAI-compatible base_url is supplied (backend generic provider).
  const providerKey = (newModel.provider || '').trim().toLowerCase();
  const providerInfo = PROVIDER_SUGGESTIONS[providerKey] || { models: [], baseUrl: '', keyHint: 'API key for this platform (if required)' };
  const isKnownProvider = Boolean(PROVIDER_SUGGESTIONS[providerKey]);
  const isCustomProvider = providerKey !== '' && !isKnownProvider && providerKey !== 'mock' && providerKey !== 'custom';

  const doTestConnection = async () => {
    // Inline validation with exact missing fields.
    const missing = [];
    const normProvider = (newModel.provider || '').trim().toLowerCase();
    if (!normProvider) missing.push('platform / provider');
    if (!newModel.model_name.trim()) missing.push('model_name');
    // Custom platform requires a base URL so backend knows where to send the request.
    if (normProvider && !PROVIDER_SUGGESTIONS[normProvider] && normProvider !== 'mock' && !(newModel.base_url || '').trim()) {
      setTestResult({ ok: false, message: `Custom platform '${newModel.provider.trim()}' needs a Base URL (OpenAI-compatible endpoint, e.g. https://api.groq.com/openai/v1).` });
      return;
    }
    if (missing.length) {
      setTestResult({ ok: false, message: `Missing required fields: ${missing.join(', ')}.` });
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const r = await api.testModelConnection({
        provider: normProvider,
        model_name: newModel.model_name.trim(),
        api_key: newModel.api_key,
        base_url: newModel.base_url,
      });
      setTestResult(r);
    } catch (e) {
      setTestResult({ ok: false, message: String(e) });
    } finally {
      setTesting(false);
    }
  };

  const addExistingToGroup = async () => {
    setAddDiag(null);
    setError('');
    if (!existingModelId) {
      setAddDiag({ ok: false, message: 'Select a model from the registry first.' });
      return;
    }
    try {
      await api.addGroupModel(activeGroup.id, {
        model_id: Number(existingModelId),
        turn_order: groupModels.length,
        is_enabled: true,
      });
      setAddDiag({ ok: true, message: 'Model added to group.' });
      setGroupModels(await api.listGroupModels(activeGroup.id));
    } catch (e) {
      setAddDiag({ ok: false, message: String(e) });
    }
  };

  const createAndAddNew = async () => {
    setAddDiag(null);
    setError('');
    const missing = [];
    const normProvider = (newModel.provider || '').trim().toLowerCase();
    if (!newModel.name.trim()) missing.push('display name');
    if (!normProvider) missing.push('platform / provider');
    if (!newModel.model_name.trim()) missing.push('model_name');
    if (missing.length) {
      setAddDiag({ ok: false, message: `Cannot add model — missing: ${missing.join(', ')}.` });
      return;
    }
    if (!PROVIDER_SUGGESTIONS[normProvider] && normProvider !== 'mock' && !(newModel.base_url || '').trim()) {
      setAddDiag({ ok: false, message: `Custom platform '${newModel.provider.trim()}' needs a Base URL (OpenAI-compatible endpoint, e.g. https://api.groq.com/openai/v1).` });
      return;
    }
    try {
      const m = await api.createModel({
        ...newModel,
        provider: normProvider,
        model_name: newModel.model_name.trim(),
        name: newModel.name.trim(),
      });
      await api.addGroupModel(activeGroup.id, {
        model_id: m.id,
        turn_order: groupModels.length,
        is_enabled: true,
      });
      setAddDiag({ ok: true, message: `Model '${m.name}' created and added to group.` });
      setGroupModels(await api.listGroupModels(activeGroup.id));
      await refreshModels();
      setNewModel({ ...newModel, name: '', api_key: '' });
      setTestResult(null);
    } catch (e) {
      setAddDiag({ ok: false, message: String(e) });
    }
  };

  // ---- Roles (plan §3) ----
  const getRoleEdit = (link) => {
    if (roleEdits[link.id]) return roleEdits[link.id];
    const current = (link.system_prompt_override || link.model?.system_prompt || '').trim();
    const matched = Object.keys(ROLE_PRESETS).find((k) => ROLE_PRESETS[k] === current) || 'Custom';
    return { expanded: false, role: matched, prompt: current };
  };

  const setRoleEdit = (linkId, patch) => {
    setRoleEdits((prev) => ({ ...prev, [linkId]: { ...getRoleEdit({ id: linkId }), ...patch } }));
  };

  const savePrompt = async (link) => {
    const edit = getRoleEdit(link);
    try {
      await api.updateGroupModel(activeGroup.id, link.id, { system_prompt_override: edit.prompt });
      setGroupModels(await api.listGroupModels(activeGroup.id));
      setAddDiag({ ok: true, message: `Prompt saved for ${link.model?.name}.` });
    } catch (e) {
      setError(String(e));
    }
  };

  const autoAssignRoles = async () => {
    const catalog = CHAT_TYPES[chatType];
    if (!catalog || catalog.roles.length === 0) {
      setError('Custom mode has no preset roles — edit each prompt manually.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      for (let i = 0; i < sortedLinks.length; i++) {
        const link = sortedLinks[i];
        const role = catalog.roles[i % catalog.roles.length];
        await api.updateGroupModel(activeGroup.id, link.id, {
          system_prompt_override: ROLE_PRESETS[role] || '',
        });
      }
      setGroupModels(await api.listGroupModels(activeGroup.id));
      setRoleEdits({});
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const suggestRolesForLink = (index) => {
    const catalog = CHAT_TYPES[chatType];
    if (!catalog || catalog.roles.length === 0) return '—';
    return catalog.roles[index % catalog.roles.length];
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: 'system-ui, sans-serif' }}>
      {/* Sidebar — plan section 13 */}
      <aside style={{ width: 280, borderRight: '1px solid #ddd', padding: 16, background: '#fafafa' }}>
        <h3>Research Groups</h3>
        <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
          <input
            value={newGroupName}
            onChange={(e) => setNewGroupName(e.target.value)}
            placeholder="+ New Group"
            style={{ flex: 1 }}
          />
          <button onClick={createGroup}>Add</button>
        </div>
        {groups.map((g) => (
          <div
            key={g.id}
            onClick={() => selectGroup(g)}
            style={{
              padding: '8px 10px',
              borderRadius: 6,
              cursor: 'pointer',
              background: activeGroup?.id === g.id ? '#e3f2fd' : 'transparent',
              marginBottom: 4,
            }}
          >
            {g.name}
          </div>
        ))}
        <hr />
        <h4>Model registry</h4>
        {allModels.filter((m) => m.provider !== 'mock').map((m) => (
          <div key={m.id} style={{ fontSize: 13, marginBottom: 4 }}>
            {m.name} <span style={{ color: '#777' }}>({m.provider}/{m.model_name})</span>
          </div>
        ))}
      </aside>

      {/* Main */}
      <main style={{ flex: 1, padding: 20, maxWidth: 900 }}>
        <h2>Multi-LLM Research Chat</h2>
        {error && <div style={{ color: '#a00', marginBottom: 10 }}>{error}</div>}
        {!activeGroup && <p>Select or create a research group from the sidebar.</p>}

        {activeGroup && (
          <>
            <h3>
              {activeConv ? `Research: ${activeConv.title}` : `Group: ${activeGroup.name}`}
            </h3>

            {/* Research controls — plan section 14 */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <button disabled={!activeConv || busy} onClick={() => run(() => api.singleTurn(activeConv.id))}>
                Single turn
              </button>
              <button disabled={!activeConv || busy} onClick={() => run(() => api.start(activeConv.id, Number(maxRounds)))}>
                ▶ Start
              </button>
              <button disabled={!activeConv || busy} onClick={() => run(() => api.pause(activeConv.id))}>
                ⏸ Pause
              </button>
              <button disabled={!activeConv || busy} onClick={() => run(() => api.stop(activeConv.id))}>
                ⏹ Stop
              </button>
              <button disabled={!activeConv || busy} onClick={() => run(() => api.cont(activeConv.id))}>
                ↻ Continue
              </button>
              <button disabled={!activeConv || busy} onClick={() => run(() => api.summarize(activeConv.id))}>
                Summarize
              </button>
              <button disabled={!activeConv || busy} onClick={() => reloadTurns(activeConv.id)}>
                Refresh
              </button>
            </div>

            <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <label>
                Number of rounds:{' '}
                <input
                  type="number"
                  min="1"
                  max="50"
                  value={maxRounds}
                  onChange={(e) => setMaxRounds(e.target.value)}
                  style={{ width: 60 }}
                />
              </label>
              <span style={{ fontSize: 13, color: '#555' }}>
                Status: {activeConv?.status ?? '—'} · Round {activeConv?.current_round ?? '—'} · Turn{' '}
                {activeConv?.current_turn ?? '—'}
                {activeConv?.chat_type ? ` · Mode: ${activeConv.chat_type}` : ''}
              </span>
            </div>

            {/* Chat type selector (plan §3) */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <strong style={{ fontSize: 14 }}>Chat type:</strong>
              {Object.entries(CHAT_TYPES).map(([key, v]) => (
                <button
                  key={key}
                  onClick={() => setChatType(key)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 14,
                    border: chatType === key ? '2px solid #6c3ce0' : '1px solid #ccc',
                    background: chatType === key ? '#efe7ff' : '#fff',
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  {v.label}
                </button>
              ))}
              <button
                onClick={autoAssignRoles}
                disabled={busy || sortedLinks.length === 0}
                title="Assign preset role prompts to each model in turn order"
                style={{ fontSize: 13 }}
              >
                🎭 Auto-Assign Roles
              </button>
            </div>

            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask the research group…"
                style={{ flex: 1, padding: 8 }}
              />
              <button disabled={busy} onClick={createConversation}>
                New discussion
              </button>
            </div>

            {/* Turn pipeline preview (plan §1) */}
            {sortedLinks.length > 0 && (
              <div
                style={{
                  background: '#f4f1ff',
                  border: '1px solid #d9ccff',
                  borderRadius: 8,
                  padding: 10,
                  marginBottom: 12,
                  fontSize: 13,
                }}
              >
                <strong>Turn pipeline:</strong>{' '}
                {enabledLinks.map((l, i) => (
                  <span key={l.id}>
                    <span
                      style={{
                        background: nextLink?.id === l.id ? '#6c3ce0' : '#fff',
                        color: nextLink?.id === l.id ? '#fff' : '#333',
                        border: '1px solid #6c3ce0',
                        borderRadius: 6,
                        padding: '2px 8px',
                        fontWeight: nextLink?.id === l.id ? 700 : 400,
                      }}
                    >
                      Turn {i + 1}: {l.model?.name}
                      {nextLink?.id === l.id ? ' ★ next' : ''}
                    </span>
                    {i < enabledLinks.length - 1 ? ' ➔ ' : ''}
                  </span>
                ))}
                {enabledLinks.length > 0 ? ' ➔ ↻ Repeat' : 'No enabled models.'}
                {enabledLinks.length !== sortedLinks.length && (
                  <span style={{ color: '#777' }}>
                    {' '}
                    ({sortedLinks.length - enabledLinks.length} disabled)
                  </span>
                )}
              </div>
            )}

            <h4>Models in group (turn order)</h4>
            {sortedLinks.map((l, idx) => {
              const edit = roleEdits[l.id] || getRoleEdit(l);
              const isNext = nextLink?.id === l.id;
              return (
                <div
                  key={l.id}
                  style={{
                    border: isNext ? '2px solid #6c3ce0' : '1px solid #ddd',
                    borderRadius: 8,
                    padding: 8,
                    marginBottom: 8,
                    background: isNext ? '#faf7ff' : '#fff',
                    fontSize: 14,
                  }}
                >
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span
                      style={{
                        background: '#333',
                        color: '#fff',
                        borderRadius: 4,
                        padding: '1px 7px',
                        fontSize: 12,
                        fontWeight: 700,
                      }}
                    >
                      #{idx + 1}
                    </span>
                    <input
                      type="checkbox"
                      checked={l.is_enabled}
                      title="Enable/disable participant"
                      onChange={async (e) => {
                        await api.toggleGroupModel(activeGroup.id, l.id, { is_enabled: e.target.checked });
                        setGroupModels(await api.listGroupModels(activeGroup.id));
                      }}
                    />
                    <strong>
                      {l.model?.name} <span style={{ color: '#777', fontWeight: 400 }}>({l.model?.provider})</span>
                    </strong>
                    {isNext && <span style={{ color: '#6c3ce0', fontWeight: 700 }}>← Next to Speak</span>}
                    <span style={{ color: '#888', fontSize: 12 }}>Suggested: {suggestRolesForLink(idx)}</span>
                    <span style={{ flex: 1 }} />
                    <button disabled={busy || idx === 0} onClick={() => moveLink(l.id, -1)} title="Move up">
                      ▲
                    </button>
                    <button
                      disabled={busy || idx === sortedLinks.length - 1}
                      onClick={() => moveLink(l.id, 1)}
                      title="Move down"
                    >
                      ▼
                    </button>
                    <button onClick={() => removeLink(l.id)} title="Remove from group">
                      ✕
                    </button>
                    <button onClick={() => setRoleEdit(l.id, { expanded: !edit.expanded })}>
                      {edit.expanded ? 'Hide Role' : '🎭 Role & Prompt'}
                    </button>
                  </div>
                  {edit.expanded && (
                    <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <select
                          value={edit.role}
                          onChange={(e) => {
                            const r = e.target.value;
                            setRoleEdit(l.id, {
                              role: r,
                              prompt: r === 'Custom' ? edit.prompt : ROLE_PRESETS[r] || edit.prompt,
                            });
                          }}
                          style={{ maxWidth: 220 }}
                        >
                          {[...Object.keys(ROLE_PRESETS), 'Custom'].map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                        <button onClick={() => savePrompt({ ...l })}>Save Prompt</button>
                      </div>
                      <textarea
                        value={roleEdits[l.id]?.prompt ?? (l.system_prompt_override || l.model?.system_prompt || '')}
                        onChange={(e) => setRoleEdit(l.id, { prompt: e.target.value })}
                        rows={3}
                        placeholder="Custom prompting instructions for this model…"
                        style={{ width: '100%', fontSize: 13 }}
                      />
                    </div>
                  )}
                </div>
              );
            })}

            <h4>Add model to group</h4>
            <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
              <button
                onClick={() => setAddTab('existing')}
                style={{ fontWeight: addTab === 'existing' ? 700 : 400 }}
              >
                Pick Existing Model
              </button>
              <button onClick={() => setAddTab('new')} style={{ fontWeight: addTab === 'new' ? 700 : 400 }}>
                Create & Add New Model
              </button>
            </div>

            {addTab === 'existing' && (
              <div style={{ display: 'flex', gap: 6, marginBottom: 20, maxWidth: 520 }}>
                <select
                  value={existingModelId}
                  onChange={(e) => setExistingModelId(e.target.value)}
                  style={{ flex: 1 }}
                >
                  <option value="">— Select registered model —</option>
                  {allModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.provider}/{m.model_name})
                    </option>
                  ))}
                </select>
                <button onClick={addExistingToGroup}>Add to Group</button>
              </div>
            )}

            {addTab === 'new' && (
              <div style={{ fontSize: 14, display: 'grid', gap: 6, maxWidth: 520, marginBottom: 20 }}>
                <input
                  placeholder="Display name (e.g. GPT)"
                  value={newModel.name}
                  onChange={(e) => setNewModel({ ...newModel, name: e.target.value })}
                />
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    placeholder="Platform / provider — type any (e.g. groq, together, mistral, deepseek)"
                    value={newModel.provider}
                    onChange={(e) => setNewModel({ ...newModel, provider: e.target.value })}
                    style={{ flex: 1 }}
                    list="provider-suggestions"
                  />
                  <datalist id="provider-suggestions">
                    {Object.keys(PROVIDER_SUGGESTIONS).map((p) => (
                      <option key={p} value={p} />
                    ))}
                    <option value="custom" />
                    <option value="groq" />
                    <option value="together" />
                    <option value="mistral" />
                    <option value="deepseek" />
                  </datalist>
                  <input
                    placeholder="model_name (e.g. gemma-2-2b, muse-spark-1.1)"
                    value={newModel.model_name}
                    onChange={(e) => setNewModel({ ...newModel, model_name: e.target.value })}
                    style={{ flex: 1 }}
                    list="model-suggestions"
                  />
                  <datalist id="model-suggestions">
                    {(providerInfo.models || []).map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                </div>
                <div style={{ fontSize: 12, color: '#666' }}>
                  {isCustomProvider ? (
                    <>Custom platform detected: uses OpenAI-compatible API at your Base URL below. Key: {providerInfo.keyHint || '—'}</>
                  ) : (
                    <>Base URL hint: {providerInfo.baseUrl || '— (enter custom Base URL below for any platform)'} · Key: {providerInfo.keyHint || '—'}</>
                  )}
                </div>
                <input
                  type="password"
                  placeholder="API key for this model (leave empty to use .env key)"
                  value={newModel.api_key}
                  onChange={(e) => setNewModel({ ...newModel, api_key: e.target.value })}
                />
                <input
                  placeholder={`Base URL ${isCustomProvider ? '(required for custom platform)' : '(optional override)'} e.g. ${providerInfo.baseUrl || 'https://api.groq.com/openai/v1'}`}
                  value={newModel.base_url}
                  onChange={(e) => setNewModel({ ...newModel, base_url: e.target.value })}
                  style={isCustomProvider && !(newModel.base_url || '').trim() ? { border: '1px solid #d33' } : {}}
                />
                <div style={{ display: 'flex', gap: 6 }}>
                  <select
                    value={preset}
                    onChange={(e) => {
                      setPreset(e.target.value);
                      setNewModel({ ...newModel, system_prompt: ROLE_PRESETS[e.target.value] });
                    }}
                  >
                    {Object.keys(ROLE_PRESETS).map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                  <button onClick={doTestConnection} disabled={testing}>
                    {testing ? 'Testing…' : 'Test Connection'}
                  </button>
                  <button onClick={createAndAddNew}>Add to group</button>
                </div>
                {testResult && (
                  <div
                    style={{
                      padding: 8,
                      borderRadius: 6,
                      background: testResult.ok ? '#e8f7ee' : '#fdecec',
                      border: testResult.ok ? '1px solid #2a7' : '1px solid #d33',
                      color: testResult.ok ? '#14532d' : '#7f1d1d',
                      fontSize: 13,
                    }}
                  >
                    {testResult.ok
                      ? `✓ Connection successful${testResult.latency_ms != null ? ` (latency: ${testResult.latency_ms}ms)` : ''}${testResult.message ? ` — ${testResult.message}` : ''}`
                      : `✗ Connection failed: ${testResult.message || 'unknown error'}`}
                  </div>
                )}
              </div>
            )}
            {addDiag && (
              <div
                style={{
                  padding: 8,
                  borderRadius: 6,
                  marginBottom: 16,
                  maxWidth: 520,
                  background: addDiag.ok ? '#e8f7ee' : '#fdecec',
                  border: addDiag.ok ? '1px solid #2a7' : '1px solid #d33',
                  color: addDiag.ok ? '#14532d' : '#7f1d1d',
                  fontSize: 13,
                }}
              >
                {addDiag.ok ? '✓ ' : '✗ '}{addDiag.message}
              </div>
            )}

            {activeConv && (
              <>
                <div style={{ background: '#eef', padding: 10, borderRadius: 8, marginBottom: 12 }}>
                  <strong>User</strong>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{activeConv.original_prompt}</div>
                </div>
                {turns.map((t) => (
                  <TurnCard key={t.id} turn={t} />
                ))}
                {turns.length === 0 && <p>No turns yet — press Single turn or Start.</p>}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
