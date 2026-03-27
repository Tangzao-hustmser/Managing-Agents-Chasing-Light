"""Database initialization and lightweight schema maintenance."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_database_schema(bind_engine=None) -> None:
    """Create tables and patch missing SQLite columns for the demo environment."""
    target_engine = bind_engine or engine
    Base.metadata.create_all(bind=target_engine)

    if not str(target_engine.url).startswith("sqlite"):
        return

    transaction_columns = {
        "status": "ALTER TABLE transactions ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'",
        "inventory_applied": "ALTER TABLE transactions ADD COLUMN inventory_applied BOOLEAN NOT NULL DEFAULT 0",
        "inventory_before_total": "ALTER TABLE transactions ADD COLUMN inventory_before_total INTEGER",
        "inventory_after_total": "ALTER TABLE transactions ADD COLUMN inventory_after_total INTEGER",
        "inventory_before_available": "ALTER TABLE transactions ADD COLUMN inventory_before_available INTEGER",
        "inventory_after_available": "ALTER TABLE transactions ADD COLUMN inventory_after_available INTEGER",
        "return_inventory_before_available": "ALTER TABLE transactions ADD COLUMN return_inventory_before_available INTEGER",
        "return_inventory_after_available": "ALTER TABLE transactions ADD COLUMN return_inventory_after_available INTEGER",
    }

    with target_engine.begin() as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(transactions)")).fetchall()
        }
        for column_name, sql in transaction_columns.items():
            if column_name not in existing_columns:
                conn.execute(text(sql))

        conn.execute(
            text(
                """
                UPDATE transactions
                SET status = CASE
                    WHEN action = 'borrow' AND return_time IS NOT NULL THEN 'returned'
                    WHEN action = 'return' THEN 'returned'
                    WHEN EXISTS (
                        SELECT 1
                        FROM approval_tasks
                        WHERE approval_tasks.transaction_id = transactions.id
                          AND approval_tasks.status = 'rejected'
                    ) THEN 'rejected'
                    WHEN EXISTS (
                        SELECT 1
                        FROM approval_tasks
                        WHERE approval_tasks.transaction_id = transactions.id
                          AND approval_tasks.status = 'approved'
                    ) THEN 'approved'
                    WHEN action IN ('replenish', 'lost', 'adjust') THEN 'approved'
                    WHEN is_approved = 1 THEN 'approved'
                    ELSE 'pending'
                END
                WHERE status IS NULL OR status = ''
                """
            )
        )

        conn.execute(
            text(
                """
                UPDATE transactions
                SET inventory_applied = CASE
                    WHEN action IN ('borrow', 'consume', 'replenish', 'lost', 'adjust')
                         AND status IN ('approved', 'returned') THEN 1
                    ELSE 0
                END
                WHERE inventory_applied IS NULL
                   OR (inventory_applied = 0 AND status IN ('approved', 'returned'))
                """
            )
        )


def get_db():
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
