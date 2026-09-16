"""
Agentic Pipeline (pipeline.py)
------------------------------
Kiến trúc Multi-Agent 2 Lần Gọi Model (2-Stage LLM Calls):
- Giai đoạn 1 (LLM Call 1 - Response 1): Gọi Model lần 1 để phân tích Intent, Action, Table & Reasoning ➔ Xuất ngay Thinking Trace Header (Response 1).
- Giai đoạn 2 (LLM Call 2 - Response 2): Chuyển ngữ cảnh cho Sub-Agent gọi Model lần 2 (sinh SQL / RAG Context) ➔ Xuất Content Body kết quả (Response 2).

Nguyên tắc thiết kế:
- LLM First: Để LLM tự nhiên phân tích intent, action, table, reasoning từ câu hỏi.
- Guardrail chỉ dùng cho hành động nguy hiểm (DELETE): tránh LLM xóa nhầm dữ liệu.
- Không dùng keyword matching để phân loại câu hỏi bình thường.
"""

import json
from typing import Generator, Optional
from dataclasses import dataclass
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.utils.formatters import detect_format_intent


# ─────────────────────────────────────────────
# Pipeline Context Object
# ─────────────────────────────────────────────
@dataclass
class PipelineContext:
    question: str
    intent: Optional[str] = None
    action: Optional[str] = None
    table: Optional[str] = None
    reasoning: Optional[str] = None
    search_query: Optional[str] = None
    history: Optional[list] = None
    response: Optional[str] = None


def format_chat_history(history: Optional[list]) -> str:
    """Định dạng lịch sử hội thoại 4-6 lượt gần nhất cho LLM"""
    if not history:
        return "Chưa có lịch sử trước đó."
    lines = []
    for item in history[-6:]:
        role = item.get("role", "user")
        content = item.get("content", "").strip()
        if not content:
            continue
        # Rút gọn câu trả lời dài của bot để tránh phình to prompt
        short_content = content[:250].replace("\n", " ")
        prefix = "User" if role == "user" else "Trợ Lý AI"
        lines.append(f"{prefix}: {short_content}")
    return "\n".join(lines) if lines else "Chưa có lịch sử trước đó."


