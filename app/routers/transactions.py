"""Transaction routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Resource, Transaction, User
from app.routers.auth import get_current_user
from app.schemas import ReturnRequest, TransactionCreate, TransactionOut
from app.services.approval_service import create_approval_task, should_require_approval
from app.services.auth_service import is_admin, is_teacher_or_admin
from app.services.time_slot_service import check_time_slot_conflict
from app.services.transaction_service import (
    apply_inventory_change,
    apply_return,
    build_transaction_out,
    validate_resource_action,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _transaction_query(db: Session):
    return db.query(Transaction).options(
        joinedload(Transaction.resource),
        joinedload(Transaction.user),
        joinedload(Transaction.approval_task),
    )


@router.post("", response_model=TransactionOut)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new application or a direct staff/admin transaction."""
    resource = db.query(Resource).filter(Resource.id == payload.resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    try:
        if payload.action in {"borrow", "consume"}:
            if current_user.role not in {"student", "teacher"}:
                raise HTTPException(status_code=403, detail="Admins do not submit resource applications")
            validate_resource_action(resource, payload.action)

            if payload.action == "borrow":
                if not payload.borrow_time or not payload.expected_return_time:
                    raise HTTPException(
                        status_code=400,
                        detail="Borrow requests must include borrow_time and expected_return_time",
                    )
                conflicts = check_time_slot_conflict(
                    db,
                    payload.resource_id,
                    payload.borrow_time,
                    payload.expected_return_time,
                )
                if conflicts:
                    raise HTTPException(status_code=400, detail="The requested time slot conflicts with an approved borrow")

            tx = Transaction(
                resource_id=payload.resource_id,
                user_id=current_user.id,
                action=payload.action,
                quantity=payload.quantity,
                note=payload.note,
                borrow_time=payload.borrow_time,
                expected_return_time=payload.expected_return_time,
                purpose=payload.purpose,
                status="pending",
                is_approved=False,
                inventory_applied=False,
            )
            db.add(tx)
            db.flush()

            if should_require_approval(payload.action):
                create_approval_task(
                    db,
                    tx,
                    current_user,
                    reason="Awaiting teacher/admin approval",
                )

        elif payload.action == "replenish":
            if not is_admin(current_user):
                raise HTTPException(status_code=403, detail="Only admins can replenish inventory directly")
            tx = Transaction(
                resource_id=payload.resource_id,
                user_id=current_user.id,
                action=payload.action,
                quantity=payload.quantity,
                note=payload.note,
                purpose=payload.purpose or "admin replenish",
                status="approved",
                is_approved=True,
            )
            db.add(tx)
            db.flush()
            tx.resource = resource
            apply_inventory_change(db, tx)

        elif payload.action == "lost":
            if not is_teacher_or_admin(current_user):
                raise HTTPException(status_code=403, detail="Only teachers or admins can register loss")
            if not payload.note.strip():
                raise HTTPException(status_code=400, detail="Loss registration must include a reason")
            tx = Transaction(
                resource_id=payload.resource_id,
                user_id=current_user.id,
                action=payload.action,
                quantity=payload.quantity,
                note=payload.note,
                purpose=payload.purpose or "loss registration",
                status="approved",
                is_approved=True,
            )
            db.add(tx)
            db.flush()
            tx.resource = resource
            apply_inventory_change(db, tx)

        else:
            raise HTTPException(status_code=400, detail="Use PATCH /transactions/{id}/return for returns")

        db.commit()
        tx = _transaction_query(db).filter(Transaction.id == tx.id).first()
        return build_transaction_out(tx, current_user)
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create transaction: {exc}") from exc


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List transactions for the current role."""
    query = _transaction_query(db).order_by(Transaction.id.desc())
    if not is_admin(current_user):
        query = query.filter(Transaction.user_id == current_user.id)
    transactions = query.all()
    return [build_transaction_out(tx, current_user) for tx in transactions]


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get one transaction detail."""
    tx = _transaction_query(db).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if not is_admin(current_user) and tx.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You cannot access another user's transaction")
    return build_transaction_out(tx, current_user)


@router.patch("/{transaction_id}/return", response_model=TransactionOut)
def return_resource(
    transaction_id: int,
    payload: ReturnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return one approved borrow record owned by the current user."""
    tx = _transaction_query(db).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if tx.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only return your own borrowed device")

    try:
        apply_return(db, tx, payload.condition_return, payload.note)
        db.commit()
        tx = _transaction_query(db).filter(Transaction.id == transaction_id).first()
        return build_transaction_out(tx, current_user)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to return resource: {exc}") from exc
