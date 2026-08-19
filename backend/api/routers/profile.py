"""Authenticated user onboarding profile APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from core.security import get_current_user_id
from db.session import db_session
from schemas import ProjectLimitFeedback, UserOnboardingUpdate

router = APIRouter(prefix="/api/profile", tags=["Profile"])
PROFILE_COLUMNS = "company_name, phone_number, role, about, primary_use_case, company_size, referral_source, willing_to_pay, project_limit_feedback, completed_at"


@router.get("/onboarding")
def onboarding_status(user_id: str = Depends(get_current_user_id)):
    with db_session() as session:
        row = session.execute(
            text(f"SELECT {PROFILE_COLUMNS} FROM public.user_profiles WHERE user_id=:user_id"),
            {"user_id": user_id},
        ).mappings().first()
    return {"completed": bool(row and row["completed_at"]), "profile": dict(row) if row else None}


@router.put("/onboarding")
def save_onboarding(payload: UserOnboardingUpdate, user_id: str = Depends(get_current_user_id)):
    values = payload.model_dump()
    for field in ("company_name", "about"):
        if values[field] is not None:
            values[field] = values[field].strip() or None
    with db_session() as session:
        row = session.execute(
            text(f"""INSERT INTO public.user_profiles
                (user_id, company_name, phone_number, role, about, primary_use_case, company_size, referral_source, completed_at, updated_at)
                VALUES (:user_id, :company_name, :phone_number, :role, :about, :primary_use_case, :company_size, :referral_source, now(), now())
                ON CONFLICT (user_id) DO UPDATE SET
                  company_name=EXCLUDED.company_name, phone_number=EXCLUDED.phone_number, role=EXCLUDED.role, about=EXCLUDED.about,
                  primary_use_case=EXCLUDED.primary_use_case, company_size=EXCLUDED.company_size,
                  referral_source=EXCLUDED.referral_source, completed_at=now(), updated_at=now()
                RETURNING {PROFILE_COLUMNS}"""),
            {"user_id": user_id, **values},
        ).mappings().one()
        session.commit()
    return {"completed": True, "profile": dict(row)}


@router.post("/project-limit-feedback")
def save_project_limit_feedback(payload: ProjectLimitFeedback, user_id: str = Depends(get_current_user_id)):
    with db_session() as session:
        session.execute(text("""
            INSERT INTO public.user_profiles (user_id, willing_to_pay, project_limit_feedback, updated_at)
            VALUES (:user_id, :willing_to_pay, :feedback, now())
            ON CONFLICT (user_id) DO UPDATE SET
              willing_to_pay=EXCLUDED.willing_to_pay,
              project_limit_feedback=EXCLUDED.project_limit_feedback,
              updated_at=now()
        """), {"user_id": user_id, "willing_to_pay": payload.willing_to_pay, "feedback": (payload.feedback or "").strip() or None})
        session.commit()
    return {"saved": True}
