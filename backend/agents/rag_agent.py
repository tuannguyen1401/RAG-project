"""
RAG Specialist Agent (rag_agent.py)
-----------------------------------
Chuyên trách xử lý toàn bộ logic Tra cứu Tài Liệu (Unstructured Document RAG):
- Query Preprocessing: Loại bỏ từ phụ, trích xuất thực thể, chuẩn hóa không dấu (Vietnamese accent normalization)
- Quản lý Hybrid Search Retriever (BM25 + Chroma Vector) với cơ chế Caching thông minh
- Keyword-based Re-ranking & Deduplication: Lọc trùng lặp chunk và ưu tiên đoạn văn liên quan trực tiếp
- Prompt tổng hợp tri thức chuẩn mực, chống lặp từ/kẹt đĩa (repeat_penalty)
"""

import os
import re
import glob
import unicodedata
from typing import Generator, List, Optional
from sqlmodel import Session, select

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever

from backend.database import engine, DocumentLog
from backend.services.ingest_service import load_single_document, CHROMA_PATH, DOCS_DIR, BASE_DIR

STOP_PHRASES = [
    "hãy tóm tắt", "tóm tắt cho tôi", "tóm tắt",
    "cho tôi biết", "hãy cho biết", "cho biết", "cho tôi hỏi",
    "thông tin về", "chi tiết về", "tìm hiểu về",
    "là ai ?", "là ai?", "là ai",
    "là gì ?", "là gì?", "là gì",
    "ở đâu ?", "ở đâu?", "ở đâu",
    "như thế nào", "ra sao",
    "ông", "bà", "anh", "chị", "em", "bạn"
]

def remove_vietnamese_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để matching chéo với tài liệu không dấu/tiếng Anh"""
    norm = unicodedata.normalize("NFD", text)
    norm = re.sub(r"[\u0300-\u036f]", "", norm)
    return norm.replace("đ", "d").replace("Đ", "D")

def extract_search_terms(question: str) -> tuple[str, list[str]]:
    """Trích xuất từ khóa tìm kiếm cốt lõi và danh sách keywords để re-rank"""
    q_clean = question.lower()
    for phrase in STOP_PHRASES:
        q_clean = q_clean.replace(phrase, " ")

    core_text = " ".join(q_clean.split())
    unacc_text = remove_vietnamese_accents(core_text)

    keywords = set()
    for w in core_text.split():
        if len(w) > 1:
            keywords.add(w.lower())
    for w in unacc_text.split():
        if len(w) > 1:
            keywords.add(w.lower())

    # Xây dựng retrieval query tối ưu cho BM25 & Vector
    parts = []
    if core_text:
        parts.append(core_text)
    if unacc_text and unacc_text != core_text:
        parts.append(unacc_text)
    if not parts:
        parts.append(question)

    retrieval_query = " ".join(parts)
    return retrieval_query, list(keywords)


def format_rag_history(history: Optional[list]) -> str:
    """Định dạng lịch sử đối thoại ngắn gọn đưa vào context của RAG"""
    if not history:
        return "Chưa có hội thoại trước đó."
    lines = []
    for item in history[-4:]:
        role = item.get("role", "user")
        content = item.get("content", "").strip()
        if not content:
            continue
        short_c = content[:200].replace("\n", " ")
        prefix = "User" if role == "user" else "AI"
        lines.append(f"{prefix}: {short_c}")
    return "\n".join(lines) if lines else "Chưa có hội thoại trước đó."


PROMPT_RAG = """Bạn là Trợ lý AI Phân Tích & Tổng Hợp Tri Thức Chuyên Sâu.
Nhiệm vụ của bạn là đọc hiểu ngữ cảnh trích dẫn và trả lời câu hỏi của người dùng một cách chính xác, mạch lạc, có cấu trúc và tự nhiên như đang trò chuyện liên tục.

--- DANH MỤC FILE TRONG HỆ THỐNG ---
{inventory}

--- LỊCH SỬ ĐỐI THOẠI GẦN ĐÂY ---
{chat_history}

--- TRÍCH DẪN NGỮ CẢNH TÌM ĐƯỢC ---
{context}

--- CÂU HỎI CỦA NGƯỜI DÙNG ---
{question}

--- NGUYÊN TẮC TRẢ LỜI CỐT LÕI ---
1. TIẾP NỐI HỘI THOẠI & ĐA LƯỢT (MULTI-TURN CHAT MEMORY):
   - Nếu câu hỏi trước đó và câu hỏi hiện tại cùng nói về một đối tượng, hãy tiếp nối mạch trò chuyện tự nhiên, trả lời đúng phần người dùng đang hỏi tiếp.
   - Gom các thông tin cùng công ty, cùng dự án hoặc cùng chủ đề vào chung một mục.
   - TUYỆT ĐỐI KHÔNG lặp lại cùng một công ty, cùng một mốc thời gian hay cùng một ý nhiều lần.

