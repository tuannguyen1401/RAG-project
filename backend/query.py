"""
Query CLI Script
----------------
Script truy vấn RAG trực tiếp từ dòng lệnh (Terminal):
    PYTHONPATH=. .venv/bin/python backend/query.py "có bao nhiêu đơn hàng?"
"""

import sys
from backend.services.rag_service import rag_service

def main():
    if len(sys.argv) < 2:
        print("❌ Vui lòng nhập câu hỏi. Ví dụ: python backend/query.py 'có bao nhiêu đơn hàng?'")
        return
        
    question = sys.argv[1]
    print(f"\n❓ Câu hỏi: {question}")
    answer = rag_service.query(question)
    print(f"🤖 Trả lời: {answer}\n")

if __name__ == "__main__":
    main()