# ─────────────────────────────────────────────────────────────────────────────
# Prompt LLM Call 1 (Stage 1: Intent & Metadata Analysis)
# Thiết kế: Phân loại câu hỏi kết hợp giải mã ngữ cảnh đa lượt (Multi-turn Context)
# ─────────────────────────────────────────────────────────────────────────────
PROMPT_STAGE1_ANALYSIS = """Bạn là Bộ Phân Tích Ý Định & Ngữ Cảnh Hội Thoại (Conversational Intent Classifier).
Phân tích câu hỏi của người dùng và trả về JSON với 5 trường:

--- LỊCH SỬ HỘI THOẠI GẦN ĐÂY ---
{chat_history}

intent (chọn 1):
  - "RAG"  → Tra cứu kiến thức, thông tin, nội dung tài liệu, con người, đơn hàng, sản phẩm
  - "SQL"  → Hỏi/xem dữ liệu bảng SQLite (nhật ký công việc, lịch sử chat, tài liệu đã upload)
  - "LOG"  → Ghi thêm hoặc xóa nhật ký công việc
  - "FILE" → Tải về / lấy file gốc đã upload (PDF, TXT, CSV, DOCX...)

action (chọn 1): "CREATE" | "READ" | "UPDATE" | "DELETE" | "DOWNLOAD"

table (chọn 1): "chroma_vector_db" | "daily_logs" | "document_logs" | "chat_messages" | "docs"

reasoning: Giải thích ngắn gọn, chính xác theo nội dung câu hỏi thực tế (tối đa 15 từ).

search_query: Từ khóa thực thể cốt lõi nhất để tra cứu vector/fulltext (chỉ áp dụng cho RAG/FILE, SQL thì để trống "").
QUY TẮC ĐẶC BIỆT KHI CÂU HỎI DÙNG ĐẠI TỪ THAM CHIẾU:
- Nếu câu hỏi dùng đại từ ("ông này", "anh ấy", "cô ấy", "họ", "người này", "ở đâu", "học trường nào", "kỹ năng của họ", "vậy còn...", "dự án đó", "tiếp tục", "chi tiết hơn"...):
  HÃY dựa vào [LỊCH SỬ HỘI THOẠI GẦN ĐÂY] để giải mã đối tượng và sinh ra search_query chứa ĐẦY ĐỦ TÊN THỰC THỂ CỤ THỂ (kèm dạng không dấu).
  Ví dụ: Lịch sử vừa trao đổi về Nguyễn Thanh Tuấn.
  Q: "ông này học ở đâu ?"
  search_query: "Nguyễn Thanh Tuấn Nguyen Thanh Tuan học vấn trường học education"

Các ví dụ minh họa:
Q: "Tuấn là ai ? tóm tắt cho tôi ? tôi ko rõ ông này là ai cả - đã làm gì"
A: {{"intent":"RAG","action":"READ","table":"chroma_vector_db","reasoning":"Tra cứu hồ sơ và lý lịch của Tuấn","search_query":"Nguyễn Thanh Tuấn Nguyen Thanh Tuan"}}

Q: "ông này học trường gì và làm ở đâu ?"
A: {{"intent":"RAG","action":"READ","table":"chroma_vector_db","reasoning":"Tra cứu học vấn và nơi làm việc của người được hỏi","search_query":"Nguyễn Thanh Tuấn Nguyen Thanh Tuan học vấn trường học kinh nghiệm"}}

Q: "này bạn ơi cho tôi hỏi cái hóa đơn phúc an nó có gì bên trong vậy"
A: {{"intent":"RAG","action":"READ","table":"chroma_vector_db","reasoning":"Tra cứu nội dung hóa đơn Phúc An","search_query":"hóa đơn phúc an hoa don phuc an"}}

Q: "Có đơn hàng nào không ?"
A: {{"intent":"RAG","action":"READ","table":"chroma_vector_db","reasoning":"Tra cứu danh sách đơn hàng trong tài liệu đã nạp","search_query":"đơn hàng don hang"}}

Q: "Hôm nay tôi đã làm gì ?"
A: {{"intent":"SQL","action":"READ","table":"daily_logs","reasoning":"Xem nhật ký công việc ngày hôm nay trong SQLite","search_query":""}}

Q: "Hiển thị daily log ngày 2026-09-02"
A: {{"intent":"SQL","action":"READ","table":"daily_logs","reasoning":"Tra cứu nhật ký công việc theo ngày cụ thể","search_query":""}}

Q: "Xem lịch sử chat gần nhất"
A: {{"intent":"SQL","action":"READ","table":"chat_messages","reasoning":"Truy vấn lịch sử hội thoại từ bảng chat_messages","search_query":""}}

Q: "Thêm log: họp team lúc 2h chiều"
A: {{"intent":"LOG","action":"CREATE","table":"daily_logs","reasoning":"Ghi mới nhật ký công việc họp team","search_query":""}}

Q: "Ghi nhật ký: đã hoàn thành task deploy"
A: {{"intent":"LOG","action":"CREATE","table":"daily_logs","reasoning":"Tạo bản ghi nhật ký hoàn thành task deploy","search_query":""}}

Q: "Xóa log nấu cơm hôm nay"
A: {{"intent":"LOG","action":"DELETE","table":"daily_logs","reasoning":"Xóa bản ghi nhật ký nấu cơm","search_query":""}}

Q: "lấy file Scene khung cảnh định.txt ra"
A: {{"intent":"FILE","action":"DOWNLOAD","table":"docs","reasoning":"Tải về file Scene khung cảnh định.txt","search_query":"Scene khung cảnh định.txt"}}

Q: "tôi cần download CV của Tuấn"
A: {{"intent":"FILE","action":"DOWNLOAD","table":"docs","reasoning":"Tải về file CV PDF của Nguyễn Thanh Tuấn","search_query":"FullStack-NguyenThanhTuan.pdf Tuấn Tuan"}}

Q: "tải file đơn hàng csv về"
A: {{"intent":"FILE","action":"DOWNLOAD","table":"docs","reasoning":"Tải về file CSV dữ liệu đơn hàng","search_query":"don_hang_chi_tiet.csv"}}

Câu hỏi người dùng: {question}
JSON:"""


