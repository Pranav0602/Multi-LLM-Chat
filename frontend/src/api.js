const RAW_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.DEV ? '' : 'https://multi-llm-chat-production.up.railway.app');
const BASE = RAW_URL.replace(/\/+$/, '');

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export const api = {
  listGroups: () => req('/groups'),
  createGroup: (name, description) =>
    req('/groups', { method: 'POST', body: JSON.stringify({ name, description }) }),
  listGroupModels: (gid) => req(`/groups/${gid}/models`),
  addGroupModel: (gid, body) =>
    req(`/groups/${gid}/models`, { method: 'POST', body: JSON.stringify(body) }),
  toggleGroupModel: (gid, linkId, body) =>
    req(`/groups/${gid}/models/${linkId}`, { method: 'PATCH', body: JSON.stringify(body) }),
  updateGroupModel: (gid, linkId, body) =>
    req(`/groups/${gid}/models/${linkId}`, { method: 'PATCH', body: JSON.stringify(body) }),
  removeGroupModel: (gid, linkId) =>
    req(`/groups/${gid}/models/${linkId}`, { method: 'DELETE' }),
  reorderGroupModels: (gid, orderedLinkIds) =>
    req(`/groups/${gid}/models/reorder`, {
      method: 'PUT',
      body: JSON.stringify({ ordered_link_ids: orderedLinkIds }),
    }),
  testModelConnection: (body) =>
    req('/models/test-connection', { method: 'POST', body: JSON.stringify(body) }),

  listModels: () => req('/models'),
  createModel: (body) => req('/models', { method: 'POST', body: JSON.stringify(body) }),

  createConversation: (body) =>
    req('/conversations', { method: 'POST', body: JSON.stringify(body) }),
  getConversation: (id) => req(`/conversations/${id}`),
  listTurns: (id) => req(`/conversations/${id}/turns`),
  singleTurn: (id) => req(`/conversations/${id}/turn`, { method: 'POST' }),
  start: (id, max_rounds) =>
    req(`/conversations/${id}/start`, { method: 'POST', body: JSON.stringify({ max_rounds }) }),
  cont: (id) => req(`/conversations/${id}/continue`, { method: 'POST', body: JSON.stringify({}) }),
  pause: (id) => req(`/conversations/${id}/pause`, { method: 'POST' }),
  stop: (id) => req(`/conversations/${id}/stop`, { method: 'POST' }),
  summarize: (id) => req(`/conversations/${id}/summarize`, { method: 'POST' }),
  retry: (id, turnNumber) =>
    req(`/conversations/${id}/retry/${turnNumber}`, { method: 'POST' }),
  preview: (id) => req(`/conversations/${id}/context-preview`),
};
