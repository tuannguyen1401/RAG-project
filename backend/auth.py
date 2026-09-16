from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

security = HTTPBearer(auto_error=False)

ADMIN_TOKEN_SECRET = "admin-super-secret-token-2026"

def verify_admin_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> str:
    """
    FastAPI Dependency để kiểm tra Token xác thực Admin trong Header Authorization (Bearer Token).
    Nếu Token không hợp lệ hoặc thiếu sẽ trả về lỗi HTTP 401 Unauthorized.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Truy cập bị từ chối: Yêu cầu Token xác thực Admin!",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    if token != ADMIN_TOKEN_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Token xác thực Admin không hợp lệ hoặc đã hết hạn!",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token
