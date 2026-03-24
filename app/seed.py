"""初始化演示数据脚本。"""

from app.database import Base, SessionLocal, engine
from app.models import Resource, User


def seed() -> None:
    """向数据库插入比赛演示所需的基础资源和用户。"""
    # 先确保表结构存在，避免首次运行时报 no such table。
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 检查是否已有数据
        count = db.query(Resource).count()
        if count > 0:
            print("已有数据，跳过初始化。")
            return

        # 创建演示用户
        demo_users = [
            User(username="admin", password="admin123", real_name="管理员", student_id="A001", email="admin@school.edu", role="admin", is_active=True),
            User(username="student1", password="123456", real_name="学生张三", student_id="S001", email="zhangsan@school.edu", role="student", is_active=True),
            User(username="student2", password="123456", real_name="学生李四", student_id="S002", email="lisi@school.edu", role="student", is_active=True),
            User(username="teacher1", password="123456", real_name="导师王老师", student_id="T001", email="wang@school.edu", role="teacher", is_active=True),
        ]
        db.add_all(demo_users)

        # 创建演示资源
        demo_resources = [
            Resource(name="创想三维 Ender-3", category="device", subtype="3D打印机", total_count=4, available_count=2, min_threshold=1, unit_cost=1999),
            Resource(name="大族激光切割机 A1", category="device", subtype="激光切割机", total_count=2, available_count=1, min_threshold=1, unit_cost=25000),
            Resource(name="Arduino UNO R3", category="material", subtype="开发板", total_count=30, available_count=12, min_threshold=10, unit_cost=89),
            Resource(name="数字万用表 UT61E", category="device", subtype="万用表", total_count=20, available_count=8, min_threshold=5, unit_cost=599),
            Resource(name="220 欧姆电阻", category="material", subtype="电子元器件", total_count=500, available_count=120, min_threshold=80, unit_cost=0.05),
        ]
        db.add_all(demo_resources)
        db.commit()
        print("演示数据初始化完成。")
        print("默认用户：")
        print("  - 管理员：admin / admin123")
        print("  - 学生1：student1 / 123456")
        print("  - 学生2：student2 / 123456")
        print("  - 导师：teacher1 / 123456")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
