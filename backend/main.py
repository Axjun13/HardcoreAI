"""HardcoreAI API — application wiring.

A thin entry point: create the FastAPI app with the startup migrations as its
lifespan, apply CORS, and mount the resource routers. All behaviour lives in the
core / db / schemas / services / api packages.

Run with ``python main.py`` or ``uvicorn main:app`` from the backend directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routers import (
    agent,
    components,
    debug,
    files,
    git,
    hardware,
    health,
    hal_generate,
    libraries,
    projects,
    rag,
    research,
    workbench,
    library_search,
    search,
    boards,
    admin,
    profile,
)
from db.migrations import lifespan

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIST_DIR = BACKEND_DIR.parent / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

app = FastAPI(title="HardcoreAI API", version="0.3.0", lifespan=lifespan)

# In local/desktop use, the frontend runs on 127.0.0.1:62017 and the backend
# serves the built frontend directly (see serve_frontend below), so same-
# origin requests need no CORS at all — the regex below only covers dev
# preview ports hitting the API cross-origin.
#
# When deployed as two separate services (e.g. frontend on Vercel, backend
# on Render), the browser origin is a real https:// domain that the regex
# below will never match, so every request would be silently blocked by
# CORS. Set FRONTEND_ORIGINS to a comma-separated list of the deployed
# frontend URL(s) — e.g. "https://hardcoreai.vercel.app" — as an env var on
# the backend host.
_extra_origins = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_extra_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(components.router)
app.include_router(projects.router)
app.include_router(workbench.router)
app.include_router(files.router)
app.include_router(agent.router)
app.include_router(rag.router)
app.include_router(research.router)
app.include_router(git.router)
app.include_router(hardware.router)
app.include_router(debug.router)
app.include_router(libraries.router)
app.include_router(library_search.router)
app.include_router(hal_generate.router) 
app.include_router(search.router)
app.include_router(boards.router)
app.include_router(admin.router)
app.include_router(profile.router)
if FRONTEND_ASSETS_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_ASSETS_DIR),
        name="frontend-assets",
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    index_file = FRONTEND_DIST_DIR / "index.html"
    requested_file = (FRONTEND_DIST_DIR / full_path).resolve()

    if requested_file.is_relative_to(FRONTEND_DIST_DIR) and requested_file.is_file():
        return FileResponse(requested_file)

    if index_file.is_file():
        return FileResponse(index_file)

    raise HTTPException(
        status_code=404,
        detail="Frontend build not found. Run npm run build from the frontend directory.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("BACKEND_HOST", "127.0.0.1"),
        port=int(os.environ.get("BACKEND_PORT", "62018")),
    )