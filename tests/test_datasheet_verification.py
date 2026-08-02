"""Regression tests for the "silent datasheet failure" fix.

Before the fix, verify_component_online() buried a missing datasheet as a
plain string inside a generic `warnings` list, with no field a caller could
branch on and no signal that reached the user. These tests pin down the new
contract: a missing datasheet must be reported as a structured, actionable
result (`datasheet_status`, `needs_upload`, `upload_prompt`), not just prose.

Run from the backend root with all project deps installed:
    pytest tests/test_datasheet_verification.py -v
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.integration_verification import verify_component_online


COMPONENT = {
    "id": "dht22",
    "name": "DHT22 Temperature/Humidity Sensor",
    "pins": [],
    "protocols": [],
    "datasheet_url": None,
}


def _llm_response(payload: dict) -> object:
    """Build a fake object shaped like whatever llm.complete() normally
    returns, based only on what verify_component_online reads from it."""
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_missing_datasheet_is_flagged_not_buried():
    """No usable search result / no datasheet URL -> the function must say
    so explicitly (needs_upload=True), not just append a warning string."""
    with (
        patch("services.integration_verification.search_web", return_value=[]),
        patch("services.integration_verification.fetch_datasheet_text", return_value=""),
        patch("llm.complete", new=AsyncMock(return_value=_llm_response({
            "pins": [],
            "protocols": [],
            "warnings": ["No evidence found."],
        }))),
    ):
        result = await verify_component_online(COMPONENT, provider="deepseek")

    assert result["datasheet_status"] == "missing"
    assert result["needs_upload"] is True
    assert result["upload_prompt"], "upload_prompt must be a non-empty, user-facing message"
    assert COMPONENT["name"] in result["upload_prompt"]
    # The old behavior (a warning buried in prose) should still be present
    # for backward compatibility, but must not be the *only* signal.
    assert any("datasheet" in w.casefold() for w in result["warnings"])


@pytest.mark.asyncio
async def test_found_datasheet_does_not_ask_for_upload():
    """When a real datasheet URL and usable evidence come back, the
    upload prompt must not fire — this guards against false positives."""
    search_results = [{
        "url": "https://example.com/dht22-datasheet.pdf",
        "title": "DHT22 Datasheet",
        "snippet": "Official datasheet with pinout and specs.",
    }]
    with (
        patch("services.integration_verification.search_web", return_value=search_results),
        patch(
            "services.integration_verification.fetch_datasheet_text",
            return_value="DHT22 pinout: VCC, DATA, NC, GND. Operating voltage 3.3-5.5V.",
        ),
        patch("llm.complete", new=AsyncMock(return_value=_llm_response({
            "datasheet_url": "https://example.com/dht22-datasheet.pdf",
            "pins": [{"name": "DATA", "role": "gpio"}],
            "protocols": ["1-Wire"],
            "operating_voltage": "3.3-5.5V",
            "warnings": [],
        }))),
    ):
        result = await verify_component_online(COMPONENT, provider="deepseek")

    assert result["datasheet_status"] == "found"
    assert result["needs_upload"] is False
    assert result["upload_prompt"] is None


@pytest.mark.asyncio
async def test_needs_upload_defaults_false_when_key_absent_elsewhere():
    """Sanity check: any code reading .get('needs_upload', False) on an
    older cached verification record degrades safely instead of crashing."""
    old_style_record = {"datasheet_url": "https://example.com/x.pdf", "warnings": []}
    assert old_style_record.get("needs_upload", False) is False