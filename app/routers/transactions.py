"""Transaction routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Resource, Transaction, TransactionItem, User
from app.routers.auth import get_current_user
from app.schemas import ReturnRequest, TransactionCreate, TransactionOut
from app.services.approval_service import create_approval_task, should_require_approval
from app.services.auth_service import is_admin, is_teacher_or_admin
from app.services.audit_service import write_audit_log
from app.services.concurrency_service import acquire_entity_lock
from app.services.idempotency_service import (
    IdempotencyConflictError,
    persist_idempotent_response,
    prepare_idempotency,
)
from app.services.rate_limit_service import RateLimitExceededError, enforce_write_rate_limit
from app.services.time_slot_service import check_time_slot_conflict, to_utc_naive
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
        joinedload(Transaction.item_links),
        joinedload(Transaction.item_links).joinedload(TransactionItem.resource_item),
    )


@router.post("", response_model=TransactionOut)
def create_transaction(
    payload: TransactionCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new application or a direct staff/admin transaction."""
    resource = db.query(Resource).filter(Resource.id == payload.resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.status == "disabled":
        raise HTTPException(status_code=400, detail="Resource is archived/disabled and cannot be used")

    try:
        enforce_write_rate_limit(user_id=current_user.id, endpoint_key=f"transactions.create.{payload.action}")
        if payload.action in {"borrow", "consume"}:
            if current_user.role not in {"student", "teacher"}:
                raise HTTPException(status_code=403, detail="Admins do not submit resource applications")
            validate_resource_action(resource, payload.action)
            borrow_time = to_utc_naive(payload.borrow_time)
            expected_return_time = to_utc_naive(payload.expected_return_time)

            if payload.action == "borrow":
                if not borrow_time or not expected_return_time:
                    raise HTTPException(
                        status_code=400,
                        detail="Borrow requests must include borrow_time and expected_return_time",
                    )
                conflicts = check_time_slot_conflict(
                    db,
                    payload.resource_id,
                    borrow_time,
                    expected_return_time,
                    requested_quantity=payload.quantity,
                    capacity=resource.total_count,
                )
                if conflicts:
                    raise HTTPException(
                        status_code=400,
                        detail="The requested time slot exceeds available device capacity",
                    )

            tx = Transaction(
                resource_id=payload.resource_id,
                user_id=current_user.id,
                action=payload.action,
                quantity=payload.quantity,
                note=payload.note,
                borrow_time=borrow_time,
                expected_return_time=expected_return_time,
                purpose=payload.purpose,
                project_name=payload.project_name,
                estimated_quantity=payload.estimated_quantity,
                evidence_url=payload.evidence_url,
                evidence_type=payload.evidence_type,
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
            audit_action = f"transaction.request.{payload.action}"

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
                project_name=payload.project_name,
                estimated_quantity=payload.estimated_quantity,
                evidence_url=payload.evidence_url,
                evidence_type=payload.evidence_type,
                status="approved",
                is_approved=True,
            )
            db.add(tx)
            db.flush()
            tx.resource = resource
            tx.user = current_user
            apply_inventory_change(db, tx)
            audit_action = "transaction.direct.replenish"

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
                project_name=payload.project_name,
                estimated_quantity=payload.estimated_quantity,
                evidence_url=payload.evidence_url,
                evidence_type=payload.evidence_type,
                status="approved",
                is_approved=True,
            )
            db.add(tx)
            db.flush()
            tx.resource = resource
            tx.user = current_user
            apply_inventory_change(db, tx, payload.resource_item_ids)
            audit_action = "transaction.direct.lost"

        else:
            raise HTTPException(status_code=400, detail="Use PATCH /transactions/{id}/return for returns")

        write_audit_log(
            db,
            actor=current_user,
            action=audit_action,
            entity_type="transaction",
            entity_id=tx.id,
            detail={
                "resource_id": tx.resource_id,
                "action": tx.action,
                "quantity": tx.quantity,
                "status": tx.status,
            },
            request=request,
        )
        db.commit()
        tx = _transaction_query(db).filter(Transaction.id == tx.id).first()
        return build_transaction_out(tx, current_user)
    except HTTPException:
        db.rollback()
        raise
    except RateLimitExceededError as exc:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
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
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return one approved borrow record owned by the current user."""
    try:
        enforce_write_rate_limit(user_id=current_user.id, endpoint_key="transactions.return")
        with acquire_entity_lock(f"transaction:return:{transaction_id}"):
            idempotency = prepare_idempotency(
                db,
                scope="transactions.return",
                user_id=current_user.id,
                idempotency_key=idempotency_key,
                request_payload={
                    "transaction_id": transaction_id,
                    "condition_return": payload.condition_return,
                    "note": payload.note,
                    "return_time": payload.return_time,
                    "lost_quantity": payload.lost_quantity,
                    "evidence_url": payload.evidence_url,
                    "evidence_type": payload.evidence_type,
                },
                entity_key=f"transaction:{transaction_id}",
            )
            if idempotency.cached_response is not None:
                return idempotency.cached_response

            tx = _transaction_query(db).filter(Transaction.id == transaction_id).first()
            if not tx:
                raise HTTPException(status_code=404, detail="Transaction not found")
            if tx.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="You can only return your own borrowed device")

            apply_return(
                db,
                tx,
                payload.condition_return,
                payload.note,
                return_time=payload.return_time,
                lost_quantity=payload.lost_quantity,
                evidence_url=payload.evidence_url,
                evidence_type=payload.evidence_type,
                actor=current_user,
            )
            tx = _transaction_query(db).filter(Transaction.id == transaction_id).first()
            response_payload = build_transaction_out(tx, current_user)
            write_audit_log(
                db,
                actor=current_user,
                action="transaction.return",
                entity_type="transaction",
                entity_id=transaction_id,
                detail={
                    "condition_return": payload.condition_return,
                    "lost_quantity": payload.lost_quantity,
                    "status": tx.status if tx else "",
                },
                request=request,
                idempotency_key=idempotency_key or "",
            )
            persist_idempotent_response(db, context=idempotency, response_payload=response_payload, status_code=200)
            db.commit()
            return response_payload
    except HTTPException:
        db.rollback()
        raise
    except IdempotencyConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RateLimitExceededError as exc:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to return resource: {exc}") from exc
