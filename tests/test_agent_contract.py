"""Contract tests for the conversational agent loop and its SSE streaming.

These lock down the behaviour that broke in production:

  * The agent loop (`run_phase`) must, for a well-specified request, run the
    THINK/CALL/write_file flow to completion and produce firmware — NOT stall on
    a clarifying question. (The "I need more information" regression.)
  * When streaming, `run_phase` must emit ordered events through its `on_event`
    callback: think → call → code (for write_file) → result → final.
  * The SSE frame formatter must produce a parseable `data: <json>\\n\\n` frame.
  * `_strip_duplicate_turn` must drop the echoed current message but keep prior
    history (so the model never sees the same turn twice).

They run in-process against the backend package (no Supabase, no live LLM): the
LLM is a deterministic fake, and write_file mutates the toolbox's in-memory
files dict. This keeps the suite fast and CI-safe while still exercising the
real parser + loop.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"


def _import_agent():
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from agent.parser import run_phase
        from agent.tools import CodingToolbox
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"backend agent package not importable: {exc}")
    return run_phase, CodingToolbox


def _toolbox(CodingToolbox):
    """A minimal toolbox: empty catalogue/workbench, in-memory files only."""
    return CodingToolbox(
        project_name="test",
        problem="Init USART2 on PA2/PA3 for an STM32F405",
        catalogue={"by_slug": {}, "by_id": {}},
        workbench={"placed_components": [], "wires": []},
        files={},
        user_id=None,
        project_id=None,
    )


# A canned STM32F405 USART2 firmware body the fake model "writes". Mirrors the
# real production case from the bug report.
_FIRMWARE = '''```c
#include "stm32f4xx_hal.h"
UART_HandleTypeDef huart2;
int main(void) {
    HAL_Init();
    __HAL_RCC_USART2_CLK_ENABLE();
    while (1) {}
}
```'''


def _fake_llm_factory(responses):
    """Return an async complete_fn yielding each canned response in order."""
    it = iter(responses)

    async def complete_fn(messages):
        try:
            return next(it)
        except StopIteration:
            return "All done."  # no CALL -> ends the phase

    return complete_fn


def test_well_specified_request_produces_code(tmp_path):
    """A clear request runs THINK/CALL write_file and yields firmware, not a question."""
    run_phase, CodingToolbox = _import_agent()
    tb = _toolbox(CodingToolbox)

    responses = [
        f'THINK: Small, well-specified task; I have the board and pins.\n'
        f'CALL write_file("src/main.c")\n{_FIRMWARE}',
        "I wrote a complete USART2 init for the STM32F405.",
    ]

    trace = asyncio.run(run_phase(
        phase="coding",
        system_prompt="sys",
        user_prompt="usr",
        toolbox=tb,
        complete_fn=_fake_llm_factory(responses),
    ))

    # The agent finished normally (not waiting on the user).
    assert trace.status == "completed"
    # It actually wrote the file.
    assert "src/main.c" in tb.files
    assert "USART2" in tb.files["src/main.c"]["content"]
    # And produced a real summary — never the "I need more information" stall.
    assert trace.final.strip()
    assert "i need more information" not in trace.final.lower()


def test_streaming_emits_ordered_events():
    """run_phase must push think -> call -> code -> result -> final via on_event."""
    run_phase, CodingToolbox = _import_agent()
    tb = _toolbox(CodingToolbox)

    responses = [
        f'THINK: Writing the firmware now.\nCALL write_file("src/main.c")\n{_FIRMWARE}',
        "Done.",
    ]

    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    asyncio.run(run_phase(
        phase="coding",
        system_prompt="sys",
        user_prompt="usr",
        toolbox=tb,
        complete_fn=_fake_llm_factory(responses),
        on_event=on_event,
    ))

    types = [e["type"] for e in events]
    # The write_file turn must surface, in order, the reasoning, the call, the
    # generated code card, the tool result, and a terminal final.
    assert "think" in types
    assert "call" in types
    assert "code" in types
    assert "result" in types
    assert types[-1] == "final"
    assert types.index("think") < types.index("call") < types.index("code")

    # The code event carries the target path and the fenced source, fence-stripped.
    code_ev = next(e for e in events if e["type"] == "code")
    assert code_ev["path"] == "src/main.c"
    assert "USART2" in code_ev["code"]
    assert not code_ev["code"].startswith("```")


def test_ask_user_streams_question_event():
    """An ambiguous turn (ask_user) must stream a `question` event and wait."""
    run_phase, CodingToolbox = _import_agent()
    tb = _toolbox(CodingToolbox)

    responses = [
        'THINK: The board is unknown, so I must ask.\n'
        'CALL ask_user("Which STM32 board?", "F407 Discovery, Blue Pill, Other - I will describe it")',
    ]

    events: list[dict] = []

    async def on_event(ev):
        events.append(ev)

    trace = asyncio.run(run_phase(
        phase="coding",
        system_prompt="sys",
        user_prompt="usr",
        toolbox=tb,
        complete_fn=_fake_llm_factory(responses),
        on_event=on_event,
    ))

    assert trace.status == "waiting_for_user"
    assert trace.question == "Which STM32 board?"
    # The "Other" escape hatch survives into the options the user sees.
    assert any("Other" in o for o in trace.options)

    q = next((e for e in events if e["type"] == "question"), None)
    assert q is not None
    assert q["question"] == "Which STM32 board?"


def test_sse_frame_is_parseable():
    """The SSE formatter must produce a `data: <json>` frame ending in a blank line."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from api.routers.agent import _sse
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"agent router not importable: {exc}")

    frame = _sse({"type": "think", "text": "hello"})
    assert frame.endswith("\n\n")
    assert frame.startswith("data: ")
    payload = json.loads(frame[len("data: "):].strip())
    assert payload == {"type": "think", "text": "hello"}


def test_strip_duplicate_turn():
    """The echoed current user message is dropped; prior history is preserved."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from api.routers.agent import _strip_duplicate_turn
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"agent router not importable: {exc}")

    # Trailing entry duplicates the problem -> dropped.
    hist = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "the new problem"},
    ]
    assert _strip_duplicate_turn(hist, "the new problem") == hist[:-1]

    # No duplication -> history kept as-is.
    hist2 = [{"role": "assistant", "content": "answer"}]
    assert _strip_duplicate_turn(hist2, "the new problem") == hist2

    # Empty / None -> None.
    assert _strip_duplicate_turn(None, "x") is None
    assert _strip_duplicate_turn([], "x") is None
