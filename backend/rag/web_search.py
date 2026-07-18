"""In-process web search for the RAG engine.

Replaces the old design that shelled out over HTTP to a self-hosted SearXNG
server on port 8080 (which required Docker and collided with the local
llama.cpp server). Search now happens inside the backend process — no separate
server, no port, no Docker.

Two backends, selected automatically:

  * Brave Search API — used when ``BRAVE_API_KEY`` is set. A licensed,
    key-based API whose ToS permits commercial use. This is the recommended
    path for a commercial deployment.
  * DuckDuckGo via the ``ddgs`` library — the zero-config default when no key
    is present. Works with no signup, but scrapes DuckDuckGo (against its ToS)
    and is rate-limited, so it is intended for dev/MVP use. Set BRAVE_API_KEY
    before a commercial launch.

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

# Licensed search API key (Brave). When set, we use Brave instead of ddgs.
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "").strip()
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
BRAVE_IMAGES_ENDPOINT = "https://api.search.brave.com/res/v1/images/search"


def _err(msg: str) -> list[dict]:
    return [{"error": msg, "title": "", "url": "", "snippet": ""}]


def _search_brave(query: str, num_results: int) -> list[dict]:
    """Query the Brave Search API (licensed, commercial-safe)."""
    import httpx

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {"q": query, "count": max(1, min(int(num_results), 20))}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(BRAVE_ENDPOINT, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return _err(f"Brave Search API request failed: {exc}")

    web = (data.get("web") or {}).get("results", []) or []
    results = []
    for item in web[:num_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })
    return results


def _search_ddg(query: str, num_results: int) -> list[dict]:
    """Query DuckDuckGo in-process via the ``ddgs`` library (no key)."""
    try:
        from ddgs import DDGS
    except ImportError:
        return _err(
            "Web search is not available: the 'ddgs' package is not installed "
            "and no BRAVE_API_KEY is set. Install ddgs (`uv add ddgs`) or set "
            "BRAVE_API_KEY in the backend .env."
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

    Uses Brave when ``BRAVE_API_KEY`` is set, otherwise falls back to the
    key-less DuckDuckGo (``ddgs``) backend. Never raises.
    """
    query = (query or "").strip()
    if not query:
        return _err("Empty search query.")
    if BRAVE_API_KEY:
        return _search_brave(query, num_results)
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
    if BRAVE_API_KEY:
        import httpx

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(
                    BRAVE_IMAGES_ENDPOINT,
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": BRAVE_API_KEY,
                    },
                    params={"q": query, "count": limit, "safesearch": "strict"},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return _err(f"Brave Image Search API request failed: {exc}")
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", "") or item.get("source", ""),
                "image": (item.get("properties") or {}).get("url", "")
                or (item.get("thumbnail") or {}).get("src", ""),
            }
            for item in (payload.get("results") or [])[:limit]
        ]

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
