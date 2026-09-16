"""
Chat Router
-----------
API Endpoints cho Chat RAG, Streaming & Upload File.
Chỉ tiếp nhận HTTP Request & gọi RAGService xử lý nghiệp vụ.
"""

import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from backend.services.rag_service import rag_service
from typing import List, Dict, Optional
from backend.services.ingest_service import DOCS_DIR

router = APIRouter(prefix="/api", tags=["RAG & Chat Engine"])

class ChatRequest(BaseModel):
    question: str
    history: Optional[List[Dict[str, str]]] = None

class ChatResponse(BaseModel):
    question: str
    answer: str

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """API Upload File đa định dạng (PDF, DOCX, CSV, Excel, JSON, TXT)"""
    os.makedirs(DOCS_DIR, exist_ok=True)
    file_path = os.path.join(DOCS_DIR, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        res = rag_service.ingest_single_file(file_path, file.filename)
        return {
            "message": f"Tải lên và xử lý tự động file '{file.filename}' thành công!",
            **res
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """API Trả lời câu hỏi RAG (Full Response) với multi-turn history"""
    answer = rag_service.query(request.question, history=request.history)
    return ChatResponse(question=request.question, answer=answer)

@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """API Trả lời câu hỏi RAG (Streaming Response) với multi-turn history"""
    return StreamingResponse(rag_service.stream_query(request.question, history=request.history), media_type="text/plain")

@router.get("/files/search")
async def search_files(q: str = ""):
    """Tìm kiếm nội dung bên trong file (text, pdf, csv) & mô tả ảnh AI trong RAG DB"""
    from backend.database import Session, engine, DocumentLog, select
    from datetime import datetime
    import unicodedata

    def normalize_text(text: str) -> str:
        """Chuyển chuỗi về chữ thường và loại bỏ dấu tiếng Việt để tìm kiếm linh hoạt"""
        if not text:
            return ""
        nfd = unicodedata.normalize('NFD', str(text).lower())
        without_accents = "".join(c for c in nfd if not unicodedata.combining(c))
        return without_accents.replace('đ', 'd').replace('Đ', 'd')


    raw_query = q.strip()
    query_str = raw_query.lower()
    norm_query = normalize_text(raw_query)

    # Không hiển thị sẵn nếu chưa nhập từ khóa tìm kiếm
    if not raw_query:
        return {
            "query": "",
            "total": 0,
            "files": []
        }

    results = []
    seen_files = set()

    # 1. Quét trong SQLite DocumentLog (bao gồm tóm tắt nội dung AI & mô tả ảnh AI Vision)
    try:
        with Session(engine) as session:
            logs = session.exec(select(DocumentLog)).all()
            for log in logs:
                summary_raw = log.summary or ""
                filename_raw = log.filename or ""
                category_raw = log.category or ""

                norm_summary = normalize_text(summary_raw)
                norm_filename = normalize_text(filename_raw)
                norm_category = normalize_text(category_raw)

                if (
                    query_str in filename_raw.lower() or norm_query in norm_filename or
                    query_str in summary_raw.lower() or norm_query in norm_summary or
                    query_str in category_raw.lower() or norm_query in norm_category
                ):
                    file_path = os.path.join(DOCS_DIR, log.filename)
                    size_kb = round(os.path.getsize(file_path) / 1024, 1) if os.path.exists(file_path) else 0
                    
                    results.append({
                        "filename": log.filename,
                        "file_type": log.file_type,
                        "category": log.category,
                        "summary": log.summary,
                        "match_type": "AI Database",
                        "chunk_count": log.chunk_count,
                        "size_kb": size_kb,
                        "created_at": log.created_at,
                        "download_url": f"/api/files/{log.filename}"
                    })
                    seen_files.add(log.filename)
    except Exception as e:
        print(f"⚠️ Lỗi đọc DocumentLog: {e}")

    # 2. Tìm kiếm trực tiếp vào nội dung các file văn bản (.txt, .csv, .json, .md) trong ổ đĩa
    if os.path.exists(DOCS_DIR):
        for f in sorted(os.listdir(DOCS_DIR)):
            file_path = os.path.join(DOCS_DIR, f)
            if os.path.isfile(file_path):
                ext = os.path.splitext(f)[1].lower()
                
                if f not in seen_files:
                    match_found = False
                    matched_content = "Tài liệu hệ thống"

                    norm_f = normalize_text(f)
                    if query_str in f.lower() or norm_query in norm_f:
                        match_found = True

                    elif ext in ['.txt', '.csv', '.json', '.md', '.log']:
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as fp:
                                content = fp.read()
                                norm_content = normalize_text(content)
                                
                                if query_str in content.lower() or norm_query in norm_content:
                                    match_found = True
                                    # Tìm vị trí xuất hiện
                                    idx = norm_content.find(norm_query)
                                    if idx == -1:
                                        idx = content.lower().find(query_str)
                                    
                                    start_idx = max(0, idx - 40)
                                    end_idx = min(len(content), idx + 110)
                                    matched_content = content[start_idx:end_idx].replace("\n", " ").strip()

                        except Exception:
                            pass

                    if match_found:
                        stat = os.stat(file_path)
                        cat = "Hình ảnh" if ext in ['.png', '.jpg', '.jpeg', '.webp', '.bmp'] else "Tài liệu"
                        results.append({
                            "filename": f,
                            "file_type": ext,
                            "category": cat,
                            "summary": matched_content,
                            "match_type": "Nội dung File",
                            "chunk_count": 1,
                            "size_kb": round(stat.st_size / 1024, 1),
                            "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "download_url": f"/api/files/{f}"
                        })
                        seen_files.add(f)

    return {
        "query": q,
        "total": len(results),
        "files": results
    }



@router.get("/files")
async def list_files():
    """Liệt kê tất cả file đã upload trong /docs/"""
    if not os.path.exists(DOCS_DIR):
        return {"files": []}

    files = []
    for f in sorted(os.listdir(DOCS_DIR)):
        full_path = os.path.join(DOCS_DIR, f)
        if os.path.isfile(full_path):
            stat = os.stat(full_path)
            files.append({
                "name": f,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "download_url": f"/api/files/{f}"
            })

    return {"files": files, "total": len(files)}

@router.get("/files/{filename}")
async def download_file(filename: str):
    """Download file gốc đã upload về máy user"""
    file_path = os.path.join(DOCS_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' không tồn tại.")

    if not os.path.abspath(file_path).startswith(os.path.abspath(DOCS_DIR)):
        raise HTTPException(status_code=400, detail="Đường dẫn không hợp lệ.")

    return FileResponse(
        path=file_path,
        filename=filename
    )


