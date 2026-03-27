"""Resource management routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Resource, Transaction, User
from app.routers.auth import get_current_user
from app.schemas import InventoryAdjustmentRequest, ResourceCreate, ResourceOut, ResourceUpdate, TransactionOut
from app.services.auth_service import is_admin
from app.services.rules_engine import run_inventory_rules, run_utilization_rules
from app.services.transaction_service import apply_inventory_change, build_transaction_out

router = APIRouter(prefix="/resources", tags=["resources"])


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
    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.get("", response_model=list[ResourceOut])
def list_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all resources."""
    return db.query(Resource).order_by(Resource.id.desc()).all()


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
    return resource


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

    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    db.commit()
    db.refresh(resource)
    return resource


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
