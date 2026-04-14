"""Resource management routes."""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MaintenanceRecord, Resource, ResourceItem, Transaction, User
from app.routers.auth import get_current_user
from app.schemas import (
    InventoryAdjustmentRequest,
    MaintenanceRecordCreate,
    MaintenanceRecordOut,
    ResourceCreate,
    ResourceItemCreate,
    ResourceItemOut,
    ResourceItemUpdate,
    ResourceOut,
    ResourceUpdate,
    TransactionOut,
    MessageOut,
)
from app.services.auth_service import is_admin
from app.services.audit_service import write_audit_log
from app.services.concurrency_service import acquire_entity_lock
from app.services.idempotency_service import (
    IdempotencyConflictError,
    persist_idempotent_response,
    prepare_idempotency,
)
from app.services.rate_limit_service import RateLimitExceededError, enforce_write_rate_limit
from app.services.resource_item_service import ensure_resource_item_capacity, get_resource_items, is_tracked_resource
from app.services.rules_engine import run_inventory_rules, run_utilization_rules
from app.services.transaction_service import apply_inventory_change, build_transaction_out

router = APIRouter(prefix="/resources", tags=["resources"])

ARCHIVE_SNAPSHOT_PREFIX = "__ARCHIVED_SNAPSHOT__:"


def _enforce_write_limit(user_id: int, endpoint_key: str) -> None:
    try:
        enforce_write_rate_limit(user_id=user_id, endpoint_key=endpoint_key)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


def _build_resource_out(resource: Resource) -> dict:
    item_count = len([item for item in resource.items if item.status != "disabled"])
    available_item_count = len([item for item in resource.items if item.status == "available"])
    return {
        "id": resource.id,
        "name": resource.name,
        "category": resource.category,
        "subtype": resource.subtype,
        "location": resource.location,
        "total_count": resource.total_count,
        "available_count": resource.available_count,
        "unit_cost": resource.unit_cost,
        "min_threshold": resource.min_threshold,
        "status": resource.status,
        "description": resource.description,
        "item_count": item_count,
        "available_item_count": available_item_count,
        "created_at": resource.created_at,
        "updated_at": resource.updated_at,
    }


