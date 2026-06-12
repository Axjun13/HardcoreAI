"""API schemas — the wire contract the frontend already speaks.

Workbench instance/wire ids are strings on the wire; the service layer maps
them to/from the integer primary keys of project_components / project_connections.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
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


class ComponentDefinition(BaseModel):
    id: str  # the slug, kept stable for the frontend
    name: str
    category: str
    description: str
    visual_type: str
    thumbnail: str
    width: int
    height: int
    pins: list[Pin]


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectCreate(SQLModel):
    name: str
    description: str = ""
    path: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None


class ProjectOut(SQLModel):
    id: str
    name: str
    description: str
    path: str | None = None
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


class PhaseTrace(BaseModel):
    phase: str
    steps: list[dict[str, Any]]
    final: str
    status: str = "completed"
    question: str = ""
    options: list[str] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)


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
