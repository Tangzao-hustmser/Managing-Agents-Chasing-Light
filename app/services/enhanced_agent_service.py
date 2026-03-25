"""增强版智能体服务：集成大语言模型实现真正的AI对话能力。"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models import Alert, ApprovalTask, Resource, Transaction, User, ChatMessage
from app.services.llm_service import get_llm_response


class EnhancedAgentService:
    """增强版智能体服务，支持多轮对话和深度分析。"""
    
    def __init__(self, db: Session):
        self.db = db
        self.system_prompt = self._get_system_prompt()
    
    def _get_system_prompt(self) -> str:
        """构建系统提示词，定义智能体的角色和能力。"""
        return """
你是一个创新实践基地的智能管理助手，负责管理3D打印机、激光切割机、电子元器件、开发板、万用表等共享资源。

你的核心能力包括：
1. 资源管理：查询设备状态、库存情况、使用记录
2. 智能调度：推荐最佳使用时段、解决冲突
3. 预警分析：识别库存不足、设备占用过高、耗材浪费等问题
4. 数据洞察：分析使用趋势、成本统计、用户行为
5. 管理建议：提供优化建议和决策支持

请根据用户的问题，结合数据库中的实时数据，提供准确、有用的回答。

数据库表结构：
- resources: 资源信息（设备/物料）
- transactions: 借还/领用记录
- alerts: 系统预警
- approval_tasks: 审批任务
- users: 用户信息
"""
    
    def get_conversation_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """获取对话历史记录。"""
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(messages)
        ]
    
    def save_conversation_message(self, session_id: str, role: str, content: str) -> None:
        """保存对话消息。"""
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content
        )
        self.db.add(message)
        self.db.commit()
    
    def get_real_time_data_context(self) -> Dict:
        """获取实时数据上下文，供LLM参考。"""
        # 当前库存状态
        low_inventory_resources = (
            self.db.query(Resource)
            .filter(Resource.available_count <= Resource.min_threshold)
            .all()
        )
        
        # 设备占用情况
        high_occupancy_devices = (
            self.db.query(Resource)
            .filter(
                Resource.category == "device",
                Resource.total_count > 0
            )
            .all()
        )
        
        # 最近预警
        recent_alerts = (
            self.db.query(Alert)
            .order_by(Alert.created_at.desc())
            .limit(5)
            .all()
        )
        
        # 待审批任务
        pending_approvals = (
            self.db.query(ApprovalTask)
            .filter(ApprovalTask.status == "pending")
            .count()
        )
        
        return {
            "low_inventory_resources": [
                {
                    "name": r.name,
                    "available_count": r.available_count,
                    "min_threshold": r.min_threshold
                }
                for r in low_inventory_resources
            ],
            "device_occupancy": [
                {
                    "name": d.name,
                    "occupancy_rate": (1 - d.available_count / d.total_count) if d.total_count > 0 else 0,
                    "available_count": d.available_count,
                    "total_count": d.total_count
                }
                for d in high_occupancy_devices
            ],
            "recent_alerts": [
                {
                    "type": a.type,
                    "level": a.level,
                    "message": a.message,
                    "created_at": a.created_at.isoformat()
                }
                for a in recent_alerts
            ],
            "pending_approvals": pending_approvals
        }
    
    def enhanced_ask_agent(self, question: str, session_id: str = "default") -> Dict:
        """增强版智能问答：集成LLM实现真正的对话能力。"""
        
        # 保存用户问题
        self.save_conversation_message(session_id, "user", question)
        
        # 获取对话历史和实时数据
        history = self.get_conversation_history(session_id)
        real_time_data = self.get_real_time_data_context()
        
        # 构建LLM提示词
        messages = [
            {"role": "system", "content": self.system_prompt},
            *history,
            {
                "role": "user", 
                "content": f"""
当前实时数据：
{json.dumps(real_time_data, ensure_ascii=False, indent=2)}

用户问题：{question}

请基于以上实时数据回答用户问题，提供准确、有用的信息和建议。
"""
            }
        ]
        
        # 调用LLM服务
        try:
            response = get_llm_response(messages)
            
            # 保存智能体回复
            self.save_conversation_message(session_id, "assistant", response)
            
            return {
                "session_id": session_id,
                "answer": response,
                "real_time_data": real_time_data,
                "success": True
            }
            
        except Exception as e:
            # 如果LLM调用失败，回退到基于规则的问答
            fallback_answer = self._fallback_rule_based_answer(question)
            self.save_conversation_message(session_id, "assistant", fallback_answer)
            
            return {
                "session_id": session_id,
                "answer": f"{fallback_answer}\n\n（LLM服务暂时不可用，已使用规则引擎回答）",
                "real_time_data": real_time_data,
                "success": False
            }
    
    def _fallback_rule_based_answer(self, question: str) -> str:
        """回退到基于规则的问答系统。"""
        q = question.lower()
        
        if any(k in q for k in ["库存", "缺货", "阈值", "low"]):
            return self._get_inventory_status()
        elif any(k in q for k in ["占用", "预约", "利用率", "忙"]):
            return self._get_utilization_status()
        elif any(k in q for k in ["预警", "风险", "异常", "alert"]):
            return self._get_alert_status()
        elif any(k in q for k in ["成本", "费用", "消耗", "支出"]):
            return self._get_cost_analysis()
        elif any(k in q for k in ["趋势", "走势", "增长", "下降"]):
            return self._get_time_series_analysis()
        elif any(k in q for k in ["审批", "待审", "批准", "拒绝"]):
            return self._get_approval_status()
        else:
            return """我可以帮你查询以下信息：
