"""LLMManager — selects provider from model.provider (plan section 4)."""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from ..config import settings
from .base import LLMResult
from .mock_provider import MockProvider
from .providers import (
    AnthropicProvider,
    CodeCraftProvider,
    GeminiProvider,
    GenericOpenAICompatibleProvider,
    LocalModelProvider,
    OpenAIProvider,
    OpenRouterProvider,
)


class LLMManager:
    def __init__(self) -> None:
        generic = GenericOpenAICompatibleProvider()
        self._providers = {
            "mock": MockProvider(),
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
            "gemini": GeminiProvider(),
            "openrouter": OpenRouterProvider(),
            "local": LocalModelProvider(),
            "codecraft": CodeCraftProvider(),
            # Explicit aliases for any custom OpenAI-compatible platform.
            "custom": generic,
            "generic": generic,
            "openai-compatible": generic,
        }
        self._generic = generic

    def get_provider(self, provider_name: str, model_config: dict[str, Any] | None = None):
        key = (provider_name or "mock").lower().strip()
        if key in self._providers:
            return self._providers[key]
        # Any unknown platform name falls back to the generic OpenAI-compatible
        # provider as long as a base_url is supplied. This is what lets users
        # type literally any platform (groq, together, mistral, deepseek, ...).
        if model_config and (model_config.get("base_url") or "").strip():
            return self._generic
        raise ValueError(
            f"Unknown LLM provider: {provider_name}. Use one of {sorted(self._providers)} "
            "or enter any custom platform name together with its OpenAI-compatible base URL."
        )

    @staticmethod
    def model_to_config(model) -> dict[str, Any]:
        """Never hard-code model names in app logic — read from DB row."""
        return {
            "name": getattr(model, "name", ""),
            "provider": getattr(model, "provider", "mock"),
            "model_name": getattr(model, "model_name", ""),
            "temperature": getattr(model, "temperature", settings.DEFAULT_TEMPERATURE),
            "max_output_tokens": getattr(model, "max_output_tokens", settings.MAX_OUTPUT_TOKENS),
            # Per-model credentials from UI; empty = provider falls back to .env key.
            "api_key": getattr(model, "api_key", "") or "",
            "base_url": getattr(model, "base_url", "") or "",
        }

    async def generate(self, model, messages: list[dict[str, str]]) -> LLMResult:
        config = self.model_to_config(model)
        provider = self.get_provider(getattr(model, "provider", "mock"), config)
        last_exc: Exception | None = None
        for _ in range(max(1, settings.LLM_MAX_RETRIES)):
            try:
                return await asyncio.wait_for(
                    provider.generate(messages, config),
                    timeout=settings.LLM_TIMEOUT_SECONDS + 5,
                )
            except Exception as exc:  # noqa: BLE001 — must survive provider failures
                last_exc = exc
        assert last_exc is not None
        raise last_exc

    async def astream(self, model, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        config = self.model_to_config(model)
        provider = self.get_provider(getattr(model, "provider", "mock"), config)
        async for chunk in provider.astream(messages, config):
            yield chunk

    async def verify_connection(self, model_config: dict[str, Any]) -> dict[str, Any]:
        """Live connection test with exact diagnostics.

        Sends a minimal ping ("Reply with 'OK'", max_tokens=5, 10s timeout)
        and classifies failures into actionable messages.
        Returns { ok, latency_ms, error_code, message }.
        """
        import time

        import httpx

        provider_name = (model_config.get("provider") or "").strip().lower()
        if not provider_name:
            return {
                "ok": False,
                "latency_ms": None,
                "error_code": "missing_provider",
                "message": "Platform / provider is required. Type any name (e.g. groq, together, mistral) plus its base URL.",
            }
        if provider_name not in self._providers:
            # Custom platform: accept any name if an OpenAI-compatible base_url is given.
            if not (model_config.get("base_url") or "").strip():
                return {
                    "ok": False,
                    "latency_ms": None,
                    "error_code": "missing_base_url",
                    "message": f"Unknown platform '{model_config.get('provider')}'. Add its OpenAI-compatible base URL (e.g. https://api.groq.com/openai/v1) to use it as a custom provider.",
                }
        if not (model_config.get("model_name") or "").strip():
            return {
                "ok": False,
                "latency_ms": None,
                "error_code": "missing_model_name",
                "message": "model_name is required. Check the model ID spelling for the chosen provider.",
            }
        # Mock always succeeds instantly (used by tests/seed).
        if provider_name == "mock":
            return {
                "ok": True,
                "latency_ms": 1.0,
                "error_code": None,
                "message": "Mock provider connection successful.",
            }

        provider = self.get_provider(provider_name, model_config)
        ping = [{"role": "user", "content": "Reply with 'OK'"}]
        cfg = {
            **model_config,
            "temperature": 0,
            "max_output_tokens": 5,
        }
        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(provider.generate(ping, cfg), timeout=10.0)
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            preview = (result.text or "")[:120]
            return {
                "ok": True,
                "latency_ms": latency_ms,
                "error_code": None,
                "message": f"Connection successful (latency: {latency_ms}ms). Model replied: {preview!r}" if preview else f"Connection successful (latency: {latency_ms}ms).",
            }
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                "error_code": "timeout",
                "message": "Connection timed out after 10s. The provider or local server is too slow or unreachable.",
            }
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            body = ""
            try:
                body = (exc.response.text or "")[:300] if exc.response is not None else ""
            except Exception:
                pass
            if status in (401, 403):
                return {
                    "ok": False,
                    "latency_ms": None,
                    "error_code": f"http_{status}",
                    "message": f"Authentication failed [HTTP {status}]. The provided API key is invalid or unauthorized. {body}",
                }
            if status == 404:
                return {
                    "ok": False,
                    "latency_ms": None,
                    "error_code": "http_404",
                    "message": f"Model '{model_config.get('model_name')}' was not found on provider '{provider_name}' [HTTP 404]. Check the model ID spelling. {body}",
                }
            if status == 429:
                return {
                    "ok": False,
                    "latency_ms": None,
                    "error_code": "http_429",
                    "message": f"Rate limit exceeded or quota exhausted for this API key [HTTP 429]. {body}",
                }
            return {
                "ok": False,
                "latency_ms": None,
                "error_code": f"http_{status}" if status else "http_error",
                "message": f"Provider request failed [HTTP {status}]: {body or exc}",
            }
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            base = model_config.get("base_url") or "the provider endpoint"
            return {
                "ok": False,
                "latency_ms": None,
                "error_code": "connection_refused",
                "message": f"Could not connect to {base}. Ensure the service (e.g. Ollama, LM Studio) is running and reachable. Details: {exc}",
            }
        except (httpx.TimeoutException, TimeoutError) as exc:
            return {
                "ok": False,
                "latency_ms": None,
                "error_code": "timeout",
                "message": f"Request timed out: {exc}. The provider or local server did not respond in time.",
            }
        except RuntimeError as exc:
            msg = str(exc)
            if "not configured" in msg or "API key" in msg or "API_KEY" in msg:
                return {
                    "ok": False,
                    "latency_ms": None,
                    "error_code": "missing_api_key",
                    "message": f"API key is required for provider '{provider_name}' and none is configured in .env or model credentials. Details: {msg}",
                }
            return {"ok": False, "latency_ms": None, "error_code": "runtime_error", "message": msg}
        except ValueError as exc:
            return {"ok": False, "latency_ms": None, "error_code": "invalid_config", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "latency_ms": None,
                "error_code": type(exc).__name__,
                "message": f"{type(exc).__name__}: {exc}",
            }


async def verify_model_connection(model_config: dict[str, Any]) -> dict[str, Any]:
    """Module-level helper used by routers (plan §2)."""
    return await LLMManager().verify_connection(model_config)


llm_manager = LLMManager()
