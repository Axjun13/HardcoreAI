"""Component catalogue listing."""

from __future__ import annotations

from fastapi import APIRouter

from db.session import db_session
from schemas import ComponentDefinition
from services.catalogue import load_catalogue

router = APIRouter()


@router.get("/api/components", response_model=list[ComponentDefinition])
def list_components(q: str | None = None) -> list[ComponentDefinition]:
    with db_session() as session:
        catalogue = load_catalogue(session)
    if not q:
        return catalogue
    term = q.casefold()
    return [
        component
        for component in catalogue
        if term in component.name.casefold()
        or term in component.category.casefold()
        or term in component.description.casefold()
    ]
