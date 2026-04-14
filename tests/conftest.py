from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import get_db, ensure_database_schema
from app.main import app
from app.models import Resource, User
from app.services.auth_service import hash_password
from app.services.rate_limit_service import clear_rate_limit_cache


def login_as(client: TestClient, username: str, password: str):
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    data = response.json()
    return {"Authorization": data["token"]}, data["user"]


@pytest.fixture()
def test_env(tmp_path):
    clear_rate_limit_cache()
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    ensure_database_schema(engine)

    session = TestingSessionLocal()
    session.add_all(
        [
            User(username="admin", password=hash_password("admin123"), real_name="Admin", student_id="A001", email="admin@test.local", role="admin", is_active=True),
            User(username="teacher1", password=hash_password("123456"), real_name="Teacher Wang", student_id="T001", email="teacher@test.local", role="teacher", is_active=True),
            User(username="student1", password=hash_password("123456"), real_name="Student Zhang", student_id="S001", email="student@test.local", role="student", is_active=True),
            Resource(name="3D Printer", category="device", subtype="printer", total_count=3, available_count=3, min_threshold=1, location="Room 101"),
            Resource(name="PLA Material", category="material", subtype="consumable", total_count=20, available_count=20, min_threshold=5, location="Shelf A"),
        ]
    )
    session.commit()
    session.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield {
            "client": client,
            "SessionLocal": TestingSessionLocal,
            "borrow_payload": {
                "resource_id": 1,
                "action": "borrow",
                "quantity": 1,
                "purpose": "course project",
                "note": "Need for prototype",
                "borrow_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
                "expected_return_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat(),
            },
            "consume_payload": {
                "resource_id": 2,
                "action": "consume",
                "quantity": 3,
                "purpose": "lab material",
                "note": "normal use",
            },
        }

    app.dependency_overrides.clear()
    clear_rate_limit_cache()
    engine.dispose()
