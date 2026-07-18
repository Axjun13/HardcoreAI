"""LLM backends for the HardcoreAI agent.

Three providers, one interface. Each `*_complete` coroutine takes the OpenAI-style
`messages` list and returns the full assistant text (no streaming — the agent
loop parses the whole reply at once).

  - llamacpp   — local OpenAI-compatible server (Prism Bonsai 8B, 1-bit quant)
  - openrouter — OpenRouter cloud (gpt-oss-120b)
  - gemini     — Google Gemini API (gemini-2.5-flash)
  - deepseek   — DeepSeek through OpenRouter, or the direct DeepSeek API
  - sarvam     — Sarvam chat-compatible API (configurable URL/model)

Keys/URLs come from backend/.env. A provider raises RuntimeError if its key is
missing, so the failure is explicit rather than a confusing 401 later.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

# Importing core.config for its side effect: it calls load_dotenv(backend/.env)
# at import time. Without this, the OPENROUTER/GEMINI keys below would be read
# before the .env is loaded (whenever this module is imported first) and get
# captured as empty strings.
import core.config  # noqa: F401

# ---------------------------------------------------------------------------
# Provider configuration — read once at import time from the environment.
# ---------------------------------------------------------------------------

LLAMACPP_URL = os.environ.get("LLAMACPP_URL", "http://127.0.0.1:62021").rstrip("/")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "prism-bonsai-8b-1bit")
OPENROUTER_HTTP_REFERER = os.environ.get(
    "OPENROUTER_HTTP_REFERER",
    "http://127.0.0.1:62017",
).strip()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-120b")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/v1/chat/completions").strip()
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_OPENROUTER_MODEL = os.environ.get(
    "DEEPSEEK_OPENROUTER_MODEL",
    OPENROUTER_MODEL,
).strip()
DEEPSEEK_OPENROUTER_FALLBACK_MODEL = os.environ.get(
    "DEEPSEEK_OPENROUTER_FALLBACK_MODEL",
    "deepseek/deepseek-v3.2",
).strip()

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "").strip()
SARVAM_URL = os.environ.get("SARVAM_URL", "https://api.sarvam.ai/v1/chat/completions").strip()
SARVAM_MODEL = os.environ.get("SARVAM_MODEL", "sarvam-30b")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")

# Per-provider display metadata, surfaced to the frontend so the panel can list
# what is actually usable (a provider with no key is reported unavailable).
PROVIDERS = {
    "llamacpp": {
        "label": "llama.cpp (Prism Bonsai 8B)",
        "model": LLAMACPP_MODEL,
        "local": True,
    },
    "openrouter": {
        "label": "OpenRouter (gpt-oss-120b)",
        "model": OPENROUTER_MODEL,
        "local": False,
    },
    "gemini": {
        "label": "Google Gemini",
        "model": GEMINI_MODEL,
        "local": False,
    },
    "deepseek": {
        "label": "DeepSeek",
        "model": (
            DEEPSEEK_MODEL
            if DEEPSEEK_API_KEY
            else DEEPSEEK_OPENROUTER_MODEL or DEEPSEEK_MODEL
        ),
        "local": False,
    },
    "sarvam": {
        "label": "Sarvam",
        "model": SARVAM_MODEL,
        "local": False,
    },
    "ollama": {
        "label": "Ollama (local)",
        "model": OLLAMA_MODEL,
        "local": True,
    },
}

# Generation is deterministic-ish and short: the agent only needs a THINK line
# plus one CALL, or a brief final answer.
TEMPERATURE = 0.1
MAX_TOKENS = 4096
HTTP_TIMEOUT = 120.0


def context_window_for_model(model: str, provider: str = "") -> int:
    """Return the usable context window for the configured model.

    Deployments can always override the model metadata with
    ``<PROVIDER>_CONTEXT_WINDOW`` (or the generic ``AGENT_CONTEXT_WINDOW``).
    The built-in values cover the providers shipped in the settings UI.
    """
    provider_key = provider.strip().upper()
    override = os.environ.get(f"{provider_key}_CONTEXT_WINDOW", "") if provider_key else ""
    override = override or os.environ.get("AGENT_CONTEXT_WINDOW", "")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass

    name = (model or "").casefold()
    if "gemini-2.5-flash" in name:
        return 1_048_576
    if "deepseek-v4" in name:
        return 1_000_000
    if provider == "deepseek" and DEEPSEEK_API_KEY and name in {"deepseek-chat", "deepseek-reasoner"}:
        # The legacy aliases currently route to DeepSeek V4 on the official API.
        return 1_000_000
    if "deepseek" in name:
        return 131_072
    if "sarvam-105b" in name:
        return 131_072
    if "sarvam-30b" in name:
        return 65_536
    if "sarvam-m" in name:
        return 8_192
    if "gpt-oss" in name:
        return 131_072
    if provider in {"llamacpp", "ollama"}:
        return 32_768
    return 32_768


def model_for_provider(provider: str) -> str:
    """Resolve the model id the next completion for ``provider`` will use."""
    if provider == "deepseek":
        return DEEPSEEK_MODEL if DEEPSEEK_API_KEY else DEEPSEEK_OPENROUTER_MODEL
    meta = PROVIDERS.get(provider) or {}
    return str(meta.get("model") or "unknown")


def context_window_for_provider(provider: str) -> int:
    return context_window_for_model(model_for_provider(provider), provider)


class CompletionText(str):
    """String-compatible completion carrying provider token-usage metadata."""

    usage: dict[str, int]
    model: str
    context_window: int

    def __new__(
        cls,
        value: str,
        *,
        usage: dict[str, int] | None = None,
        model: str = "",
        context_window: int = 0,
    ):
        obj = super().__new__(cls, value)
        obj.usage = usage or {}
        obj.model = model
        obj.context_window = context_window
        return obj


def _normalise_openai_usage(data: dict) -> dict[str, int]:
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


class LLMError(RuntimeError):
    """Raised when a provider is misconfigured or the upstream call fails."""


def available_providers() -> list[dict]:
    """Provider descriptors for the frontend, with an `available` flag."""
    out = []
    for key, meta in PROVIDERS.items():
        if key == "openrouter":
            available = bool(OPENROUTER_API_KEY)
        elif key == "gemini":
            available = bool(GEMINI_API_KEY)
        elif key == "deepseek":
            available = bool(
                DEEPSEEK_API_KEY
                or (
                    OPENROUTER_API_KEY
                    and DEEPSEEK_OPENROUTER_MODEL.casefold().startswith("deepseek/")
                )
            )
        elif key == "sarvam":
            available = bool(SARVAM_API_KEY)
        else:  # llamacpp and ollama need no key — availability is "is the server up?",
            available = True  # which we can't know without a probe, so assume yes.
        model = model_for_provider(key)
        out.append({
            "id": key,
            "available": available,
            **meta,
            "model": model,
            "context_window": context_window_for_model(model, key),
        })
    return out


async def _openai_style_complete(
    url: str, model: str, messages: list[dict], headers: dict | None = None
) -> str:
    """POST to any /v1/chat/completions endpoint and return the message text."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    if url.startswith("https://openrouter.ai/"):
        payload["provider"] = {
            "allow_fallbacks": True,
            "sort": "throughput",
        }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers or {})
        except httpx.RequestError as exc:
            raise LLMError(f"Failed to connect to {url}. Is the LLM service running? (Error: {exc})") from exc

        if resp.status_code != 200:
            raise LLMError(f"{url} returned {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected response shape from {url}: {data}") from exc
    response_model = str(data.get("model") or model)
    return CompletionText(
        content,
        usage=_normalise_openai_usage(data),
        model=response_model,
        context_window=context_window_for_model(response_model),
    )


