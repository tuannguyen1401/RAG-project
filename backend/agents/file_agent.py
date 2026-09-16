"""
file_agent.py
─────────────
Agent xử lý intent FILE / DOWNLOAD:
- Trích xuất tên file bằng cả Heuristic Regex Direct Match, Vietnamese Accent Normalization & LLM Fallback.
- Hỗ trợ cả TẢI FILE VỀ và TÓM TẮT/BÓC TÁCH NỘI DUNG FILE nếu người dùng yêu cầu.
"""

import os
import re
import unicodedata
from difflib import SequenceMatcher
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from ingest import DOCS_DIR


PROMPT_EXTRACT_FILENAME = """Người dùng đề cập đến một file. Hãy trích xuất TÊN FILE mà họ đề cập.
Chỉ trả về tên file (bao gồm phần mở rộng nếu có), không giải thích thêm.
Nếu không xác định được tên file cụ thể, trả về "UNKNOWN".

Ví dụ:
- "Hãy phân tích và tóm tắt nội dung của file 'Scene khung cảnh định.txt' giúp tôi" → Scene khung cảnh định.txt
- "download CV của Tuấn" → FullStack-NguyenThanhTuan.pdf
- "tôi cần file đơn hàng" → don_hang_chi_tiet.csv
- "tải file abc xyz" → abc xyz

Câu hỏi: {question}
Tên file:"""


def normalize_text(text: str) -> str:
    """Chuyển chuỗi về chữ thường và loại bỏ dấu tiếng Việt để so sánh linh hoạt"""
    if not text:
        return ""
    nfd = unicodedata.normalize('NFD', str(text).lower())
    without_accents = "".join(c for c in nfd if not unicodedata.combining(c))
    return without_accents.replace('đ', 'd').replace('Đ', 'd')


