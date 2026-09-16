import os
import hashlib
import sqlglot
import sqlglot.expressions as exp
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlmodel import Field, SQLModel, create_engine, Session, select, text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "daily_logs.db")
engine = create_engine(f"sqlite:///{DB_PATH}")

def hash_password(password: str) -> str:
    """Hàm băm mật khẩu SHA-256 an toàn"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# 1. Bảng Nhật ký công việc
class DailyLog(SQLModel, table=True):
    __tablename__ = "daily_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    log_date: str
    log_time: Optional[str] = Field(default=None)
    content: str
    category: str = Field(default="general")

# 2. Bảng Feature - Quản lý Danh Sách Tính Năng AI
class Feature(SQLModel, table=True):
    __tablename__ = "features"
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str
    icon: str = Field(default="bi-stars")
    badge: str = Field(default="Active")
    is_active: bool = Field(default=True)

# 3. Bảng User - Quản lý Tài khoản & Phân quyền Admin
class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    email: Optional[str] = None
    role: str = Field(default="admin")  # "admin", "user"
    is_active: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# 4. Bảng DocumentLog - Quản lý Danh mục Tất cả File đã Upload/Nạp vào RAG
class DocumentLog(SQLModel, table=True):
    __tablename__ = "document_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str = Field(index=True)
    file_type: str
    category: str = Field(default="Tài liệu chung")
    summary: str = Field(default="")
    chunk_count: int = Field(default=0)
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# 5. Bảng ChatMessage - Ghi log lịch sử trò chuyện (Tin nhắn User + AI Model)
class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    intent: str = Field(default="RAG")
    user_message: str
    bot_response: str
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def log_chat_history(user_message: str, bot_response: str, intent: str = "RAG"):
    """Tự động lưu lịch sử hội thoại vào CSDL SQLite và xuất ra file system_chat_history.log thô"""
    # 1. Lưu CSDL SQLite
    try:
        with Session(engine) as session:
            msg = ChatMessage(user_message=user_message, bot_response=bot_response, intent=intent)
            session.add(msg)
            session.commit()
    except Exception as e:
        print(f"❌ Lỗi ghi log SQLite: {e}")

    # 2. Xuất file thô system_chat_history.log cho dễ đọc/debug
    try:
        log_path = os.path.join(BASE_DIR, "system_chat_history.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [INTENT: {intent}]\n")
            f.write(f"USER: {user_message}\n")
            f.write(f"BOT : {bot_response}\n")
            f.write("-" * 60 + "\n\n")
    except Exception as e:
        print(f"❌ Lỗi ghi log file: {e}")

# Tự động khởi tạo bảng & Nạp dữ liệu mẫu
def init_db():
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # Seed Feature mặc định
        existing_feat = session.exec(select(Feature)).first()
        if not existing_feat:
            default_features = [
                Feature(title="RAG Search Engine", description="Truy vấn vector PDF, DOCX, TXT với k=8 depth.", icon="fa-solid fa-file-pdf", badge="Core", is_active=True),
                Feature(title="SQLModel SQLite", description="Quản lý nhật ký công việc daily_logs chuẩn ORM.", icon="fa-solid fa-database", badge="DB", is_active=True),
                Feature(title="NL2SQL Generator", description="Chuyển tiếng Việt thành câu lệnh SQL thuần.", icon="fa-solid fa-code", badge="AI", is_active=True),
                Feature(title="Intent Guardrails", description="Tự phát hiện câu chào hỏi xã giao phản hồi 0ms.", icon="fa-solid fa-shield-halved", badge="Speed", is_active=True),
                Feature(title="Ollama 32k Context", description="Qwen2.5:3b xử lý văn bản siêu dài thoải mái.", icon="fa-solid fa-microchip", badge="LLM", is_active=True),
            ]
            for f in default_features:
                session.add(f)
            session.commit()

        # Seed User Admin mặc định vào CSDL
        existing_user = session.exec(select(User).where(User.username == "admin")).first()
        if not existing_user:
            admin_user = User(
                username="admin",
                hashed_password=hash_password("admin123"),
                email="admin@system.local",
                role="admin",
                is_active=True
            )
            session.add(admin_user)
            session.commit()

init_db()

# Thực thi SQL thô
def execute_raw_sql(sql_query: str) -> Dict[str, Any]:
    clean_sql = sql_query.strip().strip(";").strip()
    if not clean_sql:
        return {"error": "Câu lệnh SQL trống.", "success": False}

    # ── SQL Sanitizer: sqlglot AST Parser ───────────────────────────────────
    # Dùng AST thay vì string match → tránh chẹn nhầm data chứa từ khóa
    # và chống bypass qua comment (/* DROP */ ...) hoặc obfuscation.
    BLOCKED_TYPES = (
        exp.Drop,          # DROP TABLE / DROP INDEX
        exp.Create,        # CREATE TABLE / CREATE VIEW
        exp.Alter,         # ALTER TABLE / ALTER INDEX
        exp.TruncateTable, # TRUNCATE TABLE
        exp.Attach,        # ATTACH / DETACH database
        exp.Command,       # Lệnh thô không xác định khác
    )
    try:
        parsed = sqlglot.parse_one(clean_sql, dialect="sqlite")
        if isinstance(parsed, BLOCKED_TYPES):
            stmt_name = type(parsed).__name__
            return {"error": f"⚠️ Câu lệnh `{stmt_name}` bị chặn — không được phép thực thi.", "success": False}
    except sqlglot.errors.ParseError as e:
        return {"error": f"❌ SQL không hợp lệ: {e}", "success": False}

    # ── Thực thi sau khi vượt qua kiểm tra an toàn ───────────────────────
    with Session(engine) as session:
        try:
            result = session.exec(text(clean_sql))
            if isinstance(parsed, exp.Select):
                rows = [dict(row._mapping) for row in result.all()]
                return {"sql": clean_sql, "data": rows, "count": len(rows), "success": True}
            else:
                session.commit()
                return {"sql": clean_sql, "success": True}
        except Exception as e:
            return {"error": str(e), "sql": clean_sql, "success": False}
