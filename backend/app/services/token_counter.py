"""Token estimation (plan section 17).

Prefers token-based budgets over turn counts because responses vary in length.
Uses a cheap char-based heuristic so no heavy tokenizer dependency is required.
Approx: 1 token ~= 4 chars for English text.
"""
from __future__ import annotations


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    # Small per-message overhead mirrors chat-format framing.
    return sum(estimate_tokens(m.get("content", "")) + 4 for m in messages)
