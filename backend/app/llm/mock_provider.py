"""Mock provider — always available, used for dev/tests and V1 single-LLM check."""
from __future__ import annotations

from typing import Any, AsyncIterator

from .base import LLMResult


class MockProvider:
    name = "mock"

    async def generate(
        self,
        messages: list[dict[str, str]],
        model_config: dict[str, Any],
    ) -> LLMResult:
        model_label = model_config.get("name", model_config.get("model_name", "Mock"))
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        text = (
            f"[{model_label} mock response] "
            f"Received {len(messages)} message(s). "
            f"Last user content preview: {last_user[:300]}"
        )
        return LLMResult(
            text=text,
            input_tokens=sum(len(m.get("content", "")) // 4 for m in messages),
            output_tokens=len(text) // 4,
        )

    async def astream(
        self,
        messages: list[dict[str, str]],
        model_config: dict[str, Any],
    ) -> AsyncIterator[str]:
        result = await self.generate(messages, model_config)
        for word in result.text.split():
            yield word + " "
