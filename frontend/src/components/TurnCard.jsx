import React, { useState } from 'react';

function parseContext(inputContext) {
  try {
    const p = JSON.parse(inputContext || '{}');
    return typeof p === 'object' && p !== null ? p : {};
  } catch {
    return {};
  }
}

export function TurnCard({ turn }) {
  const failed = turn.status === 'error';
  const [showPrompt, setShowPrompt] = useState(false);
  const ctx = parseContext(turn.input_context);
  const role = turn.role_name || ctx.role_name || null;
  const systemPrompt = ctx.system_prompt || (ctx.messages && ctx.messages[0]?.content) || '';
  return (
    <div
      style={{
        border: '1px solid #ddd',
        borderLeft: failed ? '4px solid #d33' : '4px solid #2a7',
        borderRadius: 8,
        padding: 12,
        marginBottom: 10,
        background: failed ? '#fff5f5' : '#fff',
      }}
    >
      <div style={{ fontSize: 13, color: '#555', marginBottom: 6, display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <strong>{turn.model_name || `model ${turn.model_id}`}</strong>
        {role && (
          <span
            style={{
              background: '#6c3ce0',
              color: '#fff',
              borderRadius: 10,
              padding: '1px 8px',
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            [{role}]
          </span>
        )}
        <span>
          {turn.provider ? ` · ${turn.provider}` : ''} · Round {turn.round_number} · Turn{' '}
          {turn.turn_number} · {new Date(turn.created_at).toLocaleString()}
          {turn.input_tokens || turn.output_tokens
            ? ` · ⬆${turn.input_tokens} ⬇${turn.output_tokens}`
            : ''}
        </span>
      </div>
      {failed ? (
        <div style={{ color: '#a00' }}>Error: {turn.error_message}</div>
      ) : (
        <div style={{ whiteSpace: 'pre-wrap' }}>{turn.response}</div>
      )}
      <div style={{ marginTop: 8 }}>
        <button
          onClick={() => setShowPrompt((s) => !s)}
          style={{ fontSize: 12, background: '#f0f0f0', border: '1px solid #ccc', borderRadius: 4, cursor: 'pointer' }}
        >
          {showPrompt ? 'Hide Prompting Context' : 'View Prompting Context'}
        </button>
        {showPrompt && (
          <pre
            style={{
              fontSize: 12,
              background: '#fafafa',
              border: '1px solid #eee',
              borderRadius: 4,
              padding: 8,
              whiteSpace: 'pre-wrap',
              marginTop: 6,
              maxHeight: 300,
              overflow: 'auto',
            }}
          >
            {systemPrompt ? `SYSTEM PROMPT:\n${systemPrompt}\n\n` : ''}
            {ctx.chat_type ? `CHAT TYPE: ${ctx.chat_type}\n` : ''}
            {ctx.recent_turn_numbers ? `RECENT TURNS: [${ctx.recent_turn_numbers.join(', ')}]\n\n` : ''}
            FULL DEBUG PAYLOAD:\n{JSON.stringify(ctx, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
