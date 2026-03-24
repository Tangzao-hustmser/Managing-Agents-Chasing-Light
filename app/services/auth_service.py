"""认证服务：用户注册、登录、会话管理。"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import User


def register_user(db: Session, username: str, password: str, real_name: str, student_id: str, email: str, role: str = "student") -> User:
    """注册新用户。"""
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise ValueError(f"用户名 {username} 已存在")
    
    user = User(
        username=username,
        password=password,  # 演示用，明文存储
        real_name=real_name,
        student_id=student_id,
        email=email,
        role=role,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, username: str, password: str) -> User:
    """验证用户登录，返回用户对象。"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise ValueError(f"用户名 {username} 不存在")
    
    if not user.is_active:
        raise ValueError(f"用户 {username} 已禁用")
    
    # 明文比较（演示用）
    if user.password != password:
        raise ValueError("密码错误")
    
    return user


def get_user_by_id(db: Session, user_id: int) -> User:
    """根据 ID 获取用户。"""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> User:
    """根据用户名获取用户。"""
    return db.query(User).filter(User.username == username).first()


def list_users(db: Session, limit: int = 100) -> list[User]:
    """列出所有用户（仅管理员可调用）。"""
    return db.query(User).order_by(User.id.desc()).limit(limit).all()


def is_admin(user: User) -> bool:
    """检查用户是否为管理员。"""
    return user and user.role == "admin"


def is_student(user: User) -> bool:
    """检查用户是否为学生。"""
    return user and user.role == "student"
