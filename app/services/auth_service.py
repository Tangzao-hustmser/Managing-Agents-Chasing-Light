"""Authentication and role helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import User

VALID_ROLES = {"student", "teacher", "admin"}
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 120_000


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def is_password_hashed(password_value: str) -> bool:
    """Whether the stored password uses the configured hash format."""
    return password_value.startswith(f"{PASSWORD_SCHEME}$")


def verify_password(password: str, stored_value: str) -> bool:
    """Verify either a legacy plaintext password or a hashed password."""
    if not stored_value:
        return False
    if not is_password_hashed(stored_value):
        return hmac.compare_digest(password, stored_value)

    try:
        _, iterations_raw, salt_hex, digest_hex = stored_value.split("$", 3)
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_raw),
        )
    except Exception:
        return False
    return hmac.compare_digest(computed.hex(), digest_hex)


def create_access_token(user: User) -> str:
    """Create a short HS256 JWT for one user."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "username": user.username,
        "iat": now,
        "exp": now + (settings.jwt_expire_minutes * 60),
    }
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> Dict[str, str]:
    """Decode and validate a JWT."""
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Malformed token") from exc

    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    actual_signature = _b64url_decode(encoded_signature)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise ValueError("Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid token payload") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    if "sub" not in payload:
        raise ValueError("Token subject is missing")
    return payload


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
        password=hash_password(password),
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
    if not verify_password(password, user.password):
        raise ValueError("Incorrect password")
    if not is_password_hashed(user.password):
        user.password = hash_password(password)
        db.add(user)
        db.commit()
        db.refresh(user)
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
