"""HTTP-based providers: OpenAI, Anthropic, Gemini, OpenRouter, Local."""
from __future__ import annotations

from typing import Any, AsyncIterator

import httpx

from ..config import settings
from .base import LLMResult


def _cfg(model_config: dict[str, Any], key: str, default: Any = "") -> Any:
    return model_config.get(key, default)


class OpenAIProvider:
    name = "openai"

    async def generate(self, messages, model_config) -> LLMResult:
        api_key = model_config.get("api_key") or settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured (set .env or per-model api_key)")
        model = _cfg(model_config, "model_name", "gpt-4o-mini")
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": _cfg(model_config, "temperature", 0.7),
                    "max_tokens": _cfg(model_config, "max_output_tokens", 1024),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResult(
            text=choice,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            raw=data,
        )

    async def astream(self, messages, model_config) -> AsyncIterator[str]:
        result = await self.generate(messages, model_config)
        yield result.text


class AnthropicProvider:
    name = "anthropic"

    async def generate(self, messages, model_config) -> LLMResult:
        api_key = model_config.get("api_key") or settings.ANTHROPIC_API_KEY
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured (set .env or per-model api_key)")
        model = _cfg(model_config, "model_name", "claude-3-5-sonnet-latest")
        system = ""
        convo = []
        for m in messages:
            if m["role"] == "system":
                system += m["content"] + "\n"
            else:
                convo.append(m)
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model,
                    "max_tokens": _cfg(model_config, "max_output_tokens", 1024),
                    "system": system or "You are a helpful researcher.",
                    "messages": convo,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        usage = data.get("usage", {})
        return LLMResult(text, usage.get("input_tokens", 0), usage.get("output_tokens", 0), data)

    async def astream(self, messages, model_config) -> AsyncIterator[str]:
        yield (await self.generate(messages, model_config)).text


class GeminiProvider:
    name = "gemini"

    async def generate(self, messages, model_config) -> LLMResult:
        api_key = model_config.get("api_key") or settings.GEMINI_API_KEY
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured (set .env or per-model api_key)")
        model = _cfg(model_config, "model_name", "gemini-1.5-flash")
        # Flatten to a single prompt for REST simplicity.
        prompt = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={api_key}"
        )
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
            resp.raise_for_status()
            data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            text = str(data)
        return LLMResult(text=text, raw=data)

    async def astream(self, messages, model_config) -> AsyncIterator[str]:
        yield (await self.generate(messages, model_config)).text


class OpenRouterProvider:
    name = "openrouter"

    async def generate(self, messages, model_config) -> LLMResult:
        api_key = model_config.get("api_key") or settings.OPENROUTER_API_KEY
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured (set .env or per-model api_key)")
        model = _cfg(model_config, "model_name", "openai/gpt-4o-mini")
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": _cfg(model_config, "temperature", 0.7),
                    "max_tokens": _cfg(model_config, "max_output_tokens", 1024),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResult(choice, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), data)

    async def astream(self, messages, model_config) -> AsyncIterator[str]:
        yield (await self.generate(messages, model_config)).text


class LocalModelProvider:
    """Call any OpenAI-compatible local server (Ollama, LM Studio, vLLM)."""

    name = "local"

    async def generate(self, messages, model_config) -> LLMResult:
        base_url = model_config.get("base_url", "http://localhost:11434/v1")
        model = _cfg(model_config, "model_name", "llama3")
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json={"model": model, "messages": messages},
            )
            resp.raise_for_status()
            data = resp.json()
        return LLMResult(text=data["choices"][0]["message"]["content"], raw=data)

    async def astream(self, messages, model_config) -> AsyncIterator[str]:
        yield (await self.generate(messages, model_config)).text


class GenericOpenAICompatibleProvider:
    """Fallback for any custom platform exposing an OpenAI-compatible API.

    The user types any platform/provider name plus a Base URL, e.g.
    Groq (https://api.groq.com/openai/v1), Together, Mistral, DeepSeek,
    Azure OpenAI, Ollama remote, vLLM, LM Studio, etc.

    Sends POST {base_url}/chat/completions with {model, messages}.
    """

    name = "custom"

    async def generate(self, messages, model_config) -> LLMResult:
        import httpx

        base_url = (model_config.get("base_url") or "").strip()
        if not base_url:
            raise ValueError(
                "base_url is required for custom provider "
                f"'{model_config.get('provider')}'. Enter the platform's "
                "OpenAI-compatible base URL, e.g. https://api.groq.com/openai/v1"
            )
        api_key = model_config.get("api_key") or ""
        model = _cfg(model_config, "model_name", "")
        if not (model or "").strip():
            raise ValueError("model_name is required for custom provider.")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": _cfg(model_config, "temperature", 0.7),
                    "max_tokens": _cfg(model_config, "max_output_tokens", 1024),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResult(
            text=choice,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            raw=data,
        )

    async def astream(self, messages, model_config) -> AsyncIterator[str]:
        yield (await self.generate(messages, model_config)).text


class CodeCraftProvider:
    """CodeCraft API — OpenAI-compatible (https://codecraftapi.com/v1).

    Uses CODECRAFT_API_KEY; model_name is any id from GET /models
    e.g. gemma-2-2b, muse-spark-1.1, gpt-5.6-sol.
    """

    name = "codecraft"

    def _auth(self, model_config) -> str:
        return model_config.get("api_key") or settings.CODECRAFT_API_KEY

    def _base_url(self, model_config) -> str:
        return (
            model_config.get("base_url")
            or getattr(settings, "CODECRAFT_BASE_URL", "https://codecraftapi.com/v1")
            or "https://codecraftapi.com/v1"
        ).rstrip("/")

    async def generate(self, messages, model_config) -> LLMResult:
        api_key = self._auth(model_config)
        if not api_key:
            raise RuntimeError("CODECRAFT_API_KEY is not configured (set .env or per-model api_key)")
        model = _cfg(model_config, "model_name", "gemma-2-2b")
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{self._base_url(model_config)}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": _cfg(model_config, "temperature", 0.7),
                    "max_tokens": _cfg(model_config, "max_output_tokens", 1024),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResult(
            text=choice,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            raw=data,
        )

    async def astream(self, messages, model_config) -> AsyncIterator[str]:
        yield (await self.generate(messages, model_config)).text
