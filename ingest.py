"""
Ingest Script Proxy
-------------------
Ủy quyền toàn bộ cho backend/services/ingest_service.py xử lý đa định dạng (PDF, DOCX, CSV, Excel, JSON, TXT, PNG, JPG).
"""

import os
from backend.services.ingest_service import (
    load_single_document,
    run_ingestion_pipeline,
    CHROMA_PATH,
    DOCS_DIR
)

def load_document(file_path: str):
    return load_single_document(file_path)

def run_ingestion():
    run_ingestion_pipeline()

if __name__ == "__main__":
    run_ingestion()
