"""Public list of the legislation LawBuddy can currently answer from."""

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from backend.rag import api as engine

router = APIRouter(prefix="/laws", tags=["public"])


class LawOut(BaseModel):
    title: str
    kind: str
    act_number: int | None
    year: int | None


@router.get("", response_model=list[LawOut])
def list_laws() -> list[LawOut]:
    return [LawOut(**asdict(law)) for law in engine.list_laws()]
