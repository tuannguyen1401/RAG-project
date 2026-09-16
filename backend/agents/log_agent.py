"""
Log Specialist Agent (log_agent.py)
-----------------------------------
Chuyên trách xử lý toàn bộ logic Nhật Ký Công Việc (Daily Log):
- Quản lý Sub-Actions: CREATE (Thêm mới) vs DELETE (Xóa nhật ký)
- Bóc tách JSON thông minh
- Thao tác trực tiếp với CSDL SQLite `daily_logs`
- Giữ nguyên văn bản tiếng Việt gốc, tuyệt đối KHÔNG tự động dịch sang tiếng nước ngoài.
"""

import json
import re
from datetime import datetime
from sqlmodel import Session, select
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.database import engine, DailyLog

PROMPT_LOG_INTENT_EXTRACTION = """Hãy phân tích câu nói của người dùng liên quan đến Nhật Ký Công Việc (Daily Log).
Hôm nay là ngày: {today_date}

Nhiệm vụ:
1. Xác định 'action':
   - 'DELETE': Khi người dùng muốn XÓA / BỎ / REMOVE / DELETE nhật ký.
   - 'CREATE': Khi người dùng muốn GHI / LƯU / THÊM / TẠO nhật ký mới.

2. Trích xuất thông tin:
   - Nếu action = 'DELETE':
     'target_keyword': Từ khóa chính của nội dung cần xóa (Chỉ lấy câu văn công việc gốc, TUYỆT ĐỐI GIỮ NGUYÊN TIẾNG VIỆT).
     'log_date': Ngày cần xóa dạng YYYY-MM-DD (nếu có đề cập), nếu không có thì null.
   - Nếu action = 'CREATE':
     'log_date': Ngày dạng YYYY-MM-DD, mặc định '{today_date}'.
     'log_time': Giờ thực hiện dạng HH:MM (ví dụ "08:00", "11:15", "15:00") hoặc null nếu không có đề cập giờ.
     'category': Thể loại (general, dev, work, personal).
     'content': TÊN SỰ KIỆN / CÔNG VIỆC CỐT LÕI (TUYỆT ĐỐI GIỮ NGUYÊN TIẾNG VIỆT GỐC).
                QUAN TRỌNG: Loại bỏ tất cả các từ chỉ dẫn/mệnh lệnh thừa như "thêm sự kiện", "ghi lại", "lưu vào log", "vào nhật ký", "hôm nay", "ngày mai".

Ví dụ tạo mới:
- "thêm sự kiện tắm chó vào log lúc 8h sáng ngày hôm nay" -> content: "tắm chó", log_time: "08:00"
- "ghi vào nhật ký: họp với khách hàng lúc 15:30" -> content: "họp với khách hàng", log_time: "15:30"
- "lưu log ngày mai đi đá bóng" -> content: "đá bóng", log_date: ngày mai, log_time: null

Câu nói: {question}

Chỉ trả về duy nhất 1 đoạn JSON thô (không markdown ```json):"""