class FileAgent:
    def __init__(self):
        self.llm = ChatOllama(model="qwen2.5:3b", temperature=0.0)

    def _list_docs(self) -> list[str]:
        """Lấy danh sách tất cả file trong /docs/"""
        if not os.path.exists(DOCS_DIR):
            return []
        return [
            f for f in os.listdir(DOCS_DIR)
            if os.path.isfile(os.path.join(DOCS_DIR, f))
        ]

    def _direct_match(self, question: str, candidates: list[str]) -> str | None:
        """
        Tìm kiếm trực tiếp từ câu hỏi bằng Heuristics & Unaccent Normalization:
        1. Tìm tên file trong ngoặc đơn/kép ('...' hoặc "...")
        2. So sánh tên file với các từ khóa quan trọng trong câu hỏi.
        """
        q_norm = normalize_text(question)

        # 1. Trích xuất text trong dấu ngoặc
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", question)
        for q_item in quoted:
            q_clean_norm = normalize_text(q_item.strip())
            if not q_clean_norm:
                continue
            for f in candidates:
                f_norm = normalize_text(f)
                if q_clean_norm == f_norm or f_norm in q_clean_norm or q_clean_norm in f_norm:
                    return f

        # 2. So sánh nguyên chuỗi không dấu
        for f in candidates:
            f_norm = normalize_text(f)
            f_no_ext = os.path.splitext(f_norm)[0]
            if f_norm in q_norm or (len(f_no_ext) >= 3 and f_no_ext in q_norm):
                return f

        # 3. Lọc ra các từ khóa có nghĩa trong câu hỏi (loại bỏ từ nối common)
        stop_words = {'lay', 'file', 'cho', 'can', 'tai', 'xem', 'cua', 'dump', 'read', 'get', 'down',
                      'download', 'tom', 'tat', 'phan', 'tich', 'noi', 'dung', 'giup', 'toi', 'voi', 've'}
        q_tokens = [w for w in re.split(r'[^\w]+', q_norm) if len(w) >= 3 and w not in stop_words]

        if q_tokens:
            for f in candidates:
                f_norm = normalize_text(f)
                # Nếu tất cả hoặc đa số tokens xuất hiện trong tên file
                if any(tok in f_norm for tok in q_tokens):
                    return f

        return None


    def _fuzzy_match(self, query: str, candidates: list[str]) -> str | None:
        """
        Tìm file khớp nhất với query bằng 2 phương pháp:
        1. Substring match
        2. SequenceMatcher similarity score
        """
        if not candidates or not query or query.strip().upper() == "UNKNOWN":
            return None

        q_norm = normalize_text(query)

        # Ưu tiên 1: Exact / Normalized substring match
        for f in candidates:
            f_norm = normalize_text(f)
            if q_norm in f_norm or f_norm in q_norm:
                return f

        # Ưu tiên 2: Fuzzy similarity (threshold >= 0.40)
        best_score = 0.0
        best_file = None
        for f in candidates:
            score = SequenceMatcher(None, q_norm, normalize_text(f)).ratio()
            if score > best_score:
                best_score = score
                best_file = f

        return best_file if best_score >= 0.40 else None

    def process(self, question: str) -> str:
        """
        Xử lý yêu cầu file (tải file hoặc đọc / tóm tắt nội dung file).
        """
        all_files = self._list_docs()
        if not all_files:
            return "❌ **Chưa có file nào được tải lên hệ thống.**"

        # ── Bước 1: Thử Direct Match trước (tránh LLM trích xuất UNKNOWN) ────
        matched_file = self._direct_match(question, all_files)
        extracted_name = matched_file or "UNKNOWN"

        # ── Bước 2: Nếu chưa thấy, dùng LLM trích xuất tên file ───────────────
        if not matched_file:
            try:
                prompt = ChatPromptTemplate.from_template(PROMPT_EXTRACT_FILENAME)
                chain = prompt | self.llm | StrOutputParser()
                extracted_name = chain.invoke({"question": question}).strip()
            except Exception as e:
                print(f"⚠️ [FileAgent] LLM extract lỗi: {e}")
                extracted_name = "UNKNOWN"

            matched_file = self._fuzzy_match(extracted_name, all_files)

        # Fallback lần 3: Quét lại câu hỏi không dấu
        if not matched_file:
            matched_file = self._direct_match(question, all_files)

        # ── Bước 3: Trả về kết quả ───────────────────────────────────────────
        if matched_file:
            from urllib.parse import quote
            encoded_name = quote(matched_file, safe='')
            download_url = f"/api/files/{encoded_name}"

            ext = matched_file.rsplit(".", 1)[-1].lower() if "." in matched_file else ""
            icon_map = {
                "pdf": "📕", "txt": "📄", "docx": "📝", "doc": "📝",
                "csv": "📊", "xlsx": "📊", "xls": "📊",
                "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️",
                "zip": "🗜️", "rar": "🗜️",
            }
            icon = icon_map.get(ext, "📁")
            file_path = os.path.join(DOCS_DIR, matched_file)
            size_kb = round(os.path.getsize(file_path) / 1024, 1) if os.path.exists(file_path) else 0

            # 1. Lấy tóm tắt / nội dung từ SQLite DocumentLog nếu có
            summary_content = ""
            try:
                from backend.database import Session, engine, DocumentLog, select
                with Session(engine) as session:
                    log = session.exec(select(DocumentLog).where(DocumentLog.filename == matched_file)).first()
                    if log and log.summary:
                        summary_content = log.summary
            except Exception:
                pass

            # 2. Nếu summary rỗng hoặc bị ngắt vụn bởi code cũ (kết thúc bằng "..."), đọc trực tiếp FULL file gốc & cập nhật lại CSDL
            if not summary_content or summary_content.endswith("..."):
                if ext in ['png', 'jpg', 'jpeg', 'webp', 'bmp']:
                    try:
                        from backend.services.ingest_service import describe_image_with_vision, register_document_metadata
                        print(f"🖼️ Đang bóc tách FULL mô tả Vision AI cho ảnh '{matched_file}'...")
                        full_desc = describe_image_with_vision(file_path)
                        summary_content = (
                            f"Tập tin Hình Ảnh: '{matched_file}'\n"
                            f"Mô tả chi tiết từ Vision AI:\n{full_desc}"
                        )
                        register_document_metadata(matched_file, f".{ext}", 1, summary_content)
                    except Exception as e:
                        print(f"⚠️ Lỗi bóc tách Vision AI: {e}")

                elif ext in ['txt', 'csv', 'json', 'md', 'log']:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as fp:
                            full_text = fp.read().strip()
                            summary_content = full_text
                            from backend.services.ingest_service import register_document_metadata
                            register_document_metadata(matched_file, f".{ext}", 1, summary_content)
                    except Exception as e:
                        print(f"⚠️ Lỗi đọc file text: {e}")


            q_lower = question.lower()
            is_summary_req = any(kw in q_lower for kw in ["tóm tắt", "phân tích", "đọc", "nội dung", "giải thích", "xem"])

            res_lines = [
                f"{icon} **File tìm thấy:** `{matched_file}`",
                f"- 📦 **Kích thước:** {size_kb} KB",
                f"- 🔗 **Link tải về:** [⬇️ Nhấp để tải `{matched_file}`]({download_url})"
            ]

            if summary_content:
                clean_summary = summary_content.strip()
                if clean_summary.endswith(".."):
                    clean_summary = clean_summary.rstrip(". ").strip()
                res_lines.append(f"\n📝 **Nội dung & Tóm tắt AI của file:**\n```\n{clean_summary}\n```")
            elif is_summary_req:
                res_lines.append(f"\nℹ️ _File `{matched_file}` đã sẵn sàng trong hệ thống RAG để truy vấn chi tiết._")

            res_lines.append("\n> _Nhấp vào link trên để tải file gốc về máy của bạn._")
            return "\n".join(res_lines)



        else:
            # Không tìm thấy → liệt kê danh sách gợi ý
            file_list = "\n".join(f"  - `{f}`" for f in sorted(all_files))
            return (
                f"❌ **Không tìm thấy file** phù hợp với từ khóa: `{extracted_name}`\n\n"
                f"📂 **Các file hiện có trong hệ thống:**\n{file_list}\n\n"
                f"> _Hãy thử lại với tên file chính xác hơn._"
            )


file_agent = FileAgent()
