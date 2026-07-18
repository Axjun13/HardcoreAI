import asyncio
from unittest.mock import AsyncMock

from backend.llm import core


def _provider(provider_id: str) -> dict:
    return next(item for item in core.available_providers() if item["id"] == provider_id)


def test_provider_metadata_exposes_context_window(monkeypatch):
    monkeypatch.setattr(core, "GEMINI_MODEL", "gemini-2.5-flash")

    provider = _provider("gemini")

    assert provider["model"] == "gemini-2.5-flash"
    assert provider["context_window"] == 1_048_576


def test_openai_usage_is_normalised_for_agent_tracking():
    assert core._normalise_openai_usage({
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    }) == {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
    }


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


def test_deepseek_uses_current_openrouter_fallback_when_configured_model_fails(monkeypatch):
    complete = AsyncMock(side_effect=[core.LLMError("upstream busy"), "Fallback response"])
    monkeypatch.setattr(core, "_openai_style_complete", complete)
    monkeypatch.setattr(core, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(core, "OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setattr(core, "DEEPSEEK_OPENROUTER_MODEL", "deepseek/older-model")
    monkeypatch.setattr(core, "DEEPSEEK_OPENROUTER_FALLBACK_MODEL", "deepseek/current-model")
    messages = [{"role": "user", "content": "Hello"}]

    result = asyncio.run(core._deepseek_complete(messages))

    assert result == "Fallback response"
    assert [call.args[1] for call in complete.await_args_list] == [
        "deepseek/older-model",
        "deepseek/current-model",
    ]
