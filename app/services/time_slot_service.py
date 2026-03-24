"""时段冲突检测服务：检查设备预约时间是否冲突。"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Transaction


def check_time_slot_conflict(
    db: Session,
    resource_id: int,
    borrow_time: datetime,
    return_time: datetime,
    exclude_transaction_id: Optional[int] = None
) -> List[Transaction]:
    """
    检查指定资源在给定时段内是否有冲突的借用。
    
    返回冲突的 transaction 列表（如果冲突则非空）。
    """
    if borrow_time >= return_time:
        raise ValueError("归还时间必须晚于借用时间")
    
    # 查找该资源的所有未归还的借用记录（action='borrow' 且 return_time 为空）
    conflicts = db.query(Transaction).filter(
        Transaction.resource_id == resource_id,
        Transaction.action == "borrow",
        Transaction.return_time.is_(None),  # 还未归还
        Transaction.borrow_time.isnot(None),
    ).all()
    
    result = []
    for tx in conflicts:
        if exclude_transaction_id and tx.id == exclude_transaction_id:
            continue
        
        tx_start = tx.borrow_time
        tx_end = tx.expected_return_time or tx.return_time
        
        if tx_end is None:
            # 若 expected_return_time 和 return_time 都为空，认为仍在借用中
            tx_end = datetime.utcnow() + __import__("datetime").timedelta(days=365)  # 默认1年内有冲突
        
        # 时间段重叠判定：max(start1, start2) < min(end1, end2)
        if max(borrow_time, tx_start) < min(return_time, tx_end):
            result.append(tx)
    
    return result


def calculate_duration(borrow_time: datetime, return_time: datetime) -> int:
    """计算借用时长（分钟）。"""
    if return_time is None:
        return None
    delta = return_time - borrow_time
    return int(delta.total_seconds() / 60)
