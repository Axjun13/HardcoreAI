"""API schemas — the wire contract the frontend already speaks.

Workbench instance/wire ids are strings on the wire; the service layer maps
them to/from the integer primary keys of project_components / project_connections.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID
from sqlmodel import SQLModel

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class Pin(BaseModel):
    name: str
    label: str
    side: str
    x: float
    y: float
    role: str = "gpio"
    voltage: float | None = None
    capabilities: str | None = None


class ComponentDefinition(BaseModel):
    id: str  # the slug, kept stable for the frontend
    name: str
    category: str
    description: str
    visual_type: str
    thumbnail: str
    width: int
    height: int
    library_name: str | None = None
    library_ids: list[str] = Field(default_factory=list)
    buy_links: list[dict[str, Any]] = Field(default_factory=list)
    datasheet_url: str | None = None
    aliases: list[str] = Field(default_factory=list)
    source_url: str | None = None
    source_name: str | None = None
    image_source_url: str | None = None
    discovery_query: str | None = None
    discovered_at: datetime | None = None
    verified_at: datetime | None = None
    protocols: list[str] = Field(default_factory=list)
    verification_sources: list[str] = Field(default_factory=list)
    pins: list[Pin]


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectCreate(SQLModel):
    name: str
    description: str = ""
    path: str | None = None
    board_id: str | None = None

class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None


class ProjectOut(SQLModel):
    id: str
    name: str
    description: str
    path: str | None = None
    board_id: str
    created_at: datetime
    updated_at: datetime

# ---------------------------------------------------------------------------
# Workbench & code files
# ---------------------------------------------------------------------------


class WorkbenchState(BaseModel):
    placed_components: list[dict[str, Any]] = Field(default_factory=list)
    wires: list[dict[str, Any]] = Field(default_factory=list)
    viewport: dict[str, Any] = Field(default_factory=lambda: {"x": 0, "y": 0, "zoom": 1})


class CodeFileUpsert(BaseModel):
    language: str = "c"
    content: str = ""


class CodeFileRead(BaseModel):
    path: str
    language: str
    content: str
    updated_at: datetime | None = None


class FirmwareResult(BaseModel):
    path: str
    language: str
    content: str
    summary: str
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """A request to run the agent on a project."""

    provider: str = "llamacpp"
    problem: str = ""
    conversation_history: list[dict[str, Any]] | None = None
    phase: str | None = None
    build_output: str = ""
    # When true, the agent auto-accepts plans, code/file changes, and builds.
    # Flashing physical hardware always requires a separate explicit approval.
    auto_approve: bool = False
    # One stable id is reused for every paid LLM/search call made by this run.
    agent_run_id: UUID | None = None


class PhaseTrace(BaseModel):
    phase: str
    steps: list[dict[str, Any]]
    final: str
    status: str = "completed"
    question: str = ""
    options: list[str] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    context_usage: dict[str, Any] = Field(default_factory=dict)
    context_manifest: dict[str, list[str]] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    provider: str
    wiring: PhaseTrace
    coding: PhaseTrace
    workbench: WorkbenchState
    files: list[CodeFileRead]


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------


class RagQueryRequest(BaseModel):
    query: str
    k: int | None = None


# ---------------------------------------------------------------------------
# Conversations (agent chat history)
# ---------------------------------------------------------------------------


class ConversationSave(BaseModel):
    """The full chat history the frontend wants to persist for a project."""

    history: list[dict[str, Any]] = Field(default_factory=list)


class ConversationRead(BaseModel):
    history: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Hardware — build / flash / device detection
# ---------------------------------------------------------------------------


class DeviceStatus(BaseModel):
    """Whether a programmer/board (ST-Link + STM32) is physically connected."""

    connected: bool = False
    probe: str | None = None  # e.g. "ST-Link V2"
    target: str | None = None  # e.g. "STM32F103 (Blue Pill)"
    detail: str = ""  # human-readable status or error
    detected_family: str | None = None  # e.g. "STM32F4", from a generic chip-ID probe
    suggested_boards: list[str] = []  # registry board ids matching detected_family
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class BuildResult(BaseModel):
    """Outcome of a real PlatformIO build."""

    success: bool
    returncode: int
    output: str  # combined stdout+stderr from `pio run`
    firmware_path: str | None = None  # path to the produced .elf/.bin, if any
    duration_s: float = 0.0


class FlashResult(BaseModel):
    """Outcome of a flash attempt. `flashed` is False with reason='no_device'
    when nothing is connected — this is a normal (HTTP 200) result, not an error."""

    flashed: bool
    reason: str = ""  # "" on success, else "no_device" | "build_failed" | "flash_failed"
    returncode: int = 0
    output: str = ""
    device: DeviceStatus | None = None


# ---------------------------------------------------------------------------
# Debug — GDB / OpenOCD session
# ---------------------------------------------------------------------------


class DebugStartRequest(BaseModel):
    """Request body for POST /debug/start."""
    board: str | None = None  # None = resolve from the project's stored board_id

class DebugBreakpointRequest(BaseModel):
    """Set a breakpoint at file:line."""
    file: str
    line: int


class DebugBreakpoint(BaseModel):
    """A breakpoint known to the current GDB session."""
    id: int
    file: str
    line: int
    enabled: bool = True


class DebugState(BaseModel):
    """Current execution state of the target."""
    running: bool = False       # target is executing
    halted: bool = False        # target stopped at bp / step / signal
    file: str | None = None     # source file from GDB *stopped event
    line: int | None = None     # source line number
    reason: str | None = None   # "breakpoint-hit" | "end-stepping-range" | "signal-received" | "exited"


class DebugRegister(BaseModel):
    """One ARM core register value."""
    name: str      # "r0", "sp", "pc", …
    number: int    # GDB register number
    value: str     # hex string e.g. "0x20001234"


class DebugFrame(BaseModel):
    """One frame in the call stack."""
    level: int
    function: str
    file: str | None = None
    line: int | None = None
    address: str | None = None


class DebugLocal(BaseModel):
    """One local variable in the current frame."""
    name: str
    value: str
    type: str = ""


class DebugSnapshot(BaseModel):
    """Full state snapshot returned after start/step/continue."""
    state: DebugState
    registers: list[DebugRegister] = Field(default_factory=list)
    call_stack: list[DebugFrame] = Field(default_factory=list)
    locals: list[DebugLocal] = Field(default_factory=list)
    breakpoints: list[DebugBreakpoint] = Field(default_factory=list)
    error: str | None = None   # set when session could not start
