"""简易智能体服务：将自然语言问题路由到业务查询。"""

from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Alert, ApprovalTask, Resource, Transaction


def _intent_from_question(question: str) -> str:
    """根据关键词识别用户意图。"""
    q = question.lower()
    if any(k in q for k in ["成本", "费用", "消耗", "支出", "花费"]):
        return "cost_analysis"
    if any(k in q for k in ["趋势", "走势", "增长", "下降", "预测"]):
        return "time_series_analysis"
    if any(k in q for k in ["谁借", "排行", "高频", "用户", "使用者"]):
        return "user_behavior"
    if any(k in q for k in ["审批", "待审", "批准", "拒绝", "申请"]):
        return "approval_status"
    if any(k in q for k in ["建议", "如何", "怎样", "优化", "改进", "方案"]):
        return "recommendation"
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
        db.query(Transaction.user_id, func.count(Transaction.id).label("cnt"))
        .group_by(Transaction.user_id)
        .order_by(func.count(Transaction.id).desc())
        .limit(5)
        .all()
    )
    if not top_users:
        return "还没有借还流水记录。"
    lines = []
    for user_id, cnt in top_users:
        user = db.query(Resource).first()  # 简化：仅显示 user_id
        lines.append(f"- 用户 {user_id}：{cnt} 次操作")
    return "最近高频使用者：\n" + "\n".join(lines)


def _cost_analysis_answer(db: Session) -> str:
    """成本分析：统计各资源消耗成本。"""
    consumptions = (
        db.query(
            Transaction.resource_id,
            func.sum(Transaction.quantity).label("total_qty"),
            Resource.unit_cost,
            Resource.name
        )
        .filter(Transaction.action.in_(["consume", "lost"]))
        .join(Resource, Transaction.resource_id == Resource.id)
        .group_by(Transaction.resource_id, Resource.unit_cost, Resource.name)
        .order_by(func.sum(Transaction.quantity * Resource.unit_cost).desc())
        .limit(10)
        .all()
    )
    
    if not consumptions:
        return "暂无消耗记录，成本为 0。"
    
    total_cost = 0
    lines = []
    for resource_id, qty, unit_cost, name in consumptions:
        cost = qty * unit_cost if unit_cost else 0
        total_cost += cost
        lines.append(f"- {name}：消耗 {qty} 件，成本 ¥{cost:.2f}")
    
    lines.insert(0, f"总成本：¥{total_cost:.2f}")
    return "资源消耗成本统计：\n" + "\n".join(lines)


def _time_series_answer(db: Session) -> str:
    """趋势分析：过去 7 天的借用和消耗趋势。"""
    now = datetime.utcnow()
    past_7_days = now - timedelta(days=7)
    
    daily_counts = (
        db.query(
            func.date(Transaction.created_at).label("date"),
            Transaction.action,
            func.count(Transaction.id).label("cnt")
        )
        .filter(Transaction.created_at >= past_7_days)
        .group_by(func.date(Transaction.created_at), Transaction.action)
        .all()
    )
    
    if not daily_counts:
        return "过去 7 天内没有流水记录。"
    
    lines = ["过去 7 天趋势："]
    for date, action, cnt in daily_counts:
        lines.append(f"- {date} {action}：{cnt} 次")
    
    return "\n".join(lines)


def _user_behavior_answer(db: Session) -> str:
    """用户行为分析：排行榜。"""
    top_users = (
        db.query(Transaction.user_id, func.count(Transaction.id).label("cnt"))
        .group_by(Transaction.user_id)
        .order_by(func.count(Transaction.id).desc())
        .limit(10)
        .all()
    )
    
    if not top_users:
        return "暂无用户借还记录。"
    
    lines = ["用户使用排行榜："]
    for rank, (user_id, cnt) in enumerate(top_users, 1):
        lines.append(f"{rank}. 用户 {user_id}：{cnt} 次操作")
    
    return "\n".join(lines)


def _approval_status_answer(db: Session) -> str:
    """审批状态：待审项统计。"""
    pending = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
    approved = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "approved").scalar() or 0
    rejected = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "rejected").scalar() or 0
    
    lines = [
        f"待审批：{pending} 项",
        f"已批准：{approved} 项",
        f"已拒绝：{rejected} 项"
    ]
    
    if pending > 0:
        lines.append("\n最近待审项：")
        pending_tasks = db.query(ApprovalTask).filter(ApprovalTask.status == "pending").order_by(ApprovalTask.created_at.desc()).limit(3).all()
        for task in pending_tasks:
            tx = task.transaction
            lines.append(f"- 申请 {tx.action}（资源#{tx.resource_id}，数量 {tx.quantity}）")
    
    return "\n".join(lines)


def _recommendation_answer(db: Session) -> str:
    """提出管理建议。"""
    lines = ["智能体管理建议："]
    
    # 建议 1：库存预警
    low_count = db.query(func.count(Resource.id)).filter(Resource.available_count <= Resource.min_threshold).scalar() or 0
    if low_count > 0:
        lines.append(f"⚠️ 当前有 {low_count} 个资源库存不足，建议及时补货。")
    
    # 建议 2：设备占用
    high_occupancy = db.query(Resource).filter(Resource.category == "device").all()
    for device in high_occupancy:
        if device.total_count > 0:
            occupancy = 1 - (device.available_count / device.total_count)
            if occupancy >= 0.8:
                lines.append(f"📊 {device.name} 占用率 {occupancy:.0%}，建议增加设备或错开预约时段。")
    
    # 建议 3：审批堆积
    pending_approvals = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
    if pending_approvals > 0:
        lines.append(f"📋 有 {pending_approvals} 个待审批任务，建议及时处理。")
    
    if len(lines) == 1:
        lines.append("✅ 当前资源管理状态良好，继续保持！")
    
    return "\n".join(lines)


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
    elif intent == "cost_analysis":
        answer = _cost_analysis_answer(db)
    elif intent == "time_series_analysis":
        answer = _time_series_answer(db)
    elif intent == "user_behavior":
        answer = _user_behavior_answer(db)
    elif intent == "approval_status":
        answer = _approval_status_answer(db)
    elif intent == "recommendation":
        answer = _recommendation_answer(db)
    else:
        answer = (
            "我可以帮你查看库存、设备占用率、预警信息、借还流水、成本分析、趋势预测、用户行为和管理建议。\n"
            "示例：'当前哪些资源快缺货？'、'3D打印机占用率如何？'、'本月消耗成本多少？'、'谁用得最多？'"
        )
    
    return {"intent": intent, "answer": answer}
