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
    # tool result, the staged file proposal, and a terminal final. The file
    # change is a *proposal* (Allow/Reject in the UI), not an auto-applied write.
    assert "think" in types
    assert "call" in types
    assert "proposal" in types
    assert "result" in types
    assert types[-1] == "final"
    assert types.index("think") < types.index("call") < types.index("proposal")

    # The proposal event carries the target path and the fenced source,
    # fence-stripped, plus the pre-edit baseline for the diff.
    prop_ev = next(e for e in events if e["type"] == "proposal")
    assert prop_ev["path"] == "src/main.c"
    assert "USART2" in prop_ev["code"]
    assert not prop_ev["code"].startswith("```")
    assert "old" in prop_ev  # baseline for the diff (empty string for a new file)


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


def test_new_filesystem_and_search_tools():
    """Verify list_files, view_file, create_file, copy_file, move_file, grep_search, and sed_replace."""
    _, CodingToolbox = _import_agent()
    
    # Initialize with default files
    tb = CodingToolbox(
        project_name="test",
        problem="Test",
        catalogue={},
        workbench={"placed_components": [], "wires": []},
        files={
            "src/main.c": {"language": "c", "content": "line 1\nline 2\nline 3\n"},
            "README.md": {"language": "markdown", "content": "# README\nThis is a test project.\n"}
        },
        user_id=None,
        project_id="test_proj",
    )
    
    # Test list_files
    files_list = tb.list_files()
    assert "src/main.c" in files_list
    assert "README.md" in files_list
    
    # Test view_file (full and range)
    view_full = tb.view_file("src/main.c")
    assert "line 1" in view_full
    assert "line 3" in view_full
    assert "3: line 3" in view_full
    
    view_range = tb.view_file("src/main.c", start_line=2, end_line=3)
    assert "line 1" not in view_range
    assert "2: line 2" in view_range
    assert "3: line 3" in view_range
    
    # Test create_file
    create_res = tb.create_file("src/utils.h", "#define UTILS_H")
    assert "src/utils.h" in tb.files
    assert tb.files["src/utils.h"]["content"] == "#define UTILS_H"
    
    # Test copy_file
    copy_res = tb.copy_file("src/utils.h", "src/utils_backup.h")
    assert "src/utils_backup.h" in tb.files
    assert tb.files["src/utils_backup.h"]["content"] == "#define UTILS_H"
    
    # Test move_file
    move_res = tb.move_file("src/utils_backup.h", "src/utils_backup_final.h")
    assert "src/utils_backup.h" not in tb.files
    assert "src/utils_backup_final.h" in tb.files
    assert tb.files["src/utils_backup_final.h"]["content"] == "#define UTILS_H"
    
    # Test grep_search
    grep_res = tb.grep_search("line 2")
    assert "src/main.c:2: line 2" in grep_res
    
    # Test sed_replace
    sed_res = tb.sed_replace("src/main.c", "line 2", "modified line 2")
    assert tb.files["src/main.c"]["content"] == "line 1\nmodified line 2\nline 3\n"
    assert "=== Unified Diff ===" in sed_res
    assert "-line 2" in sed_res
    assert "+modified line 2" in sed_res
    
    # Test delete_file (safeguard unconfirmed)
    from agent.tools import AskUserException
    with pytest.raises(AskUserException) as excinfo:
        tb.delete_file("src/utils.h", confirmed=False)
    assert "Are you sure you want to delete" in str(excinfo.value)
    assert "src/utils.h" in tb.files # still exists
    
    # Test delete_file (confirmed)
    delete_res = tb.delete_file("src/utils.h", confirmed=True)
    assert "src/utils.h" not in tb.files # deleted!


def test_git_tools_with_gitmanager(tmp_path, monkeypatch):
    """Verify git_log, git_diff, and git_show using real GitManager redirected to tmp_path."""
    _, CodingToolbox = _import_agent()
    from agent.git_manager import GitManager
    
    # Redirect GitManager storage to the pytest tmp_path
    def mock_init(self, project_id):
        self.project_id = project_id
        self.workspace_dir = tmp_path / "workspaces" / str(project_id)
        
    monkeypatch.setattr(GitManager, "__init__", mock_init)
    
    tb = CodingToolbox(
        project_name="test",
        problem="Test",
        catalogue={},
        workbench={"placed_components": [], "wires": []},
        files={
            "src/main.c": {"language": "c", "content": "int main() { return 0; }\n"}
        },
        user_id=None,
        project_id="test_proj",
    )
    
    # Instantiate GitManager directly to sync files initially
    git_mgr = GitManager("test_proj")
    git_mgr.sync_db_to_disk(tb.files)
    git_mgr.commit_changes("Initial commit")
    
    # Make a change and commit it
    tb.files["src/main.c"]["content"] = "int main() { return 1; }\n"
    git_mgr.sync_db_to_disk(tb.files)
    git_mgr.commit_changes("Update main return value")
    
    # Test git_log tool
    log_output = tb.git_log()
    assert "Initial commit" in log_output
    assert "Update main return value" in log_output
    
    # Test git_diff tool (diff between HEAD~1 and HEAD)
    diff_output = tb.git_diff("HEAD~1", "HEAD")
    assert "return 0;" in diff_output
    assert "return 1;" in diff_output
    
    # Test git_show tool
    show_output = tb.git_show("HEAD")
    assert "Update main return value" in show_output
    assert "+int main() { return 1; }" in show_output

