"""Authentication: resolve a Supabase access token to a user id.

The desktop backend verifies live sessions through Supabase Auth using only the
public project URL and anon key. No JWT secret or service-role key is shipped.
The legacy test token works only with an explicit local-test flag.
"""

from __future__ import annotations

import os
from contextvars import ContextVar

import httpx
from fastapi import Depends, Header, HTTPException

_access_token: ContextVar[str | None] = ContextVar("request_access_token", default=None)
_user_id: ContextVar[str | None] = ContextVar("request_user_id", default=None)
_agent_run_id: ContextVar[str | None] = ContextVar("request_agent_run_id", default=None)
_project_id: ContextVar[str | None] = ContextVar("request_project_id", default=None)


def request_access_token() -> str | None:
    """Return the current request's Supabase access token without persisting it."""
    return _access_token.get()


def request_user_id() -> str | None:
    return _user_id.get()


def set_cloud_request_context(*, agent_run_id: str, project_id: str) -> None:
    _agent_run_id.set(agent_run_id)
    _project_id.set(project_id)


def cloud_request_context() -> tuple[str | None, str | None]:
    return _agent_run_id.get(), _project_id.get()


async def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ")[1]
    _access_token.set(token)

    if token == "TEST_TOKEN":
        if os.environ.get("ALLOW_TEST_TOKEN", "").lower() not in {"1", "true", "yes"}:
            raise HTTPException(status_code=401, detail="Invalid auth token")
        test_user = "cee19697-23d0-44f1-8e98-1460239ed921"
        _user_id.set(test_user)
        return {"id": test_user, "email": os.environ.get("TEST_USER_EMAIL", "")}

    supabase_url = os.environ.get("SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")

    if not supabase_url or not anon_key:
        raise HTTPException(status_code=500, detail="Supabase configuration is missing in backend")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": anon_key,
                },
            )
        except Exception:
            raise HTTPException(status_code=401, detail="Failed to verify auth token")

        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid auth token")

        user_data = response.json()
        user_id = str(user_data["id"])
        _user_id.set(user_id)
        return user_data


async def get_current_user_id(authorization: str = Header(None)) -> str:
    """Return the authenticated Supabase user id (legacy router dependency)."""
    user = await get_current_user(authorization)
    return str(user["id"])


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require an authenticated user whose email is explicitly configured as admin."""
    configured = {email.strip().casefold() for email in os.environ.get("ADMIN_EMAILS", "").split(",") if email.strip()}
    email = str(user.get("email") or "").casefold()
    if not configured or email not in configured:
        raise HTTPException(status_code=403, detail="Administrator access is required")
    return user
