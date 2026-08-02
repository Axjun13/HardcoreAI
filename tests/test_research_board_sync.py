"""Regression tests for the "research board vs top target board" mismatch.

Before the fix, `_apply_research_target_board()` — the only function that
writes the research-selected board back into `project.board_id` (the single
value the top nav and the coding agent's get_device_for_project() both read)
— was only called from /verify/stream and /advance. Selecting a board in
Research mode via /select left `project.board_id` stale until the user
reached one of those two later checkpoints, so mid-conversation the coding
agent and top bar kept using the old board.

These tests check two things:
  1. The reconciliation function itself does what it claims (unit-level).
  2. /select's source actually calls it (regression guard: this is the exact
     line that was missing, so if it's ever removed again these tests catch
     it without needing a live DB/HTTP stack).

Run from the backend root with all project deps installed:
    pytest tests/test_research_board_sync.py -v
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import patch

import api.routers.research as research_router
from boards.registry import registry


def _fake_project(board_id: str | None, project_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=project_id, board_id=board_id)


def _controller_component(board_id: str) -> dict:
    """A component shaped like a Research-mode-selected controller board."""
    device = registry.get(board_id)
    assert device is not None, f"test fixture assumes {board_id!r} exists in the registry"
    return {
        "id": board_id,
        "name": device.label,
        "category": "microcontroller",
        "visual_type": "board",
        "protocols": [],
        "pins": [],
    }


def test_apply_research_target_board_updates_stale_project():
    """A board explicitly selected in Research must overwrite whatever the
    project's previous (top-nav) board_id was — this is the core unitary-
    selection contract."""
    project = _fake_project(board_id="bluepill_f103c8")  # old top-nav target
    selected = [_controller_component("esp32dev")]  # newly picked in Research
    state: dict = {}

    with patch(
        "services.hardware.configure_project_environment",
        return_value=(registry.get("esp32dev"), "", None),
    ) as mocked_configure:
        board = research_router._apply_research_target_board(
            session=object(), project=project, selected=selected, state=state
        )

    assert board.id == "esp32dev"
    mocked_configure.assert_called_once()
    # The decision must be recorded in research state for auditability too.
    assert state["board_selection"]["selected_board_id"] == "esp32dev"


def test_apply_research_target_board_keeps_current_when_no_explicit_pick():
    """With no controller component in the selection, the function must not
    invent a board switch — it should fall back to the project's current
    board_id rather than guessing."""
    project = _fake_project(board_id="uno")
    state: dict = {}

    with patch(
        "services.hardware.configure_project_environment",
        return_value=(registry.get("uno"), "", None),
    ):
        board = research_router._apply_research_target_board(
            session=object(), project=project, selected=[], state=state
        )

    assert board.id == "uno"


def test_select_endpoint_reconciles_board_id_immediately():
    """Regression guard for the actual root cause: /select must call
    _apply_research_target_board itself, not defer it to /verify or
    /advance. If this line is ever removed, this test fails immediately
    instead of the bug silently coming back."""
    source = inspect.getsource(research_router.select_components)
    assert "_apply_research_target_board(" in source, (
        "select_components() no longer reconciles project.board_id — "
        "the top nav / coding agent will show a stale board again until "
        "the user reaches /verify or /advance."
    )


def test_verify_and_advance_still_reconcile_too():
    """The two pre-existing checkpoints must keep calling the reconciler as
    well — this fix should be additive, not a replacement for them."""
    verify_source = inspect.getsource(research_router.stream_phase3_verification)
    advance_source = inspect.getsource(research_router.advance_research_workflow)
    assert "_apply_research_target_board(" in verify_source
    assert "_apply_research_target_board(" in advance_source