class LogAgent:
    def __init__(self):
        self.llm = ChatOllama(model="qwen2.5:3b", temperature=0.0)

    def _clean_delete_keyword(self, text: str) -> str:
        """Làm sạch câu chữ để lấy đúng từ khóa gốc cần xóa trong SQLite"""
        clean = text
        for _ in range(3):
            clean = re.sub(r'^\s*(remove|delete|xóa|bỏ|daily\s*log|log|nhật\s*ký)\s*:?\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^\d+[\.\)]\s*', '', clean)  # Xóa số đầu dòng (1., 2.)
        clean = re.sub(r'\d{4}-\d{2}-\d{2}', '', clean)  # Xóa ngày YYYY-MM-DD
        clean = re.sub(r'[📌└`\'"]', '', clean)  # Xóa icon & markdown
        clean = re.sub(r'\s*\b(đi|nhé|giùm|dùm)\b\s*$', '', clean, flags=re.IGNORECASE)
        return clean.strip()

    def _clean_create_content(self, text: str) -> str:
        """Làm sạch các từ mệnh lệnh đầu/cuối câu khi tạo log mới"""
        clean = text
        # 1. Loại bỏ tiền tố mệnh lệnh & từ chỉ dẫn ở đầu câu
        for _ in range(3):
            clean = re.sub(r'^\s*(thêm|lưu|ghi|tạo)\s+(lại\s+)?(sự\s+kiện|công\s+việc|nội\s+dung|nhật\s*ký|log|daily\s*log)*\s*:?\s*', '', clean, flags=re.IGNORECASE)
            clean = re.sub(r'^\s*(vào|cho|ngày\s+hôm\s+nay|ngày\s+mai|hôm\s+nay|hôm\s+qua)\s*:?\s*', '', clean, flags=re.IGNORECASE)
            clean = re.sub(r'^\s*(công\s+việc|sự\s+kiện|nhật\s*ký|log)\s*:?\s*', '', clean, flags=re.IGNORECASE)
            clean = re.sub(r'^\s*đi\s+', '', clean, flags=re.IGNORECASE)
        # 2. Loại bỏ hậu tố vị trí / thời gian thừa ở cuối câu
        clean = re.sub(r'\s*vào\s+(log|nhật\s*ký|daily\s*log)(\s+công\s+việc)?(\s+ngày)?(\s+hôm\s+nay|\s+ngày\s+mai|\s+hôm\s+qua)?\s*$', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*(cho|vào)\s+(ngày\s+hôm\s+nay|hôm\s+nay|ngày\s+mai|hôm\s+qua)\s*$', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*\b(đi|nhé|giùm|dùm)\b\s*$', '', clean, flags=re.IGNORECASE)
        return clean.strip()

    def process(self, question: str) -> str:
        """Xử lý yêu cầu Nhật ký công việc (Tạo mới hoặc Xóa)"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        prompt = ChatPromptTemplate.from_template(PROMPT_LOG_INTENT_EXTRACTION)
        chain = prompt | self.llm | StrOutputParser()
        
        raw_json = chain.invoke({"today_date": today_str, "question": question}).strip()
        raw_json = raw_json.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(raw_json)
            action = data.get("action", "CREATE").upper()

            # Nếu câu nói chứa từ xóa, ép buộc action = DELETE
            q_lower = question.lower()
            if any(k in q_lower for k in ["remove", "delete", "xóa", "bỏ"]):
                action = "DELETE"

            # ----------------------------------------------------
            # 1. SUB-ACTION: DELETE / UPDATE (BỊ KHÓA TRÊN CHAT)
            # ----------------------------------------------------
            if action in ["DELETE", "UPDATE"] or any(k in q_lower for k in ["xóa", "xoá", "bỏ", "delete", "remove", "truncate", "sửa", "chỉnh sửa", "update", "cập nhật", "sửa đổi", "thay đổi"]):
                return "🚫 **Từ chối thao tác:** Bạn không được phép xóa hoặc sửa dữ liệu nhật ký trực tiếp qua giao diện Chatbot. Thao tác này chỉ được phép thực hiện trên giao diện Quản lý (Admin Dashboard)."

            # ----------------------------------------------------
            # 2. SUB-ACTION: CREATE (TẠO MỚI NHẬT KÝ)
            # ----------------------------------------------------
            else:
                log_date = data.get("log_date", today_str) or today_str
                log_time = data.get("log_time")
                category = data.get("category", "general")
                raw_content = data.get("content", "").strip()
                
                # Làm sạch nội dung: Bóc tách sự kiện cốt lõi
                content = self._clean_create_content(raw_content)
                if not content:
                    content = self._clean_create_content(question)

                # Guardrail: Nếu không lấy được nội dung hoặc câu nói là câu hỏi tra cứu
                q_lower = question.lower()
                query_indicators = ["?", "có việc gì", "cần làm gì", "hôm nay làm gì", "xem log", "danh sách"]
                if not content or any(qi in q_lower for qi in query_indicators):
                    # Nếu là câu hỏi tra cứu, chuyển sang SQL Agent tra cứu danh sách
                    from backend.agents.sql_agent import sql_agent
                    return sql_agent.process(question)

                with Session(engine) as session:
                    log_entry = DailyLog(log_date=log_date, log_time=log_time, category=category, content=content)
                    session.add(log_entry)
                    session.commit()
                    session.refresh(log_entry)

                time_str = f" {log_time}" if log_time else ""
                return f"✅ **Đã lưu nhật ký:** \"{content}\" *(Ngày: {log_date}{time_str} | Phân loại: {category})*"

        except Exception as e:
            return f"❌ Không thể xử lý nhật ký: {e}."

log_agent = LogAgent()
