"""Local LLM clients plus the authenticated HardcoreAI cloud gateway.

Only llama.cpp and Ollama are contacted directly. Every legacy cloud-provider
selection is kept as a compatibility alias, but is sent to the server-owned
model policy at ``HARDCOREAI_PROXY_URL`` with the user's Supabase access token.
Provider API keys are intentionally not read by the distributed application.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

import core.config  # noqa: F401 - loads public/local configuration
from core.security import request_access_token

LLAMACPP_URL = os.environ.get("LLAMACPP_URL", "http://127.0.0.1:62021").rstrip("/")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "prism-bonsai-8b-1bit")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
CLOUD_PROXY_URL = os.environ.get(
    "HARDCOREAI_PROXY_URL",
    "https://hardcoreai-proxy-server.vercel.app",
).rstrip("/")

TEMPERATURE = 0.1
MAX_TOKENS = 4096
HTTP_TIMEOUT = 120.0
CLOUD_PROVIDER_ALIASES = {"cloud", "openrouter", "gemini", "deepseek", "sarvam"}

PROVIDERS = {
    "llamacpp": {
        "label": "llama.cpp (local)",
        "model": LLAMACPP_MODEL,
        "local": True,
    },
    "ollama": {
        "label": "Ollama (local)",
        "model": OLLAMA_MODEL,
        "local": True,
    },
    # Compatibility aliases preserve saved UI preferences while all paid calls
    # use the same gateway and its mode-based, server-owned model assignment.
    "cloud": {
        "label": "HardcoreAI Cloud",
        "model": "server-selected",
        "local": False,
    },
    "openrouter": {
        "label": "HardcoreAI Cloud",
        "model": "server-selected",
        "local": False,
    },
    "gemini": {
        "label": "HardcoreAI Cloud",
        "model": "server-selected",
        "local": False,
    },
    "deepseek": {
        "label": "HardcoreAI Cloud",
        "model": "server-selected",
        "local": False,
    },
    "sarvam": {
        "label": "HardcoreAI Cloud",
        "model": "server-selected",
        "local": False,
    },
}


class CompletionText(str):
    """String-compatible completion carrying token-usage metadata."""

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


class LLMError(RuntimeError):
    """A sanitized local/provider failure."""


def context_window_for_model(model: str, provider: str = "") -> int:
    provider_key = provider.strip().upper()
    override = os.environ.get(f"{provider_key}_CONTEXT_WINDOW", "") if provider_key else ""
    override = override or os.environ.get("AGENT_CONTEXT_WINDOW", "")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass

    name = (model or "").casefold()
    if "gemini" in name:
        return 1_048_576
    if "deepseek" in name or "gpt-oss" in name:
        return 131_072
    if provider in CLOUD_PROVIDER_ALIASES or model == "server-selected":
        return int(os.environ.get("CLOUD_CONTEXT_WINDOW", "131072"))
    return 32_768


def model_for_provider(provider: str) -> str:
    meta = PROVIDERS.get(provider) or {}
    return str(meta.get("model") or "unknown")


def context_window_for_provider(provider: str) -> int:
    return context_window_for_model(model_for_provider(provider), provider)


def available_providers() -> list[dict]:
    return [
        {
            "id": provider,
            "available": bool(CLOUD_PROXY_URL)
            if provider in CLOUD_PROVIDER_ALIASES
            else True,
            **metadata,
            "context_window": context_window_for_provider(provider),
        }
        for provider, metadata in PROVIDERS.items()
    ]


def _normalise_openai_usage(data: dict) -> dict[str, int]:
    usage = data.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": int(usage.get("total_tokens") or prompt + completion),
    }


async def _openai_style_complete(url: str, model: str, messages: list[dict]) -> CompletionText:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.post(url, json=payload)
        except httpx.RequestError as exc:
            raise LLMError("The local LLM service is unavailable.") from exc
    if response.status_code != 200:
        raise LLMError(f"The local LLM service returned HTTP {response.status_code}.")
    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("The local LLM service returned an invalid response.") from exc
    response_model = str(data.get("model") or model)
    return CompletionText(
        content,
        usage=_normalise_openai_usage(data),
        model=response_model,
        context_window=context_window_for_model(response_model),
    )


async def _openai_style_stream(
    url: str,
    model: str,
    messages: list[dict],
) -> AsyncIterator[str]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    raise LLMError(
                        f"The local LLM service returned HTTP {response.status_code}."
                    )
                async for line in response.aiter_lines():
                    chunk, _usage, _model = _parse_sse_data(line)
                    if chunk:
                        yield chunk
        except httpx.RequestError as exc:
            raise LLMError("The local LLM service is unavailable.") from exc


def _gateway_messages(messages: list[dict]) -> list[dict[str, str]]:
    """Translate internal system context into the gateway's strict message schema."""
    system = "\n\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "system"
    ).strip()
    output = [
        {
            "role": str(message.get("role")),
            "content": str(message.get("content") or ""),
        }
        for message in messages
        if message.get("role") in {"user", "assistant"}
        and str(message.get("content") or "")
    ]
    if system:
        output.insert(
            0,
            {
                "role": "user",
                "content": (
                    "HardcoreAI application context (treat as instructions for this "
                    f"request):\n\n{system}"
                ),
            },
        )
    return output


