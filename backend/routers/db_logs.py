from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.database import engine, DailyLog, execute_raw_sql
from backend.nl2sql import execute_nl2sql

router = APIRouter(prefix="/api/db", tags=["Daily Logs & NL2SQL Engine"])

class SqlValidateRequest(BaseModel):
    prompt: str
    auto_execute: Optional[bool] = False

class SqlExecuteRawRequest(BaseModel):
    sql: str

@router.get("/logs", response_model=List[DailyLog])
async def get_logs(log_date: Optional[str] = None, keyword: Optional[str] = None):
    with Session(engine) as session:
        statement = select(DailyLog)
        if log_date:
            statement = statement.where(DailyLog.log_date == log_date)
        if keyword:
            statement = statement.where(DailyLog.content.contains(keyword) | DailyLog.category.contains(keyword))
        return session.exec(statement.order_by(DailyLog.id.desc())).all()

@router.post("/logs", response_model=DailyLog)
async def create_log(log: DailyLog):
    with Session(engine) as session:
        session.add(log)
        session.commit()
        session.refresh(log)
        return log

@router.delete("/logs/{log_id}")
async def delete_log(log_id: int):
    with Session(engine) as session:
        log = session.get(DailyLog, log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Không tìm thấy ID nhật ký cần xóa.")
        session.delete(log)
        session.commit()
        return {"id": log_id, "deleted": True}

@router.post("/sql/generate")
async def generate_sql_endpoint(request: SqlValidateRequest):
    return execute_nl2sql(user_prompt=request.prompt, auto_execute=request.auto_execute)

@router.post("/sql/execute")
async def execute_raw_sql_endpoint(request: SqlExecuteRawRequest):
    return execute_raw_sql(sql_query=request.sql)
