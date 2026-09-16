"""
Response Formatter Module (formatters.py)
----------------------------------------
Chuyên trách định dạng dữ liệu đầu ra dựa theo Intent Format của câu hỏi.
Sử dụng pattern match-case (Switch-Case trong Python) để phân loại & format linh hoạt:
1. DATE_CONTENT: Format đơn giản nhất `ngày - công việc` (1 dòng/bản ghi)
2. PURE_CONTENT: Chỉ lấy duy nhất dòng nội dung thuần
3. SIMPLE_LINE: Format 1 dòng đơn giản ngắn gọn
4. PRETTY_MARKDOWN: Format đẹp mắt dạng danh sách Markdown có icon & chỉ số
"""

def detect_format_intent(question: str) -> str:
    """Xác định kiểu Format (Format Intent) dựa vào từ khóa trong câu hỏi"""
    q_lower = question.lower()
    
    # 1. Intent DATE_CONTENT: "số ngày - công việc", "ngày - công việc", "ngày - nội dung"
    if any(k in q_lower for k in [
        "số ngày - công việc", "ngày - công việc", "ngày - nội dung", 
        "số ngày - nội dung", "ngày - công việc : trong 1 dòng"
    ]):
        return "DATE_CONTENT"

    # 2. Intent PURE_CONTENT: "chỉ lấy nội dung", "dữ liệu thuần", "dòng thuần", "chỉ lấy dòng"
    if any(k in q_lower for k in [
        "dữ liệu thuần", "chỉ lấy dòng thuần", "dòng thuần", "chỉ lấy nội dung", 
        "dữ liệu thô", "dạng thuần", "thuần", "chỉ lấy dòng"
    ]):
        return "PURE_CONTENT"

    # 3. Intent SIMPLE_LINE: "format đơn giản", "1 dòng", "trong 1 dòng", "gọn"
    if any(k in q_lower for k in [
        "format đơn giản", "đơn giản", "1 dòng", "trong 1 dòng", "trong một dòng", "gọn"
    ]):
        return "SIMPLE_LINE"

    # 4. Intent Mặc định: PRETTY_MARKDOWN
    return "PRETTY_MARKDOWN"


def format_sql_response(data: list, question: str, sql: str = "") -> str:
    """Hàm Format điều hướng bằng Switch-Case (match-case Python 3.10+)"""
    format_intent = detect_format_intent(question)

    if not data:
        return "Chưa có bản ghi nào." if format_intent != "PRETTY_MARKDOWN" else f"📊 **[Kết quả CSDL SQLite]**\n- Câu lệnh SQL: `{sql}`\n- Kết quả: *(Không có bản ghi nào)*"

    # SWITCH-CASE (match-case) phân loại & format theo Intent
    match format_intent:
        case "DATE_CONTENT":
            lines = []
            for row in data:
                # Tìm kiếm thông minh theo key tên cột hoặc alias từ LLM
                log_date = row.get("log_date") or row.get("tanggal") or row.get("ngày") or row.get("số ngày") or str(row.get("created_at", ""))[:10]
                content = row.get("content") or row.get("tugas") or row.get("công việc") or row.get("nội dung") or row.get("summary") or row.get("user_message") or ""

                # Nếu LLM tự đặt alias lạ, lấy giá trị theo thứ tự vị trí cột [0] và [1]
                if not log_date or not content:
                    vals = [str(v) for v in row.values() if v is not None]
                    if len(vals) >= 2:
                        log_date, content = vals[0], vals[1]
                    elif len(vals) == 1:
                        content = vals[0]

                if log_date and content and log_date != content:
                    lines.append(f"- {log_date} - {content}")
                else:
                    lines.append(f"- {content or log_date}")
            return "\n".join(lines)

        case "PURE_CONTENT":
            lines = []
            for row in data:
                content = row.get("content") or row.get("tugas") or row.get("công việc") or row.get("nội dung") or row.get("summary") or row.get("user_message") or list(row.values())[-1]
                lines.append(f"- {content}")
            return "\n".join(lines)

        case "SIMPLE_LINE":
            lines = []
            for row in data:
                log_date = row.get("log_date") or row.get("tanggal") or row.get("ngày") or ""
                content = row.get("content") or row.get("tugas") or row.get("công việc") or row.get("summary") or list(row.values())[-1]
                if log_date and content:
                    lines.append(f"- {log_date} - {content}")
                else:
                    lines.append(f"- {content}")
            return "\n".join(lines)

        case "PRETTY_MARKDOWN" | _:
            items = []
            for i, row in enumerate(data, 1):
                rec_id = row.get("id")
                content = row.get("content") or row.get("tugas") or row.get("công việc") or row.get("summary") or row.get("user_message") or ""
                category = row.get("category") or row.get("file_type") or ""
                log_date = row.get("log_date") or row.get("tanggal") or row.get("ngày") or row.get("created_at") or ""
                log_time = row.get("log_time") or ""
                
                meta = []
                if rec_id is not None: meta.append(f"*(ID: {rec_id})*")
                if log_date:
                    date_display = f"`{log_date} {log_time}`" if log_time else f"`{log_date}`"
                    meta.append(date_display)
                if category: meta.append(f"*[{category}]*")
                meta_str = " ".join(meta)

                if content:
                    items.append(f"{i}. {meta_str}\n   └ 📌 {content}")
                else:
                    row_str = " | ".join([f"**{k}**: `{v}`" for k, v in row.items()])
                    items.append(f"{i}. {row_str}")

            result_str = "\n".join(items)
            return f"📊 **[Kết quả truy vấn CSDL SQLite - {len(data)} bản ghi]**\n- Câu lệnh SQL: `{sql}`\n\n{result_str}"
