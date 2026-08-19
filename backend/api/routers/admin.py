"""Administrator-only reporting APIs."""
from __future__ import annotations
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import text
from core.security import get_current_admin
from db.session import db_session

router = APIRouter(prefix="/api/admin", tags=["Admin"])

USER_COLUMNS = """u.id::text AS id, u.email, u.created_at, u.last_sign_in_at,
  COALESCE(u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'name', split_part(u.email, '@', 1)) AS name,
  COALESCE(u.raw_user_meta_data->>'avatar_url', u.raw_user_meta_data->>'picture') AS avatar_url,
  up.company_name, up.phone_number, up.role, up.about, up.primary_use_case, up.company_size, up.referral_source,
  up.project_limit_unlocked, up.willing_to_pay, up.project_limit_feedback, up.completed_at"""

@router.get("/dashboard")
def dashboard(_: dict = Depends(get_current_admin)):
    with db_session() as session:
        totals = session.execute(text("""SELECT
          (SELECT count(*) FROM auth.users) AS users,
          (SELECT count(*) FROM public.projects) AS projects,
          (SELECT count(*) FROM public.ai_usage) AS requests,
          COALESCE((SELECT sum(input_tokens) FROM public.ai_usage),0) AS input_tokens,
          COALESCE((SELECT sum(output_tokens) FROM public.ai_usage),0) AS output_tokens,
          COALESCE((SELECT sum(total_tokens) FROM public.ai_usage),0) AS total_tokens""")).mappings().one()
        usage = session.execute(text("""SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS date,
          count(*) AS requests, COALESCE(sum(total_tokens),0) AS total_tokens
          FROM public.ai_usage WHERE created_at >= now() - interval '30 days'
          GROUP BY 1 ORDER BY 1""")).mappings().all()
    return {**dict(totals), "usage_over_time": [dict(row) for row in usage]}

@router.get("/users")
def users(_: dict = Depends(get_current_admin), search: str = "", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    pattern = f"%{search.strip()}%"
    with db_session() as session:
        count = session.execute(text("SELECT count(*) FROM auth.users u WHERE (:q = '%%' OR u.email ILIKE :q OR COALESCE(u.raw_user_meta_data->>'full_name','') ILIKE :q)"), {"q": pattern}).scalar_one()
        rows = session.execute(text(f"""SELECT {USER_COLUMNS},
          COALESCE(project_stats.projects, 0) AS projects,
          COALESCE(usage_stats.ai_requests, 0) AS ai_requests,
          COALESCE(usage_stats.total_tokens, 0) AS total_tokens
          FROM auth.users u
          LEFT JOIN public.user_profiles up ON up.user_id = u.id
          LEFT JOIN LATERAL (
            SELECT count(*) AS projects FROM public.projects p WHERE p.user_id=u.id
          ) project_stats ON true
          LEFT JOIN LATERAL (
            SELECT count(*) AS ai_requests, sum(total_tokens) AS total_tokens
            FROM public.ai_usage au WHERE au.user_id=u.id
          ) usage_stats ON true
          WHERE (:q = '%%' OR u.email ILIKE :q OR COALESCE(u.raw_user_meta_data->>'full_name','') ILIKE :q)
          ORDER BY COALESCE(u.last_sign_in_at,u.created_at) DESC LIMIT :limit OFFSET :offset"""), {"q": pattern, "limit": page_size, "offset": (page-1)*page_size}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": count, "page": page, "page_size": page_size}

@router.get("/users/{user_id}")
def user_detail(user_id: str, _: dict = Depends(get_current_admin)):
    with db_session() as session:
        user = session.execute(text(f"SELECT {USER_COLUMNS} FROM auth.users u LEFT JOIN public.user_profiles up ON up.user_id = u.id WHERE u.id::text=:id"), {"id": user_id}).mappings().first()
        if not user: raise HTTPException(status_code=404, detail="User not found")
        projects = session.execute(text("SELECT id, name, created_at, updated_at FROM public.projects WHERE user_id::text=:id ORDER BY updated_at DESC"), {"id": user_id}).mappings().all()
        summary = session.execute(text("SELECT count(*) AS ai_requests, COALESCE(sum(input_tokens),0) AS input_tokens, COALESCE(sum(output_tokens),0) AS output_tokens, COALESCE(sum(total_tokens),0) AS total_tokens FROM public.ai_usage WHERE user_id::text=:id"), {"id": user_id}).mappings().one()
        recent = session.execute(text("SELECT id, project_id, provider, model, request_type, input_tokens, output_tokens, total_tokens, created_at FROM public.ai_usage WHERE user_id::text=:id ORDER BY created_at DESC LIMIT 30"), {"id": user_id}).mappings().all()
    return {"user": dict(user), "projects": [dict(row) for row in projects], "usage": dict(summary), "recent_usage": [dict(row) for row in recent]}

@router.patch("/users/{user_id}/project-limit")
def set_project_limit(user_id: str, unlocked: bool = Body(..., embed=True), _: dict = Depends(get_current_admin)):
    """Allow an administrator to remove the two-project limit for one user."""
    with db_session() as session:
        exists = session.execute(text("SELECT 1 FROM auth.users WHERE id::text = :id"), {"id": user_id}).scalar()
        if not exists:
            raise HTTPException(status_code=404, detail="User not found")
        session.execute(text("""
            INSERT INTO public.user_profiles (user_id, project_limit_unlocked, updated_at)
            VALUES (:id, :unlocked, now())
            ON CONFLICT (user_id) DO UPDATE SET project_limit_unlocked = EXCLUDED.project_limit_unlocked, updated_at = now()
        """), {"id": user_id, "unlocked": unlocked})
        session.commit()
    return {"user_id": user_id, "project_limit_unlocked": unlocked}

@router.get("/usage")
def usage(_: dict = Depends(get_current_admin), days: int = Query(30, ge=1, le=365)):
    with db_session() as session:
        rows = session.execute(text("""SELECT to_char(date_trunc('day', created_at),'YYYY-MM-DD') AS date, model,
          count(*) AS requests, COALESCE(sum(input_tokens),0) AS input_tokens,
          COALESCE(sum(output_tokens),0) AS output_tokens, COALESCE(sum(total_tokens),0) AS total_tokens
          FROM public.ai_usage WHERE created_at >= now() - (:days * interval '1 day')
          GROUP BY 1, model ORDER BY 1 DESC, model"""), {"days": days}).mappings().all()
    return {"items": [dict(row) for row in rows]}
