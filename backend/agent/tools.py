"""The Toolbox: the concrete tools the agent calls in each phase.

A Toolbox is constructed per agent run with the project, its DB session, the
component catalogue, and a working copy of the workbench. Tools mutate that
working copy (and, in phase 2, code-file content) in memory; the caller commits
once the phase finishes.

Two tool sets:
  WiringToolbox — place/move/rotate/remove components, wire/unwire pins.
  CodingToolbox — inspect the finished netlist, read/write code files.

Both share read-only inspection tools so the model can always re-orient itself.
"""

from __future__ import annotations

import uuid
from typing import Any

from . import editmatch
from .parser import ToolSpec, tool

import re as _re


def _extract_fenced_code(body: str) -> str:
    """Pull the file content out of a write_file body.

    The model is told to put the file in a ```fence``` after the CALL line, but it
    frequently wraps that fence in prose ("Here's the code:\n```c\n...\n```\nKey
    changes: ..."). Earlier we only stripped a fence when the body *started* with
    one, so a leading sentence caused the entire prose+fence blob to be saved as
    the file — producing a markdown "C file" that never compiles.

    Strategy:
      1. If there is at least one ``` fenced block anywhere, return the contents
         of the FIRST one (prose before/after is discarded).
      2. Otherwise return the stripped body unchanged (a bare code body).
    """
    text = (body or "").strip()
    if "```" not in text:
        return text

    # Match the first fenced block; the opening fence may carry a language tag
    # (```c, ```cpp, ...). DOTALL so the body can span lines; non-greedy so we
    # stop at the first closing fence.
    m = _re.search(r"```[^\n]*\n(.*?)```", text, _re.DOTALL)
    if m:
        return m.group(1).strip()

    # An opening fence with no closing fence: drop the opening line, keep the rest.
    lines = text.split("\n")
    if lines and lines[0].lstrip().startswith("```"):
        return "\n".join(lines[1:]).strip()
    return text


def _looks_like_c(text: str, is_header: bool = False) -> bool:
    """Heuristic: does this body look like C source rather than English prose?

    Used by write_file to reject the failure mode where the model's explanatory
    answer (or a half-finished thought) gets saved as code and clobbers main.c.
    We require at least one structural C signal AND a low ratio of prose-like
    sentences. Deliberately lenient so genuine code is never rejected.
    """
    t = text.strip()
    if not t:
        return False
    # Strong, unambiguous C signals — any one is enough.
    strong = ("#include", "int main", "void ", "HAL_", "__HAL_", "uint8_t",
              "uint16_t", "uint32_t", "while (", "while(", "GPIO_", "typedef",
              "#define", "return ", "static ", "#ifndef", "#endif")
    has_strong = any(s in t for s in strong)
    if is_header:
        # Header files may only contain preprocessor guards/defines, skip punctuation checks
        return has_strong
    # Structural punctuation density: real C is full of ; { } ( ).
    braces = t.count("{") + t.count("}")
    semis = t.count(";")
    # A page of prose has almost none of these.
    structural = braces >= 1 or semis >= 2
    return has_strong and structural


class AskUserException(Exception):
    """Raised when the agent wants to ask the user a question."""
    def __init__(self, question: str, options: list[str] = None):
        super().__init__(question)
        self.question = question
        self.options = options or []

class ProposePlanException(Exception):
    """Raised when the agent proposes a plan for user approval."""
    def __init__(self, plan: str):
        super().__init__(plan)
        self.plan = plan

class ConfirmActionException(Exception):
    """Raised when a side-effecting action (build/flash) needs user approval.

    Carries the tool name so the UI can show a specific 'Agent wants to build /
    flash — Allow / Reject' prompt. On Allow, the frontend re-runs the agent with
    auto_approve (or a 'yes' answer) so the same action proceeds."""
    def __init__(self, action: str, question: str):
        super().__init__(question)
        self.action = action
        self.question = question

# ---------------------------------------------------------------------------
# Base toolbox — shared inspection tools + the working workbench copy.
# ---------------------------------------------------------------------------


