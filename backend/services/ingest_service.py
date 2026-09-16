"""
Ingest Service Module
---------------------
Quản lý việc bóc tách tài liệu đa định dạng (PDF, DOCX, CSV, Excel, JSON, TXT)
và đăng ký lưu trữ kép vào SQLite DocumentLog & ChromaDB Vector Store.
"""

import os
import glob
import shutil
import json
import pandas as pd
from typing import List

from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from sqlmodel import Session, select

from backend.database import engine, DocumentLog

import base64
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
DOCS_DIR = os.path.join(BASE_DIR, "docs")


import io
from PIL import Image

def get_optimized_image_b64(image_path: str, max_dim: int = 1024) -> str:
    """Nén & Resize ảnh thông minh để Vision AI xử lý tốc độ cao (nhanh gấp 5 lần)"""
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > max_dim:
                scale = max_dim / float(max(w, h))
                new_w = int(w * scale)
                new_h = int(h * scale)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"⚠️ Không thể nén ảnh, dùng file gốc: {e}")
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


def describe_image_with_vision(image_path: str) -> str:
    """Sử dụng Vision AI (Ollama) để phân tích & mô tả chi tiết nội dung bức ảnh bằng tiếng Việt"""
    img_b64 = get_optimized_image_b64(image_path, max_dim=1024)

    # Ưu tiên moondream (chạy 100% VRAM GPU siêu nhanh 2s) -> minicpm-v (chi tiết hơn 8s)
    for model_name in ["moondream", "minicpm-v", "llava"]:
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model_name,
                    "prompt": (
                        "Hãy phân tích và mô tả thật chi tiết bức ảnh này bằng tiếng Việt. "
                        "Nêu rõ: Khung cảnh, các đối tượng xuất hiện, màu sắc chủ đạo, hành động, "
                        "và tất cả các dòng chữ/văn bản có trong ảnh (nếu có) để phục vụ tìm kiếm RAG."
                    ),
                    "images": [img_b64],
                    "stream": False
                },
                timeout=60
            )
            if response.status_code == 200:
                res_text = response.json().get("response", "").strip()
                if res_text:
                    print(f"⚡ Đã phân tích ảnh siêu nhanh bằng model Vision: {model_name}")
                    return res_text
        except Exception as e:
            print(f"⚠️ Model {model_name} không khả dụng: {e}")
            continue

    return "Tập tin hình ảnh (chưa thể trích xuất chi tiết văn bản)."


def load_single_document(file_path: str) -> List[Document]:
    """Đọc và bóc tách nội dung 1 file bất kỳ dựa theo định dạng mở rộng (extension)"""
    ext = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path)
    docs: List[Document] = []

    try:
        if ext == ".txt":
            loader = TextLoader(file_path, encoding="utf-8")
            docs = loader.load()
            for doc in docs:
                doc.metadata["source"] = filename
                doc.metadata.setdefault("page", 1)

        elif ext == ".pdf":
            loader = PyPDFLoader(file_path)
            docs = loader.load()
            for doc in docs:
                doc.metadata["source"] = filename
                if "page" in doc.metadata:
                    doc.metadata["page"] += 1

        elif ext in [".docx", ".doc"]:
            import docx
            doc = docx.Document(file_path)
            full_text = [para.text for para in doc.paragraphs if para.text.strip()]
            text = "\n".join(full_text)
            docs = [Document(page_content=text, metadata={"source": filename, "page": 1})]

        elif ext == ".csv":
            df = pd.read_csv(file_path)
            rows_text = [
                f"Hàng {idx+1}: " + ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                for idx, row in df.iterrows()
            ]
            full_text = f"Tập dữ liệu CSV '{filename}' ({len(df)} hàng) [Cột: {', '.join(df.columns)}]:\n" + "\n".join(rows_text)
            docs = [Document(page_content=full_text, metadata={"source": filename, "page": 1})]

        elif ext in [".xlsx", ".xls"]:
            excel = pd.ExcelFile(file_path)
            sheets_text = []
            for sheet_name in excel.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                rows_text = [
                    f"Hàng {idx+1}: " + ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                    for idx, row in df.iterrows()
                ]
                sheets_text.append(f"--- Sheet '{sheet_name}' ({len(df)} hàng) ---\n" + "\n".join(rows_text))
            full_text = f"File Excel '{filename}':\n" + "\n\n".join(sheets_text)
            docs = [Document(page_content=full_text, metadata={"source": filename, "page": 1})]

        elif ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            pretty_text = f"Dữ liệu JSON '{filename}':\n" + json.dumps(data, ensure_ascii=False, indent=2)
            docs = [Document(page_content=pretty_text, metadata={"source": filename, "page": 1})]

        elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
            print(f"🖼️ Đang dùng Vision AI phân tích mô tả nội dung hình ảnh '{filename}'...")
            description = describe_image_with_vision(file_path)
            full_text = (
                f"Tập tin Hình Ảnh: '{filename}'\n"
                f"Đường dẫn file: docs/{filename}\n"
                f"Nội dung & Mô tả chi tiết hình ảnh từ Vision AI:\n{description}"
            )
            docs = [Document(page_content=full_text, metadata={"source": filename, "page": 1})]

        else:
            print(f"⚠️ Chưa hỗ trợ định dạng: {filename}")

    except Exception as e:
        print(f"❌ Lỗi bóc tách file {filename}: {e}")

    return docs


