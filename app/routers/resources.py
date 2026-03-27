"""Resource management routes."""

from fastapi import APIRouter, Depends, HTTPException
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
)
from app.services.auth_service import is_admin
from app.services.resource_item_service import ensure_resource_item_capacity, get_resource_items, is_tracked_resource
from app.services.rules_engine import run_inventory_rules, run_utilization_rules
from app.services.transaction_service import apply_inventory_change, build_transaction_out

router = APIRouter(prefix="/resources", tags=["resources"])


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
        restore_candidates = [item for item in active_items if item.status in {"maintenance", "quarantine"}]
        if len(restore_candidates) < available_delta:
            raise ValueError("Cannot increase available_count without freeing more tracked instances")
        for item in restore_candidates[:available_delta]:
            item.status = "available"
            item.current_location = resource.location


@router.post("", response_model=ResourceOut)
def create_resource(
    payload: ResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a resource. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can create resources")
    if payload.available_count > payload.total_count:
        raise HTTPException(status_code=400, detail="Available inventory cannot exceed total inventory")

    resource = Resource(**payload.model_dump())
    db.add(resource)
    db.flush()
    if is_tracked_resource(resource):
        ensure_resource_item_capacity(db, resource)
        _reconcile_device_items(resource, resource.total_count, resource.available_count)
    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    db.commit()
    db.refresh(resource)
    return _build_resource_out(resource)


@router.get("", response_model=list[ResourceOut])
def list_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all resources."""
    resources = db.query(Resource).order_by(Resource.id.desc()).all()
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a resource. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can update resources")

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
    db.commit()
    db.refresh(resource)
    return _build_resource_out(resource)


@router.post("/{resource_id}/inventory-adjustments", response_model=TransactionOut)
def adjust_inventory(
    resource_id: int,
    payload: InventoryAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Directly adjust total and available inventory. Admin only."""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can adjust inventory directly")

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

    try:
        db.add(tx)
        db.flush()
        tx.resource = resource
        tx.user = current_user
        apply_inventory_change(db, tx)
        db.commit()
        db.refresh(tx)
        return build_transaction_out(tx, current_user)
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
