# Enterprise RAG & AI Hub

Hệ thống Hỏi đáp Tài liệu Thông minh (RAG) kết hợp **FastAPI**, **LangChain**, **ChromaDB**, **Ollama** (`qwen2.5:3b`, `nomic-embed-text`) và cơ sở dữ liệu **SQLite**.

---

## 🚀 Tính Năng Chính
- **Multi-format Document Ingestion:** Tự động đọc và lập chỉ mục các file PDF, DOCX, CSV, Excel, JSON, TXT, hình ảnh.
- **RAG Engine:** Tìm kiếm ngữ nghĩa với ChromaDB & Ollama Embedding `nomic-embed-text`.
- **LLM Streaming & Chat:** Trả lời trực tiếp dạng stream thời gian thực với `qwen2.5:3b`.
- **Text-to-SQL (NL2SQL):** Chuyển đổi câu hỏi tự nhiên thành truy vấn SQL an toàn (được phân tích qua AST sqlglot).
- **Admin Management:** Trang quản trị tính năng, duyệt file, xem logs tài liệu và hệ thống.

---

## 🛠️ Cài Đặt & Khởi Chạy

### 1. Yêu cầu hệ thống
- Python 3.11+
- [Ollama](https://ollama.com/) với 2 model:
  ```bash
  ollama pull nomic-embed-text
  ollama pull qwen2.5:3b
  ```

### 2. Cài đặt thư viện
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Khởi chạy 1 lệnh duy nhất
```bash
chmod +x run.sh
./run.sh
```

- **Giao diện người dùng:** [http://localhost:8000](http://localhost:8000)
- **Trang Quản trị Admin:** [http://localhost:8000/admin](http://localhost:8000/admin) *(Mặc định: `admin` / `admin123`)*
- **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 📂 Cấu Trúc Thư Mục
```text
├── admin/               # Giao diện Admin quản trị
├── backend/             # Mã nguồn FastAPI & Services
│   ├── agents/          # Các agent xử lý nghiệp vụ chuyên biệt
│   ├── routers/         # API Routers (chat, admin, features, logs)
│   ├── services/        # Ingest Service & RAG Service
│   └── database.py      # SQLite CSDL & SQLModel ORM
├── docs/                # Thư mục chứa tài liệu upload (.gitkeep)
├── frontend/            # Giao diện Web Chat & File Explorer
├── ingest.py            # Script nạp tài liệu CLI
├── query.py             # Script hỏi đáp tương tác CLI
├── run.sh               # Shell script khởi động tự động toàn bộ hệ thống
└── requirements.txt     # Danh sách thư viện Python
```
