"""In-process web search for the RAG engine.

Replaces the old design that shelled out over HTTP to a self-hosted SearXNG
server on port 8080 (which required Docker and collided with the local
llama.cpp server). Search now happens inside the backend process — no separate
server, no port, no Docker.

Two backends, selected automatically:

  * HardcoreAI's authenticated cloud proxy. The distributed application never
    receives or reads the paid Brave API key.
  * DuckDuckGo via the ``ddgs`` library — the zero-config default when no key
    is present. Works with no signup, but scrapes DuckDuckGo (against its ToS)
    and is rate-limited, so it is intended for local development only.

Public surface::

    search_web(query: str, num_results: int = 5) -> list[dict]
    search_images(query: str, num_results: int = 5) -> list[dict]

Returns ``[{"title", "url", "snippet"}, ...]``. Never raises — on failure it
returns a single-element list ``[{"error": <msg>, "title": "", "url": "",
"snippet": ""}]`` so callers can surface a readable message (mirrors the
contract the previous SearXNG-based implementation exposed).
"""

from __future__ import annotations

import os
import uuid

from core.security import cloud_request_context, request_access_token

CLOUD_PROXY_URL = os.getenv(
    "HARDCOREAI_PROXY_URL",
    "https://hardcoreai-proxy-server.vercel.app",
).rstrip("/")


def _err(msg: str) -> list[dict]:
    return [{"error": msg, "title": "", "url": "", "snippet": ""}]


def _search_cloud(query: str, num_results: int) -> list[dict]:
    """Query paid search through the authenticated gateway."""
    import httpx

    access_token = request_access_token()
    if not access_token:
        return _err("Sign in again before using cloud search.")
    agent_run_id, project_id = cloud_request_context()
    payload = {
        "query": query,
        "count": max(1, min(int(num_results), 10)),
        "agentRunId": agent_run_id or str(uuid.uuid4()),
        **({"projectId": project_id} if project_id else {}),
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{CLOUD_PROXY_URL}/api/search",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return _err(f"Cloud search request failed: {exc}")

    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        }
        for item in (data.get("results") or [])[:num_results]
    ]


def _search_ddg(query: str, num_results: int) -> list[dict]:
    """Query DuckDuckGo in-process via the ``ddgs`` library (no key)."""
    try:
        from ddgs import DDGS
    except ImportError:
        return _err(
            "Web search is not available: the 'ddgs' package is not installed "
            "and no authenticated cloud session is available. Install ddgs "
            "(`uv add ddgs`) for local development."
        )

    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=int(num_results)))
    except Exception as exc:
        return _err(f"DuckDuckGo search failed: {exc}")

    results = []
    for item in hits[:num_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("href", "") or item.get("url", ""),
            "snippet": item.get("body", "") or item.get("snippet", ""),
        })
    return results


def search_web(query: str, num_results: int = 5) -> list[dict]:
    """Run an in-process web search and return result metadata.

    Uses the paid cloud proxy for authenticated requests, otherwise falls back
    to the key-less DuckDuckGo development backend. Never raises.
    """
    query = (query or "").strip()
    if not query:
        return _err("Empty search query.")
    if request_access_token():
        return _search_cloud(query, num_results)
    return _search_ddg(query, num_results)


def search_images(query: str, num_results: int = 5) -> list[dict]:
    """Find remotely hosted product images for catalogue cards.

    Each result contains ``image`` (the actual image URL), ``url`` (the source
    page), and ``title``. Like :func:`search_web`, failures are returned as an
    error record so component discovery can degrade without breaking Research.
    """
    query = (query or "").strip()
    if not query:
        return _err("Empty image search query.")
    limit = max(1, min(int(num_results), 20))
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            hits = list(ddgs.images(query, max_results=limit, safesearch="on"))
    except ImportError:
        return _err("Image search is unavailable because the 'ddgs' package is not installed.")
    except Exception as exc:
        return _err(f"DuckDuckGo image search failed: {exc}")
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", "") or item.get("source", ""),
            "image": item.get("image", "") or item.get("thumbnail", ""),
        }
        for item in hits[:limit]
    ]
