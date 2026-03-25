"""智能调度算法服务：优化设备使用时段和资源分配。"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Resource, Transaction


class SmartScheduler:
    """智能调度器：基于历史数据和预测算法优化资源分配。"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_optimal_time_slots(self, resource_id: int, duration_minutes: int, 
                             preferred_start: Optional[datetime] = None) -> List[Dict]:
        """
        获取最优使用时段推荐。
        
        Args:
            resource_id: 资源ID
            duration_minutes: 需要使用的时长（分钟）
            preferred_start: 偏好开始时间（可选）
            
        Returns:
            推荐时段列表，包含评分和冲突信息
        """
        resource = self.db.query(Resource).filter(Resource.id == resource_id).first()
        if not resource or resource.category != "device":
            return []
        
        # 获取未来7天的时段占用情况
        base_time = preferred_start or datetime.utcnow()
        time_slots = self._generate_time_slots(base_time, duration_minutes)
        
        # 为每个时段评分
        scored_slots = []
        for slot in time_slots:
            score = self._score_time_slot(resource_id, slot["start"], slot["end"])
            slot["score"] = score
            slot["conflicts"] = self._check_conflicts(resource_id, slot["start"], slot["end"])
            scored_slots.append(slot)
        
        # 按评分排序，返回前5个推荐
        scored_slots.sort(key=lambda x: x["score"], reverse=True)
        return scored_slots[:5]
    
    def _generate_time_slots(self, base_time: datetime, duration_minutes: int) -> List[Dict]:
        """生成候选时段。"""
        slots = []
        
        # 生成未来7天的时段，每2小时一个候选
        for day_offset in range(7):
            day_start = base_time.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
            
            # 生成当天的工作时段（8:00-22:00）
            for hour in range(8, 22, 2):
                if hour + duration_minutes // 60 > 22:
                    continue
                    
                start_time = day_start + timedelta(hours=hour)
                end_time = start_time + timedelta(minutes=duration_minutes)
                
                slots.append({
                    "start": start_time,
                    "end": end_time,
                    "day": day_start.date(),
                    "hour": hour
                })
        
        return slots
    
    def _score_time_slot(self, resource_id: int, start_time: datetime, end_time: datetime) -> float:
        """为时段评分（0-100分）。"""
        score = 100.0
        
        # 1. 冲突检测（权重最高）
        conflicts = self._check_conflicts(resource_id, start_time, end_time)
        if conflicts:
            score -= 50  # 严重扣分
        
        # 2. 历史使用模式（基于相似时段的占用率）
        historical_score = self._calculate_historical_score(resource_id, start_time, end_time)
        score += historical_score * 0.3  # 权重30%
        
        # 3. 时间偏好（工作日 vs 周末，上午 vs 下午）
        time_preference_score = self._calculate_time_preference_score(start_time)
        score += time_preference_score * 0.2  # 权重20%
        
        # 4. 紧急程度（距离当前时间越近，分数越高）
        urgency_score = self._calculate_urgency_score(start_time)
        score += urgency_score * 0.1  # 权重10%
        
        return max(0, min(100, score))
    
    def _check_conflicts(self, resource_id: int, start_time: datetime, end_time: datetime) -> List[Dict]:
        """检查时段冲突。"""
        conflicts = []
        
        overlapping_txs = (
            self.db.query(Transaction)
            .filter(
                and_(
                    Transaction.resource_id == resource_id,
                    Transaction.action == "borrow",
                    Transaction.borrow_time < end_time,
                    Transaction.expected_return_time > start_time
                )
            )
            .all()
        )
        
        for tx in overlapping_txs:
            conflicts.append({
                "transaction_id": tx.id,
                "user_id": tx.user_id,
                "borrow_time": tx.borrow_time,
                "expected_return_time": tx.expected_return_time
            })
        
        return conflicts
    
    def _calculate_historical_score(self, resource_id: int, start_time: datetime, end_time: datetime) -> float:
        """基于历史使用模式评分。"""
        # 获取相似时段的历史占用率
        day_of_week = start_time.weekday()
        hour = start_time.hour
        
        # 查询过去4周相同星期几、相同时段的使用情况
        four_weeks_ago = start_time - timedelta(weeks=4)
        
        similar_txs = (
            self.db.query(Transaction)
            .filter(
                and_(
                    Transaction.resource_id == resource_id,
                    Transaction.action == "borrow",
                    Transaction.borrow_time >= four_weeks_ago,
                    func.extract('dow', Transaction.borrow_time) == day_of_week,
                    func.extract('hour', Transaction.borrow_time) == hour
                )
            )
            .all()
        )
        
        if not similar_txs:
            return 80.0  # 无历史数据，默认中等分数
        
        # 计算平均占用率（越低越好）
        total_slots = len(similar_txs) * 4  # 假设每周4个相似时段
        occupied_slots = len(similar_txs)
        occupancy_rate = occupied_slots / total_slots if total_slots > 0 else 0
        
        # 占用率越低，分数越高
        return 100 * (1 - occupancy_rate)
    
    def _calculate_time_preference_score(self, start_time: datetime) -> float:
        """基于时间偏好的评分。"""
        # 工作日（0-4）比周末（5-6）分数高
        day_score = 90 if start_time.weekday() < 5 else 70
        
        # 上午（8-12）和下午（14-18）分数较高
        hour = start_time.hour
        if 8 <= hour < 12 or 14 <= hour < 18:
            hour_score = 90
        else:
            hour_score = 70
        
        return (day_score + hour_score) / 2
    
    def _calculate_urgency_score(self, start_time: datetime) -> float:
        """基于紧急程度的评分。"""
        now = datetime.utcnow()
        time_diff = (start_time - now).total_seconds() / 3600  # 小时数
        
        # 距离现在越近，分数越高（最多24小时内）
        if time_diff <= 24:
            return 100 * (1 - time_diff / 24)
        else:
            return 0
    
    def predict_resource_demand(self, resource_id: int, days_ahead: int = 7) -> List[Dict]:
        """预测未来资源需求。"""
        predictions = []
        today = datetime.utcnow().date()
        
        for day_offset in range(days_ahead):
            target_date = today + timedelta(days=day_offset)
            
            # 基于历史数据预测
            predicted_demand = self._predict_daily_demand(resource_id, target_date)
            
            predictions.append({
                "date": target_date,
                "predicted_demand": predicted_demand,
                "confidence": 0.8,  # 置信度
                "recommendation": self._generate_recommendation(predicted_demand)
            })
        
        return predictions
    
    def _predict_daily_demand(self, resource_id: int, target_date: datetime.date) -> float:
        """预测单日需求。"""
        day_of_week = target_date.weekday()
        
        # 获取过去4周相同星期几的平均使用次数
        four_weeks_ago = target_date - timedelta(weeks=4)
        
        historical_usage = (
            self.db.query(func.count(Transaction.id))
            .filter(
                and_(
                    Transaction.resource_id == resource_id,
                    Transaction.action == "borrow",
                    func.date(Transaction.borrow_time) >= four_weeks_ago,
                    func.extract('dow', Transaction.borrow_time) == day_of_week
                )
            )
            .scalar() or 0
        )
        
        # 简单平均预测
        return historical_usage / 4 if historical_usage > 0 else 1.0
    
    def _generate_recommendation(self, predicted_demand: float) -> str:
        """根据预测需求生成建议。"""
        if predicted_demand >= 5:
            return "高需求日，建议增加设备或延长开放时间"
        elif predicted_demand >= 3:
            return "中等需求，正常安排即可"
        else:
            return "低需求日，可考虑维护或培训"
    
    def optimize_resource_allocation(self) -> Dict:
        """优化资源分配策略。"""
        recommendations = []
        
        # 分析所有设备资源
        devices = self.db.query(Resource).filter(Resource.category == "device").all()
        
        for device in devices:
            # 计算设备利用率
            utilization = self._calculate_device_utilization(device.id)
            
            # 生成优化建议
            if utilization >= 0.9:
                recommendations.append({
                    "resource_id": device.id,
                    "resource_name": device.name,
                    "utilization": utilization,
                    "recommendation": "高利用率，建议增加设备数量或优化调度",
                    "priority": "high"
                })
            elif utilization <= 0.3:
                recommendations.append({
                    "resource_id": device.id,
                    "resource_name": device.name,
                    "utilization": utilization,
                    "recommendation": "低利用率，建议推广使用或调整开放时间",
                    "priority": "medium"
                })
        
        return {
            "total_devices": len(devices),
            "recommendations": recommendations,
            "generated_at": datetime.utcnow()
        }
    
    def _calculate_device_utilization(self, resource_id: int) -> float:
        """计算设备利用率。"""
        # 获取过去30天的使用记录
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        usage_records = (
            self.db.query(Transaction)
            .filter(
                and_(
                    Transaction.resource_id == resource_id,
                    Transaction.action == "borrow",
                    Transaction.borrow_time >= thirty_days_ago
                )
            )
            .all()
        )
        
        if not usage_records:
            return 0.0
        
        # 计算总使用时长（小时）
        total_hours = 0
        for record in usage_records:
            if record.borrow_time and record.expected_return_time:
                duration = (record.expected_return_time - record.borrow_time).total_seconds() / 3600
                total_hours += duration
        
        # 假设设备每天工作14小时（8:00-22:00）
        max_possible_hours = 14 * 30
        
        return min(1.0, total_hours / max_possible_hours)


def get_optimal_time_slots(db: Session, resource_id: int, duration_minutes: int, 
                          preferred_start: Optional[datetime] = None) -> List[Dict]:
    """对外提供的智能调度接口。"""
    scheduler = SmartScheduler(db)
    return scheduler.get_optimal_time_slots(resource_id, duration_minutes, preferred_start)


def predict_resource_demand(db: Session, resource_id: int, days_ahead: int = 7) -> List[Dict]:
    """对外提供的需求预测接口。"""
    scheduler = SmartScheduler(db)
    return scheduler.predict_resource_demand(resource_id, days_ahead)


def optimize_resource_allocation(db: Session) -> Dict:
    """对外提供的资源优化接口。"""
    scheduler = SmartScheduler(db)
    return scheduler.optimize_resource_allocation()