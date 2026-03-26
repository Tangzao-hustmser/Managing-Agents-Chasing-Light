"""借还/领用流水路由。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Resource, Transaction, User
from app.routers.auth import get_current_user
from app.schemas import TransactionCreate, TransactionOut
from app.services.approval_service import create_approval_task, should_require_approval
from app.services.rules_engine import run_inventory_rules, run_utilization_rules, run_waste_rules
from app.services.time_slot_service import calculate_duration, check_time_slot_conflict

router = APIRouter(prefix="/transactions", tags=["借还与领用"])


@router.post("", response_model=TransactionOut)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """记录一次借还或领用行为，并同步更新库存/可用量。"""
    resource = db.query(Resource).filter(Resource.id == payload.resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="资源不存在")

    # 时段检测：设备类资源的 borrow 动作需要检查冲突
    if payload.action == "borrow" and resource.category == "device":
        if not payload.borrow_time or not payload.expected_return_time:
            raise HTTPException(status_code=400, detail="设备借用需要提供 borrow_time 和 expected_return_time")
        
        conflicts = check_time_slot_conflict(
            db,
            payload.resource_id,
            payload.borrow_time,
            payload.expected_return_time
        )
        if conflicts:
            conflict_info = "; ".join([f"ID#{c.id} 用户{c.user_id}" for c in conflicts])
            raise HTTPException(
                status_code=400,
                detail=f"时段冲突：{conflict_info}"
            )

    # 库存检查（只检查，不更新）
    if payload.action in ("borrow", "consume", "lost"):
        if resource.available_count < payload.quantity:
            raise HTTPException(status_code=400, detail="可用数量不足")
    elif payload.action in ("return", "replenish"):
        # 归还和补货不需要检查库存限制
        pass
    else:
        raise HTTPException(status_code=400, detail="不支持的 action")

    # 创建 transaction 对象
    tx = Transaction(
        resource_id=payload.resource_id,
        user_id=current_user.id,
        action=payload.action,
        quantity=payload.quantity,
        note=payload.note,
        borrow_time=payload.borrow_time,
        expected_return_time=payload.expected_return_time,
        purpose=payload.purpose,
        condition_return=payload.condition_return
    )
    
    # 检查是否需要审批
    require_approval, reason = should_require_approval(payload.action, payload.quantity, resource)
    
    if require_approval:
        tx.is_approved = False
        db.add(tx)
        db.flush()  # 获取 tx.id
        approval_task = create_approval_task(db, tx, current_user, reason)
        tx.approval_id = approval_task.id
    else:
        tx.is_approved = True
        # 只有审批通过的事务才更新库存
        if payload.action in ("borrow", "consume", "lost"):
            resource.available_count -= payload.quantity
        elif payload.action in ("return", "replenish"):
            resource.available_count += payload.quantity
            if resource.available_count > resource.total_count:
                if resource.category == "material":
                    resource.total_count = resource.available_count
                else:
                    resource.available_count = resource.total_count

    try:
        db.add(tx)
        run_inventory_rules(db, resource)
        run_utilization_rules(db, resource)
        run_waste_rules(db, resource, payload.action, payload.quantity)
        db.commit()
        db.refresh(tx)
        return tx
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"数据库操作失败: {str(e)}")


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询流水记录。
    
    学生仅能查看自己的流水，管理员可以查看全部。
    """
    if current_user.role == "admin":
        txs = db.query(Transaction).order_by(Transaction.id.desc()).all()
    else:
        txs = db.query(Transaction).filter(Transaction.user_id == current_user.id).order_by(Transaction.id.desc()).all()
    
    return txs


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取单条流水详情。"""
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="流水不存在")
    
    # 权限检查
    if current_user.role != "admin" and tx.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问他人的流水")
    
    return tx


@router.patch("/{transaction_id}/return")
def return_resource(
    transaction_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """归还资源：填充 return_time 和 condition_return。"""
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="流水不存在")
    
    if tx.action != "borrow":
        raise HTTPException(status_code=400, detail="仅借用类流水可以归还")
    
    if tx.return_time is not None:
        raise HTTPException(status_code=400, detail="该资源已归还")
    
    # 权限检查
    if current_user.role != "admin" and tx.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权归还他人的资源")
    
    # 更新归还信息
    tx.return_time = datetime.utcnow()
    tx.condition_return = payload.get("condition_return", "完好")
    
    if tx.borrow_time:
        tx.duration_minutes = calculate_duration(tx.borrow_time, tx.return_time)
    
    db.commit()
    db.refresh(tx)
    
    return {
        "id": tx.id,
        "return_time": tx.return_time,
        "duration_minutes": tx.duration_minutes,
        "condition_return": tx.condition_return
    }
