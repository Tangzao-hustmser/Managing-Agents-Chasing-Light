"""资源管理路由。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Resource
from app.schemas import ResourceCreate, ResourceOut, ResourceUpdate
from app.services.rules_engine import run_inventory_rules, run_utilization_rules

router = APIRouter(prefix="/resources", tags=["资源管理"])


@router.post("", response_model=ResourceOut)
def create_resource(payload: ResourceCreate, db: Session = Depends(get_db)):
    """创建资源条目，并立即做一次规则检测。"""
    resource = Resource(**payload.model_dump())
    db.add(resource)
    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.get("", response_model=list[ResourceOut])
def list_resources(db: Session = Depends(get_db)):
    """查询所有资源。"""
    return db.query(Resource).order_by(Resource.id.desc()).all()


@router.patch("/{resource_id}", response_model=ResourceOut)
def update_resource(resource_id: int, payload: ResourceUpdate, db: Session = Depends(get_db)):
    """更新资源字段。"""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="资源不存在")

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(resource, key, value)

    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    db.commit()
    db.refresh(resource)
    return resource
