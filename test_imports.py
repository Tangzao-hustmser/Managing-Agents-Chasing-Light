"""快速测试脚本：检查所有模块是否可以正确导入。"""

import sys
import traceback

def test_imports():
    """测试所有关键模块的导入。"""
    modules = [
        "app.models",
        "app.schemas",
        "app.services.auth_service",
        "app.services.time_slot_service",
        "app.services.approval_service",
        "app.services.agent_service",
        "app.routers.auth",
        "app.routers.approvals",
        "app.routers.resources",
        "app.routers.transactions",
        "app.main",
    ]
    
    failed = []
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except Exception as e:
            print(f"✗ {module}: {str(e)}")
            traceback.print_exc()
            failed.append(module)
    
    if failed:
        print(f"\n❌ 导入失败: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("\n✅ 所有模块导入成功！")

if __name__ == "__main__":
    test_imports()
