"""Best-effort persistence for completed AI calls."""
from __future__ import annotations
import logging
from uuid import UUID
from core.config import now_utc
from db.models import AIUsageRow
from db.session import db_session

logger = logging.getLogger(__name__)

def record_usage(*, user_id: str | None, project_id: str | None, provider: str, model: str, request_type: str, usage: dict[str, int]) -> None:
    if not user_id: return
    try:
        prompt = int(usage.get("prompt_tokens") or 0); completion = int(usage.get("completion_tokens") or 0)
        with db_session(user_id) as session:
            session.add(AIUsageRow(user_id=UUID(user_id), project_id=int(project_id) if project_id and str(project_id).isdigit() else None, provider=provider, model=model, request_type=request_type, input_tokens=prompt, output_tokens=completion, total_tokens=int(usage.get("total_tokens") or prompt + completion), created_at=now_utc()))
            session.commit()
    except Exception:
        # Do not fail the user's AI response, but make persistence failures
        # visible in the backend log instead of silently losing usage data.
        logger.exception("Failed to persist AI usage")
