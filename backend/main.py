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
    conversations,
    files,
    git,
    hardware,
    health,
    projects,
    rag,
    workbench,
)
from db.migrations import lifespan

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIST_DIR = BACKEND_DIR.parent / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

app = FastAPI(title="HardcoreAI API", version="0.3.0", lifespan=lifespan)

# The frontend normally runs on 127.0.0.1:62017, but keeping this to localhost
# origins lets preview builds and one-off dev ports work without CORS churn.
app.add_middleware(
    CORSMiddleware,
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
app.include_router(conversations.router)
app.include_router(rag.router)
app.include_router(git.router)
app.include_router(hardware.router)

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
