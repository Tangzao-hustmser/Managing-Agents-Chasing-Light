"""Authentication and role helpers."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import User

VALID_ROLES = {"student", "teacher", "admin"}


def register_user(
    db: Session,
    username: str,
    password: str,
    real_name: str,
    student_id: str,
    email: Optional[str],
    role: str = "student",
) -> User:
    """Register a new user."""
    if role not in VALID_ROLES:
        raise ValueError("Invalid role")

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise ValueError(f"Username {username} already exists")

    user = User(
        username=username,
        password=password,
        real_name=real_name,
        student_id=student_id,
        email=email,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, username: str, password: str) -> User:
    """Validate a username and password pair."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise ValueError("Username does not exist")
    if not user.is_active:
        raise ValueError("User is inactive")
    if user.password != password:
        raise ValueError("Incorrect password")
    return user


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Fetch a user by id."""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Fetch a user by username."""
    return db.query(User).filter(User.username == username).first()


def list_users(db: Session, limit: int = 100) -> List[User]:
    """List users."""
    return db.query(User).order_by(User.id.desc()).limit(limit).all()


def is_admin(user: Optional[User]) -> bool:
    """Return True if user is admin."""
    return bool(user and user.role == "admin")


def is_teacher(user: Optional[User]) -> bool:
    """Return True if user is teacher."""
    return bool(user and user.role == "teacher")


def is_student(user: Optional[User]) -> bool:
    """Return True if user is student."""
    return bool(user and user.role == "student")


def is_teacher_or_admin(user: Optional[User]) -> bool:
    """Return True if user is teacher or admin."""
    return bool(user and user.role in {"teacher", "admin"})
