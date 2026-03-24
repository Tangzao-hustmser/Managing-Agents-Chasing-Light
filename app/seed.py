"""初始化演示数据脚本。"""

from app.database import Base, SessionLocal, engine
from app.models import Resource


def seed() -> None:
    """向数据库插入比赛演示所需的基础资源。"""
    # 先确保表结构存在，避免首次运行时报 no such table。
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        count = db.query(Resource).count()
        if count > 0:
            print("已有数据，跳过初始化。")
            return

        demo_resources = [
            Resource(name="创想三维 Ender-3", category="device", subtype="3D打印机", total_count=4, available_count=2, min_threshold=1),
            Resource(name="大族激光切割机 A1", category="device", subtype="激光切割机", total_count=2, available_count=1, min_threshold=1),
            Resource(name="Arduino UNO R3", category="material", subtype="开发板", total_count=30, available_count=12, min_threshold=10),
            Resource(name="数字万用表 UT61E", category="device", subtype="万用表", total_count=20, available_count=8, min_threshold=5),
            Resource(name="220 欧姆电阻", category="material", subtype="电子元器件", total_count=500, available_count=120, min_threshold=80),
        ]
        db.add_all(demo_resources)
        db.commit()
        print("演示数据初始化完成。")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
