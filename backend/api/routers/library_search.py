"""Library registry search — PlatformIO public API with subprocess fallback.

Strategy:
  1. Try the PlatformIO REST API (fast, structured JSON).
  2. If that fails (offline, rate-limit), fall back to `pio pkg search` CLI.
  3. Always merge results with local libraries.json so curated entries appear
     even if the registry is unreachable.

Endpoint registered at:
  GET /api/libraries/search?query=<str>&page=<int>&limit=<int>
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from services.hardware import ensure_platformio

router = APIRouter(prefix="/api/libraries", tags=["Libraries"])

# PlatformIO public registry — same API the official IDE extension uses
_REGISTRY_URL = "https://api.registry.platformio.org/v3/packages"
_REQUEST_TIMEOUT = 8  # seconds


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _norm_registry(pkg: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single PlatformIO registry API package object."""
    latest = (pkg.get("versions") or [{}])[0]
    meta = latest.get("system", {})

    # pio install name is "owner/name" for registry packages
    owner = pkg.get("owner", {}).get("username", "") or pkg.get("owner", "")
    name = pkg.get("name", "")
    pio_name = f"{owner}/{name}" if owner else name

    return {
        "id": pio_name,
        "pio_name": pio_name,
        "name": name,
        "author": owner,
        "version": latest.get("name", ""),
        "description": pkg.get("description", ""),
        "category": (pkg.get("keywords") or [""])[0].title() if pkg.get("keywords") else "Library",
        "targets": meta.get("frameworks", []),
        "license": latest.get("license", ""),
        "homepage": pkg.get("homepage", ""),
        "source": "registry",
    }


def _norm_cli_line(owner_name: str, version_raw: str, description: str) -> dict[str, Any]:
    """Normalise a single result parsed from `pio pkg search` stdout."""
    # version_raw looks like "Verified • 10.5.1  • ..." or just "10.5.1"
    parts = [p.strip() for p in version_raw.split("•")]
    version = parts[1] if len(parts) > 1 else parts[0] if parts else ""
    category = parts[0].replace("Verified", "").strip() or "Library"

    name = owner_name.split("/")[-1] if "/" in owner_name else owner_name
    author = owner_name.split("/")[0] if "/" in owner_name else ""

    return {
        "id": owner_name,
        "pio_name": owner_name,
        "name": name,
        "author": author,
        "version": version,
        "description": description,
        "category": category,
        "targets": [],
        "license": "",
        "homepage": "",
        "source": "cli",
    }


# ---------------------------------------------------------------------------
# Search backends
# ---------------------------------------------------------------------------

def _search_via_api(query: str, page: int = 1, limit: int = 50) -> list[dict[str, Any]]:
    """Hit the PlatformIO REST API. Raises on any failure."""
    # Registry rejects queries shorter than 2 chars with 400
    if len(query) < 2:
        raise ValueError("Query too short for registry API (min 2 chars)")
    params = {
        "types": "library",
        "query": query,
        "page": page,
        "per_page": limit,
    }
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        resp = client.get(_REGISTRY_URL, params=params)
        resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    return [_norm_registry(pkg) for pkg in items]


def _search_via_cli(query: str) -> list[dict[str, Any]]:
    """Fall back to `pio pkg search` CLI. Slower (~2-5s) but works offline."""
    try:
        pio = ensure_platformio()
    except RuntimeError as exc:
        raise RuntimeError(f"PlatformIO not available: {exc}") from exc

    result = subprocess.run(
        [pio, "pkg", "search", query],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "pio pkg search failed")

    libraries: list[dict[str, Any]] = []
    lines = result.stdout.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Skip blanks, header lines ("Found N libraries:")
        if not line or re.match(r"Found \d+", line):
            i += 1
            continue
        # Package line format: "owner/name"
        if "/" in line and not line.startswith("#"):
            owner_name = line
            version_raw = lines[i + 1].strip() if i + 1 < len(lines) else ""
            description = lines[i + 2].strip() if i + 2 < len(lines) else ""
            # Skip if next line looks like another package (not version meta)
            if "/" in version_raw:
                i += 1
                continue
            libraries.append(_norm_cli_line(owner_name, version_raw, description))
            i += 3
            continue
        i += 1

    return libraries


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/search")
def search_libraries(
    query: str = "",
    page: int = 1,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search the PlatformIO library registry.

    Falls back to the CLI if the registry API is unreachable.
    Returns an empty list (not an error) if both fail — the frontend
    should handle an empty result gracefully.
    """
    q = query.strip()
    if len(q) < 2:
        return []  # too short — avoid 400 from registry and useless CLI results

    # 1. Try fast HTTP API
    try:
        return _search_via_api(q, page=page, limit=limit)
    except Exception as api_err:
        print(f"[library_search] Registry API failed ({api_err}), trying CLI…")

    # 2. Fall back to CLI
    try:
        return _search_via_cli(q)
    except Exception as cli_err:
        print(f"[library_search] CLI search also failed: {cli_err}")
        # Return empty rather than 500 — the local registry still works
        return []