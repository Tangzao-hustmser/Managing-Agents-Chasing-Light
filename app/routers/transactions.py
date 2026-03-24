"""借还/领用流水路由。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Resource, Transaction
from app.schemas import TransactionCreate, TransactionOut
from app.services.rules_engine import run_inventory_rules, run_utilization_rules, run_waste_rules

router = APIRouter(prefix="/transactions", tags=["借还与领用"])


@router.post("", response_model=TransactionOut)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    """记录一次借还或领用行为，并同步更新库存/可用量。"""
    resource = db.query(Resource).filter(Resource.id == payload.resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="资源不存在")

    if payload.action in ("borrow", "consume", "lost"):
        if resource.available_count < payload.quantity:
            raise HTTPException(status_code=400, detail="可用数量不足")
        resource.available_count -= payload.quantity
    elif payload.action in ("return", "replenish"):
        resource.available_count += payload.quantity
        if resource.available_count > resource.total_count:
            # 设备归还时不应超过总量；物料补充时可同步拉高总量。
            if resource.category == "material":
                resource.total_count = resource.available_count
            else:
                resource.available_count = resource.total_count
    else:
        raise HTTPException(status_code=400, detail="不支持的 action")

    tx = Transaction(**payload.model_dump())
    db.add(tx)
    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    run_waste_rules(db, resource, payload.action, payload.quantity)
    db.commit()
    db.refresh(tx)
    return tx


@router.get("", response_model=list[TransactionOut])
def list_transactions(db: Session = Depends(get_db)):
    """查询所有流水记录。"""
    return db.query(Transaction).order_by(Transaction.id.desc()).all()
