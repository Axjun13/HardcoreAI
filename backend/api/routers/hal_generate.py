from __future__ import annotations
import logging
import os
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from core.security import get_current_user_id
from db.models import CodeFileRow, ProjectRow
from db.session import db_session
from services.projects import get_project_or_404
from .hal_codegen import generate_hal_files

logger = logging.getLogger(__name__)
router = APIRouter()


class PeripheralConfig(BaseModel):
    id: str
    label: str
    mode: str
    params: dict = {}


class GenerateHALRequest(BaseModel):
    project_id: str
    board: str
    peripherals: list[PeripheralConfig]


class GeneratedFile(BaseModel):
    path: str
    content: str


class GenerateHALResponse(BaseModel):
    files: list[GeneratedFile]


@router.post("/api/generate-hal", response_model=GenerateHALResponse)
def generate_hal(
    req: GenerateHALRequest,
    user_id: str = Depends(get_current_user_id),
) -> GenerateHALResponse:
    logger.info("[HAL] board=%s peripherals=%s", req.board, [p.id for p in req.peripherals])

    with db_session(user_id) as session:
        # Use the exact same lookup all other routes use
        project = get_project_or_404(session, req.project_id, user_id)

        # Generate file contents
        peripheral_dicts = [
            {"id": p.id, "label": p.label, "mode": p.mode, "params": p.params}
            for p in req.peripherals
        ]
        generated = generate_hal_files(board=req.board, peripherals=peripheral_dicts)

        written: list[GeneratedFile] = []

        for rel_path, content in generated.items():
            # Upsert into DB so the file explorer sees it
            existing = session.exec(
                select(CodeFileRow).where(
                    CodeFileRow.project_id == project.id,
                    CodeFileRow.path == rel_path,
                )
            ).first()

            if existing:
                existing.content = content
                session.add(existing)
            else:
                session.add(CodeFileRow(
                    project_id=project.id,
                    path=rel_path,
                    language="c",
                    content=content,
                ))

            # Also write to disk if project has a folder path
            if project.path:
                full_path = os.path.join(project.path, rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

            written.append(GeneratedFile(path=rel_path, content=content))
            logger.info("[HAL] Wrote %s", rel_path)

        session.commit()

    logger.info("[HAL] Done — %d files", len(written))
    return GenerateHALResponse(files=written)