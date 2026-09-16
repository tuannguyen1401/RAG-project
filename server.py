import os
import shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingest import load_document, CHROMA_PATH, DOCS_DIR

app = FastAPI(
    title="RAG Intelligence API",
    description="Hệ Thống RAG Hỏi Đáp Tài Liệu Thông Minh",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

embeddings = OllamaEmbeddings(model="nomic-embed-text")
llm = ChatOllama(model="qwen2.5:3b", temperature=0.1)

def get_vectorstore():
    if os.path.exists(CHROMA_PATH):
        return Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    return None

class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    question: str
    answer: str

def format_docs_with_sources(documents):
    formatted = []
    for i, doc in enumerate(documents, 1):
        source = doc.metadata.get("source", "Tài liệu")
        page = doc.metadata.get("page", 1)
        formatted.append(f"[Đoạn {i} | File: {source} (Trang {page})]:\n{doc.page_content}")
    return "\n\n".join(formatted)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    os.makedirs(DOCS_DIR, exist_ok=True)
    file_path = os.path.join(DOCS_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        from backend.services.rag_service import rag_service
        res = rag_service.ingest_single_file(file_path, file.filename)
        return {
            "message": f"Tải lên và xử lý file '{file.filename}' thành công!",
            **res
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể đọc nội dung từ file tải lên: {str(e)}")


@app.get("/api/files/search")
async def search_files(q: str = ""):
    """Tìm kiếm file tài liệu / ảnh trong RAG qua SQLite DocumentLog & ổ đĩa local"""
    from backend.database import Session, engine, DocumentLog, select
    from datetime import datetime
    
    query_str = q.strip().lower()
    results = []
    seen_files = set()

    # 1. Tìm kiếm trong SQLite DocumentLog theo tên file, mô tả summary hoặc danh mục
    try:
        with Session(engine) as session:
            logs = session.exec(select(DocumentLog)).all()
            for log in logs:
                if not query_str or (
                    query_str in log.filename.lower() or 
                    query_str in log.summary.lower() or 
                    query_str in log.category.lower()
                ):
                    file_path = os.path.join(DOCS_DIR, log.filename)
                    size_kb = round(os.path.getsize(file_path) / 1024, 1) if os.path.exists(file_path) else 0
                    results.append({
                        "filename": log.filename,
                        "file_type": log.file_type,
                        "category": log.category,
                        "summary": log.summary,
                        "chunk_count": log.chunk_count,
                        "size_kb": size_kb,
                        "created_at": log.created_at,
                        "download_url": f"/api/files/{log.filename}"
                    })
                    seen_files.add(log.filename)
    except Exception as e:
        print(f"⚠️ Lỗi đọc DocumentLog SQLite: {e}")

    # 2. Tìm kiếm các file trong thư mục DOCS_DIR chưa có trong SQLite
    if os.path.exists(DOCS_DIR):
        for f in sorted(os.listdir(DOCS_DIR)):
            if f not in seen_files and os.path.isfile(os.path.join(DOCS_DIR, f)):
                if not query_str or query_str in f.lower():
                    stat = os.stat(os.path.join(DOCS_DIR, f))
                    ext = os.path.splitext(f)[1].lower()
                    cat = "Hình ảnh" if ext in ['.png', '.jpg', '.jpeg', '.webp', '.bmp'] else "Tài liệu"
                    results.append({
                        "filename": f,
                        "file_type": ext,
                        "category": cat,
                        "summary": "Tài liệu hệ thống",
                        "chunk_count": 1,
                        "size_kb": round(stat.st_size / 1024, 1),
                        "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "download_url": f"/api/files/{f}"
                    })

    return {
        "query": q,
        "total": len(results),
        "files": results
    }


@app.get("/api/files")
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


@app.get("/api/files/{filename}")
async def download_file(filename: str):
    """Download file gốc đã upload về máy user"""
    file_path = os.path.join(DOCS_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' không tồn tại.")

    # Bảo vệ khỏi path traversal attack (vd: ../secret)
    if not os.path.abspath(file_path).startswith(os.path.abspath(DOCS_DIR)):
        raise HTTPException(status_code=400, detail="Đường dẫn không hợp lệ.")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"  # Buộc browser download, không mở trên browser
    )


@app.get("/api/features")
async def get_features():
    """Trả về danh sách tính năng AI cho sidebar UI từ cơ sở dữ liệu"""
    from backend.database import Session, engine, Feature, select
    with Session(engine) as session:
        features = session.exec(select(Feature).where(Feature.is_active == True)).all()
        return [
            {
                "icon": f.icon,
                "title": f.title,
                "badge": f.badge,
                "description": f.description
            }
            for f in features
        ]


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    from backend.services.rag_service import rag_service
    answer = rag_service.query(request.question)
    return ChatResponse(question=request.question, answer=answer)

@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    from backend.services.rag_service import rag_service
    def generate_chunks():
        for chunk in rag_service.stream_query(request.question):
            yield chunk

    return StreamingResponse(generate_chunks(), media_type="text/plain")

# ── Static Files (Frontend) ──────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return FileResponse(FRONTEND_DIR / "index.html")