- 库存状态：哪些资源快缺货了？
- 设备占用：3D打印机占用率如何？
- 预警信息：当前有哪些风险？
- 成本分析：本月消耗成本多少？
- 使用趋势：最近使用情况如何？
- 审批状态：待审批任务有哪些？

请具体描述你的问题。"""
    
    def _get_inventory_status(self) -> str:
        """获取库存状态。"""
        low_items = (
            self.db.query(Resource)
            .filter(Resource.available_count <= Resource.min_threshold)
            .order_by(Resource.available_count.asc())
            .all()
        )
        
        if not low_items:
            return "? 当前没有低库存资源，库存状态健康。"
        
        lines = [f"?? 以下资源库存不足："]
        for r in low_items:
            lines.append(f"- {r.name}（可用 {r.available_count} / 阈值 {r.min_threshold}）")
        
        return "\n".join(lines)
    
    def _get_utilization_status(self) -> str:
        """获取设备占用情况。"""
        devices = self.db.query(Resource).filter(Resource.category == "device").all()
        
        if not devices:
            return "当前没有设备类资源。"
        
        lines = ["? 设备利用率概览："]
        for d in devices:
            if d.total_count > 0:
                ratio = 1 - (d.available_count / d.total_count)
                status = "?" if ratio < 0.7 else "?" if ratio < 0.9 else "?"
                lines.append(f"{status} {d.name}：占用率 {ratio:.0%}（可用 {d.available_count}/{d.total_count}）")
        
        return "\n".join(lines)
    
    def _get_alert_status(self) -> str:
        """获取预警信息。"""
        alerts = self.db.query(Alert).order_by(Alert.created_at.desc()).limit(10).all()
        
        if not alerts:
            return "? 暂无预警。"
        
        lines = ["? 最近预警："]
        for a in alerts:
            level_icon = "??" if a.level == "info" else "??" if a.level == "warn" else "?"
            lines.append(f"{level_icon} [{a.type}] {a.message}")
        
        return "\n".join(lines)
    
    def _get_cost_analysis(self) -> str:
        """成本分析。"""
        consumptions = (
            self.db.query(
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
        lines = ["? 资源消耗成本统计："]
        for resource_id, qty, unit_cost, name in consumptions:
            cost = qty * unit_cost if unit_cost else 0
            total_cost += cost
            lines.append(f"- {name}：消耗 {qty} 件，成本 ?{cost:.2f}")
        
        lines.insert(1, f"总成本：?{total_cost:.2f}")
        return "\n".join(lines)
    
    def _get_time_series_analysis(self) -> str:
        """时间序列分析。"""
        now = datetime.utcnow()
        past_7_days = now - timedelta(days=7)
        
        daily_counts = (
            self.db.query(
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
        
        lines = ["? 过去 7 天趋势："]
        for date, action, cnt in daily_counts:
            lines.append(f"- {date} {action}：{cnt} 次")
        
        return "\n".join(lines)
    
    def _get_approval_status(self) -> str:
        """审批状态。"""
        pending = self.db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
        approved = self.db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "approved").scalar() or 0
        rejected = self.db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "rejected").scalar() or 0
        
        lines = [
            "? 审批状态概览：",
            f"待审批：{pending} 项",
            f"已批准：{approved} 项", 
            f"已拒绝：{rejected} 项"
        ]
        
        if pending > 0:
            lines.append("\n最近待审项：")
            pending_tasks = self.db.query(ApprovalTask).filter(ApprovalTask.status == "pending").order_by(ApprovalTask.created_at.desc()).limit(3).all()
            for task in pending_tasks:
                tx = task.transaction
                lines.append(f"- 申请 {tx.action}（资源#{tx.resource_id}，数量 {tx.quantity}）")
        
        return "\n".join(lines)


def enhanced_ask_agent(db: Session, question: str, session_id: str = "default") -> Dict:
    """对外提供的增强版智能问答接口。"""
    agent = EnhancedAgentService(db)
    return agent.enhanced_ask_agent(question, session_id)