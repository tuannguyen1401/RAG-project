#!/usr/bin/env bash

# Lấy thư mục gốc của project
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=================================================="
echo "⚡ Đang khởi động hệ thống RAG Enterprise AI..."
echo "=================================================="

# 1. Kiểm tra và khởi động Ollama nếu chưa chạy
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "⚙️  Ollama chưa chạy, đang khởi động Ollama service..."
    ollama serve > /dev/null 2>&1 &
    
    # Chờ tối đa 10s cho Ollama sẵn sàng
    for i in {1..10}; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo "✅ Ollama đã khởi động thành công!"
            break
        fi
        sleep 1
    done
else
    echo "✅ Ollama service đang hoạt động."
fi

# 2. Kiểm tra các models cần thiết
REQUIRED_MODELS=("nomic-embed-text" "qwen2.5:3b")
INSTALLED_MODELS=$(ollama list 2>/dev/null)

for MODEL in "${REQUIRED_MODELS[@]}"; do
    if ! echo "$INSTALLED_MODELS" | grep -q "$MODEL"; then
        echo "📥 Đang tải model $MODEL qua Ollama..."
        ollama pull "$MODEL"
    fi
done

# 3. Kiểm tra môi trường ảo .venv
if [ -d "$PROJECT_DIR/.venv" ]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
    UVICORN_BIN="$PROJECT_DIR/.venv/bin/uvicorn"
else
    echo "⚠️  Không tìm thấy .venv, dùng Python hệ thống..."
    PYTHON_BIN="$(which python3)"
    UVICORN_BIN="$(which uvicorn)"
fi

echo ""
echo "=================================================="
echo "🚀 HỆ THỐNG RAG ĐÃ SẴN SÀNG!"
echo "🌐 Mở trình duyệt và truy cập các đường dẫn sau:"
echo ""
echo "   👉 Giao diện Chat & RAG : http://localhost:8000"
echo "   👉 Trang Quản trị Admin : http://localhost:8000/admin"
echo "      (Tài khoản: admin  |  Mật khẩu: admin123)"
echo "   👉 Tài liệu Swagger API : http://localhost:8000/docs"
echo "=================================================="
echo ""

# Chạy server FastAPI qua uvicorn
exec "$UVICORN_BIN" backend.main:app --host 0.0.0.0 --port 8000