class Toolbox:
    """Holds per-run state and exposes tools as bound methods.

    `workbench` is a mutable dict {placed_components, wires, viewport}. `catalogue`
    maps slug -> ComponentDefinition (the pydantic model from main.py). Subclasses
    add phase-specific tools; `specs()` collects every @tool method on the class.
    """

    def __init__(
        self,
        *,
        project_name: str,
        problem: str,
        catalogue: dict[str, Any],
        workbench: dict[str, Any],
        files: dict[str, dict[str, Any]] | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
        build_output: str = "",
        auto_approve: bool = False,
    ) -> None:
        self.project_name = project_name
        self.problem = problem
        self.catalogue = catalogue
        self.workbench = workbench
        # files: path -> {"language": str, "content": str}
        self.files = files or {}
        # Set by run_phase before invoking a wants_body tool: the verbatim text
        # following the CALL line, from which file_edit parses its ``` fences.
        self.call_body = ""
        self.user_id = user_id
        self.project_id = project_id
        self.build_output = build_output or ""
        # Session-level "auto-approve everything" toggle. When true, gated tools
        # (build/flash/delete) run without raising for confirmation. Treated the
        # same as a per-call user_confirmed=True.
        self.auto_approve = auto_approve
        # Immutable snapshot of the files as they were when the run started. Used
        # to (a) render an accurate before/after diff for each proposal and (b)
        # let the agent loop detect which files a tool actually changed.
        import copy as _copy
        self.baseline = _copy.deepcopy(self.files)
        # Last content we surfaced as a proposal per path, so a multi-step run
        # only re-emits a file when it actually changed again since last emit.
        self._last_emitted: dict[str, str | None] = {
            p: m.get("content") for p, m in self.baseline.items()
        }

    def drain_pending_changes(self) -> list[str]:
        """Return paths whose content changed since they were last surfaced.

        A path counts when it is new, deleted, or its content differs from what
        we last emitted (baseline initially). The diff the UI renders always uses
        the original baseline, so it shows the full cumulative change."""
        changed: list[str] = []
        all_paths = set(self.files) | set(self._last_emitted)
        for path in sorted(all_paths):
            cur = self.files.get(path)
            cur_content = cur.get("content") if cur else None
            if cur_content != self._last_emitted.get(path):
                changed.append(path)
                self._last_emitted[path] = cur_content
        return changed

    # -- registry --------------------------------------------------------

    @classmethod
    def specs(cls) -> list[ToolSpec]:
        """Every @tool method on this class (and its bases), declaration order."""
        seen: dict[str, ToolSpec] = {}
        for klass in reversed(cls.__mro__):
            for name, member in vars(klass).items():
                spec = getattr(member, "_tool_spec", None)
                if spec is not None:
                    seen[name] = spec
        return list(seen.values())

    # -- helpers (not tools) --------------------------------------------

    def _find_component(self, ref: str) -> dict[str, Any] | None:
        """Resolve a component reference: its id, or its display name (case-insensitive)."""
        ref = str(ref).strip()
        for c in self.workbench["placed_components"]:
            if c["id"] == ref:
                return c
        low = ref.lower()
        matches = [c for c in self.workbench["placed_components"] if c["display_name"].lower() == low]
        if len(matches) == 1:
            return matches[0]
        matches = [c for c in self.workbench["placed_components"] if c.get("definition_id", "").lower() == low]
        return matches[0] if len(matches) == 1 else None

    def _definition(self, slug: str) -> Any | None:
        return self.catalogue.get(slug)

    def _pin_exists(self, component: dict[str, Any], pin_name: str) -> bool:
        definition = self._definition(component.get("definition_id", ""))
        if not definition:
            return False
        return any(p.name == pin_name for p in definition.pins)

    def _describe_component(self, c: dict[str, Any]) -> str:
        definition = self._definition(c.get("definition_id", ""))
        pins = ", ".join(p.name for p in definition.pins) if definition else "?"
        return (
            f"[{c['id']}] {c['display_name']} ({c.get('definition_id')}) "
            f"at ({int(c['x'])},{int(c['y'])}) rot {c.get('rotation', 0)} — pins: {pins}"
        )

    # -- shared inspection tools ----------------------------------------

    @tool
    def ask_user(self, question: str, options: str = "") -> str:
        """Pause execution and ask the user a clarifying question. Use this if the prompt is ambiguous. Options can be a comma-separated list of choices."""
        opts = [o.strip() for o in options.split(",") if o.strip()]
        raise AskUserException(question, opts)

    @tool
    def propose_plan(self, plan: str) -> str:
        """Pause execution and present an implementation plan to the user for approval. Use this after reading the manual but before wiring or coding."""
        raise ProposePlanException(plan)

    @tool
    def show_problem(self) -> str:
        """Re-read the hardware problem statement you must solve."""
        return self.problem or "(no problem statement provided)"

    @tool
    def list_workbench(self) -> str:
        """List every component currently placed on the workbench, with their pins."""
        comps = self.workbench["placed_components"]
        if not comps:
            return "Workbench is empty."
        lines = [self._describe_component(c) for c in comps]
        return f"{len(comps)} component(s):\n" + "\n".join(lines)

    @tool
    def list_wires(self) -> str:
        """List every wire (pin-to-pin connection) currently on the workbench."""
        wires = self.workbench["wires"]
        if not wires:
            return "No wires yet."
        out = []
        for w in wires:
            out.append(
                f"[{w['id']}] {w['from']['componentId']}.{w['from']['pinName']} "
                f"-> {w['to']['componentId']}.{w['to']['pinName']}"
            )
        return f"{len(wires)} wire(s):\n" + "\n".join(out)

    @tool
    def describe_component(self, component: str) -> str:
        """Show one placed component's details and the role of each of its pins."""
        c = self._find_component(component)
        if not c:
            return f"No placed component matches '{component}'. You must pass the numeric ID (e.g. '64') shown in brackets in list_workbench."
        definition = self._definition(c.get("definition_id", ""))
        if not definition:
            return self._describe_component(c)
        pins = "\n".join(
            f"  {p.name} (label '{p.label}', role {p.role}, side {p.side})"
            for p in definition.pins
        )
        return f"{self._describe_component(c)}\nPins:\n{pins}"

    @tool
    def search_hardware_manuals(self, query: str) -> str:
        """Search the user's uploaded reference manuals and datasheets for hardware information."""
        if not self.user_id or not self.project_id:
            return "ERROR: user_id or project_id is not set. Cannot access the project knowledge base."
        from rag import RAGService
        try:
            svc = RAGService(user_id=str(self.user_id), project_id=str(self.project_id))
            result = svc.query(query)
            if result.get("returncode") != 0:
                err = result.get('stderr', '').strip()
                if "no such table: chunks" in err:
                    return "No documents have been uploaded to the hardware manual database yet."
                return f"ERROR: RAG query failed: {err}"
            context = result.get("context", "")
            if not isinstance(context, str) or not context.strip():
                return "No relevant information found in the uploaded manuals."
            return context.strip()
        except Exception as e:
            return f"ERROR: Failed to search manuals: {e}"

    @tool
    def read_build_output(self) -> str:
        """Read the log of a PREVIOUS build (does NOT compile; use build() to compile)."""
        output = (self.build_output or "").strip()
        if not output:
            return "Build Output console is empty. Ask the user to build the project, or have them copy and paste the Build Output if this snapshot is unavailable."
        if len(output) > 12000:
            output = output[-12000:]
            return "(showing the last 12000 characters of Build Output)\n" + output
        return output

    @tool
    def build(self, confirmed: bool = False) -> str:
        """Actually compile the firmware with PlatformIO (same as the Build button).

        Use this whenever asked to build/compile/make. Stores the full compiler
        output so a later read_build_output() returns it. Returns a short summary
        (status + the tail of the log) for the model.

        Requires user approval: calling with confirmed=False pauses and asks the
        user first. Pass confirmed=True only after the user has approved."""
        if not self.project_id:
            return "ERROR: No project is associated with this run; cannot build."
        if not (confirmed or getattr(self, "user_confirmed", False) or self.auto_approve):
            raise ConfirmActionException(
                action="build",
                question="The agent wants to build (compile) the firmware. Allow the build to run?",
            )
        from services import hardware

        result = hardware.build_project(self.project_id)
        # Persist the real output so read_build_output() reflects this build.
        self.build_output = result.output or ""
        tail = (result.output or "").strip()
        if len(tail) > 4000:
            tail = "(last 4000 chars)\n" + tail[-4000:]
        status = "SUCCESS" if result.success else f"FAILED (exit {result.returncode})"
        fw = f"\nFirmware: {result.firmware_path}" if result.firmware_path else ""
        return f"Build {status} in {result.duration_s}s.{fw}\n\n{tail}"

    @tool
    def flash(self, confirmed: bool = False) -> str:
        """Flash the built firmware to a connected STM32 (Blue Pill) over ST-Link.

        Builds first if needed. If no board is connected this returns a clear
        'no device' message rather than failing.

        Requires user approval: calling with confirmed=False pauses and asks the
        user first. Pass confirmed=True only after the user has approved."""
        if not self.project_id:
            return "ERROR: No project is associated with this run; cannot flash."
        if not (confirmed or getattr(self, "user_confirmed", False) or self.auto_approve):
            raise ConfirmActionException(
                action="flash",
                question="The agent wants to flash firmware to the connected board. Allow the flash to run?",
            )
        from services import hardware

        result = hardware.flash_project(self.project_id)
        if result.flashed:
            return f"Flash SUCCESS.\n\n{(result.output or '').strip()[-2000:]}"
        if result.reason == "no_device":
            return f"No device connected — nothing was flashed. {result.output}".strip()
        return f"Flash FAILED ({result.reason}, exit {result.returncode}).\n\n{(result.output or '').strip()[-2000:]}"

    @tool
    def generate_hal(self, board: str, peripherals: str) -> str:
        """Generate ready-made STM32 HAL init files (src/hal/*.c and *.h) from
        templates — the same output as the Embedded Configurator's Generate button.

        Use this when the user wants the structured per-peripheral HAL setup files
        (e.g. gpio_init.c, uart2_init.c, rcc_init.c, main_init.c) rather than a
        single hand-written src/main.c. For a simple one-file blink demo, prefer
        write_file("src/main.c") instead.

        Args:
          board:       one of STM32F401, STM32F103, STM32H743 (defaults applied otherwise).
          peripherals: comma-separated peripheral ids to enable. Supported ids:
                       rcc, gpio, usart1, usart2, spi1, i2c1, tim1, adc1, dma, nvic.
                       Example: "rcc, gpio, usart2".

        The generated files are staged as normal diff proposals for the user to
        Allow/Reject — nothing is written until approved."""
        from api.routers.hal_codegen import generate_hal_files

        ids = [p.strip().lower() for p in peripherals.split(",") if p.strip()]
        if not ids:
            return "ERROR: no peripherals given. Pass a comma-separated list, e.g. \"rcc, gpio, usart2\"."

        peripheral_dicts = [{"id": pid, "label": pid.upper(), "mode": "", "params": {}} for pid in ids]
        try:
            generated = generate_hal_files(board=board, peripherals=peripheral_dicts)
        except Exception as exc:  # noqa: BLE001 — surface generation errors to the model
            return f"ERROR: HAL generation failed: {exc}"

        if not generated:
            return (
                f"No files generated for peripherals {ids}. None matched a known "
                "template (rcc, gpio, usart1, usart2, spi1, i2c1, tim1, adc1, dma, nvic)."
            )

        # Stage each file into the working set so it flows through the standard
        # proposal/Allow-Reject diff path, exactly like write_file does.
        for rel_path, content in generated.items():
            self.files[rel_path] = {"language": "c", "content": content}

        paths = ", ".join(sorted(generated))
        return (
            f"Generated {len(generated)} HAL file(s) for {board} "
            f"({', '.join(ids)}): {paths}. Staged as diff proposals for approval."
        )


