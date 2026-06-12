"""Database models — mapped onto the existing Supabase ``public`` schema.

The catalogue (components, pins) is read-only from the API's point of view;
it is populated by the seed migration. Projects, their placed components,
connections, and code files are read/write.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

from core.config import now_utc


class Component(SQLModel, table=True):
    __tablename__ = "components"

    id: int | None = SQLField(default=None, primary_key=True)
    slug: str
    name: str
    library_name: str | None = None
    description: str | None = None
    is_controller: bool = False
    cpp_class_name: str | None = None
    header_file: str | None = None
    category: str = "Component"
    visual_type: str = "generic"
    thumbnail: str = "generic"
    width: int = 140
    height: int = 100
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PinRow(SQLModel, table=True):
    __tablename__ = "pins"

    id: int | None = SQLField(default=None, primary_key=True)
    component_id: int = SQLField(foreign_key="components.id", index=True)
    name: str
    label: str
    side: str = "left"
    x: float = 0
    y: float = 0
    role: str = "gpio"
    voltage: float | None = None
    is_input: bool = False
    is_output: bool = False
    capabilities: str | None = None
    created_at: datetime | None = None


class ProjectRow(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = SQLField(default=None, primary_key=True)
    name: str
    description: str = ""
    user_id: UUID | None = SQLField(default=None)
    path: str | None = SQLField(default=None)
    viewport: dict[str, Any] = SQLField(
        default_factory=lambda: {"x": 0, "y": 0, "zoom": 1}, sa_column=Column(JSON)
    )
    # These columns are NOT NULL in Postgres with a `default now()`, but that
    # default only applies when the column is omitted from the INSERT. SQLModel
    # always emits it, so we supply the value from Python.
    created_at: datetime = SQLField(default_factory=now_utc)
    updated_at: datetime = SQLField(default_factory=now_utc)


class ProjectComponentRow(SQLModel, table=True):
    __tablename__ = "project_components"

    id: int | None = SQLField(default=None, primary_key=True)
    project_id: int = SQLField(foreign_key="projects.id", index=True)
    component_id: int = SQLField(foreign_key="components.id")
    instance_name: str
    x: float = 480
    y: float = 280
    rotation: int = 0
    config: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = SQLField(default_factory=now_utc)


class ProjectConnectionRow(SQLModel, table=True):
    __tablename__ = "project_connections"

    id: int | None = SQLField(default=None, primary_key=True)
    project_id: int = SQLField(foreign_key="projects.id", index=True)
    from_instance_id: int = SQLField(foreign_key="project_components.id")
    from_pin_label: str
    to_instance_id: int = SQLField(foreign_key="project_components.id")
    to_pin_label: str
    label: str | None = None
    color: str | None = None
    created_at: datetime = SQLField(default_factory=now_utc)


class CodeFileRow(SQLModel, table=True):
    __tablename__ = "code_files"

    id: int | None = SQLField(default=None, primary_key=True)
    project_id: int = SQLField(foreign_key="projects.id", index=True)
    path: str
    language: str = "c"
    content: str = ""
    updated_at: datetime = SQLField(default_factory=now_utc)


class ConversationRow(SQLModel, table=True):
    """The agent chat history for a project, stored as a single JSON blob.

    One row per project (the whole message list is replaced on each save). This
    mirrors how the frontend persists ``aiMessages`` to localStorage, so the two
    can stay in sync without modelling each message as its own table.
    """

    __tablename__ = "conversations"

    id: int | None = SQLField(default=None, primary_key=True)
    project_id: int = SQLField(foreign_key="projects.id", index=True, unique=True)
    history: list[Any] = SQLField(default_factory=list, sa_column=Column(JSON))
    updated_at: datetime = SQLField(default_factory=now_utc)
