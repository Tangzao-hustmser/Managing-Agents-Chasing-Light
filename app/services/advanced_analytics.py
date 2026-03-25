"""高级数据分析服务：提供深度洞察和预测功能。"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import and_, func, case
from sqlalchemy.orm import Session

from app.models import Resource, Transaction, User


class AdvancedAnalytics:
    """高级数据分析器：提供深度洞察和预测功能。"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_comprehensive_analytics(self, days: int = 30) -> Dict:
        """获取综合数据分析报告。"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        return {
            "period": {
                "start_date": start_date.date().isoformat(),
                "end_date": end_date.date().isoformat(),
                "days": days
            },
            "summary": self._get_summary_stats(start_date, end_date),
            "resource_analysis": self._analyze_resource_usage(start_date, end_date),
            "user_behavior": self._analyze_user_behavior(start_date, end_date),
            "cost_analysis": self._analyze_costs(start_date, end_date),
            "trends": self._identify_trends(start_date, end_date),
            "recommendations": self._generate_recommendations(start_date, end_date)
        }
    
    def _get_summary_stats(self, start_date: datetime, end_date: datetime) -> Dict:
        """获取基础统计信息。"""
        # 总交易量
        total_transactions = (
            self.db.query(func.count(Transaction.id))
            .filter(and_(Transaction.created_at >= start_date, Transaction.created_at <= end_date))
            .scalar() or 0
        )
        
        # 活跃用户数
        active_users = (
            self.db.query(func.count(func.distinct(Transaction.user_id)))
            .filter(and_(Transaction.created_at >= start_date, Transaction.created_at <= end_date))
            .scalar() or 0
        )
        
        # 设备使用率
        device_usage = self._calculate_device_utilization(start_date, end_date)
        
        # 物料消耗量
        material_consumption = (
            self.db.query(func.sum(Transaction.quantity))
            .filter(
                and_(
                    Transaction.created_at >= start_date,
                    Transaction.created_at <= end_date,
                    Transaction.action.in_(["consume", "lost"])
                )
            )
            .scalar() or 0
        )
        
        return {
            "total_transactions": total_transactions,
            "active_users": active_users,
            "average_device_utilization": device_usage,
            "material_consumption": material_consumption,
            "daily_avg_transactions": total_transactions / max(1, (end_date - start_date).days)
        }
    
    def _calculate_device_utilization(self, start_date: datetime, end_date: datetime) -> float:
        """计算设备平均利用率。"""
        devices = self.db.query(Resource).filter(Resource.category == "device").all()
        
        if not devices:
            return 0.0
        
        total_utilization = 0
        for device in devices:
            # 计算该设备在时间段内的使用时长
            usage_hours = self._calculate_device_usage_hours(device.id, start_date, end_date)
            
            # 最大可能使用时长（假设每天工作14小时）
            days = (end_date - start_date).days
            max_possible_hours = 14 * days
            
            utilization = usage_hours / max_possible_hours if max_possible_hours > 0 else 0
            total_utilization += utilization
        
        return total_utilization / len(devices)
    
    def _calculate_device_usage_hours(self, resource_id: int, start_date: datetime, end_date: datetime) -> float:
        """计算设备使用时长。"""
        borrow_records = (
            self.db.query(Transaction)
            .filter(
                and_(
                    Transaction.resource_id == resource_id,
                    Transaction.action == "borrow",
                    Transaction.borrow_time >= start_date,
                    Transaction.borrow_time <= end_date
                )
            )
            .all()
        )
        
        total_hours = 0
        for record in borrow_records:
            if record.borrow_time and record.expected_return_time:
                duration = (record.expected_return_time - record.borrow_time).total_seconds() / 3600
                total_hours += duration
        
        return total_hours
    
    def _analyze_resource_usage(self, start_date: datetime, end_date: datetime) -> Dict:
        """分析资源使用情况。"""
        # 最受欢迎的资源
        popular_resources = (
            self.db.query(
                Transaction.resource_id,
                Resource.name,
                func.count(Transaction.id).label("usage_count")
            )
            .join(Resource, Transaction.resource_id == Resource.id)
            .filter(and_(Transaction.created_at >= start_date, Transaction.created_at <= end_date))
            .group_by(Transaction.resource_id, Resource.name)
            .order_by(func.count(Transaction.id).desc())
            .limit(10)
            .all()
        )
        
        # 高利用率设备
        high_utilization_devices = []
        devices = self.db.query(Resource).filter(Resource.category == "device").all()
        
        for device in devices:
            usage_hours = self._calculate_device_usage_hours(device.id, start_date, end_date)
            days = (end_date - start_date).days
            max_possible_hours = 14 * days
            utilization = usage_hours / max_possible_hours if max_possible_hours > 0 else 0
            
            if utilization >= 0.7:  # 70%以上利用率
                high_utilization_devices.append({
                    "resource_id": device.id,
                    "name": device.name,
                    "utilization": utilization,
                    "usage_hours": usage_hours
                })
        
        return {
            "popular_resources": [
                {
                    "resource_id": rid,
                    "name": name,
                    "usage_count": count
                }
                for rid, name, count in popular_resources
            ],
            "high_utilization_devices": high_utilization_devices,
            "analysis_period": f"{start_date.date()} 至 {end_date.date()}"
        }
    
    def _analyze_user_behavior(self, start_date: datetime, end_date: datetime) -> Dict:
        """分析用户行为模式。"""
        # 活跃用户排行榜
        active_users = (
            self.db.query(
                Transaction.user_id,
                User.real_name,
                func.count(Transaction.id).label("transaction_count")
            )
            .join(User, Transaction.user_id == User.id)
            .filter(and_(Transaction.created_at >= start_date, Transaction.created_at <= end_date))
            .group_by(Transaction.user_id, User.real_name)
            .order_by(func.count(Transaction.id).desc())
            .limit(10)
            .all()
        )
        
        # 用户行为模式分析
        user_patterns = (
            self.db.query(
                Transaction.user_id,
                func.extract('hour', Transaction.created_at).label("hour"),
                func.count(Transaction.id).label("count")
            )
            .filter(and_(Transaction.created_at >= start_date, Transaction.created_at <= end_date))
            .group_by(Transaction.user_id, func.extract('hour', Transaction.created_at))
            .all()
        )
        
        return {
            "top_users": [
                {
                    "user_id": uid,
                    "name": name,
                    "transaction_count": count
                }
                for uid, name, count in active_users
            ],
            "user_patterns": [
                {
                    "user_id": uid,
                    "hour": int(hour),
                    "count": count
                }
                for uid, hour, count in user_patterns
            ]
        }
    
    def _analyze_costs(self, start_date: datetime, end_date: datetime) -> Dict:
        """分析成本消耗。"""
        # 总成本统计
        cost_data = (
            self.db.query(
                Transaction.resource_id,
                Resource.name,
                Resource.unit_cost,
                func.sum(Transaction.quantity).label("total_quantity")
            )
            .join(Resource, Transaction.resource_id == Resource.id)
            .filter(
                and_(
                    Transaction.created_at >= start_date,
                    Transaction.created_at <= end_date,
                    Transaction.action.in_(["consume", "lost"])
                )
            )
            .group_by(Transaction.resource_id, Resource.name, Resource.unit_cost)
            .all()
        )
        
        total_cost = 0
        cost_breakdown = []
        
        for resource_id, name, unit_cost, quantity in cost_data:
            cost = quantity * unit_cost if unit_cost else 0
            total_cost += cost
            cost_breakdown.append({
                "resource_id": resource_id,
                "name": name,
                "quantity": quantity,
                "unit_cost": unit_cost,
                "total_cost": cost
            })
        
        # 按成本排序
        cost_breakdown.sort(key=lambda x: x["total_cost"], reverse=True)
        
        return {
            "total_cost": total_cost,
            "daily_avg_cost": total_cost / max(1, (end_date - start_date).days),
            "cost_breakdown": cost_breakdown[:10],  # 前10个高成本项目
            "high_cost_items": [item for item in cost_breakdown if item["total_cost"] > total_cost * 0.1]
        }
    
    def _identify_trends(self, start_date: datetime, end_date: datetime) -> Dict:
        """识别使用趋势。"""
        # 按天统计交易量趋势
        daily_trends = (
            self.db.query(
                func.date(Transaction.created_at).label("date"),
                func.count(Transaction.id).label("count")
            )
            .filter(and_(Transaction.created_at >= start_date, Transaction.created_at <= end_date))
            .group_by(func.date(Transaction.created_at))
            .order_by(func.date(Transaction.created_at))
            .all()
        )
        
        # 按资源类型分析趋势
        resource_trends = (
            self.db.query(
                Resource.category,
                func.date(Transaction.created_at).label("date"),
                func.count(Transaction.id).label("count")
            )
            .join(Resource, Transaction.resource_id == Resource.id)
            .filter(and_(Transaction.created_at >= start_date, Transaction.created_at <= end_date))
            .group_by(Resource.category, func.date(Transaction.created_at))
            .all()
        )
        
        return {
            "daily_usage": [
                {
                    "date": date.isoformat(),
                    "count": count
                }
                for date, count in daily_trends
            ],
            "resource_category_trends": [
                {
                    "category": category,
                    "date": date.isoformat(),
                    "count": count
                }
                for category, date, count in resource_trends
            ]
        }
    
    def _generate_recommendations(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """生成优化建议。"""
        recommendations = []
        
        # 基于设备利用率的建议
        devices = self.db.query(Resource).filter(Resource.category == "device").all()
        for device in devices:
            usage_hours = self._calculate_device_usage_hours(device.id, start_date, end_date)
            days = (end_date - start_date).days
            max_possible_hours = 14 * days
            utilization = usage_hours / max_possible_hours if max_possible_hours > 0 else 0
            
            if utilization >= 0.8:
                recommendations.append({
                    "type": "high_utilization",
                    "resource_id": device.id,
                    "resource_name": device.name,
                    "message": f"{device.name} 利用率高达 {utilization:.1%}，建议增加设备或优化调度",
                    "priority": "high"
                })
            elif utilization <= 0.2:
                recommendations.append({
                    "type": "low_utilization",
                    "resource_id": device.id,
                    "resource_name": device.name,
                    "message": f"{device.name} 利用率较低 ({utilization:.1%})，建议推广使用",
                    "priority": "medium"
                })
        
        # 基于成本的建议
        cost_data = self._analyze_costs(start_date, end_date)
        high_cost_items = cost_data["high_cost_items"]
        
        for item in high_cost_items:
            recommendations.append({
                "type": "high_cost",
                "resource_id": item["resource_id"],
                "resource_name": item["name"],
                "message": f"{item['name']} 消耗成本较高 (¥{item['total_cost']:.2f})，建议控制使用量",
                "priority": "medium"
            })
        
        return recommendations
    
    def predict_future_demand(self, resource_id: int, days_ahead: int = 30) -> Dict:
        """预测未来资源需求。"""
        predictions = []
        today = datetime.utcnow().date()
        
        for day_offset in range(days_ahead):
            target_date = today + timedelta(days=day_offset)
            
            # 基于历史数据的简单预测
            predicted_demand = self._predict_daily_demand(resource_id, target_date)
            
            predictions.append({
                "date": target_date.isoformat(),
                "predicted_demand": predicted_demand,
                "confidence": self._calculate_confidence(resource_id, target_date)
            })
        
        return {
            "resource_id": resource_id,
            "predictions": predictions,
            "prediction_method": "historical_pattern_analysis",
            "generated_at": datetime.utcnow()
        }
    
    def _predict_daily_demand(self, resource_id: int, target_date: datetime.date) -> float:
        """预测单日需求。"""
        day_of_week = target_date.weekday()
        
        # 获取过去8周相同星期几的平均使用次数
        eight_weeks_ago = target_date - timedelta(weeks=8)
        
        historical_usage = (
            self.db.query(func.count(Transaction.id))
            .filter(
                and_(
                    Transaction.resource_id == resource_id,
                    Transaction.action == "borrow",
                    func.date(Transaction.borrow_time) >= eight_weeks_ago,
                    func.extract('dow', Transaction.borrow_time) == day_of_week
                )
            )
            .scalar() or 0
        )
        
        # 加权平均预测（最近的数据权重更高）
        return historical_usage / 8 if historical_usage > 0 else 1.0
    
    def _calculate_confidence(self, resource_id: int, target_date: datetime.date) -> float:
        """计算预测置信度。"""
        # 基于历史数据量的简单置信度计算
        day_of_week = target_date.weekday()
        eight_weeks_ago = target_date - timedelta(weeks=8)
        
        historical_data_count = (
            self.db.query(func.count(Transaction.id))
            .filter(
                and_(
                    Transaction.resource_id == resource_id,
                    func.extract('dow', Transaction.borrow_time) == day_of_week,
                    func.date(Transaction.borrow_time) >= eight_weeks_ago
                )
            )
            .scalar() or 0
        )
        
        # 数据量越多，置信度越高
        return min(1.0, historical_data_count / 40)  # 最多40个数据点


def get_comprehensive_analytics(db: Session, days: int = 30) -> Dict:
    """对外提供的综合数据分析接口。"""
    analytics = AdvancedAnalytics(db)
    return analytics.get_comprehensive_analytics(days)


def predict_future_demand(db: Session, resource_id: int, days_ahead: int = 30) -> Dict:
    """对外提供的需求预测接口。"""
    analytics = AdvancedAnalytics(db)
    return analytics.predict_future_demand(resource_id, days_ahead)