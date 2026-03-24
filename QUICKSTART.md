# 🚀 快速开始指南（新增功能）

## ⚡ 30 秒快速启动

```bash
# 1. 初始化数据库和演示数据
python -m app.seed

# 2. 启动服务
python -m uvicorn app.main:app --reload

# 3. 访问 API 文档
# 浏览器打开：http://localhost:8000/docs
```

## 📝 演示用户（预置）

```
管理员：
  账号：admin
  密码：admin123
  角色：可创建资源、批准审批

学生：
  账号：student1 / student2
  密码：123456
  角色：借用设备、消耗耗材

教师：
  账号：teacher1
  密码：123456
  角色：查看权限（可选）
```

## 🎯 5 分钟完整演示流程

### Step 1：登录
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 保存返回的 token，例如：Bearer 1
```

### Step 2：借用设备（测试时段检测）
```bash
curl -X POST http://localhost:8000/transactions \
  -H "Authorization: Bearer 2" \
  -H "Content-Type: application/json" \
  -d '{
    "resource_id": 1,
    "action": "borrow",
    "quantity": 1,
    "borrow_time": "2026-03-24T14:00:00",
    "expected_return_time": "2026-03-24T16:00:00",
    "purpose": "科技竞赛"
  }'
```

### Step 3：大额消耗（测试审批流程）
```bash
curl -X POST http://localhost:8000/transactions \
  -H "Authorization: Bearer 2" \
  -H "Content-Type: application/json" \
  -d '{
    "resource_id": 5,
    "action": "consume",
    "quantity": 15,
    "purpose": "电路实验"
  }'
```

### Step 4：管理员批准
```bash
curl -X POST http://localhost:8000/approvals/1/approve \
  -H "Authorization: Bearer 1" \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "reason": "已批准"}'
```

### Step 5：智能体问答（测试新意图）
```bash
# 成本分析
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"本月消耗成本多少？"}'

# 用户排行
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"谁用得最多？"}'

# 管理建议
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"有什么优化建议吗？"}'
```

## 🧪 自动化测试

```bash
python test_features.py
```

这会自动测试：
- ✅ 用户注册、登录、获取信息
- ✅ 时段冲突检测
- ✅ 审批流程（创建、批准）
- ✅ 所有 10 个智能体意图

## 📊 关键 API 端点速查

| 功能 | 方法 | 端点 | 需认证 |
|------|------|------|--------|
| 注册 | POST | `/auth/register` | ❌ |
| 登录 | POST | `/auth/login` | ❌ |
| 当前用户 | GET | `/auth/me` | ✅ |
| 创建资源 | POST | `/resources` | ✅ 管理员 |
| 查看资源 | GET | `/resources` | ✅ |
| 借用/消耗 | POST | `/transactions` | ✅ |
| 查看流水 | GET | `/transactions` | ✅ |
| 归还资源 | PATCH | `/transactions/{id}/return` | ✅ |
| 待审批项 | GET | `/approvals?status=pending` | ✅ 管理员 |
| 批准审批 | POST | `/approvals/{id}/approve` | ✅ 管理员 |
| 审批统计 | GET | `/approvals/stats/summary` | ✅ |
| 智能体问答 | POST | `/agent/ask` | ❌ |
| 智能体对话 | POST | `/agent/chat` | ❌ |

## 🔑 认证方式

所有需要认证的 API 都需要在请求头中添加：

```
Authorization: Bearer {user_id}
```

例如：
```bash
curl -H "Authorization: Bearer 1" http://localhost:8000/approvals
```

## 💡 常见场景

### 场景 1：学生借用设备
1. 学生登录获得 token
2. 查询资源列表 (`GET /resources`)
3. 借用设备 (`POST /transactions`)
   - 系统自动检测时段冲突
   - 成功返回流水信息
4. 操作完成后，调用 `/transactions/{id}/return` 归还

### 场景 2：大额消耗审批
1. 学生消耗 ≥10 个物料 (`POST /transactions` action=consume)
2. 系统自动创建审批任务
3. 管理员查看待审项 (`GET /approvals?status=pending`)
4. 管理员批准或拒绝 (`POST /approvals/{id}/approve`)
5. 只有批准后，库存才会真实扣减

### 场景 3：智能分析
1. 用户询问 "本月消耗成本多少？"
2. 智能体识别为 `cost_analysis` 意图
3. 查询所有消耗类交易并计算成本
4. 返回成本排行和总额

## 🐛 故障排除

### 问题 1：401 Unauthorized
**原因**：缺少或格式错误的 Authorization header
**解决**：确保添加了 `Authorization: Bearer {user_id}` 头

### 问题 2：时段检测不工作
**原因**：时段检测仅对设备类资源有效
**解决**：
- 确保 resource.category = "device"
- 确保 action = "borrow"
- 确保提供了 borrow_time 和 expected_return_time

### 问题 3：审批任务未创建
**原因**：不符合审批条件
**解决**：
- consume 且 quantity ≥ 10
- 或 action = "lost"
- 或 action = "replenish"

### 问题 4：500 Internal Server Error
**原因**：通常是数据库问题
**解决**：
```bash
# 重新初始化
rm smart_lab.db
python -m app.seed
python -m uvicorn app.main:app --reload
```

## 📚 进阶用法

### 多轮对话（上下文记忆）
```bash
# 第一次提问
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"当前库存如何？"}'

# 返回包含 session_id，使用该 session_id 继续对话
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"abc123xyz","message":"如何改善？"}'
```

### 查看会话历史
```bash
curl http://localhost:8000/agent/sessions

# 查看指定会话的消息
curl http://localhost:8000/agent/sessions/{session_id}/messages
```

### 权限演示
```bash
# 学生尝试创建资源（会被拒绝）
curl -X POST http://localhost:8000/resources \
  -H "Authorization: Bearer 2" \
  -H "Content-Type: application/json" \
  -d '{"name":"新设备","category":"device","subtype":"测试"}'

# 返回 403：仅管理员可创建资源
```

## 🎯 答辩演示顺序（推荐）

1. **展示数据初始化**（2 分钟）
   - 展示数据库中的用户和资源
   - 展示不同角色的用户权限

2. **演示时段检测**（2 分钟）
   - 学生 A 借用设备（14:00-16:00）
   - 学生 B 尝试同时间借用 → 被拒绝 ✓
   - 学生 B 换个时间借用 → 成功 ✓

3. **演示审批流程**（2 分钟）
   - 学生消耗 15 个电阻
   - 自动创建审批任务
   - 管理员批准

4. **演示增强智能体**（2 分钟）
   - "本月消耗成本多少？" → 成本分析
   - "谁用得最多？" → 用户排行
   - "有什么建议吗？" → 智能建议

5. **展示用户认证**（1 分钟）
   - 展示不同用户权限
   - 学生只能看自己的流水
   - 管理员可以看全部

**总时间：约 10 分钟** ✨

