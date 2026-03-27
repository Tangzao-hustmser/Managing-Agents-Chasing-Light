"""Authentication routes."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginOut, UserCreate, UserLogin, UserOut
from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    get_user_by_id,
    login_user,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_current_user(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
) -> User:
    """Read the current user from a bearer JWT."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="Authorization must be 'Bearer <jwt>'")

    try:
        payload = decode_access_token(parts[1])
        user_id = int(payload["sub"])
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")
    return user


@router.post("/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """Public registration only creates student accounts."""
    try:
        return register_user(
            db,
            username=payload.username,
            password=payload.password,
            real_name=payload.real_name,
            student_id=payload.student_id,
            email=payload.email,
            role="student",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=LoginOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """Login and return a bearer JWT."""
    try:
        user = login_user(db, payload.username, payload.password)
        user_out = UserOut.model_validate(user)
        token = create_access_token(user)
        return LoginOut(token=f"Bearer {token}", user=user_out)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the current authenticated user."""
    return current_user
