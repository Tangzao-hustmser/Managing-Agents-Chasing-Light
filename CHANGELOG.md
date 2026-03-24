# 项目更新说明（2026年3月24日）

## 📌 本次更新概览

在原有项目基础上，完整实现了以下四大功能模块：

1. **✅ 用户认证与权限系统**
2. **✅ 时间维度 + 时段冲突检测**
3. **✅ 高风险操作审批流程**
4. **✅ 增强的智能体意图识别**

---

## 🆕 新增 API 接口（25+ 端点）

### 认证模块 (`/auth`)
```
POST   /auth/register              注册新用户
POST   /auth/login                 用户登录
GET    /auth/me                    获取当前用户信息
```

### 审批流程模块 (`/approvals`)
```
GET    /approvals                  查询审批列表
GET    /approvals/{id}             获取审批详情
POST   /approvals/{id}/approve     批准/拒绝审批
GET    /approvals/stats/summary    审批统计
```

### 增强的事务模块 (`/transactions`)
```
POST   /transactions               创建交易（含时段检测）
GET    /transactions               查询交易（含权限过滤）
GET    /transactions/{id}          获取交易详情
PATCH  /transactions/{id}/return   归还资源
```

### 增强的资源模块 (`/resources`)
```
POST   /resources                  创建资源（含认证）
GET    /resources                  查询资源
GET    /resources/{id}             获取资源详情
PATCH  /resources/{id}             更新资源（含认证）
```

---

## 📊 新增数据表

### User 表（用户）
- id, username (unique), password, real_name, student_id
- email, role (student/admin/teacher), is_active
- created_at, updated_at

### ApprovalTask 表（审批任务）
- id, transaction_id (FK), requester_id (FK), approver_id (FK)
- status (pending/approved/rejected), reason, created_at, approved_at

### Transaction 扩展字段
```
新增时间维度：
  - borrow_time (借用开始时间)
  - return_time (实际归还时间)
  - expected_return_time (预期归还时间)
  - duration_minutes (借用时长)

新增交易细节：
  - user_id (操作用户，从 user_name 升级)
  - purpose (使用目的)
  - condition_return (归还状态：完好/损坏/部分丢失)
  - approval_id (关联审批任务)
  - is_approved (是否已批准)
```

---

## 🧠 增强的智能体意图（10 个）

| # | 意图 ID | 触发关键词 | 功能 |
|---|---------|----------|------|
| 1 | `cost_analysis` | 成本、费用、消耗 | 💰 成本分析 + 排行 |
| 2 | `time_series_analysis` | 趋势、走势、增长 | 📈 7天趋势 |
| 3 | `user_behavior` | 谁借、排行、高频 | 👥 用户排行 |
| 4 | `approval_status` | 审批、待审、批准 | 📋 审批统计 |
| 5 | `recommendation` | 建议、如何、优化 | 💡 智能建议 |
| 6 | `inventory_status` | 库存、缺货 | 📦 库存查询 |
| 7 | `utilization_status` | 占用、利用率 | 📊 占用率 |
| 8 | `alert_status` | 预警、风险 | ⚠️ 预警查询 |
| 9 | `transaction_status` | 谁借、流水 | 📝 流水统计 |
| 10 | `general_help` | 其他 | ❓ 帮助 |

---

## 🔐 认证机制

### 认证流程
```
1. 用户调用 POST /auth/login
2. 服务返回 Bearer token (格式: "Bearer {user_id}")
3. 后续请求在 Authorization header 中传递 token
4. 服务端验证并提取用户身份
5. 根据角色检查权限
```

### 权限模型
- **管理员** (admin)：创建资源、批准审批、查看全部流水
- **学生** (student)：借用设备、消耗耗材、查看自己的流水
- **教师** (teacher)：查看权限（可选）

---

## ⏰ 时段检测机制

### 适用场景
- 仅对 `category='device'` 的资源有效
- 仅在 `action='borrow'` 时触发
- 检查 `[borrow_time, expected_return_time]` 与现有借用的重叠

### 冲突判定逻辑
```
两个时段 [S1, E1] 和 [S2, E2] 重叠判定：
if max(S1, S2) < min(E1, E2) → 冲突 ✗
else → 不冲突 ✓
```

### 示例
```
已有借用：14:00 - 16:00
新申请 1：15:00 - 17:00 → 冲突（14:00→16:00 与 15:00→17:00 重叠）
新申请 2：16:00 - 18:00 → 冲突（边界也算重叠）
新申请 3：16:01 - 18:00 → 不冲突 ✓
```

---

## ✅ 审批流程

### 自动触发条件
- ✅ `action='consume'` 且 `quantity >= 10`
- ✅ `action='lost'`（丢失登记）
- ✅ `action='replenish'`（补货）

### 审批流转
```
创建交易 → 检查是否需要审批 → 是 → 创建 ApprovalTask (status=pending)
                          ↓
        管理员批准 → update ApprovalTask (status=approved) + is_approved=True
        ↓
    库存才会真实扣减（之前仅预扣）
```

### API 交互
```
POST /transactions          创建（会自动创建审批任务）
GET  /approvals             查看待审项
POST /approvals/{id}/approve 批准或拒绝
```

---

## 📝 新增演示数据

