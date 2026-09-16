from datetime import datetime
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from backend.database import execute_raw_sql

llm_sql = ChatOllama(model="qwen2.5:3b", temperature=0.0)

SQL_GENERATION_PROMPT = """Bạn là một chuyên gia SQL cho SQLite database.
Dưới đây là cấu trúc bảng 'daily_logs':
- Table: daily_logs
- Columns:
  * id: INTEGER PRIMARY KEY AUTOINCREMENT
  * log_date: TEXT (định dạng YYYY-MM-DD, ví dụ: '2026-09-02')
  * content: TEXT (nội dung công việc / nhật ký)
  * category: TEXT (thể loại, mặc định: 'general')

Hôm nay là ngày: {today_date}

Nhiệm vụ: Chuyển đổi yêu cầu bằng tiếng Việt dưới đây thành đúng 1 câu lệnh SQL thuần (SELECT, INSERT, UPDATE, hoặc DELETE) phù hợp với SQLite.

Yêu cầu:
1. Chỉ trả về duy nhất 1 câu lệnh SQL (không giải thích, không dùng markdown ```sql, chỉ câu lệnh thô).
2. Nếu câu hỏi không chỉ định ngày, mặc định dùng ngày hôm nay: '{today_date}'.

Yêu cầu tiếng Việt:
{user_prompt}

Câu SQL:"""

prompt_template = ChatPromptTemplate.from_template(SQL_GENERATION_PROMPT)
sql_chain = prompt_template | llm_sql | StrOutputParser()

def generate_sql_query(user_prompt: str) -> str:
    """Sinh câu SQL từ ngôn ngữ tự nhiên"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    raw_sql = sql_chain.invoke({"today_date": today_str, "user_prompt": user_prompt})
    
    clean_sql = raw_sql.strip()
    if clean_sql.startswith("```sql"):
        clean_sql = clean_sql.replace("```sql", "")
    if clean_sql.startswith("```"):
        clean_sql = clean_sql.replace("```", "")
    return clean_sql.strip()

def execute_nl2sql(user_prompt: str, auto_execute: bool = False):
    """
    - auto_execute = False: Dry-run / Validate
    - auto_execute = True: Thực thi vào DB
    """
    sql_query = generate_sql_query(user_prompt)
    
    if not auto_execute:
        return {
            "mode": "dry_run",
            "prompt": user_prompt,
            "generated_sql": sql_query,
            "message": "Câu lệnh SQL đã khởi tạo. Set auto_execute=True để thực thi!"
        }
    
    result = execute_raw_sql(sql_query)
    return {
        "mode": "executed",
        "prompt": user_prompt,
        "generated_sql": sql_query,
        "result": result
    }