# ---------------------------------------------------------------------------
# Phase 1 — WIRING toolbox
# ---------------------------------------------------------------------------


class WiringToolbox(Toolbox):
    """Place components and wire their pins to satisfy the problem statement."""

    @tool
    def list_catalogue(self) -> str:
        """List every component type available in the catalogue to place."""
        lines = []
        for slug, definition in self.catalogue.items():
            pins = ", ".join(f"{p.name}:{p.role}" for p in definition.pins)
            lines.append(f"  {slug} — {definition.name} ({definition.category}); pins: {pins}")
        return "Catalogue:\n" + "\n".join(lines)

    @tool
    def place_component(self, slug: str, name: str = "", x: int = 480, y: int = 280) -> str:
        """Place a catalogue component on the workbench. slug from list_catalogue."""
        definition = self._definition(slug)
        if not definition:
            return f"Unknown slug '{slug}'. Use list_catalogue for valid slugs."
        # Clamp to the same 1600x1000 canvas the frontend uses.
        cx = max(0, min(int(x), 1600 - definition.width))
        cy = max(0, min(int(y), 1000 - definition.height))
        instance = {
            "id": f"part-{uuid.uuid4()}",
            "definition_id": slug,
            "display_name": name.strip() or definition.name,
            "x": cx,
            "y": cy,
            "rotation": 0,
            "config": {},
        }
        self.workbench["placed_components"].append(instance)
        return f"Placed {instance['display_name']} as [{instance['id']}] at ({cx},{cy})."

    @tool
    def move_component(self, component: str, x: int, y: int) -> str:
        """Move a placed component to a new (x, y) position on the canvas."""
        c = self._find_component(component)
        if not c:
            return f"No placed component matches '{component}'."
        definition = self._definition(c.get("definition_id", ""))
        w = definition.width if definition else 140
        h = definition.height if definition else 100
        c["x"] = max(0, min(int(x), 1600 - w))
        c["y"] = max(0, min(int(y), 1000 - h))
        return f"Moved {c['display_name']} to ({c['x']},{c['y']})."

    @tool
    def rotate_component(self, component: str) -> str:
        """Rotate a placed component 90 degrees clockwise."""
        c = self._find_component(component)
        if not c:
            return f"No placed component matches '{component}'."
        c["rotation"] = (int(c.get("rotation", 0)) + 90) % 360
        return f"Rotated {c['display_name']} to {c['rotation']} degrees."

    @tool
    def rename_component(self, component: str, name: str) -> str:
        """Give a placed component a clearer instance name."""
        c = self._find_component(component)
        if not c:
            return f"No placed component matches '{component}'."
        old = c["display_name"]
        c["display_name"] = name.strip() or old
        return f"Renamed '{old}' to '{c['display_name']}'."

    @tool
    def remove_component(self, component: str) -> str:
        """Remove a placed component and every wire attached to it."""
        c = self._find_component(component)
        if not c:
            return f"No placed component matches '{component}'."
        cid = c["id"]
        self.workbench["placed_components"] = [
            x for x in self.workbench["placed_components"] if x["id"] != cid
        ]
        before = len(self.workbench["wires"])
        self.workbench["wires"] = [
            w for w in self.workbench["wires"]
            if w["from"]["componentId"] != cid and w["to"]["componentId"] != cid
        ]
        dropped = before - len(self.workbench["wires"])
        return f"Removed {c['display_name']} and {dropped} attached wire(s)."

    @tool
    def add_wire(self, from_component: str, from_pin: str, to_component: str, to_pin: str) -> str:
        """Wire one pin to another. Pin names come from describe_component."""
        a = self._find_component(from_component)
        b = self._find_component(to_component)
        if not a:
            return f"No placed component matches '{from_component}'."
        if not b:
            return f"No placed component matches '{to_component}'."
        if not self._pin_exists(a, from_pin):
            return f"{a['display_name']} has no pin '{from_pin}'. Use describe_component."
        if not self._pin_exists(b, to_pin):
            return f"{b['display_name']} has no pin '{to_pin}'. Use describe_component."
        if a["id"] == b["id"] and from_pin == to_pin:
            return "A pin cannot wire to itself."
        # Reject an exact duplicate (either direction).
        for w in self.workbench["wires"]:
            ends = {
                (w["from"]["componentId"], w["from"]["pinName"]),
                (w["to"]["componentId"], w["to"]["pinName"]),
            }
            if ends == {(a["id"], from_pin), (b["id"], to_pin)}:
                return "Those two pins are already wired together."
        wire = {
            "id": f"wire-{uuid.uuid4()}",
            "from": {"componentId": a["id"], "pinName": from_pin},
            "to": {"componentId": b["id"], "pinName": to_pin},
        }
        self.workbench["wires"].append(wire)
        return (
            f"Wired {a['display_name']}.{from_pin} -> {b['display_name']}.{to_pin} "
            f"as [{wire['id']}]."
        )

    @tool
    def remove_wire(self, wire_id: str) -> str:
        """Delete a wire by its id (shown in list_wires)."""
        before = len(self.workbench["wires"])
        self.workbench["wires"] = [w for w in self.workbench["wires"] if w["id"] != str(wire_id)]
        if len(self.workbench["wires"]) == before:
            return f"No wire with id '{wire_id}'."
        return f"Removed wire {wire_id}."


