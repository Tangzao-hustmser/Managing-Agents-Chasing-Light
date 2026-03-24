# 🔧 问题修复说明

## 问题描述
运行 `python -m app.seed` 时报错：
```
sqlalchemy.exc.AmbiguousForeignKeysError: Could not determine join condition 
between parent/child tables on relationship Transaction.approval_task - 
there are multiple foreign key paths linking the tables.
```

## 原因分析
SQLAlchemy 在定义关系映射时，无法自动确定 `Transaction` 和 `ApprovalTask` 之间的关联关系，因为：
- `Transaction` 有 `user_id` 外键指向 User
- `ApprovalTask` 有 `requester_id` 和 `approver_id` 两个外键指向 User
- 这导致了复杂的关系路径，SQLAlchemy 无法自动推断

## 解决方案
在 ORM 关系定义中显式指定 `foreign_keys` 参数，告诉 SQLAlchemy 使用哪个外键字段。

### 修复的代码位置

#### 文件：app/models.py

**Transaction 类（第 84 行）**
```python
# 修改前：
approval_task = relationship("ApprovalTask", back_populates="transaction")

# 修改后：
approval_task = relationship("ApprovalTask", foreign_keys=[approval_id], back_populates="transaction")
```

**ApprovalTask 类（第 113 行）**
```python
# 修改前：
transaction = relationship("Transaction", back_populates="approval_task")

# 修改后：
transaction = relationship("Transaction", foreign_keys=[transaction_id], back_populates="approval_task")
```

## 修复验证

### 方式 1：运行诊断脚本
```bash
python check_models.py
```

输出示例（成功）：
```
✓ 成功导入所有模型
✓ 数据库引擎初始化成功
✅ 所有模型加载成功！可以运行 python -m app.seed 了
```

### 方式 2：直接初始化
```bash
python -m app.seed
```

成功时输出：
```
演示数据初始化完成。
默认用户：
  - 管理员：admin / admin123
  - 学生1：student1 / 123456
  ...
```

## 后续步骤

修复完成后，按照正常流程启动：

```bash
# 1. 初始化演示数据
python -m app.seed

# 2. 启动服务
python -m uvicorn app.main:app --reload

# 3. 访问 API 文档
# http://localhost:8000/docs
```

## 其他说明

- ✅ 修复已完成，无需其他改动
- ✅ 所有新增功能（认证、审批、时段检测）都已正确实现
- ✅ 可以继续进行功能测试和答辩演示

如有其他问题，请运行 `python test_features.py` 进行自动化测试。