class AgentPipeline:
    def __init__(self):
        self.llm = ChatOllama(model="qwen2.5:3b", temperature=0.0)

    def _call_llm_stage1(self, question: str, history: Optional[list] = None) -> PipelineContext:
        """
        LLM CALL 1 (Stage 1): Phân tích Intent, Action, Table, Reasoning & Search Query kết hợp Chat Memory.
        """
        ctx = PipelineContext(question=question, history=history)
        q_lower = question.lower()

        # ── Safety Guardrail 1: Chặn DELETE trước LLM ─────────────────────
        delete_kws = ["xóa log", "xóa daily log", "remove daily log", "bỏ log", "delete log",
                      "xóa nhật ký", "bỏ nhật ký"]
        if any(kw in q_lower for kw in delete_kws):
            ctx.intent = "LOG"
            ctx.action = "DELETE"
            ctx.table = "daily_logs"
            ctx.reasoning = "Xóa bản ghi nhật ký công việc theo yêu cầu"
            return ctx

        # ── Safety Guardrail 2: Chặn FILE_DOWNLOAD trước LLM ──────────────
        # Lý do: Từ khoá "lấy file", "tải file", "download" + tên file đủ rõ để bypass LLM
        download_kws = ["lấy file", "tải file", "download file", "tải về file",
                        "cho tôi file", "xuất file", "lấy tài liệu", "tải tài liệu"]
        if any(kw in q_lower for kw in download_kws):
            ctx.intent = "FILE"
            ctx.action = "DOWNLOAD"
            ctx.table = "docs"
            ctx.reasoning = "Tải về file gốc đã upload theo yêu cầu"
            return ctx

        # ── LLM Phân Tích Tự Nhiên (Chính) ──────────────────────────────────
        try:
            chat_history_str = format_chat_history(history)
            prompt = ChatPromptTemplate.from_template(PROMPT_STAGE1_ANALYSIS)
            chain = prompt | self.llm | StrOutputParser()
            raw_output = chain.invoke({
                "question": question,
                "chat_history": chat_history_str
            }).strip()

            # Trích xuất JSON từ output (đề phòng LLM thêm text thừa)
            start = raw_output.find("{")
            end = raw_output.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError(f"Không tìm thấy JSON trong output: {raw_output}")

            data = json.loads(raw_output[start:end])

            ctx.intent = data.get("intent", "RAG").upper()
            ctx.action = data.get("action", "READ").upper()
            ctx.table = data.get("table", "chroma_vector_db")
            ctx.reasoning = data.get("reasoning", "Đã phân tích yêu cầu")
            ctx.search_query = data.get("search_query", "")

        except Exception as e:
            # ── Fallback (last resort): Chỉ khi LLM lỗi hoàn toàn ───────────
            print(f"⚠️ [Pipeline] LLM Stage 1 lỗi, dùng fallback: {e}")
            # Heuristic đơn giản: câu có dấu ? và không đề cập log → RAG
            if "?" in question and not any(k in q_lower for k in ["log", "nhật ký", "daily"]):
                ctx.intent = "RAG"
                ctx.action = "READ"
                ctx.table = "chroma_vector_db"
            else:
                ctx.intent = "SQL"
                ctx.action = "READ"
                ctx.table = "daily_logs"
            ctx.reasoning = "Phân tích fallback (LLM không phản hồi)"
            ctx.search_query = ""

        return ctx

    def _build_thinking_header(self, ctx: PipelineContext) -> str:
        """Dựng khối Thinking Trace (Response 1) phát về client"""
        format_intent = detect_format_intent(ctx.question)
        table_str = ctx.table or "chroma_vector_db"
        reasoning_str = f" | 💡 **Lý do**: {ctx.reasoning}" if ctx.reasoning else ""

        return (
            f"🧠 **[Tiến Trình Tư Duy AI / Thinking Trace - Response 1]**\n"
            f"- 🎯 **Intent**: `{ctx.intent}` | ⚡ **Action**: `{ctx.action}` | 🗂️ **Table**: `{table_str}`\n"
            f"- 🎨 **Format Intent**: `{format_intent}`{reasoning_str}\n"
            f"--------------------------------------------------\n"
        )

    # ── Main Entry Points ─────────────────────────────────────────────────────
    def dispatch_stages(self, question: str, history: Optional[list] = None) -> Generator[tuple[str, str, str], None, None]:
        """
        2-Stage Sequential Pipeline (hỗ trợ multi-turn history):
        - Stage 1 (Response 1): Thinking Trace → phát ngay về client
        - Stage 2 (Response 2): Sub-Agent thực thi → phát kết quả về client
        """
        # STAGE 1: LLM Call → THINKING TRACE
        ctx = self._call_llm_stage1(question, history=history)
        intent = ctx.intent
        action = ctx.action

        yield ("thinking", self._build_thinking_header(ctx), intent)

        # STAGE 2: Sub-Agent thực thi → CONTENT BODY
        if intent == "FILE":
            from backend.agents.file_agent import file_agent
            yield ("body", file_agent.process(question), intent)

        elif intent == "LOG" and action != "READ":
            from backend.agents.log_agent import log_agent
            yield ("body", log_agent.process(question), intent)

        elif intent == "RAG":
            from backend.agents.rag_agent import rag_agent
            yield ("body", rag_agent.process(question, search_query=ctx.search_query, history=history), intent)

        else:  # SQL
            from backend.agents.sql_agent import sql_agent
            from backend.agents.rag_agent import rag_agent
            yield ("body", sql_agent.process(question, rag_fallback_fn=rag_agent.process), intent)

    def dispatch(self, question: str, history: Optional[list] = None) -> tuple[str, str]:
        """Hàm đồng bộ: ghép 2 response thành 1 chuỗi hoàn chỉnh."""
        thinking = ""
        body = ""
        final_intent = "RAG"
        for stage, content, intent in self.dispatch_stages(question, history=history):
            final_intent = intent
            if stage == "thinking":
                thinking = content
            elif stage == "body":
                body = content
        return thinking + body, final_intent


agent_pipeline = AgentPipeline()