def register_document_metadata(filename: str, file_type: str, chunk_count: int, sample_text: str):
    """Tự động ghi thông tin tóm tắt và metadata tài liệu vào CSDL SQLite DocumentLog"""
    if file_type in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
        category = "Hình ảnh"
    elif file_type in [".csv", ".xlsx", ".json"]:
        category = "Bảng dữ liệu"
    else:
        category = "Tài liệu văn bản"

    # Lưu đầy đủ tóm tắt / mô tả Vision AI (lên đến 3000 ký tự) không cắt vụn thành 180 ký tự
    summary = sample_text[:3000].strip() if len(sample_text) > 3000 else sample_text.strip()


    with Session(engine) as session:
        existing = session.exec(select(DocumentLog).where(DocumentLog.filename == filename)).first()
        if existing:
            existing.chunk_count = chunk_count
            existing.summary = summary
            existing.file_type = file_type
            session.add(existing)
        else:
            doc_log = DocumentLog(
                filename=filename,
                file_type=file_type,
                category=category,
                summary=summary,
                chunk_count=chunk_count
            )
            session.add(doc_log)
        session.commit()


def run_ingestion_pipeline():
    """Hàm chạy toàn bộ quy trình Ingestion nạp tất cả tài liệu trong thư mục docs/ vào RAG"""
    os.makedirs(DOCS_DIR, exist_ok=True)
    files_to_process = []

    tailieu_root = os.path.join(BASE_DIR, "tailieu.txt")
    if os.path.exists(tailieu_root):
        files_to_process.append(tailieu_root)

    for ext in ["*.txt", "*.pdf", "*.docx", "*.doc", "*.csv", "*.xlsx", "*.xls", "*.json", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"]:
        files_to_process.extend(glob.glob(os.path.join(DOCS_DIR, ext)))

    files_to_process = list(set(files_to_process))
    if not files_to_process:
        print("📁 Không tìm thấy tài liệu nào.")
        return

    print(f"1. 📄 Đang xử lý {len(files_to_process)} tài liệu...")
    all_documents = []
    for f in files_to_process:
        docs = load_single_document(f)
        all_documents.extend(docs)

    if not all_documents:
        print("❌ Không có dữ liệu văn bản.")
        return

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
    splits = text_splitter.split_documents(all_documents)
    print(f"2. ✂️ Đã tạo {len(splits)} chunks vector.")

    # Đăng ký CSDL SQLite DocumentLog
    for f in files_to_process:
        filename = os.path.basename(f)
        ext = os.path.splitext(filename)[1].lower()
        file_chunks = [s for s in splits if s.metadata.get("source") == filename]
        sample_text = file_chunks[0].page_content if file_chunks else ""
        register_document_metadata(filename, ext, len(file_chunks), sample_text)

    # Làm sạch CSDL VectorStore cũ
    if os.path.exists(CHROMA_PATH):
        try:
            shutil.rmtree(CHROMA_PATH)
        except Exception:
            pass

    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    Chroma.from_documents(documents=splits, embedding=embeddings, persist_directory=CHROMA_PATH)
    print("✅ Ingestion thành công!")
