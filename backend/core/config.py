"""Application configuration and small shared helpers.

Loads ``backend/.env`` and validates the database URL early so a missing or
placeholder password fails loudly at import time rather than on first query.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# backend/ — the directory that contains this package's parent.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy backend/.env.example to backend/.env "
        "and fill in your Supabase database password."
    )
if "YOUR-PASSWORD" in DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL still contains the YOUR-PASSWORD placeholder. "
        "Edit backend/.env and set the real Supabase database password."
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
