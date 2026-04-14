"""Deterministic competition scenario seeding."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal, ensure_database_schema
from app.models import (
    Alert,
    ApprovalTask,
    ChatMessage,
    ChatSession,
    FollowUpTask,
    MaintenanceRecord,
    Resource,
    ResourceItem,
    Transaction,
    TransactionItem,
    User,
)
from app.seed import seed_demo_data
from app.services.approval_service import approve_task, create_approval_task
from app.services.resource_item_service import ensure_resource_item_capacity
from app.services.time_slot_service import to_utc_naive
from app.services.transaction_service import apply_inventory_change, apply_return

BASELINE_RESOURCES = [
    {
        "name": "Ender-3 3D Printer",
        "category": "device",
        "subtype": "3D printer",
        "total_count": 4,
        "available_count": 4,
        "min_threshold": 1,
        "unit_cost": 1999.0,
        "location": "Innovation Lab",
    },
    {
        "name": "Laser Cutter A1",
        "category": "device",
        "subtype": "laser cutter",
        "total_count": 2,
        "available_count": 2,
        "min_threshold": 1,
        "unit_cost": 25000.0,
        "location": "Innovation Lab",
    },
    {
        "name": "Arduino UNO R3",
        "category": "device",
        "subtype": "development board",
        "total_count": 20,
        "available_count": 20,
        "min_threshold": 4,
        "unit_cost": 89.0,
        "location": "Innovation Lab",
    },
    {
        "name": "UT61E Multimeter",
        "category": "device",
        "subtype": "multimeter",
        "total_count": 20,
        "available_count": 20,
        "min_threshold": 5,
        "unit_cost": 599.0,
        "location": "Innovation Lab",
    },
    {
        "name": "PLA Filament 1.75mm",
        "category": "material",
        "subtype": "printing material",
        "total_count": 60,
        "available_count": 60,
        "min_threshold": 15,
        "unit_cost": 95.0,
        "location": "Innovation Lab",
    },
    {
        "name": "220 Ohm Resistor",
        "category": "material",
        "subtype": "electronic component",
        "total_count": 500,
        "available_count": 500,
        "min_threshold": 80,
        "unit_cost": 0.05,
        "location": "Innovation Lab",
    },
]


def _get_user(db: Session, username: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise ValueError(f"Missing required demo user: {username}")
    return user


def _reset_operational_tables(db: Session) -> None:
    db.query(TransactionItem).delete(synchronize_session=False)
    db.query(FollowUpTask).delete(synchronize_session=False)
    db.query(MaintenanceRecord).delete(synchronize_session=False)
    db.query(ApprovalTask).delete(synchronize_session=False)
    db.query(Transaction).delete(synchronize_session=False)
    db.query(Alert).delete(synchronize_session=False)
    db.query(ChatMessage).delete(synchronize_session=False)
    db.query(ChatSession).delete(synchronize_session=False)
    db.flush()


def _sync_baseline_resources(db: Session) -> None:
    existing_by_name = {resource.name: resource for resource in db.query(Resource).all()}
    for payload in BASELINE_RESOURCES:
        resource = existing_by_name.get(payload["name"])
        if not resource:
            resource = Resource(
                name=payload["name"],
                category=payload["category"],
                subtype=payload["subtype"],
                location=payload["location"],
                total_count=payload["total_count"],
                available_count=payload["available_count"],
                unit_cost=payload["unit_cost"],
                min_threshold=payload["min_threshold"],
                status="active",
                description="",
            )
            db.add(resource)
            db.flush()
            existing_by_name[payload["name"]] = resource
        else:
            resource.category = payload["category"]
            resource.subtype = payload["subtype"]
            resource.location = payload["location"]
            resource.total_count = payload["total_count"]
            resource.available_count = payload["available_count"]
            resource.unit_cost = payload["unit_cost"]
            resource.min_threshold = payload["min_threshold"]
            resource.status = "active"

        if resource.category == "device":
            ensure_resource_item_capacity(db, resource)
            items = (
                db.query(ResourceItem)
                .filter(ResourceItem.resource_id == resource.id)
                .order_by(ResourceItem.id.asc())
                .all()
            )
            for index, item in enumerate(items):
                if index < resource.total_count:
                    item.status = "available"
                    item.current_borrower_id = None
                    item.current_location = resource.location
                    item.maintenance_notes = ""
                else:
                    item.status = "disabled"
                    item.current_borrower_id = None
                    item.current_location = f"{resource.location} / disabled"
            resource.available_count = resource.total_count

    db.flush()


def _create_and_approve_application(
    db: Session,
    *,
    resource: Resource,
    requester: User,
    approver: User,
    action: str,
    quantity: int,
    borrow_time: datetime | None = None,
    expected_return_time: datetime | None = None,
    note: str = "",
    purpose: str = "",
    project_name: str = "",
) -> Transaction:
    tx = Transaction(
        resource_id=resource.id,
        user_id=requester.id,
        action=action,
        quantity=quantity,
        note=note,
        borrow_time=to_utc_naive(borrow_time),
        expected_return_time=to_utc_naive(expected_return_time),
        purpose=purpose,
        project_name=project_name,
        estimated_quantity=quantity,
        status="pending",
        is_approved=False,
        inventory_applied=False,
    )
    db.add(tx)
    db.flush()
    tx.resource = resource
    tx.user = requester
    task = create_approval_task(db, tx, requester, reason="scenario seeding")
    approve_task(db, task, approver, reason="scenario auto-approve")
    db.flush()
    return tx


def _create_pending_application(
    db: Session,
    *,
    resource: Resource,
    requester: User,
    action: str,
    quantity: int,
    borrow_time: datetime | None = None,
    expected_return_time: datetime | None = None,
    note: str = "",
    purpose: str = "",
    project_name: str = "",
) -> Transaction:
    tx = Transaction(
        resource_id=resource.id,
        user_id=requester.id,
        action=action,
        quantity=quantity,
        note=note,
        borrow_time=to_utc_naive(borrow_time),
        expected_return_time=to_utc_naive(expected_return_time),
        purpose=purpose,
        project_name=project_name,
        estimated_quantity=quantity,
        status="pending",
        is_approved=False,
        inventory_applied=False,
    )
    db.add(tx)
    db.flush()
    tx.resource = resource
    tx.user = requester
    create_approval_task(db, tx, requester, reason="scenario pending approval")
    db.flush()
    return tx


def _create_direct_transaction(
    db: Session,
    *,
    resource: Resource,
    operator: User,
    action: str,
    quantity: int,
    note: str = "",
    purpose: str = "",
    project_name: str = "",
) -> Transaction:
    tx = Transaction(
        resource_id=resource.id,
        user_id=operator.id,
        action=action,
        quantity=quantity,
        note=note,
        purpose=purpose,
        project_name=project_name,
        estimated_quantity=quantity,
        status="approved",
        is_approved=True,
        inventory_applied=False,
    )
    db.add(tx)
    db.flush()
    tx.resource = resource
    tx.user = operator
    apply_inventory_change(db, tx)
    db.flush()
    return tx


def seed_deterministic_scenarios(db: Session) -> dict:
    """Build deterministic demo scenarios for final competition presentation."""
    # Ensure base rows exist first.
    seed_demo_data(db)
    db.flush()

    _reset_operational_tables(db)
    _sync_baseline_resources(db)

    admin = _get_user(db, "admin")
    teacher = _get_user(db, "teacher1")
    student = _get_user(db, "student1")
    student2 = _get_user(db, "student2")

    printer = db.query(Resource).filter(Resource.name == "Ender-3 3D Printer").first()
    material = db.query(Resource).filter(Resource.name == "PLA Filament 1.75mm").first()
    resistor = db.query(Resource).filter(Resource.name == "220 Ohm Resistor").first()
    if not printer or not material or not resistor:
        raise ValueError("Missing required baseline resources")

    now = datetime.utcnow()

    # Scenario A: approved borrow + normal return
    tx_good = _create_and_approve_application(
        db,
        resource=printer,
        requester=student,
        approver=teacher,
        action="borrow",
        quantity=1,
        borrow_time=now - timedelta(hours=18),
        expected_return_time=now - timedelta(hours=16),
        note="Scenario normal borrow",
        purpose="course prototype",
        project_name="FinalDemo-Normal",
    )
    apply_return(
        db,
        tx_good,
        condition_return="good",
        note="Scenario normal return",
        return_time=now - timedelta(hours=15),
        actor=student,
    )

    # Scenario B: approved borrow + damaged return -> maintenance + follow-up
    tx_damaged = _create_and_approve_application(
        db,
        resource=printer,
        requester=student,
        approver=teacher,
        action="borrow",
        quantity=1,
        borrow_time=now - timedelta(hours=32),
        expected_return_time=now - timedelta(hours=30),
        note="Scenario damaged borrow",
        purpose="equipment calibration",
        project_name="FinalDemo-Damaged",
    )
    apply_return(
        db,
        tx_damaged,
        condition_return="damaged",
        note="Nozzle damaged during use",
        return_time=now - timedelta(hours=29),
        evidence_url="qiniu://scenario/damage-proof-1.jpg",
        evidence_type="image",
        actor=student,
    )

    # Scenario C: approved borrow + partial loss -> accountability + registry_backfill
    tx_partial_loss = _create_and_approve_application(
        db,
        resource=printer,
        requester=student2,
        approver=teacher,
        action="borrow",
        quantity=2,
        borrow_time=now - timedelta(hours=50),
        expected_return_time=now - timedelta(hours=46),
        note="Scenario partial lost borrow",
        purpose="joint build",
        project_name="FinalDemo-PartialLoss",
    )
    apply_return(
        db,
        tx_partial_loss,
        condition_return="partial_lost",
        note="One accessory missing",
        return_time=now - timedelta(hours=45),
        lost_quantity=1,
        actor=teacher,
    )

    # Scenario D: overdue active borrow (approved, not returned)
    _create_and_approve_application(
        db,
        resource=printer,
        requester=student,
        approver=teacher,
        action="borrow",
        quantity=1,
        borrow_time=now - timedelta(hours=8),
        expected_return_time=now - timedelta(hours=2),
        note="Scenario overdue borrow",
        purpose="overnight print job",
        project_name="FinalDemo-Overdue",
    )

    # Scenario E: pending approvals (borrow + consume)
    _create_pending_application(
        db,
        resource=printer,
        requester=student2,
        action="borrow",
        quantity=1,
        borrow_time=now + timedelta(hours=18),
        expected_return_time=now + timedelta(hours=20),
        note="Scenario pending borrow approval",
        purpose="next-day usage",
        project_name="FinalDemo-PendingBorrow",
    )
    _create_pending_application(
        db,
        resource=material,
        requester=student,
        action="consume",
        quantity=12,
        note="Scenario pending high consume approval",
        purpose="material request",
        project_name="FinalDemo-PendingConsume",
    )

    # Scenario F: approved material consumption and direct loss for alerts/governance
    _create_and_approve_application(
        db,
        resource=material,
        requester=student,
        approver=teacher,
        action="consume",
        quantity=8,
        note="Scenario approved material usage",
        purpose="prototype consumables",
        project_name="FinalDemo-MaterialUse",
    )
    _create_direct_transaction(
        db,
        resource=resistor,
        operator=teacher,
        action="lost",
        quantity=20,
        note="Scenario direct loss registration",
        purpose="inventory audit mismatch",
        project_name="FinalDemo-Lost",
    )

    db.commit()

    return {
        "transactions": db.query(Transaction.id).count(),
        "pending_approvals": db.query(ApprovalTask.id).filter(ApprovalTask.status == "pending").count(),
        "open_follow_up_tasks": db.query(FollowUpTask.id).filter(FollowUpTask.status.in_(["open", "in_progress"])).count(),
        "alerts": db.query(Alert.id).count(),
    }


def main() -> None:
    """CLI entry point."""
    ensure_database_schema()
    db: Session = SessionLocal()
    try:
        summary = seed_deterministic_scenarios(db)
        print("Deterministic scenario data seeded successfully.")
        print(
            f"transactions={summary['transactions']} "
            f"pending_approvals={summary['pending_approvals']} "
            f"open_follow_up_tasks={summary['open_follow_up_tasks']} "
            f"alerts={summary['alerts']}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