def _extract_archive_snapshot(description: str) -> Optional[dict]:
    lines = [line.strip() for line in (description or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if not line.startswith(ARCHIVE_SNAPSHOT_PREFIX):
            continue
        raw = line[len(ARCHIVE_SNAPSHOT_PREFIX) :]
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
    return None


def _reconcile_device_items(resource: Resource, target_total: int, target_available: int) -> None:
    items = [item for item in resource.items if item.status != "lost"]
    if target_total < 0 or target_available < 0 or target_available > target_total:
        raise ValueError("Invalid tracked device counts")

    while len([item for item in items if item.status != "disabled"]) < target_total:
        index = len(resource.items) + 1
        item = ResourceItem(
            resource_id=resource.id,
            asset_number=f"R{resource.id:04d}-{index:04d}",
            qr_code=f"qr://resource/{resource.id}/item/{index}",
            status="available",
            current_location=resource.location,
        )
        resource.items.append(item)
        items.append(item)

    active_items = [item for item in items if item.status != "disabled"]
    if len(active_items) > target_total:
        removable = [item for item in active_items if item.status == "available"]
        overflow = len(active_items) - target_total
        if len(removable) < overflow:
            raise ValueError("Cannot reduce tracked total_count below active non-available instances")
        for item in removable[:overflow]:
            item.status = "disabled"
            item.current_borrower_id = None
            item.current_location = f"{resource.location} / disabled"

    active_items = [item for item in resource.items if item.status not in {"lost", "disabled"}]
    current_available_items = [item for item in active_items if item.status == "available"]
    available_delta = target_available - len(current_available_items)
    if available_delta < 0:
        to_hold = current_available_items[: abs(available_delta)]
        for item in to_hold:
            item.status = "maintenance"
            item.current_location = f"{resource.location} / maintenance"
    elif available_delta > 0:
        # Allow pure available-count adjustments by prioritizing:
        # 1) maintenance/quarantine items, 2) stale borrowed items, 3) borrowed items (admin override).
        restore_candidates = [item for item in active_items if item.status in {"maintenance", "quarantine"}]
        stale_borrowed_candidates = [
            item for item in active_items if item.status == "borrowed" and item.current_borrower_id is None
        ]
        borrowed_candidates = [
            item for item in active_items if item.status == "borrowed" and item.current_borrower_id is not None
        ]
        candidates = restore_candidates + stale_borrowed_candidates + borrowed_candidates
        if len(candidates) < available_delta:
            raise ValueError("Cannot increase available_count beyond tracked instance capacity")
        for item in candidates[:available_delta]:
            item.status = "available"
            item.current_borrower_id = None
            item.current_location = resource.location


@router.post("", response_model=ResourceOut)
def create_resource(
    payload: ResourceCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a resource. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can create resources")
    if payload.available_count > payload.total_count:
        raise HTTPException(status_code=400, detail="Available inventory cannot exceed total inventory")

    _enforce_write_limit(current_user.id, "resources.create")
    resource = Resource(**payload.model_dump())
    db.add(resource)
    db.flush()
    if is_tracked_resource(resource):
        ensure_resource_item_capacity(db, resource)
        _reconcile_device_items(resource, resource.total_count, resource.available_count)
    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    write_audit_log(
        db,
        actor=current_user,
        action="resource.create",
        entity_type="resource",
        entity_id=resource.id,
        detail={
            "name": resource.name,
            "category": resource.category,
            "total_count": resource.total_count,
            "available_count": resource.available_count,
        },
        request=request,
    )
    db.commit()
    db.refresh(resource)
    return _build_resource_out(resource)


@router.get("", response_model=list[ResourceOut])
def list_resources(
    include_disabled: bool = Query(default=False, description="Include disabled resources"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all resources."""
    query = db.query(Resource)
    if not include_disabled:
        query = query.filter(Resource.status != "disabled")
    resources = query.order_by(Resource.id.desc()).all()
    return [_build_resource_out(resource) for resource in resources]


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get one resource."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return _build_resource_out(resource)


@router.patch("/{resource_id}", response_model=ResourceOut)
def update_resource(
    resource_id: int,
    payload: ResourceUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a resource. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can update resources")
    _enforce_write_limit(current_user.id, "resources.update")

    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    updates = payload.model_dump(exclude_none=True)
    next_total = updates.get("total_count", resource.total_count)
    next_available = updates.get("available_count", resource.available_count)
    if next_available > next_total:
        raise HTTPException(status_code=400, detail="Available inventory cannot exceed total inventory")

    for key, value in updates.items():
        setattr(resource, key, value)

    if is_tracked_resource(resource):
        try:
            ensure_resource_item_capacity(db, resource)
            _reconcile_device_items(resource, next_total, next_available)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    write_audit_log(
        db,
        actor=current_user,
        action="resource.update",
        entity_type="resource",
        entity_id=resource.id,
        detail={"updates": updates},
        request=request,
    )
    db.commit()
    db.refresh(resource)
    return _build_resource_out(resource)


@router.delete("/{resource_id}", response_model=MessageOut)
def archive_resource(
    resource_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive (soft-delete) one resource. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can archive resources")
    _enforce_write_limit(current_user.id, "resources.archive")

    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    active_borrow = (
        db.query(Transaction.id)
        .filter(
            Transaction.resource_id == resource_id,
            Transaction.action == "borrow",
            Transaction.status == "approved",
            Transaction.return_time.is_(None),
        )
        .first()
    )
    if active_borrow:
        raise HTTPException(status_code=400, detail="Cannot delete resource while an approved borrow is active")

    snapshot = {
        "total_count": resource.total_count,
        "available_count": resource.available_count,
        "status": resource.status,
    }
    resource.status = "disabled"
    archived_note = f"[{datetime.utcnow().isoformat()}] archived by admin user#{current_user.id}"
    snapshot_note = f"{ARCHIVE_SNAPSHOT_PREFIX}{json.dumps(snapshot, ensure_ascii=False)}"
    resource.description = f"{resource.description}\n{archived_note}\n{snapshot_note}".strip()

    write_audit_log(
        db,
        actor=current_user,
        action="resource.archive",
        entity_type="resource",
        entity_id=resource.id,
        detail=snapshot,
        request=request,
    )
    db.commit()
    return MessageOut(message="Resource archived successfully")


@router.post("/{resource_id}/restore", response_model=ResourceOut)
def restore_resource(
    resource_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore one archived resource. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can restore resources")
    _enforce_write_limit(current_user.id, "resources.restore")

    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.status != "disabled":
        raise HTTPException(status_code=400, detail="Resource is not archived")

    snapshot = _extract_archive_snapshot(resource.description)
    if snapshot:
        snapshot_total = int(snapshot.get("total_count", resource.total_count or 0))
        snapshot_available = int(snapshot.get("available_count", resource.available_count or 0))
        if snapshot_total >= 0:
            resource.total_count = snapshot_total
        if 0 <= snapshot_available <= max(resource.total_count, 0):
            resource.available_count = snapshot_available

    resource.status = "active"

    if is_tracked_resource(resource):
        ensure_resource_item_capacity(db, resource)
        try:
            _reconcile_device_items(resource, resource.total_count, resource.available_count)
        except ValueError:
            # Fall back to a safe state if historical data is inconsistent.
            safe_available = min(resource.available_count, resource.total_count)
            _reconcile_device_items(resource, resource.total_count, max(0, safe_available))
            resource.available_count = max(0, safe_available)

    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    write_audit_log(
        db,
        actor=current_user,
        action="resource.restore",
        entity_type="resource",
        entity_id=resource.id,
        detail={
            "total_count": resource.total_count,
            "available_count": resource.available_count,
            "status": resource.status,
        },
        request=request,
    )
    db.commit()
    db.refresh(resource)
    return _build_resource_out(resource)


@router.post("/{resource_id}/inventory-adjustments", response_model=TransactionOut)
def adjust_inventory(
    resource_id: int,
    payload: InventoryAdjustmentRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Directly adjust total and available inventory. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can adjust inventory directly")

    try:
        enforce_write_rate_limit(user_id=current_user.id, endpoint_key="resources.inventory_adjustment")
        with acquire_entity_lock(f"resource:inventory:{resource_id}"):
            idempotency = prepare_idempotency(
                db,
                scope="resources.inventory_adjustment",
                user_id=current_user.id,
                idempotency_key=idempotency_key,
                request_payload={
                    "resource_id": resource_id,
                    "target_total_count": payload.target_total_count,
                    "target_available_count": payload.target_available_count,
                    "reason": payload.reason,
                    "evidence_url": payload.evidence_url,
                    "evidence_type": payload.evidence_type,
                },
                entity_key=f"resource:{resource_id}",
            )
            if idempotency.cached_response is not None:
                return idempotency.cached_response

            resource = db.query(Resource).filter(Resource.id == resource_id).first()
            if not resource:
                raise HTTPException(status_code=404, detail="Resource not found")
            if payload.target_available_count > payload.target_total_count:
                raise HTTPException(status_code=400, detail="Available inventory cannot exceed total inventory")
            if (
                payload.target_total_count == resource.total_count
                and payload.target_available_count == resource.available_count
            ):
                raise HTTPException(status_code=400, detail="No inventory change detected")

            before_total = resource.total_count
            before_available = resource.available_count
            delta_total = abs(payload.target_total_count - before_total)
            delta_available = abs(payload.target_available_count - before_available)

            tx = Transaction(
                resource_id=resource.id,
                user_id=current_user.id,
                action="adjust",
                quantity=max(delta_total, delta_available, 1),
                note=payload.reason,
                purpose="admin inventory adjustment",
                status="approved",
                is_approved=True,
                inventory_after_total=payload.target_total_count,
                inventory_after_available=payload.target_available_count,
                evidence_url=payload.evidence_url,
                evidence_type=payload.evidence_type,
            )

            db.add(tx)
            db.flush()
            tx.resource = resource
            tx.user = current_user
            if is_tracked_resource(resource):
                ensure_resource_item_capacity(db, resource)
                _reconcile_device_items(resource, payload.target_total_count, payload.target_available_count)
                resource.total_count = payload.target_total_count
                resource.available_count = payload.target_available_count
                tx.inventory_before_total = before_total
                tx.inventory_after_total = resource.total_count
                tx.inventory_before_available = before_available
                tx.inventory_after_available = resource.available_count
                tx.inventory_applied = True
                run_inventory_rules(db, resource)
                run_utilization_rules(db, resource)
            else:
                apply_inventory_change(db, tx)

            response_payload = build_transaction_out(tx, current_user)
            write_audit_log(
                db,
                actor=current_user,
                action="resource.inventory_adjustment",
                entity_type="resource",
                entity_id=resource_id,
                detail={
                    "transaction_id": tx.id,
                    "target_total_count": payload.target_total_count,
                    "target_available_count": payload.target_available_count,
                    "reason": payload.reason,
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
        raise HTTPException(status_code=500, detail=f"Failed to adjust inventory: {exc}") from exc


@router.get("/{resource_id}/items", response_model=list[ResourceItemOut])
def list_resource_items(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List tracked instances for one resource."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return get_resource_items(db, resource_id)


@router.post("/{resource_id}/items", response_model=ResourceItemOut)
def create_resource_item(
    resource_id: int,
    payload: ResourceItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a tracked instance. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can create tracked instances")
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not is_tracked_resource(resource):
        raise HTTPException(status_code=400, detail="Only device resources support tracked instances")

    item = ResourceItem(resource_id=resource_id, **payload.model_dump())
    db.add(item)
    resource.total_count += 1
    if item.status == "available":
        resource.available_count += 1
    db.commit()
    db.refresh(item)
    return item


@router.patch("/items/{item_id}", response_model=ResourceItemOut)
def update_resource_item(
    item_id: int,
    payload: ResourceItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update one tracked instance. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can update tracked instances")

    item = db.query(ResourceItem).filter(ResourceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Tracked instance not found")

    before_available = item.status == "available"
    updates = payload.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(item, key, value)

    resource = item.resource
    if before_available and item.status != "available":
        resource.available_count = max(0, resource.available_count - 1)
    elif not before_available and item.status == "available":
        resource.available_count = min(resource.total_count, resource.available_count + 1)

    db.commit()
    db.refresh(item)
    return item


@router.get("/items/{item_id}/maintenance", response_model=list[MaintenanceRecordOut])
def list_item_maintenance_records(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List maintenance records for one tracked instance."""
    item = db.query(ResourceItem).filter(ResourceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Tracked instance not found")
    return (
        db.query(MaintenanceRecord)
        .filter(MaintenanceRecord.resource_item_id == item_id)
        .order_by(MaintenanceRecord.created_at.desc())
        .all()
    )


@router.post("/items/{item_id}/maintenance", response_model=MaintenanceRecordOut)
def create_item_maintenance_record(
    item_id: int,
    payload: MaintenanceRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a maintenance record. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can create maintenance records")
    item = db.query(ResourceItem).filter(ResourceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Tracked instance not found")

    record = MaintenanceRecord(
        resource_item_id=item_id,
        recorded_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    item.status = payload.status
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
