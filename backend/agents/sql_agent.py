"""
SQL Specialist Agent (sql_agent.py)
-----------------------------------
Chuyên trách xử lý toàn bộ logic NL2SQL & Truy vấn CSDL SQLite:
- Bước 1: Trích xuất tham số & ý định (JSON Slot Extraction) từ câu hỏi tự nhiên.
- Bước 2: Dựng câu SQL chuẩn xác 100% bằng Python Builder (Deterministic SQL Construction).
- Bước 3: Thực thi CSDL & Chuyển giao dữ liệu tới Formatter Module (formatters.py).
"""

import json
import re
from datetime import datetime, timedelta
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.database import execute_raw_sql
from backend.utils.formatters import format_sql_response

PROMPT_SLOT_EXTRACTION = """Dựa vào câu hỏi người dùng và cấu trúc các bảng SQLite:
1. daily_logs(id, log_date, log_time, content, category)
2. users(id, username, email, role, is_active, created_at)
3. document_logs(id, filename, file_type, category, summary, chunk_count, created_at)
4. features(id, title, description, icon, badge, is_active)
5. chat_messages(id, intent, user_message, bot_response, created_at)

BỐC CẢNH THỜI GIAN THỰC TẾ:
- Hôm nay: {today_date} | Ngày mai: {tomorrow_date} | Hôm qua: {yesterday_date}
- Tháng hiện tại: {current_month} | Năm hiện tại: {current_year}

Quy tắc chọn Bảng (`table`):
- Khi câu hỏi đề cập đến event, sự kiện, nhật ký, công việc, lịch trình -> chọn "daily_logs".
- Khi câu hỏi đề cập đến user, người dùng, tài khoản -> chọn "users".
- Khi câu hỏi đề cập đến tài liệu, file, document -> chọn "document_logs".
- Khi câu hỏi đề cập đến tin nhắn, lịch sử chat -> chọn "chat_messages".

Nhiệm vụ: Trích xuất JSON (KHÔNG dùng markdown ```json):
{{
  "table": "daily_logs" | "users" | "document_logs" | "features" | "chat_messages",
  "action": "LIST" | "COUNT" | "FIND_DUPLICATES" | "SEMANTIC_CHECK",
  "date_filter": "YYYY-MM-DD" hoặc null,
  "month_filter": "YYYY-MM" hoặc null,
  "year_filter": "YYYY" hoặc null,
  "specific_id": integer hoặc null
}}

Ví dụ 1: "Hiển thị danh sách sự kiện trong tháng này"
{{"table": "daily_logs", "action": "LIST", "date_filter": null, "month_filter": "{current_month}", "year_filter": null, "specific_id": null}}

Ví dụ 2: "hiển thị tất cả sự kiện năm nay"
{{"table": "daily_logs", "action": "LIST", "date_filter": null, "month_filter": null, "year_filter": "{current_year}", "specific_id": null}}

Ví dụ 3: "ngày mai có sự kiện gì bạn"
{{"table": "daily_logs", "action": "LIST", "date_filter": "{tomorrow_date}", "month_filter": null, "year_filter": null, "specific_id": null}}

Ví dụ 4: "hiển thị tất cả dữ liệu bảng daily_logs"
{{"table": "daily_logs", "action": "LIST", "date_filter": null, "month_filter": null, "year_filter": null, "specific_id": null}}

Hãy trích xuất JSON cho câu hỏi: '{question}'
JSON:"""


