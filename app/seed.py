"""Seed demo data."""

from sqlalchemy.orm import Session

from app.database import SessionLocal, ensure_database_schema
from app.models import Resource, User
from app.services.auth_service import hash_password


def seed_demo_data(db: Session) -> None:
    """Seed minimal demo users and resources."""
    if db.query(Resource).count() > 0:
        return

    db.add_all(
        [
            User(
                username="admin",
                password=hash_password("admin123"),
                real_name="Admin",
                student_id="A001",
                email="admin@school.edu",
                role="admin",
                is_active=True,
            ),
            User(
                username="student1",
                password=hash_password("123456"),
                real_name="Student Zhang",
                student_id="S001",
                email="zhangsan@school.edu",
                role="student",
                is_active=True,
            ),
            User(
                username="student2",
                password=hash_password("123456"),
                real_name="Student Li",
                student_id="S002",
                email="lisi@school.edu",
                role="student",
                is_active=True,
            ),
            User(
                username="teacher1",
                password=hash_password("123456"),
                real_name="Teacher Wang",
                student_id="T001",
                email="wang@school.edu",
                role="teacher",
                is_active=True,
            ),
        ]
    )

    db.add_all(
        [
            Resource(name="Ender-3 3D Printer", category="device", subtype="3D printer", total_count=4, available_count=2, min_threshold=1, unit_cost=1999),
            Resource(name="Laser Cutter A1", category="device", subtype="laser cutter", total_count=2, available_count=1, min_threshold=1, unit_cost=25000),
            Resource(name="Arduino UNO R3", category="device", subtype="development board", total_count=20, available_count=11, min_threshold=4, unit_cost=89),
            Resource(name="UT61E Multimeter", category="device", subtype="multimeter", total_count=20, available_count=8, min_threshold=5, unit_cost=599),
            Resource(name="PLA Filament 1.75mm", category="material", subtype="printing material", total_count=60, available_count=26, min_threshold=15, unit_cost=95),
            Resource(name="220 Ohm Resistor", category="material", subtype="electronic component", total_count=500, available_count=120, min_threshold=80, unit_cost=0.05),
        ]
    )
    db.commit()


def main() -> None:
    """CLI entry point for seeding demo data."""
    ensure_database_schema()
    db: Session = SessionLocal()
    try:
        seed_demo_data(db)
        print("Demo data seeded successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