2. KHI ĐƯỢC YÊU CẦU "TÓM TẮT" HOẶC HỎI "LÀ AI":
   - Mở đầu: Họ tên đầy đủ, vai trò/vị trí chuyên môn chính và tổng quan năng lực.
   - Quá trình làm việc tiêu biểu: Liệt kê theo từng mốc công ty/dự án có thật trong trích dẫn (Tên công ty/dự án | Thời gian | Vai trò & đóng góp chính). Chỉ nêu công ty/dự án xuất hiện trong trích dẫn, KHÔNG tự gán ghép tên nơi khác.
   - Kỹ năng & Công nghệ cốt lõi: Nêu ngắn gọn các tech stack tiêu biểu.
   - Đánh giá tổng quan: 1 câu kết luận súc tích.
   - Trình bày dạng Markdown gạch đầu dòng rõ ràng, súc tích (khoảng 3-5 ý chính), KHÔNG liệt kê dàn trải lê thê.

3. TRUNG THỰC & CHỐNG BỊA ĐẶT (STRICT ANTI-HALLUCINATION):
   - CHỈ lấy thông tin có trong phần TRÍCH DẪN NGỮ CẢNH ở trên.
   - Nếu trong trích dẫn không có thông tin về đối tượng/chủ đề được hỏi, hãy trả lời rõ ràng: "Không tìm thấy thông tin về [đối tượng] trong tài liệu đã nạp."
   - TUYỆT ĐỐI KHÔNG lấy thông tin từ các công ty, ghi chú hay dự án khác trong ngữ cảnh để gán ghép sai lệch vào đối tượng đang hỏi.