# ---------------------------------------------------------------------------
# Phase 2 — CODING toolbox
# ---------------------------------------------------------------------------


class CodingToolbox(Toolbox):
    """Inspect the finished netlist and write STM32 firmware into the code files."""

    @tool(wants_body=True)
    def write_file(self, path: str) -> str:
        """Replace a code file's content entirely. Use only for a new file or a full rewrite."""
        # Normalize bare filenames: "main.c" -> "src/main.c", "stm32f4xx.h" -> "src/stm32f4xx.h"
        # Only applies to C/H files that have no directory component at all.
        if "/" not in path and "\\" not in path and (path.endswith(".c") or path.endswith(".h")):
            path = "src/" + path
        content = _extract_fenced_code(self.call_body)

        is_code = path.endswith(".c") or path.endswith(".h")
        existing = self.files.get(path)

        # Guard 1: never write an empty body — that would silently blank a file.
        if not content:
            return (
                f"ERROR: refused to write empty content to {path}. "
                "Put the full file body in a ``` fenced block after the CALL line."
            )

        # Guard 2: a C/H write must actually look like C, not explanatory prose.
        # This is the core fix for 'random agent text overwrote main.c'.
        if is_code and not _looks_like_c(content, is_header=path.endswith(".h")):
            return (
                f"ERROR: that body does not look like C source, so I did not write {path}. "
                "If you meant to explain something, just say it in plain text (no tool call). "
                "To save code, put real C inside a ```c fence after CALL write_file."
            )

        # Guard 3: don't let a full rewrite quietly shrink an existing file to a
        # stub. A 95%+ size drop on a non-trivial file is almost always the model
        # truncating; force it through file_edit instead.
        if is_code and existing:
            old = existing.get("content", "")
            if len(old) > 400 and len(content) < len(old) * 0.5:
                return (
                    f"ERROR: refused to shrink {path} from {len(old)} to {len(content)} bytes via write_file. "
                    "A full rewrite must contain the COMPLETE file. To change part of it, use file_edit, "
                    "or re-send the entire file (every function, every include) with write_file."
                )

        language = "markdown" if path.endswith(".md") else "c"
        if existing is not None:
            language = existing.get("language", language)
            
        # Auto-inject SysTick_Handler only when code uses the STM32 HAL
        # (HAL_Init present). Avoids duplicate symbol errors with custom RTOS.
        if path.endswith(".c") and "SysTick_Handler" not in content and "HAL_Init" in content:
            content = content.rstrip() + "\n\nvoid SysTick_Handler(void) {\n    HAL_IncTick();\n}\n"
            
        self.files[path] = {"language": language, "content": content}
        return f"Successfully wrote {len(content)} bytes to {path}."

    @tool
    def list_files(self) -> str:
        """List all files in the current project workspace."""
        if not self.files:
            return "The project workspace is empty."
        lines = []
        for path in sorted(self.files.keys()):
            size = len(self.files[path].get("content", ""))
            lang = self.files[path].get("language", "c")
            lines.append(f"  - {path} ({size} bytes, language: {lang})")
        return "Files in workspace:\n" + "\n".join(lines)

    @tool
    def view_file(self, path: str, start_line: int = 1, end_line: int = -1) -> str:
        """View the content of a file in the workspace. Optionally specify start_line and end_line (1-indexed, inclusive) to read specific parts."""
        if "/" not in path and "\\" not in path and (path.endswith(".c") or path.endswith(".h")):
            path = "src/" + path
            
        file_meta = self.files.get(path)
        if file_meta is None:
            return f"ERROR: File '{path}' not found. Use list_files to see available files."
            
        content = file_meta.get("content", "")
        lines = content.splitlines()
        total_lines = len(lines)
        
        if end_line == -1 or end_line > total_lines:
            end_line = total_lines
            
        if start_line < 1:
            start_line = 1
            
        if start_line > total_lines:
            return f"File '{path}' only has {total_lines} lines. Cannot read starting from line {start_line}."
            
        selected_lines = lines[start_line - 1 : end_line]
        formatted = []
        for idx, line in enumerate(selected_lines, start=start_line):
            formatted.append(f"{idx:4d}: {line}")
            
        header = f"File: {path} (Showing lines {start_line} to {end_line} of {total_lines} total lines):\n"
        return header + "\n".join(formatted)

    @tool
    def create_file(self, path: str, content: str = "") -> str:
        """Create a new file in the workspace with optional initial content."""
        if "/" not in path and "\\" not in path and (path.endswith(".c") or path.endswith(".h")):
            path = "src/" + path
            
        if path in self.files:
            return f"ERROR: File '{path}' already exists. Use write_file or file_edit to modify it."
            
        language = "markdown" if path.endswith(".md") else ("c" if (path.endswith(".c") or path.endswith(".h")) else "text")
        self.files[path] = {"language": language, "content": content}
        return f"Successfully created file '{path}' ({len(content)} bytes)."

    @tool
    def delete_file(self, path: str, confirmed: bool = False) -> str:
        """Delete a file from the workspace. You MUST get user confirmation first. Calling this tool with confirmed=False will automatically prompt the user for approval; call it with confirmed=True only after the user explicitly approves it."""
        if "/" not in path and "\\" not in path and (path.endswith(".c") or path.endswith(".h")):
            path = "src/" + path
            
        if path not in self.files:
            return f"ERROR: File '{path}' not found."
            
        is_confirmed = confirmed or getattr(self, "user_confirmed", False)
        if not is_confirmed:
            raise AskUserException(
                question=f"Are you sure you want to delete the file '{path}'? This action cannot be undone.",
                options=["Yes", "No"]
            )
            
        del self.files[path]
        return f"Successfully deleted file '{path}'."

    @tool
    def copy_file(self, src: str, dest: str) -> str:
        """Copy a file from src to dest in the workspace."""
        if "/" not in src and "\\" not in src and (src.endswith(".c") or src.endswith(".h")):
            src = "src/" + src
        if "/" not in dest and "\\" not in dest and (dest.endswith(".c") or dest.endswith(".h")):
            dest = "src/" + dest
            
        if src not in self.files:
            return f"ERROR: Source file '{src}' not found."
            
        self.files[dest] = {
            "language": self.files[src].get("language", "c"),
            "content": self.files[src].get("content", "")
        }
        return f"Successfully copied '{src}' to '{dest}'."

    @tool
    def move_file(self, src: str, dest: str) -> str:
        """Move or rename a file from src to dest in the workspace."""
        if "/" not in src and "\\" not in src and (src.endswith(".c") or src.endswith(".h")):
            src = "src/" + src
        if "/" not in dest and "\\" not in dest and (dest.endswith(".c") or dest.endswith(".h")):
            dest = "src/" + dest
            
        if src not in self.files:
            return f"ERROR: Source file '{src}' not found."
            
        self.files[dest] = {
            "language": self.files[src].get("language", "c"),
            "content": self.files[src].get("content", "")
        }
        del self.files[src]
        return f"Successfully moved/renamed '{src}' to '{dest}'."

    @tool(wants_body=True)
    def file_edit(self, path: str, old: str = "", new: str = "") -> str:
        """Edit part of a file: keep one unchanged context line above and below the change.

        Two ways to call it. Inline, for a short single-line fix:
            CALL file_edit("src/main.c", "old context+line", "new context+line")
        Or paired, best for multi-line edits — put TWO ``` blocks after the CALL,
        first the before block, then the after block (repeat for more sites):
            CALL file_edit("src/main.c")
            ```c
            <context line>
            <original lines>
            <context line>
            ```
            ```c
            <context line>
            <changed lines>
            <context line>
            ```
        The before block must match the file exactly and uniquely — include
        enough surrounding lines that it appears only once.
        """
        meta = self.files.get(path)
        if meta is None:
            return f"No file '{path}'. Use list_files."

        # Inline form takes priority when old/new were given as args; otherwise
        # parse the ``` fence pairs the agent captured after the CALL line.
        if old or new:
            edits = [editmatch.Edit(old=old, new=new)]
        else:
            edits, parse_err = editmatch.parse_edits(self.call_body or "")
            if parse_err is not None:
                return f"ERROR: {parse_err}"

        original_content = meta["content"]
        content, results = editmatch.apply_all(original_content, edits)
        applied = [r for r in results if r.applied]
        failed = next((r for r in results if r.error is not None), None)

        if failed is not None:
            if applied:
                meta["content"] = content
            done = f"{len(applied)} edit(s) applied; " if applied else ""
            return f"ERROR: {done}edit #{len(applied) + 1} failed: {failed.error}"

        meta["content"] = content
        
        # Calculate unified diff
        import difflib
        diff_lines = list(difflib.unified_diff(
            original_content.splitlines(),
            content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=""
        ))
        diff_text = "\n".join(diff_lines)
        
        spans = ", ".join(f"L{r.start_line}-{r.end_line}" for r in applied)
        return (
            f"Applied {len(applied)} edit(s) to {path} ({spans}).\n\n"
            f"=== Unified Diff ===\n"
            f"{diff_text}\n"
            f"===================="
        )

    @tool
    def grep_search(self, query: str) -> str:
        """Search for a regular expression or plain-text query across all files in the workspace. Returns matching lines with line numbers."""
        import re
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as exc:
            return f"ERROR: Invalid regex pattern: {exc}"
            
        matches = []
        for path, file_meta in self.files.items():
            content = file_meta.get("content", "")
            lines = content.splitlines()
            for line_idx, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches.append(f"  - {path}:{line_idx}: {line.strip()}")
                    
        if not matches:
            return f"No matches found for query: '{query}'"
            
        return f"Found {len(matches)} match(es) for query '{query}':\n" + "\n".join(matches[:50])

    @tool
    def sed_replace(self, path: str, pattern: str, replacement: str) -> str:
        """Perform a regex-based search and replace inside a specific file. Returns a unified diff of the change."""
        import re
        import difflib
        
        if "/" not in path and "\\" not in path and (path.endswith(".c") or path.endswith(".h")):
            path = "src/" + path
            
        file_meta = self.files.get(path)
        if file_meta is None:
            return f"ERROR: File '{path}' not found."
            
        original_content = file_meta.get("content", "")
        
        try:
            compiled_pattern = re.compile(pattern)
        except re.error as exc:
            return f"ERROR: Invalid regex pattern: {exc}"
            
        new_content, count = compiled_pattern.subn(replacement, original_content)
        
        if count == 0:
            return f"No replacements made in '{path}' using pattern '{pattern}'."
            
        diff_lines = list(difflib.unified_diff(
            original_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=""
        ))
        
        file_meta["content"] = new_content
        diff_text = "\n".join(diff_lines)
        return (
            f"Successfully made {count} replacement(s) in '{path}'.\n\n"
            f"=== Unified Diff ===\n"
            f"{diff_text}\n"
            f"===================="
        )

    @tool
    def git_log(self) -> str:
        """Show the Git commit history of the workspace repository."""
        if not self.project_id:
            return "ERROR: Project ID is not set. Cannot access git repository."
        from .git_manager import GitManager
        git_mgr = GitManager(self.project_id)
        return git_mgr.get_log()

    @tool
    def git_diff(self, commit_a: str, commit_b: str) -> str:
        """Show the Git diff between two commits or revisions (e.g. HEAD~1, HEAD)."""
        if not self.project_id:
            return "ERROR: Project ID is not set. Cannot access git repository."
        from .git_manager import GitManager
        git_mgr = GitManager(self.project_id)
        return git_mgr.get_diff(commit_a, commit_b)

    @tool
    def git_show(self, commit: str) -> str:
        """Show the changes made in a specific Git commit."""
        if not self.project_id:
            return "ERROR: Project ID is not set. Cannot access git repository."
        from .git_manager import GitManager
        git_mgr = GitManager(self.project_id)
        return git_mgr.get_show(commit)

    @tool
    def list_supported_boards(self) -> str:
        """List all supported STM32 boards with chip details, HAL header, and default pin assignments."""
        return """Supported STM32 boards:

STM32F407 Discovery (STM32F407VGT6 — Cortex-M4, up to 168 MHz)
  Header : #include \"stm32f4xx_hal.h\"
  LEDs   : PD12 (green), PD13 (orange), PD14 (red), PD15 (blue)
  UART   : USART2 on PA2 (TX) / PA3 (RX)
  Button : PA0 (active HIGH)

STM32F103C8T6 — Blue Pill (Cortex-M3, up to 72 MHz)
  Header : #include \"stm32f1xx_hal.h\"
  LED    : PC13 (built-in, active LOW — reset to turn ON)
  UART   : USART1 on PA9 (TX) / PA10 (RX)
  Button : PA0 (active HIGH)

STM32F401 Nucleo (STM32F401RET6 — Cortex-M4, up to 84 MHz)
  Header : #include \"stm32f4xx_hal.h\"
  LED    : PA5 (LD2, active HIGH)
  UART   : USART2 on PA2 (TX) / PA3 (RX)
  Button : PC13 (active LOW)

STM32F446RE Nucleo (STM32F446RET6 — Cortex-M4, up to 180 MHz)
  Header : #include \"stm32f4xx_hal.h\"
  LED    : PA5 (LD2, active HIGH)
  UART   : USART2 on PA2 (TX) / PA3 (RX)
  Button : PC13 (active LOW)

CRITICAL: Always use HSI oscillator. HSE is not supported by the QEMU emulator."""

    @tool
    def netlist(self) -> str:
        """Show the full netlist: every wire with both endpoints' component + pin role."""
        wires = self.workbench["wires"]
        if not wires:
            return "Netlist is empty — no wires."
        by_id = {c["id"]: c for c in self.workbench["placed_components"]}

        def endpoint(e: dict[str, Any]) -> str:
            c = by_id.get(e["componentId"])
            if not c:
                return f"?.{e['pinName']}"
            definition = self._definition(c.get("definition_id", ""))
            pin = next((p for p in definition.pins if p.name == e["pinName"]), None) if definition else None
            label = pin.label if pin else e["pinName"]
            role = pin.role if pin else "?"
            return f"{c['display_name']}.{label}({role})"

        lines = [f"  {endpoint(w['from'])} <-> {endpoint(w['to'])}" for w in wires]
        return f"Netlist ({len(wires)} connections):\n" + "\n".join(lines)
