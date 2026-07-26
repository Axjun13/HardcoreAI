import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.llm import core


def _provider(provider_id: str) -> dict:
    return next(item for item in core.available_providers() if item["id"] == provider_id)


def test_cloud_provider_metadata_uses_server_owned_model():
    provider = _provider("deepseek")

    assert provider["available"] is True
    assert provider["model"] == "server-selected"
    assert provider["local"] is False
    assert provider["context_window"] > 0


def test_openai_usage_is_normalised_for_agent_tracking():
    assert core._normalise_openai_usage({
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    }) == {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
    }


def test_gateway_payload_rejects_agent_call_without_stable_run_id():
    with pytest.raises(core.LLMError, match="stable agent run ID"):
        core._gateway_payload(
            [{"role": "user", "content": "Hello"}],
            mode="agent",
            project_id="42",
            agent_run_id=None,
        )


def test_gateway_payload_uses_strict_proxy_contract():
    payload = core._gateway_payload(
        [
            {"role": "system", "content": "Use the project board."},
            {"role": "user", "content": "Blink the LED."},
        ],
        mode="agent",
        project_id="42",
        agent_run_id="fd15bb17-19a3-4745-baca-4ab6982db74b",
    )

    assert set(payload) == {"mode", "messages", "projectId", "agentRunId"}
    assert all(message["role"] in {"user", "assistant"} for message in payload["messages"])
    assert payload["projectId"] == "42"
    assert payload["agentRunId"] == "fd15bb17-19a3-4745-baca-4ab6982db74b"


def test_legacy_cloud_selection_routes_through_gateway(monkeypatch):
    gateway = AsyncMock(return_value=core.CompletionText("Cloud response"))
    monkeypatch.setattr(core, "_gateway_complete", gateway)
    messages = [{"role": "user", "content": "Hello"}]

    result = asyncio.run(
        core.complete(
            "deepseek",
            messages,
            mode="research",
            project_id="42",
            access_token="user-access-token",
        )
    )

    assert result == "Cloud response"
    gateway.assert_awaited_once_with(
        messages,
        mode="research",
        project_id="42",
        agent_run_id=None,
        access_token="user-access-token",
    )


def test_gateway_error_uses_sanitized_message_and_body_request_id():
    request = httpx.Request("POST", "https://cloud.example/api/llm")
    response = httpx.Response(
        500,
        request=request,
        json={
            "error": {
                "code": "provider_unavailable",
                "message": "The configured model is temporarily unavailable",
                "requestId": "req-123",
            }
        },
    )

    error = asyncio.run(core._gateway_response_error(response))

    assert str(error) == (
        "HardcoreAI Cloud: The configured model is temporarily unavailable "
        "(request req-123)."
    )


def test_gateway_complete_retries_a_transient_500(monkeypatch):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                500,
                json={
                    "error": {
                        "code": "internal_error",
                        "message": "Temporary provider failure",
                        "requestId": "req-retry",
                    }
                },
            )
        event = {
            "choices": [{"delta": {"content": "Recovered"}}],
            "model": "test-model",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 1,
                "total_tokens": 11,
            },
        }
        return httpx.Response(
            200,
            text=f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        core.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock())

    result = asyncio.run(
        core._gateway_complete(
            [{"role": "user", "content": "Hello"}],
            mode="agent",
            project_id="42",
            agent_run_id="fd15bb17-19a3-4745-baca-4ab6982db74b",
            access_token="user-access-token",
        )
    )

    assert result == "Recovered"
    assert result.model == "test-model"
    assert calls == 2
