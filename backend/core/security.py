"""Authentication: resolve a Supabase JWT to a user id.

Verifies the token locally with the Supabase JWT secret when available
(HMAC-SHA256), falling back to a network call to Supabase's ``/auth/v1/user``
endpoint. ``TEST_TOKEN`` short-circuits to a fixed id for the test suite.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import httpx
from fastapi import Header, HTTPException


async def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ")[1]

    if token == "TEST_TOKEN":
        return "cee19697-23d0-44f1-8e98-1460239ed921"

    # 1. Attempt local JWT signature verification if the secret is available
    supabase_jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    if supabase_jwt_secret:
        try:
            parts = token.split(".")
            if len(parts) == 3:
                header_b64, payload_b64, signature_b64 = parts

                # Re-verify the HMAC-SHA256 signature
                signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
                key = supabase_jwt_secret.encode("utf-8")
                expected_sig = hmac.new(key, signing_input, hashlib.sha256).digest()

                # base64url decode signature
                rem = len(signature_b64) % 4
                sig_padded = signature_b64 + ("=" * (4 - rem) if rem else "")
                decoded_sig = base64.urlsafe_b64decode(sig_padded)

                if hmac.compare_digest(expected_sig, decoded_sig):
                    # Decode payload
                    rem = len(payload_b64) % 4
                    payload_padded = payload_b64 + ("=" * (4 - rem) if rem else "")
                    payload_json = base64.urlsafe_b64decode(payload_padded).decode("utf-8")
                    payload = json.loads(payload_json)

                    # Verify expiration
                    if payload.get("exp") and payload["exp"] >= int(time.time()):
                        # Verify Supabase client audience
                        if payload.get("aud") == "authenticated":
                            return payload["sub"]
        except Exception:
            # Fall back to external Supabase validation if any error occurs
            pass

    # 2. Network Fallback
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
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Failed to verify token: {str(e)}")

        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid auth token")

        user_data = response.json()
        return user_data["id"]
