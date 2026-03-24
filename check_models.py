"""快速诊断脚本：检查模型是否可以正确加载。"""

import sys
import traceback

print("正在测试模型加载...")

try:
    print("1. 导入 models 模块...")
    from app.models import Base, User, Resource, Transaction, Alert, ApprovalTask, ChatMessage
    print("   ✓ 成功导入所有模型")
    
    print("\n2. 检查模型映射...")
    print(f"   ✓ Resource: {Resource.__tablename__}")
    print(f"   ✓ User: {User.__tablename__}")
    print(f"   ✓ Transaction: {Transaction.__tablename__}")
    print(f"   ✓ ApprovalTask: {ApprovalTask.__tablename__}")
    print(f"   ✓ Alert: {Alert.__tablename__}")
    print(f"   ✓ ChatMessage: {ChatMessage.__tablename__}")
    
    print("\n3. 初始化数据库引擎...")
    from app.database import engine, Base as DBBase
    DBBase.metadata.create_all(bind=engine)
    print("   ✓ 数据库引擎初始化成功")
    
    print("\n✅ 所有模型加载成功！可以运行 python -m app.seed 了")
    sys.exit(0)
    
except Exception as e:
    print(f"\n❌ 错误: {str(e)}")
    traceback.print_exc()
    sys.exit(1)
