import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.routers import admin, chat, features, db_logs

app = FastAPI(
    title="Enterprise AI & RAG Hub API",
    description="Modular FastAPI Application với Admin Authentication Guard & Feature CRUD Table",
    version="5.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INCLUDE MODULAR APIRouters ---
app.include_router(chat.router)
app.include_router(features.router)
app.include_router(db_logs.router)
app.include_router(admin.router)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
ADMIN_DIR = os.path.join(BASE_DIR, "admin")

# --- EXPLICIT ROUTES FOR /admin, /admin/feature, /admin/features ---
@app.get("/admin", include_in_schema=False)
@app.get("/admin/feature", include_in_schema=False)
@app.get("/admin/features", include_in_schema=False)
async def serve_admin():
    admin_index = os.path.join(ADMIN_DIR, "index.html")
    if os.path.exists(admin_index):
        return FileResponse(admin_index)
    return {"detail": "Admin index.html not found"}

# --- EXPLICIT ROUTE FOR /files and /files-search ---
@app.get("/files", include_in_schema=False)
@app.get("/files-search", include_in_schema=False)
async def serve_files_explorer():
    files_page = os.path.join(FRONTEND_DIR, "files.html")
    if os.path.exists(files_page):
        return FileResponse(files_page)
    return {"detail": "files.html not found"}

# --- MOUNT STATIC DIRECTORIES ---
if os.path.exists(ADMIN_DIR):
    app.mount("/admin", StaticFiles(directory=ADMIN_DIR, html=True), name="admin")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