def parse_temporal_filters(slots: dict) -> dict:
    """Tự động phân loại linh hoạt bộ lọc thời gian dựa vào regex pattern, không phụ thuộc vào vị trí slot LLM gán"""
    extracted_date = None
    extracted_month = None
    extracted_year = None

    # Thu thập tất cả các giá trị thời gian LLM đã trả về
    raw_values = [
        slots.get("date_filter"),
        slots.get("month_filter"),
        slots.get("year_filter")
    ]

    for val in raw_values:
        if not val or not isinstance(val, str):
            continue
        val = val.strip()
        # Chuẩn hóa DD-MM-YYYY -> YYYY-MM-DD nếu cần
        if re.match(r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$', val):
            d, m, y = re.split(r'[-/]', val)
            val = f"{y}-{int(m):02d}-{int(d):02d}"

        # Match linh hoạt theo Pattern
        if re.match(r'^\d{4}-\d{2}-\d{2}$', val):
            extracted_date = val
        elif re.match(r'^\d{4}-\d{2}$', val):
            extracted_month = val
        elif re.match(r'^\d{4}$', val):
            extracted_year = val

    return {
        "date": extracted_date,
        "month": extracted_month,
        "year": extracted_year
    }


def build_sql_from_slots(slots: dict) -> str:
    """Tầng SQL Builder động: Tự động phân tích kiểu dữ liệu & dựng SQL chính xác 100%"""
    action = slots.get("action", "LIST")
    if action in ["UPDATE", "DELETE"]:
        return None

    table = slots.get("table", "daily_logs")
    specific_id = slots.get("specific_id")

    filters = parse_temporal_filters(slots)
    date = filters["date"]
    month = filters["month"]
    year = filters["year"]

    if table == "daily_logs":
        where_clauses = []
        if specific_id and str(specific_id).isdigit() and action not in ["UPDATE", "DELETE"]:
            return f"SELECT id, log_date, log_time, content, category FROM daily_logs WHERE id = {specific_id}"

        # Ưu tiên độ chi tiết: Ngày -> Tháng -> Năm
        if date:
            where_clauses.append(f"log_date = '{date}'")
        elif month:
            where_clauses.append(f"strftime('%Y-%m', log_date) = '{month}'")
        elif year:
            where_clauses.append(f"strftime('%Y', log_date) = '{year}'")

        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        if action == "COUNT":
            return f"SELECT COUNT(*) AS event_count FROM daily_logs{where_sql}"
        elif action == "FIND_DUPLICATES":
            return f"SELECT log_date, content, COUNT(*) AS count FROM daily_logs{where_sql} GROUP BY content HAVING count > 1"
        else:  # LIST hoặc SEMANTIC_CHECK
            return f"SELECT id, log_date, log_time, content FROM daily_logs{where_sql}"

    elif table == "users":
        if action == "COUNT":
            return "SELECT COUNT(*) AS user_count FROM users"
        return "SELECT id, username, email, role, is_active, created_at FROM users"

    elif table == "document_logs":
        return "SELECT id, filename, file_type, category, chunk_count, created_at FROM document_logs"

    elif table == "features":
        return "SELECT id, title, description, icon, badge, is_active FROM features"

    elif table == "chat_messages":
        return "SELECT id, intent, user_message, created_at FROM chat_messages ORDER BY id DESC LIMIT 20"

    return f"SELECT * FROM {table} LIMIT 50"


class SQLAgent:
    def __init__(self):
        self.llm = ChatOllama(model="qwen2.5:3b", temperature=0.0)

    def process(self, question: str, rag_fallback_fn=None) -> str:
        """Xử lý linh hoạt Ý định -> Slot Extraction -> Dynamic Builder -> CSDL Execution"""
        q_lower = question.lower()

        # Guardrail bảo mật: Cấm thao tác XÓA / SỬA trực tiếp qua Chatbot
        if any(k in q_lower for k in ["truncate", "xóa", "xoá", "delete", "drop", "update", "sửa", "chỉnh sửa", "cập nhật", "sửa đổi", "thay đổi"]):
            return "🚫 **Từ chối thao tác:** Bạn không được phép xóa hoặc chỉnh sửa dữ liệu CSDL trực tiếp qua giao diện Chatbot. Thao tác này chỉ được phép thực hiện trên giao diện Quản lý (Admin Dashboard)."

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        current_month = now.strftime("%Y-%m")
        current_year = now.strftime("%Y")

        # Bước 1: Trích xuất Slot JSON hoàn toàn từ LLM
        prompt = ChatPromptTemplate.from_template(PROMPT_SLOT_EXTRACTION)
        chain = prompt | self.llm | StrOutputParser()
        raw_json = chain.invoke({
            "today_date": today_str,
            "tomorrow_date": tomorrow_str,
            "yesterday_date": yesterday_str,
            "current_month": current_month,
            "current_year": current_year,
            "question": question
        }).strip()

        # Cleanup JSON markdown nếu có
        raw_json = raw_json.replace("```json", "").replace("```", "").strip()

        try:
            slots = json.loads(raw_json)
        except Exception:
            slots = {"table": "daily_logs", "action": "LIST"}

        # Nếu user đề cập "ngữ nghĩa", cập nhật action = SEMANTIC_CHECK
        if "ngữ nghĩa" in q_lower:
            slots["action"] = "SEMANTIC_CHECK"

        # Bước 2: Dựng câu lệnh SQL động từ SQL Builder
        sql = build_sql_from_slots(slots)
        if sql is None or slots.get("action") in ["UPDATE", "DELETE"]:
            return "🚫 **Từ chối thao tác:** Bạn không được phép xóa hoặc chỉnh sửa dữ liệu CSDL trực tiếp qua giao diện Chatbot. Thao tác này chỉ được phép thực hiện trên giao diện Quản lý (Admin Dashboard)."

        # Bước 3: Thực thi CSDL
        result = execute_raw_sql(sql)
        if not result.get("success") and rag_fallback_fn:
            return rag_fallback_fn(question)

        data = result.get("data", [])

        # Bước 4: Phân tích Ngữ Nghĩa Bổ Trợ (Semantic Deduplication) nếu được yêu cầu
        if data and slots.get("action") == "SEMANTIC_CHECK":
            prompt_semantic = ChatPromptTemplate.from_template(
                "Dưới đây là danh sách các nhật ký công việc trong CSDL SQLite:\n{data}\n\n"
                "Nhiệm vụ: Phân tích kỹ nội dung ngữ nghĩa và kiểm tra xem có các công việc nào bị trùng lặp hoặc mang ý nghĩa tương tự nhau không (ví dụ: 'tắm chó' và 'đi cho chó tắm', hoặc 'phơi đồ' và 'giặt đồ').\n"
                "Hãy liệt kê chi tiết các công việc tương tự/trùng lặp (nếu phát hiện), hoặc xác nhận không có nếu tất cả đều độc lập."
            )
            semantic_chain = prompt_semantic | self.llm | StrOutputParser()
            analysis = semantic_chain.invoke({"data": json.dumps(data, ensure_ascii=False)}).strip()
            return f"📊 **[Kết quả Phân Tích Ngữ Nghĩa CSDL - {len(data)} bản ghi]**\n- Câu lệnh SQL: `{sql}`\n\n{analysis}"

        # Bước 5: Gọi Formatter Switch-Case
        return format_sql_response(data, question, sql)


sql_agent = SQLAgent()
