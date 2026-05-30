"""Database engine and session management.

``db_session`` opens a SQLModel session and, when a ``user_id`` is supplied,
sets the Postgres RLS context (``authenticated`` role + the JWT ``sub`` claim)
so row-level security policies scope every query to that user.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import text
from sqlmodel import Session, create_engine

from core.config import DATABASE_URL

# psycopg (v3) connection. pool_pre_ping recovers from Supabase idle drops.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


@contextmanager
def db_session(user_id: str | None = None):
    with Session(engine) as session:
        if user_id:
            try:
                session.execute(text("SET LOCAL ROLE authenticated"))
                session.execute(
                    text("SELECT set_config('request.jwt.claim.sub', :user_id, true)"),
                    {"user_id": str(user_id)},
                )
            except Exception as e:
                raise RuntimeError(f"Failed to configure session RLS context: {e}")
        yield session
