"""认证路由：注册、登录、获取当前用户信息。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserLogin, UserOut
from app.services.auth_service import get_user_by_id, login_user, register_user

router = APIRouter(prefix="/auth", tags=["认证"])


def get_current_user(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None)
) -> User:
    """从 Authorization header 获取当前用户。
    
    格式：Authorization: Bearer {user_id}
    （简化实现：直接传递 user_id，生产环境应使用 JWT）
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少认证信息")
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="认证格式错误，应为 'Bearer {user_id}'")
    
    try:
        user_id = int(parts[1])
    except ValueError:
        raise HTTPException(status_code=401, detail="用户 ID 无效")
    
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="用户已禁用")
    
    return user


@router.post("/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """用户注册。"""
    try:
        user = register_user(
            db,
            username=payload.username,
            password=payload.password,
            real_name=payload.real_name,
            student_id=payload.student_id,
            email=payload.email,
            role=payload.role
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """用户登录，返回 user_id 作为 token。"""
    try:
        user = login_user(db, payload.username, payload.password)
        return {
            "token": f"Bearer {user.id}",  # 简化实现
            "user": {
                "id": user.id,
                "username": user.username,
                "real_name": user.real_name,
                "role": user.role,
                "student_id": user.student_id,
                "email": user.email,
                "is_active": user.is_active
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户的信息。"""
    return current_user
