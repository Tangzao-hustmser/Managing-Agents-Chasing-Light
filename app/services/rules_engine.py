"""规则引擎：根据业务规则生成预警。"""

from sqlalchemy.orm import Session

from app.models import Alert, Resource


def run_inventory_rules(db: Session, resource: Resource) -> None:
    """库存规则：可用数量低于阈值时发出预警。"""
    # 清除已解决的低库存预警
    existing_alerts = db.query(Alert).filter(
        Alert.type == "low_inventory",
        Alert.message.like(f"%{resource.name}%")
    ).all()
    for alert in existing_alerts:
        if resource.available_count > resource.min_threshold:
            db.delete(alert)
    
    if resource.available_count <= resource.min_threshold:
        alert = Alert(
            level="warn",
            type="low_inventory",
            message=f"资源[{resource.name}]库存不足，可用 {resource.available_count}，阈值 {resource.min_threshold}",
        )
        db.add(alert)


def run_utilization_rules(db: Session, resource: Resource) -> None:
    """利用率规则：设备可用率过低时提示占用不均。"""
    if resource.category == "device" and resource.total_count > 0:
        utilization = 1 - (resource.available_count / resource.total_count)
        if utilization >= 0.8:
            alert = Alert(
                level="warn",
                type="high_occupancy",
                message=f"设备[{resource.name}]占用率 {utilization:.0%}，建议协调预约时段",
            )
            db.add(alert)


def run_waste_rules(db: Session, resource: Resource, action: str, quantity: int) -> None:
    """耗材浪费规则：单次领用量过高或标记丢失触发告警。"""
    if action == "consume" and quantity >= 10:
        db.add(
            Alert(
                level="warn",
                type="possible_waste",
                message=f"资源[{resource.name}]单次领用数量={quantity}，请核查是否存在浪费",
            )
        )
    if action == "lost":
        db.add(
            Alert(
                level="error",
                type="resource_lost",
                message=f"资源[{resource.name}]发生丢失登记，数量={quantity}",
            )
        )