--- PHẢN HỒI ---"""


class RAGAgent:
    def __init__(self):
        self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
        self.llm = ChatOllama(
            model="qwen2.5:3b",
            temperature=0.2,
            repeat_penalty=1.18,
            num_ctx=16384
        )
        self._cached_retriever = None

    def get_document_inventory(self) -> str:
        """Trả về danh mục tên file tài liệu (không chèn tóm tắt text để tránh model nhỏ bị lẫn lộn dữ liệu giữa các file)"""
        try:
            with Session(engine) as session:
                logs = session.exec(select(DocumentLog)).all()
                if not logs:
                    return "Chưa có file tài liệu nào trong CSDL."
                lines = [f"- {log.filename} ({log.file_type}, phân loại: {log.category})" for log in logs]
                return "\n".join(lines)
        except Exception:
            return ""

    def get_hybrid_retriever(self, force_refresh: bool = False):
        """Khởi tạo hoặc trả về Hybrid Retriever đã được cache"""
        if not os.path.exists(CHROMA_PATH):
            return None

        if self._cached_retriever and not force_refresh:
            return self._cached_retriever

        vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=self.embeddings)
        chroma_retriever = vectorstore.as_retriever(search_kwargs={"k": 6})

        all_documents = []
        if os.path.exists(DOCS_DIR):
            for ext in ["*.txt", "*.pdf", "*.docx", "*.doc", "*.csv", "*.xlsx", "*.xls", "*.json"]:
                for file_path in glob.glob(os.path.join(DOCS_DIR, ext)):
                    try:
                        docs = load_single_document(file_path)
                        all_documents.extend(docs)
                    except Exception as e:
                        print(f"⚠️ [RAGAgent] Không thể nạp file {file_path}: {e}")

        tailieu_root = os.path.join(BASE_DIR, "tailieu.txt")
        if os.path.exists(tailieu_root):
            try:
                all_documents.extend(load_single_document(tailieu_root))
            except Exception as e:
                print(f"⚠️ [RAGAgent] Không thể nạp tailieu.txt: {e}")

        if all_documents:
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
            splits = text_splitter.split_documents(all_documents)
            bm25_retriever = BM25Retriever.from_documents(splits)
            bm25_retriever.k = 6
            
            self._cached_retriever = EnsembleRetriever(
                retrievers=[bm25_retriever, chroma_retriever],
                weights=[0.5, 0.5]
            )
            return self._cached_retriever

        self._cached_retriever = chroma_retriever
        return self._cached_retriever

    def _prioritize_and_deduplicate(self, documents, keywords: List[str]):
        """Lọc trùng lặp chunk (Deduplication) và Re-rank ưu tiên các đoạn chứa từ khóa trực tiếp"""
        seen_signatures = set()
        unique_docs = []

        for doc in documents:
            text = doc.page_content.strip()
            if not text:
                continue
            norm_key = " ".join(text.split())[:120].lower()
            if norm_key not in seen_signatures:
                seen_signatures.add(norm_key)
                unique_docs.append(doc)

        # Chấm điểm độ khớp từ khóa (ưu tiên các chunk trực tiếp nhắc đến entity)
        def score_doc(d):
            full_text = (d.page_content + " " + str(d.metadata.get("source", ""))).lower()
            unacc = remove_vietnamese_accents(full_text)
            matches = sum(1 for kw in keywords if kw in full_text or kw in unacc)
            return matches

        # Nếu có từ khóa thực thể cụ thể và có tài liệu chứa từ khóa này, CHỈ lấy những tài liệu đó
        if keywords:
            matching_docs = [d for d in unique_docs if score_doc(d) > 0]
            if matching_docs:
                sorted_docs = sorted(matching_docs, key=score_doc, reverse=True)
                return sorted_docs[:4]

        sorted_docs = sorted(unique_docs, key=score_doc, reverse=True)
        # Giới hạn tối đa 4-5 chunks phù hợp nhất
        return sorted_docs[:4]

    def _format_docs_with_sources(self, documents) -> str:
        """Định dạng các trích đoạn kèm nguồn file và trang"""
        if not documents:
            return "Không tìm thấy đoạn trích dẫn liên quan."

        formatted = []
        for i, doc in enumerate(documents, 1):
            source = os.path.basename(doc.metadata.get("source", "Tài liệu"))
            page = doc.metadata.get("page", 1)
            formatted.append(f"[Trích đoạn {i} | Nguồn: {source} (Trang {page})]:\n{doc.page_content.strip()}")
        return "\n\n".join(formatted)

    def process(self, question: str, search_query: str = "", history: Optional[list] = None) -> str:
        """Xử lý tra cứu RAG sinh phản hồi hoàn chỉnh (hỗ trợ multi-turn history)"""
        retriever = self.get_hybrid_retriever()
        if not retriever:
            return "Chưa có dữ liệu tài liệu. Vui lòng nạp file trước!"

        if search_query and search_query.strip():
            sq = search_query.strip()
            unacc = remove_vietnamese_accents(sq)
            retrieval_query = f"{sq} {unacc}".strip()
            keywords = list(set([w.lower() for w in sq.split() + unacc.split() if len(w) > 1 and w.lower() not in ["file", "pdf", "txt", "docx", "csv"]]))
        else:
            retrieval_query, keywords = extract_search_terms(question)

        raw_docs = retriever.invoke(retrieval_query)
        selected_docs = self._prioritize_and_deduplicate(raw_docs, keywords)
        context_str = self._format_docs_with_sources(selected_docs)
        inventory_str = self.get_document_inventory()
        chat_history_str = format_rag_history(history)

        prompt = ChatPromptTemplate.from_template(PROMPT_RAG)
        chain = prompt | self.llm | StrOutputParser()

        return chain.invoke({
            "inventory": inventory_str,
            "chat_history": chat_history_str,
            "context": context_str,
            "question": question
        })

    def stream_process(self, question: str, search_query: str = "", history: Optional[list] = None) -> Generator[str, None, None]:
        """Xử lý tra cứu RAG dạng Streaming (hỗ trợ multi-turn history)"""
        retriever = self.get_hybrid_retriever()
        if not retriever:
            yield "Chưa có dữ liệu tài liệu. Vui lòng nạp file trước!"
            return

        if search_query and search_query.strip():
            sq = search_query.strip()
            unacc = remove_vietnamese_accents(sq)
            retrieval_query = f"{sq} {unacc}".strip()
            keywords = list(set([w.lower() for w in sq.split() + unacc.split() if len(w) > 1 and w.lower() not in ["file", "pdf", "txt", "docx", "csv"]]))
        else:
            retrieval_query, keywords = extract_search_terms(question)

        raw_docs = retriever.invoke(retrieval_query)
        selected_docs = self._prioritize_and_deduplicate(raw_docs, keywords)
        context_str = self._format_docs_with_sources(selected_docs)
        inventory_str = self.get_document_inventory()
        chat_history_str = format_rag_history(history)

        prompt = ChatPromptTemplate.from_template(PROMPT_RAG)
        chain = prompt | self.llm | StrOutputParser()

        for chunk in chain.stream({
            "inventory": inventory_str,
            "chat_history": chat_history_str,
            "context": context_str,
            "question": question
        }):
            yield chunk

rag_agent = RAGAgent()
