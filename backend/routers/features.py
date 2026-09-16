from typing import List
from fastapi import APIRouter
from sqlmodel import Session, select

from backend.database import engine, Feature

router = APIRouter(prefix="/api/features", tags=["Public Features"])

@router.get("", response_model=List[Feature])
async def get_public_features():
    """[PUBLIC READ] Lấy danh sách các Feature đang Hoạt động (is_active == True) cho trang RAG"""
    with Session(engine) as session:
        return session.exec(select(Feature).where(Feature.is_active == True)).all()
