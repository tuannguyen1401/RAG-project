"""
RAG Service Module (Facade)
---------------------------
Cung cấp Service Layer tập trung kết nối với các Agent chuyên trách:
- Router Agent (router_agent.py): Điều hướng ý định & xử lý hội thoại.
- Log Agent (log_agent.py): Xử lý Nhật ký công việc.
- SQL Agent (sql_agent.py): Xử lý NL2SQL & Format kết quả.
- RAG Agent (rag_agent.py): Xử lý Tra cứu văn bản Hybrid Search.
"""

import os
from typing import Generator, Optional
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.agents.router_agent import router_agent
from backend.services.ingest_service import load_single_document, register_document_metadata, CHROMA_PATH

class RAGService:
    def query(self, question: str, history: Optional[list] = None) -> str:
        """Truy vấn chính: Chuyển qua Router Agent điều hướng (hỗ trợ multi-turn history)"""
        return router_agent.route_and_execute(question, history=history)

    def stream_query(self, question: str, history: Optional[list] = None) -> Generator[str, None, None]:
        """Truy vấn dạng Streaming: Chuyển qua Router Agent điều hướng (hỗ trợ multi-turn history)"""
        return router_agent.route_and_stream(question, history=history)

    def ingest_single_file(self, file_path: str, filename: str) -> dict:
        """Nạp file đơn lẻ"""
        docs = load_single_document(file_path)
        if not docs:
            raise ValueError(f"Không thể bóc tách nội dung từ file '{filename}'.")

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)

        embeddings = OllamaEmbeddings(model="nomic-embed-text")
        Chroma.from_documents(documents=splits, embedding=embeddings, persist_directory=CHROMA_PATH)

        ext = os.path.splitext(filename)[1].lower()
        sample_text = splits[0].page_content if splits else ""
        register_document_metadata(filename, ext, len(splits), sample_text)

        # Làm mới cache retriever để tài liệu mới có hiệu lực ngay
        from backend.agents.rag_agent import rag_agent
        rag_agent.get_hybrid_retriever(force_refresh=True)

        return {
            "filename": filename,
            "file_type": ext,
            "chunks_added": len(splits),
            "summary": sample_text
        }

rag_service = RAGService()
