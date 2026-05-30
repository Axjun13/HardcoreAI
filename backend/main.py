"""HardcoreAI API — application wiring.

A thin entry point: create the FastAPI app with the startup migrations as its
lifespan, apply CORS, and mount the resource routers. All behaviour lives in the
core / db / schemas / services / api packages.

Run with ``python main.py`` or ``uvicorn main:app`` from the backend directory.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    agent,
    components,
    conversations,
    files,
    health,
    projects,
    rag,
    workbench,
)
from db.migrations import lifespan

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("BACKEND_HOST", "127.0.0.1"),
        port=int(os.environ.get("BACKEND_PORT", "62018")),
    )
