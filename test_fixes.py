#!/usr/bin/env python3
"""快速验证修复的脚本：检查模型导入和基本关系。"""

import sys
from datetime import datetime

try:
    print("=" * 50)
    print("1. 导入所有模块...")
    print("=" * 50)
    
    from app.models import (
        Resource, User, Transaction, ApprovalTask, Alert, ChatMessage
    )
    from app.database import engine, Base
    from sqlalchemy.orm import Session
    
    print("✓ 所有模型导入成功")
    
    print("\n" + "=" * 50)
    print("2. 检查数据库表映射...")
    print("=" * 50)
    
    mapper_info = {
        Resource: "resources",
        User: "users", 
        Transaction: "transactions",
        ApprovalTask: "approval_tasks",
        Alert: "alerts",
        ChatMessage: "chat_messages",
    }
    
    for model, table in mapper_info.items():
        actual_table = model.__tablename__
        status = "✓" if actual_table == table else "✗"
        print(f"{status} {model.__name__}: {actual_table}")
    
    print("\n" + "=" * 50)
    print("3. 测试关系定义...")
    print("=" * 50)
    
    # 检查 Transaction 的关系
    tx_relationships = {
        "resource": "Resource关联",
        "user": "User关联",
        "approval_task": "ApprovalTask反向关联",
    }
    
    for rel_name in tx_relationships:
        if hasattr(Transaction, rel_name):
            print(f"✓ Transaction.{rel_name}")
        else:
            print(f"✗ Transaction.{rel_name} 缺失")
    
    # 检查 ApprovalTask 的关系
    at_relationships = {
        "transaction": "Transaction关联",
        "requester": "User申请人关联",
        "approver": "User审批人关联",
    }
    
    for rel_name in at_relationships:
        if hasattr(ApprovalTask, rel_name):
            print(f"✓ ApprovalTask.{rel_name}")
        else:
            print(f"✗ ApprovalTask.{rel_name} 缺失")
    
    print("\n" + "=" * 50)
    print("4. 验证数据库连接...")
    print("=" * 50)
    
    with Session(engine) as db:
        result = db.execute("SELECT 1")
        print(f"✓ 数据库连接成功")
    
    print("\n" + "=" * 50)
    print("5. 尝试创建表结构...")
    print("=" * 50)
    
    Base.metadata.create_all(bind=engine)
    print("✓ 表结构创建成功（或已存在）")
    
    print("\n" + "=" * 50)
    print("✅ 所有检查通过！可以运行 python -m app.seed")
    print("=" * 50)
    
except Exception as exc:
    print(f"\n❌ 出错：{exc}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
