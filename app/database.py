"""Database initialization and lightweight schema maintenance."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _bootstrap_device_items(target_engine) -> None:
    """Create instance rows for device resources in legacy databases."""
    from app.models import Resource, ResourceItem, Transaction, TransactionItem

    bootstrap_session = sessionmaker(autocommit=False, autoflush=False, bind=target_engine)()
    try:
        device_resources = bootstrap_session.query(Resource).filter(Resource.category == "device").all()
        for resource in device_resources:
            items = (
                bootstrap_session.query(ResourceItem)
                .filter(ResourceItem.resource_id == resource.id)
                .order_by(ResourceItem.id.asc())
                .all()
            )
            created_from_legacy = len(items) == 0

            while len(items) < max(resource.total_count, 0):
                index = len(items) + 1
                item = ResourceItem(
                    resource_id=resource.id,
                    asset_number=f"R{resource.id:04d}-{index:04d}",
                    qr_code=f"qr://resource/{resource.id}/item/{index}",
                    status="available",
                    current_location=resource.location,
                )
                bootstrap_session.add(item)
                bootstrap_session.flush()
                items.append(item)

            if created_from_legacy:
                available_target = max(0, min(resource.available_count, len(items)))
                for index, item in enumerate(items):
                    item.status = "available" if index < available_target else "borrowed"
                    item.current_location = resource.location
                    item.current_borrower_id = None

            active_borrows = (
                bootstrap_session.query(Transaction)
                .filter(
                    Transaction.resource_id == resource.id,
                    Transaction.action == "borrow",
                    Transaction.status == "approved",
                    Transaction.return_time.is_(None),
                )
                .order_by(Transaction.created_at.asc())
                .all()
            )

            for tx in active_borrows:
                linked_item_ids = {
                    link.resource_item_id
                    for link in bootstrap_session.query(TransactionItem).filter(
                        TransactionItem.transaction_id == tx.id
                    )
                }
                missing_count = max(0, tx.quantity - len(linked_item_ids))
                if missing_count == 0:
                    continue

                candidates = [
                    item
                    for item in items
                    if item.id not in linked_item_ids and item.status in {"borrowed", "available"}
                ]
                for item in candidates[:missing_count]:
                    item.status = "borrowed"
                    item.current_borrower_id = tx.user_id
                    item.current_location = f"Borrowed by user#{tx.user_id}"
                    bootstrap_session.add(TransactionItem(transaction_id=tx.id, resource_item_id=item.id))

        bootstrap_session.commit()
    finally:
        bootstrap_session.close()


def ensure_database_schema(bind_engine=None) -> None:
    """Create tables and patch missing SQLite columns for the demo environment."""
    target_engine = bind_engine or engine
    Base.metadata.create_all(bind=target_engine)

    if str(target_engine.url).startswith("sqlite"):
        transaction_columns = {
            "status": "ALTER TABLE transactions ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'",
            "inventory_applied": "ALTER TABLE transactions ADD COLUMN inventory_applied BOOLEAN NOT NULL DEFAULT 0",
            "inventory_before_total": "ALTER TABLE transactions ADD COLUMN inventory_before_total INTEGER",
            "inventory_after_total": "ALTER TABLE transactions ADD COLUMN inventory_after_total INTEGER",
            "inventory_before_available": "ALTER TABLE transactions ADD COLUMN inventory_before_available INTEGER",
            "inventory_after_available": "ALTER TABLE transactions ADD COLUMN inventory_after_available INTEGER",
            "return_inventory_before_available": "ALTER TABLE transactions ADD COLUMN return_inventory_before_available INTEGER",
            "return_inventory_after_available": "ALTER TABLE transactions ADD COLUMN return_inventory_after_available INTEGER",
            "project_name": "ALTER TABLE transactions ADD COLUMN project_name VARCHAR(120) DEFAULT ''",
            "estimated_quantity": "ALTER TABLE transactions ADD COLUMN estimated_quantity INTEGER",
            "evidence_url": "ALTER TABLE transactions ADD COLUMN evidence_url VARCHAR(500) DEFAULT ''",
            "evidence_type": "ALTER TABLE transactions ADD COLUMN evidence_type VARCHAR(50) DEFAULT ''",
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

    _bootstrap_device_items(target_engine)


def get_db():
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
