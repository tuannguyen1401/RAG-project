from typing import List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.database import engine, Feature, User, hash_password
from backend.auth import verify_admin_token, ADMIN_TOKEN_SECRET

router = APIRouter(prefix="/api/admin", tags=["Admin Portal Management"])

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
async def admin_login(request: LoginRequest):
    """Đăng nhập Admin Portal (Truy vấn CSDL bảng users)"""
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == request.username)).first()
        if not user or user.hashed_password != hash_password(request.password):
            raise HTTPException(status_code=401, detail="Tài khoản hoặc mật khẩu không chính xác!")
        
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Tài khoản này đã bị khóa!")
            
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Tài khoản không có quyền truy cập Admin Portal!")

        return {
            "status": "success",
            "token": ADMIN_TOKEN_SECRET,
            "username": user.username,
            "role": user.role,
            "message": "Đăng nhập thành công!"
        }

# --- FULL CRUD CHO BẢNG FEATURE ---

@router.get("/features", response_model=List[Feature])
async def get_all_features(token: str = Depends(verify_admin_token)):
    """[READ ALL] Admin xem danh sách tất cả các Feature"""
    with Session(engine) as session:
        return session.exec(select(Feature).order_by(Feature.id.desc())).all()

@router.get("/features/{feature_id}", response_model=Feature)
async def get_feature_by_id(feature_id: int, token: str = Depends(verify_admin_token)):
    """[READ ONE] Admin xem chi tiết 1 Feature theo ID"""
    with Session(engine) as session:
        db_feature = session.get(Feature, feature_id)
        if not db_feature:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Feature với ID {feature_id}")
        return db_feature

@router.post("/features", response_model=Feature)
async def create_feature(feature: Feature, token: str = Depends(verify_admin_token)):
    """[CREATE] Admin tạo mới 1 Feature"""
    with Session(engine) as session:
        session.add(feature)
        session.commit()
        session.refresh(feature)
        return feature

@router.put("/features/{feature_id}", response_model=Feature)
async def update_feature(feature_id: int, feature: Feature, token: str = Depends(verify_admin_token)):
    """[UPDATE] Admin cập nhật toàn bộ thông tin 1 Feature"""
    with Session(engine) as session:
        db_feature = session.get(Feature, feature_id)
        if not db_feature:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Feature với ID {feature_id}")
        
        db_feature.title = feature.title
        db_feature.description = feature.description
        db_feature.icon = feature.icon
        db_feature.badge = feature.badge
        db_feature.is_active = feature.is_active
        
        session.commit()
        session.refresh(db_feature)
        return db_feature

@router.delete("/features/{feature_id}")
async def delete_feature(feature_id: int, token: str = Depends(verify_admin_token)):
    """[DELETE] Admin xóa 1 Feature khỏi CSDL"""
    with Session(engine) as session:
        db_feature = session.get(Feature, feature_id)
        if not db_feature:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Feature với ID {feature_id}")
        session.delete(db_feature)
        session.commit()
        return {"id": feature_id, "deleted": True, "message": "Xóa Feature thành công!"}
