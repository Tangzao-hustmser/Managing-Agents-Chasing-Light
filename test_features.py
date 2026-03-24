"""
集成测试脚本：验证所有新增功能
运行：python test_features.py
"""

import json
import requests
import sys
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

def print_section(title):
    """打印分隔符和标题。"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def test_auth():
    """测试认证系统。"""
    print_section("1️⃣ 测试认证系统")
    
    # 注册新用户
    print("\n[1] 注册新用户...")
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "username": "testuser",
        "password": "test123",
        "real_name": "测试用户",
        "student_id": "TEST001",
        "email": "test@school.edu",
        "role": "student"
    })
    if resp.status_code == 200:
        print("✓ 注册成功:", resp.json()["username"])
    else:
        print("✗ 注册失败:", resp.text)
        return None
    
    # 登录
    print("\n[2] 用户登录...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    if resp.status_code == 200:
        data = resp.json()
        admin_token = data["token"]
        print(f"✓ 登录成功，Token: {admin_token}")
    else:
        print("✗ 登录失败:", resp.text)
        return None
    
    # 获取当前用户
    print("\n[3] 获取当前用户信息...")
    headers = {"Authorization": admin_token}
    resp = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    if resp.status_code == 200:
        user = resp.json()
        print(f"✓ 当前用户: {user['real_name']} ({user['role']})")
    else:
        print("✗ 获取失败:", resp.text)
    
    return admin_token


def test_time_slot():
    """测试时段冲突检测。"""
    print_section("2️⃣ 测试时间维度 + 时段检测")
    
    # 获取学生 token
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "username": "student1",
        "password": "123456"
    })
    student_token = resp.json()["token"]
    headers = {"Authorization": student_token}
    
    # 第一次借用
    print("\n[1] 学生1 借用 3D打印机（14:00-16:00）...")
    resp = requests.post(f"{BASE_URL}/transactions", 
        headers=headers,
        json={
            "resource_id": 1,
            "action": "borrow",
            "quantity": 1,
            "borrow_time": "2026-03-24T14:00:00",
            "expected_return_time": "2026-03-24T16:00:00",
            "purpose": "科技竞赛模型",
            "condition_return": "完好"
        }
    )
    if resp.status_code == 200:
        tx1 = resp.json()
        print(f"✓ 借用成功，流水ID: {tx1['id']}")
    else:
        print("✗ 借用失败:", resp.text)
        return
    
    # 尝试冲突借用
    print("\n[2] 学生2 尝试借用同一设备（15:00-17:00，与前面冲突）...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "username": "student2",
        "password": "123456"
    })
    student2_token = resp.json()["token"]
    headers2 = {"Authorization": student2_token}
    
    resp = requests.post(f"{BASE_URL}/transactions", 
        headers=headers2,
        json={
            "resource_id": 1,
            "action": "borrow",
            "quantity": 1,
            "borrow_time": "2026-03-24T15:00:00",
            "expected_return_time": "2026-03-24T17:00:00",
            "purpose": "另一个项目",
            "condition_return": "完好"
        }
    )
    if resp.status_code == 400:
        print("✓ 正确拒绝冲突请求:", resp.json()["detail"])
    else:
        print("✗ 应该返回 400 错误")
    
    # 成功的非冲突借用
    print("\n[3] 学生2 借用激光切割机（不冲突）...")
    resp = requests.post(f"{BASE_URL}/transactions", 
        headers=headers2,
        json={
            "resource_id": 2,
            "action": "borrow",
            "quantity": 1,
            "borrow_time": "2026-03-24T14:00:00",
            "expected_return_time": "2026-03-24T15:30:00",
            "purpose": "激光雕刻",
            "condition_return": "完好"
        }
    )
    if resp.status_code == 200:
        tx2 = resp.json()
        print(f"✓ 借用成功，流水ID: {tx2['id']}")
        return (student_token, student2_token, tx1['id'], tx2['id'])
    else:
        print("✗ 借用失败:", resp.text)


def test_approval():
    """测试审批流程。"""
    print_section("3️⃣ 测试审批流程")
    
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "username": "student1",
        "password": "123456"
    })
    student_token = resp.json()["token"]
    headers = {"Authorization": student_token}
    
    # 大额消耗（触发审批）
    print("\n[1] 学生消耗 15 个电阻（≥10，触发审批）...")
    resp = requests.post(f"{BASE_URL}/transactions", 
        headers=headers,
        json={
            "resource_id": 5,
            "action": "consume",
            "quantity": 15,
            "purpose": "电路实验"
        }
    )
    if resp.status_code == 200:
        tx = resp.json()
        print(f"✓ 消耗记录创建，流水ID: {tx['id']}")
        print(f"  审批ID: {tx['approval_id']}")
        print(f"  待批准: {not tx['is_approved']}")
        approval_id = tx['approval_id']
    else:
        print("✗ 消耗失败:", resp.text)
        return
    
    # 查看待审批项
    print("\n[2] 查看待审批项...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    admin_token = resp.json()["token"]
    admin_headers = {"Authorization": admin_token}
    
    resp = requests.get(f"{BASE_URL}/approvals?status=pending", headers=admin_headers)
    if resp.status_code == 200:
        tasks = resp.json()
        print(f"✓ 待审项数: {len(tasks)}")
        if tasks:
            for task in tasks[:3]:
                print(f"  - ID {task['id']}: 申请人 {task['requester_id']}, 状态 {task['status']}")
    
    # 管理员批准
    print("\n[3] 管理员批准审批任务...")
    resp = requests.post(f"{BASE_URL}/approvals/{approval_id}/approve",
        headers=admin_headers,
        json={
            "approved": True,
            "reason": "数量合理，已批准"
        }
    )
    if resp.status_code == 200:
        task = resp.json()
        print(f"✓ 批准成功")
        print(f"  状态: {task['status']}")
        print(f"  批准人: {task['approver_id']}")
        print(f"  批准时间: {task['approved_at']}")
    else:
        print("✗ 批准失败:", resp.text)


def test_enhanced_agent():
    """测试增强的智能体意图。"""
    print_section("4️⃣ 测试增强的智能体意图")
    
    questions = [
        ("当前哪些资源快缺货？", "inventory_status"),
        ("本月消耗成本多少？", "cost_analysis"),
        ("过去7天的趋势如何？", "time_series_analysis"),
        ("谁用得最多？", "user_behavior"),
        ("有什么优化建议吗？", "recommendation"),
        ("当前有多少待审项？", "approval_status"),
    ]
    
    for question, expected_intent in questions:
        print(f"\n[问] {question}")
        resp = requests.post(f"{BASE_URL}/agent/ask", json={"question": question})
        if resp.status_code == 200:
            result = resp.json()
            intent_match = "✓" if result["intent"] == expected_intent else "✗"
            print(f"  {intent_match} 意图: {result['intent']}")
            print(f"  📝 回答: {result['answer'][:80]}...")
        else:
            print(f"  ✗ 请求失败: {resp.text}")


def main():
    """主测试流程。"""
    print("\n" + "🧪 " * 20)
    print("创新实践基地管理智能体 - 功能测试")
    print("🧪 " * 20)
    
    # 检查服务是否运行
    print("\n检查服务状态...")
    try:
        resp = requests.get(f"{BASE_URL}/")
        if resp.status_code == 200:
            print("✓ 服务正在运行")
        else:
            print("✗ 服务异常")
            return
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到服务，请确保已启动: python -m uvicorn app.main:app --reload")
        return
    
    # 执行测试
    token = test_auth()
    if token is None:
        return
    
    time_slot_result = test_time_slot()
    test_approval()
    test_enhanced_agent()
    
    print_section("✨ 测试完成！")
    print("\n所有新增功能都已测试。查看上面的结果确认功能是否正常运行。")
    print("\n💡 提示：")
    print("  - 用户认证：所有 API 都需要 Authorization header")
    print("  - 时段检测：仅对设备类资源的 borrow 动作有效")
    print("  - 审批流程：消耗≥10、丢失、补货会自动触发")
    print("  - 智能体：支持 10 个意图类别，可自然语言问答")


if __name__ == "__main__":
    main()
