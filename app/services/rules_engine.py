"""规则引擎：根据业务规则生成预警。"""

from sqlalchemy.orm import Session

from app.models import Resource
from app.services.alert_service import emit_alert, resolve_alert_by_dedup_key


def run_inventory_rules(db: Session, resource: Resource) -> None:
    """库存规则：可用数量低于阈值时发出预警。"""
    dedup_key = f"low_inventory:resource:{resource.id}"
    if resource.available_count <= resource.min_threshold:
        emit_alert(
            db,
            level="warn",
            alert_type="low_inventory",
            message=f"资源[{resource.name}]库存不足，可用 {resource.available_count}，阈值 {resource.min_threshold}",
            dedup_key=dedup_key,
        )
    else:
        resolve_alert_by_dedup_key(db, alert_type="low_inventory", dedup_key=dedup_key)


def run_utilization_rules(db: Session, resource: Resource) -> None:
    """利用率规则：设备可用率过低时提示占用不均。"""
    dedup_key = f"high_occupancy:resource:{resource.id}"
    if resource.category == "device" and resource.total_count > 0:
        utilization = 1 - (resource.available_count / resource.total_count)
        if utilization >= 0.8:
            emit_alert(
                db,
                level="warn",
                alert_type="high_occupancy",
                message=f"设备[{resource.name}]占用率 {utilization:.0%}，建议协调预约时段",
                dedup_key=dedup_key,
            )
        else:
            resolve_alert_by_dedup_key(db, alert_type="high_occupancy", dedup_key=dedup_key)


def run_waste_rules(db: Session, resource: Resource, action: str, quantity: int) -> None:
    """耗材浪费规则：单次领用量过高或标记丢失触发告警。"""
    if action == "consume" and quantity >= 10:
        emit_alert(
            db,
            level="warn",
            alert_type="possible_waste",
            message=f"资源[{resource.name}]单次领用数量={quantity}，请核查是否存在浪费",
            dedup_key=f"possible_waste:resource:{resource.id}",
        )
    if action == "lost":
        emit_alert(
            db,
            level="error",
            alert_type="resource_lost",
            message=f"资源[{resource.name}]发生丢失登记，数量={quantity}",
            dedup_key=f"resource_lost:resource:{resource.id}",
        )