async def _openai_style_stream(
    url: str, model: str, messages: list[dict], headers: dict | None = None
) -> AsyncIterator[str]:
    """Yield content deltas from an OpenAI-compatible SSE response."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": True,
    }
    if url.startswith("https://openrouter.ai/"):
        payload["provider"] = {
            "allow_fallbacks": True,
            "sort": "throughput",
        }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            async with client.stream("POST", url, json=payload, headers=headers or {}) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode(errors="replace")
                    raise LLMError(f"{url} returned {resp.status_code}: {body[:300]}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        data = json.loads(raw)
                        delta = data["choices"][0].get("delta") or {}
                        content = delta.get("content") or ""
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if content:
                        yield content
        except httpx.RequestError as exc:
            raise LLMError(f"Failed to connect to {url}. Is the LLM service running? (Error: {exc})") from exc


async def _gemini_stream(messages: list[dict]) -> AsyncIterator[str]:
    """Yield text deltas from Gemini's streaming generate-content endpoint."""
    if not GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not set in backend/.env.")

    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        }
        for m in messages
        if m["role"] in ("user", "assistant")
    ]
    payload: dict = {
        "contents": contents,
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": MAX_TOKENS},
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:streamGenerateContent?alt=sse"
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            async with client.stream(
                "POST", url, json=payload, headers={"x-goog-api-key": GEMINI_API_KEY}
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode(errors="replace")
                    raise LLMError(f"Gemini returned {resp.status_code}: {body[:300]}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                        parts = data["candidates"][0]["content"]["parts"]
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    text = "".join(part.get("text", "") for part in parts)
                    if text:
                        yield text
        except httpx.RequestError as exc:
            raise LLMError(f"Failed to connect to Gemini API. (Error: {exc})") from exc


async def _llamacpp_complete(messages: list[dict]) -> str:
    return await _openai_style_complete(
        f"{LLAMACPP_URL}/v1/chat/completions", LLAMACPP_MODEL, messages
    )


async def _ollama_complete(messages: list[dict]) -> str:
    return await _openai_style_complete(
        f"{OLLAMA_URL}/v1/chat/completions", OLLAMA_MODEL, messages
    )


async def _openrouter_complete(messages: list[dict]) -> str:
    if not OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set in backend/.env.")
    return await _openai_style_complete(
        "https://openrouter.ai/api/v1/chat/completions",
        OPENROUTER_MODEL,
        messages,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "X-Title": "HardcoreAI",
        },
    )


async def _gemini_complete(messages: list[dict]) -> str:
    """Gemini has its own schema — translate the OpenAI message list to it.

    System messages are merged into `system_instruction`; user/assistant turns
    become `contents` with roles user/model.
    """
    if not GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not set in backend/.env.")

    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        }
        for m in messages
        if m["role"] in ("user", "assistant")
    ]
    payload: dict = {
        "contents": contents,
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": MAX_TOKENS},
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            resp = await client.post(
                url, json=payload, headers={"x-goog-api-key": GEMINI_API_KEY}
            )
        except httpx.RequestError as exc:
            raise LLMError(f"Failed to connect to Gemini API. (Error: {exc})") from exc
            
        if resp.status_code != 200:
            raise LLMError(f"Gemini returned {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
    try:
        content = "".join(
            part.get("text", "")
            for part in data["candidates"][0]["content"]["parts"]
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected Gemini response: {data}") from exc
    usage_meta = data.get("usageMetadata") or {}
    prompt_tokens = int(usage_meta.get("promptTokenCount") or 0)
    total_tokens = int(usage_meta.get("totalTokenCount") or 0)
    completion_tokens = max(
        int(usage_meta.get("candidatesTokenCount") or 0),
        total_tokens - prompt_tokens,
    )
    return CompletionText(
        content,
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens or prompt_tokens + completion_tokens,
        },
        model=GEMINI_MODEL,
        context_window=context_window_for_model(GEMINI_MODEL, "gemini"),
    )


async def _deepseek_complete(messages: list[dict]) -> str:
    if DEEPSEEK_API_KEY:
        return await _openai_style_complete(
            DEEPSEEK_URL,
            DEEPSEEK_MODEL,
            messages,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        )

    if OPENROUTER_API_KEY and DEEPSEEK_OPENROUTER_MODEL.casefold().startswith("deepseek/"):
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "X-Title": "HardcoreAI",
        }
        last_error: LLMError | None = None
        models = dict.fromkeys([
            DEEPSEEK_OPENROUTER_MODEL,
            DEEPSEEK_OPENROUTER_FALLBACK_MODEL,
        ])
        for model in models:
            if not model.casefold().startswith("deepseek/"):
                continue
            try:
                return await _openai_style_complete(
                    "https://openrouter.ai/api/v1/chat/completions",
                    model,
                    messages,
                    headers=headers,
                )
            except LLMError as exc:
                last_error = exc
        if last_error:
            raise last_error

    if OPENROUTER_API_KEY:
        raise LLMError(
            "DeepSeek through OpenRouter requires OPENROUTER_MODEL (or "
            "DEEPSEEK_OPENROUTER_MODEL) to use a deepseek/* model id."
        )
    raise LLMError(
        "Configure OPENROUTER_API_KEY with a deepseek/* model, or set "
        "DEEPSEEK_API_KEY in backend/.env."
    )


async def _sarvam_complete(messages: list[dict]) -> str:
    if not SARVAM_API_KEY:
        raise LLMError("SARVAM_API_KEY is not set in backend/.env.")
    return await _openai_style_complete(
        SARVAM_URL,
        SARVAM_MODEL,
        messages,
        headers={"Authorization": f"Bearer {SARVAM_API_KEY}", "api-subscription-key": SARVAM_API_KEY},
    )


_DISPATCH = {
    "llamacpp": _llamacpp_complete,
    "ollama": _ollama_complete,
    "openrouter": _openrouter_complete,
    "gemini": _gemini_complete,
    "deepseek": _deepseek_complete,
    "sarvam": _sarvam_complete,
}


async def complete(provider: str, messages: list[dict]) -> str:
    """Run a single completion against the named provider."""
    fn = _DISPATCH.get(provider)
    if fn is None:
        raise LLMError(f"Unknown provider '{provider}'. Choose: {list(_DISPATCH)}")
    result = await fn(messages)
    if isinstance(result, CompletionText):
        # Provider-specific overrides and ambiguous aliases are resolved here,
        # after the generic OpenAI-compatible client has returned.
        result.context_window = context_window_for_model(result.model, provider)
        return result
    model = model_for_provider(provider)
    return CompletionText(
        str(result),
        model=model,
        context_window=context_window_for_model(model, provider),
    )


async def stream(provider: str, messages: list[dict]) -> AsyncIterator[str]:
    """Stream visible assistant text from the named provider as it is generated."""
    if provider == "gemini":
        async for chunk in _gemini_stream(messages):
            yield chunk
        return

    if provider == "deepseek" and not DEEPSEEK_API_KEY:
        if not OPENROUTER_API_KEY:
            raise LLMError("Configure OPENROUTER_API_KEY or DEEPSEEK_API_KEY in backend/.env.")
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "X-Title": "HardcoreAI",
        }
        last_error: LLMError | None = None
        models = dict.fromkeys([
            DEEPSEEK_OPENROUTER_MODEL,
            DEEPSEEK_OPENROUTER_FALLBACK_MODEL,
        ])
        for model in models:
            if not model.casefold().startswith("deepseek/"):
                continue
            emitted = False
            try:
                async for chunk in _openai_style_stream(
                    "https://openrouter.ai/api/v1/chat/completions", model, messages, headers
                ):
                    emitted = True
                    yield chunk
                if emitted:
                    return
            except LLMError as exc:
                if emitted:
                    raise
                last_error = exc
        if last_error:
            raise last_error
        raise LLMError("No valid DeepSeek model is configured for OpenRouter.")

    configs = {
        "llamacpp": (f"{LLAMACPP_URL}/v1/chat/completions", LLAMACPP_MODEL, {}),
        "ollama": (f"{OLLAMA_URL}/v1/chat/completions", OLLAMA_MODEL, {}),
        "openrouter": (
            "https://openrouter.ai/api/v1/chat/completions",
            OPENROUTER_MODEL,
            {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": OPENROUTER_HTTP_REFERER,
                "X-Title": "HardcoreAI",
            },
        ),
        "deepseek": (
            DEEPSEEK_URL if DEEPSEEK_API_KEY else "https://openrouter.ai/api/v1/chat/completions",
            DEEPSEEK_MODEL if DEEPSEEK_API_KEY else DEEPSEEK_OPENROUTER_MODEL,
            (
                {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
                if DEEPSEEK_API_KEY
                else {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": OPENROUTER_HTTP_REFERER,
                    "X-Title": "HardcoreAI",
                }
            ),
        ),
        "sarvam": (
            SARVAM_URL,
            SARVAM_MODEL,
            {"Authorization": f"Bearer {SARVAM_API_KEY}", "api-subscription-key": SARVAM_API_KEY},
        ),
    }
    if provider not in configs:
        raise LLMError(f"Unknown provider '{provider}'. Choose: {list(_DISPATCH)}")
    if provider == "openrouter" and not OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set in backend/.env.")
    if provider == "sarvam" and not SARVAM_API_KEY:
        raise LLMError("SARVAM_API_KEY is not set in backend/.env.")

    url, model, headers = configs[provider]
    async for chunk in _openai_style_stream(url, model, messages, headers):
        yield chunk