### 预置用户
```
管理员：admin / admin123
学生 1：student1 / 123456
学生 2：student2 / 123456
教师：teacher1 / 123456
```

### 预置资源
- 3D打印机 x 4 台 (¥1999 each)
- 激光切割机 x 2 台 (¥25000 each)
- Arduino 开发板 x 30 块 (¥89 each)
- 万用表 x 20 台 (¥599 each)
- 220Ω 电阻 x 500 个 (¥0.05 each)

---

## 🔄 迁移说明

### 数据库升级
由于修改了 Transaction 模型和新增了两张表，需要重新初始化：

```bash
# 备份旧数据（可选）
cp smart_lab.db smart_lab.db.backup

# 删除旧数据库
rm smart_lab.db

# 重新初始化（会创建新表和演示数据）
python -m app.seed

# 启动服务
python -m uvicorn app.main:app --reload
```

### 向后兼容性
- 旧的流水查询仍然可用（Transaction 向后兼容）
- 旧的 API 接口（/resources, /transactions, /alerts 等）仍然有效
- 新增的字段都有默认值，不会破坏现有逻辑

---

## 📁 文件变动清单

### 新增文件（5 个）
```
app/services/auth_service.py         用户认证和权限检查
app/services/time_slot_service.py    时段冲突检测逻辑
app/services/approval_service.py     审批流程管理
app/routers/auth.py                  认证路由（注册/登录）
app/routers/approvals.py             审批路由
```

### 修改文件（7 个）
```
app/models.py
  - 新增 User 类
  - 新增 ApprovalTask 类
  - 修改 Transaction 类（加字段和关系）

app/schemas.py
  - 新增 UserCreate, UserLogin, UserOut
  - 新增 ApprovalTaskOut, ApprovalTaskApprove
  - 修改 TransactionCreate, TransactionOut

app/services/agent_service.py
  - 新增 6 个意图识别函数
  - 增强问答覆盖范围

app/routers/transactions.py
  - 新增时段检测逻辑
  - 新增审批触发机制
  - 新增权限检查

app/routers/resources.py
  - 新增认证依赖
  - 新增权限检查

app/main.py
  - 新增路由注册（auth, approvals）

app/seed.py
  - 新增演示用户和成本数据
```

### 新增文档（3 个）
```
QUICKSTART.md               快速开始指南
CHANGELOG.md                本变更说明
test_features.py            自动化测试脚本
```

---

## 🧪 测试方式

### 自动化测试
```bash
python test_features.py
```

会自动测试：
- ✅ 用户注册、登录
- ✅ 时段冲突检测
- ✅ 审批流程（创建、批准）
- ✅ 10 个智能体意图

### 手动测试（curl）
详见 QUICKSTART.md 中的 API 示例

### 浏览器 UI 测试
```
1. http://localhost:8000/docs (Swagger 自动生成)
2. http://localhost:8000/dashboard (现有管理面板)
```

---

## ⚙️ 配置说明

无需额外配置，原有的 `.env.example` 配置仍然有效。

新功能不依赖：
- 七牛云（可选）
- 大模型（可选）
- Redis（使用默认内存存储）

---

## 📊 性能考量

### 数据库索引
- User: username (unique), role, is_active
- Transaction: user_id, resource_id, created_at, action
- ApprovalTask: status, created_at
- Resource: available_count, category

### 查询优化
- 权限过滤在数据库层完成
- 时段检测使用范围查询（高效）
- 审批统计使用聚合函数

---

## 🚀 后续扩展方向

1. **密码安全**：使用 bcrypt 进行密码哈希（当前为演示用）
2. **JWT Token**：替换简化的 Bearer token 实现
3. **缓存层**：加入 Redis 缓存预警和用户信息
4. **消息推送**：集成企业微信/钉钉
5. **前端适配**：更新前端 JavaScript 以支持新 API
6. **日志审计**：记录所有关键操作
7. **性能优化**：查询分页、批量操作、连接池

---

## ❓ 常见问题

**Q: 旧数据会丢失吗？**
A: 是的。由于模型修改较大，需要重新初始化。如需保留数据，可在迁移脚本中添加转换逻辑。

**Q: 是否需要修改前端？**
A: 
- API 文档自动生成（Swagger），可直接测试
- 现有管理面板 `/dashboard` 继续可用
- 新功能（认证、审批、时段检测）可通过 Swagger 体验

**Q: 时段检测的时区如何处理？**
A: 统一使用 UTC（datetime.utcnow()）。如需本地时区，可在前端进行转换。

**Q: 审批拒绝后库存如何处理？**
A: 交易被拒绝但不删除（保留审计记录），库存不会扣减。is_approved 保持 False。

---

## 📞 技术支持

如有任何问题，请检查：
1. 是否执行了 `python -m app.seed` 初始化
2. 是否正确传递了 Authorization header
3. 查看 QUICKSTART.md 中的故障排除章节
4. 运行 `test_features.py` 进行诊断

---

## 版本信息

- **项目名**：创新实践基地共享设备和物料管理智能体
- **更新日期**：2026年3月24日
- **版本号**：v2.0.0
- **状态**：✅ 完全可用

---

**更新完成！祝答辩顺利！** 🎉

