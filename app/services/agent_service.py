"""简易智能体服务：将自然语言问题路由到业务查询。"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Alert, Resource, Transaction


def _intent_from_question(question: str) -> str:
    """根据关键词识别用户意图。"""
    q = question.lower()
    if any(k in q for k in ["库存", "缺货", "阈值", "low"]):
        return "inventory_status"
    if any(k in q for k in ["占用", "预约", "利用率", "忙"]):
        return "utilization_status"
    if any(k in q for k in ["预警", "风险", "异常", "alert"]):
        return "alert_status"
    if any(k in q for k in ["谁借", "借了", "流水", "日志"]):
        return "transaction_status"
    return "general_help"


def _inventory_answer(db: Session) -> str:
    """输出库存不足资源列表。"""
    low_items = (
        db.query(Resource)
        .filter(Resource.available_count <= Resource.min_threshold)
        .order_by(Resource.available_count.asc())
        .all()
    )
    if not low_items:
        return "当前没有低库存资源，库存状态健康。"
    lines = [f"- {r.name}（可用 {r.available_count} / 阈值 {r.min_threshold}）" for r in low_items]
    return "以下资源库存不足：\n" + "\n".join(lines)


def _utilization_answer(db: Session) -> str:
    """输出设备占用情况，帮助协调使用时段。"""
    devices = db.query(Resource).filter(Resource.category == "device").all()
    if not devices:
        return "当前没有设备类资源。"
    lines = []
    for d in devices:
        ratio = 0.0 if d.total_count == 0 else (1 - d.available_count / d.total_count)
        lines.append(f"- {d.name}：占用率 {ratio:.0%}（可用 {d.available_count}/{d.total_count}）")
    return "设备利用率概览：\n" + "\n".join(lines)


def _alert_answer(db: Session) -> str:
    """返回最新预警，便于管理员快速干预。"""
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(10).all()
    if not alerts:
        return "暂无预警。"
    lines = [f"- [{a.level}] {a.type}: {a.message}" for a in alerts]
    return "最近预警：\n" + "\n".join(lines)


def _transaction_answer(db: Session) -> str:
    """统计最近借还流水，识别高频使用者。"""
    top_users = (
        db.query(Transaction.user_name, func.count(Transaction.id).label("cnt"))
        .group_by(Transaction.user_name)
        .order_by(func.count(Transaction.id).desc())
        .limit(5)
        .all()
    )
    if not top_users:
        return "还没有借还流水记录。"
    lines = [f"- {name}：{cnt} 次操作" for name, cnt in top_users]
    return "最近高频使用者：\n" + "\n".join(lines)


def ask_agent(db: Session, question: str) -> dict:
    """智能体主入口：识别意图并返回可执行的管理建议。"""
    intent = _intent_from_question(question)
    if intent == "inventory_status":
        answer = _inventory_answer(db)
    elif intent == "utilization_status":
        answer = _utilization_answer(db)
    elif intent == "alert_status":
        answer = _alert_answer(db)
    elif intent == "transaction_status":
        answer = _transaction_answer(db)
    else:
        answer = (
            "我可以帮你查看库存、设备占用率、预警信息和借还流水。"
            "示例：'当前哪些资源快缺货？'、'3D打印机占用率如何？'"
        )
    return {"intent": intent, "answer": answer}