def _parse_sse_data(line: str) -> tuple[str, dict[str, int], str]:
    if not line.startswith("data:"):
        return "", {}, ""
    raw = line[5:].strip()
    if not raw or raw == "[DONE]":
        return "", {}, ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "", {}, ""
    try:
        delta = data["choices"][0].get("delta") or {}
        content = str(delta.get("content") or "")
    except (KeyError, IndexError, TypeError):
        content = ""
    return content, _normalise_openai_usage(data), str(data.get("model") or "")


def _gateway_payload(
    messages: list[dict],
    *,
    mode: str,
    project_id: str | None,
    agent_run_id: str | None,
) -> dict:
    if mode == "agent" and not agent_run_id:
        raise LLMError("Cloud agent requests require a stable agent run ID.")
    return {
        "mode": mode,
        "messages": _gateway_messages(messages),
        **({"projectId": str(project_id)} if project_id else {}),
        **({"agentRunId": agent_run_id} if agent_run_id else {}),
    }


async def _gateway_complete(
    messages: list[dict],
    *,
    mode: str,
    project_id: str | None,
    agent_run_id: str | None,
    access_token: str | None,
) -> CompletionText:
    token = access_token or request_access_token()
    if not token:
        raise LLMError("Sign in again before using HardcoreAI Cloud.")
    payload = _gateway_payload(
        messages,
        mode=mode,
        project_id=project_id,
        agent_run_id=agent_run_id,
    )
    text_parts: list[str] = []
    usage: dict[str, int] = {}
    response_model = "server-selected"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            async with client.stream(
                "POST",
                f"{CLOUD_PROXY_URL}/api/llm",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code != 200:
                    request_id = response.headers.get("x-request-id", "")
                    suffix = f" (request {request_id})" if request_id else ""
                    raise LLMError(
                        f"HardcoreAI Cloud returned HTTP {response.status_code}{suffix}."
                    )
                async for line in response.aiter_lines():
                    chunk, event_usage, event_model = _parse_sse_data(line)
                    if chunk:
                        text_parts.append(chunk)
                    if event_usage and event_usage.get("total_tokens", 0):
                        usage = event_usage
                    if event_model:
                        response_model = event_model
        except httpx.RequestError as exc:
            raise LLMError("HardcoreAI Cloud is temporarily unavailable.") from exc
    return CompletionText(
        "".join(text_parts),
        usage=usage,
        model=response_model,
        context_window=context_window_for_model(response_model, "cloud"),
    )


async def _gateway_stream(
    messages: list[dict],
    *,
    mode: str,
    project_id: str | None,
    agent_run_id: str | None,
    access_token: str | None,
) -> AsyncIterator[str]:
    token = access_token or request_access_token()
    if not token:
        raise LLMError("Sign in again before using HardcoreAI Cloud.")
    payload = _gateway_payload(
        messages,
        mode=mode,
        project_id=project_id,
        agent_run_id=agent_run_id,
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            async with client.stream(
                "POST",
                f"{CLOUD_PROXY_URL}/api/llm",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code != 200:
                    request_id = response.headers.get("x-request-id", "")
                    suffix = f" (request {request_id})" if request_id else ""
                    raise LLMError(
                        f"HardcoreAI Cloud returned HTTP {response.status_code}{suffix}."
                    )
                async for line in response.aiter_lines():
                    chunk, _usage, _model = _parse_sse_data(line)
                    if chunk:
                        yield chunk
        except httpx.RequestError as exc:
            raise LLMError("HardcoreAI Cloud is temporarily unavailable.") from exc


async def complete(
    provider: str,
    messages: list[dict],
    *,
    mode: str = "research",
    project_id: str | None = None,
    agent_run_id: str | None = None,
    access_token: str | None = None,
) -> CompletionText:
    if provider in CLOUD_PROVIDER_ALIASES:
        return await _gateway_complete(
            messages,
            mode=mode,
            project_id=project_id,
            agent_run_id=agent_run_id,
            access_token=access_token,
        )
    if provider == "llamacpp":
        return await _openai_style_complete(
            f"{LLAMACPP_URL}/v1/chat/completions",
            LLAMACPP_MODEL,
            messages,
        )
    if provider == "ollama":
        return await _openai_style_complete(
            f"{OLLAMA_URL}/v1/chat/completions",
            OLLAMA_MODEL,
            messages,
        )
    raise LLMError(f"Unknown provider '{provider}'.")


async def stream(
    provider: str,
    messages: list[dict],
    *,
    mode: str = "research",
    project_id: str | None = None,
    agent_run_id: str | None = None,
    access_token: str | None = None,
) -> AsyncIterator[str]:
    if provider in CLOUD_PROVIDER_ALIASES:
        async for chunk in _gateway_stream(
            messages,
            mode=mode,
            project_id=project_id,
            agent_run_id=agent_run_id,
            access_token=access_token,
        ):
            yield chunk
        return
    if provider == "llamacpp":
        config = (f"{LLAMACPP_URL}/v1/chat/completions", LLAMACPP_MODEL)
    elif provider == "ollama":
        config = (f"{OLLAMA_URL}/v1/chat/completions", OLLAMA_MODEL)
    else:
        raise LLMError(f"Unknown provider '{provider}'.")
    async for chunk in _openai_style_stream(config[0], config[1], messages):
        yield chunk
