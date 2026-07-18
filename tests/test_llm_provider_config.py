import asyncio
from unittest.mock import AsyncMock

from backend.llm import core


def _provider(provider_id: str) -> dict:
    return next(item for item in core.available_providers() if item["id"] == provider_id)


def test_deepseek_is_available_through_configured_openrouter(monkeypatch):
    monkeypatch.setattr(core, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(core, "OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setattr(core, "DEEPSEEK_OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")

    assert _provider("deepseek")["available"] is True


def test_deepseek_routes_through_openrouter(monkeypatch):
    complete = AsyncMock(return_value="DeepSeek response")
    monkeypatch.setattr(core, "_openai_style_complete", complete)
    monkeypatch.setattr(core, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(core, "OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setattr(core, "OPENROUTER_HTTP_REFERER", "http://127.0.0.1:62017")
    monkeypatch.setattr(core, "DEEPSEEK_OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")
    messages = [{"role": "user", "content": "Hello"}]

    result = asyncio.run(core._deepseek_complete(messages))

    assert result == "DeepSeek response"
    complete.assert_awaited_once_with(
        "https://openrouter.ai/api/v1/chat/completions",
        "deepseek/deepseek-chat-v3-0324",
        messages,
        headers={
            "Authorization": "Bearer openrouter-key",
            "HTTP-Referer": "http://127.0.0.1:62017",
            "X-Title": "HardcoreAI",
        },
    )


def test_direct_deepseek_key_takes_precedence(monkeypatch):
    complete = AsyncMock(return_value="Direct response")
    monkeypatch.setattr(core, "_openai_style_complete", complete)
    monkeypatch.setattr(core, "DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr(core, "DEEPSEEK_URL", "https://api.deepseek.test/v1/chat/completions")
    monkeypatch.setattr(core, "DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setattr(core, "OPENROUTER_API_KEY", "openrouter-key")
    messages = [{"role": "user", "content": "Hello"}]

    result = asyncio.run(core._deepseek_complete(messages))

    assert result == "Direct response"
    complete.assert_awaited_once_with(
        "https://api.deepseek.test/v1/chat/completions",
        "deepseek-chat",
        messages,
        headers={"Authorization": "Bearer deepseek-key"},
    )
