"""LLM provider abstraction — plan section 4.

The conversation manager never talks to OpenAI/Anthropic/Gemini directly;
it talks to LLMManager, which dispatches to an LLMProvider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        messages: list[dict[str, str]],
        model_config: dict[str, Any],
    ) -> LLMResult:
        ...

    async def astream(
        self,
        messages: list[dict[str, str]],
        model_config: dict[str, Any],
    ) -> AsyncIterator[str]:
        ...
