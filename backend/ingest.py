"""
Ingest CLI Script
-----------------
Script chạy nạp tài liệu từ CLI:
    PYTHONPATH=. .venv/bin/python backend/ingest.py
"""

from backend.services.ingest_service import run_ingestion_pipeline

if __name__ == "__main__":
    run_ingestion_pipeline()
