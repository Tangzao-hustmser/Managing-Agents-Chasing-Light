# 测试文档

## 1. 测试目标

本项目的测试重点不是“页面是否好看”，而是验证下面这些高风险业务链路在当前版本中可靠可用：

- JWT 登录和鉴权
- 资源申请与审批
- 审批前后库存变化
- 实例级借出与归还
- 损坏归还和部分丢失归还
- 追责/补录/维护任务生成
- 闭环任务查询与状态流转
- Agent 会话 owner 绑定
- Agent 确认后执行业务工具
- 调度、增强分析、七牛证据流接口
- 静态页面是否仍包含关键角色流程入口

## 2. 当前测试栈

- 测试框架：`pytest`
- 接口测试：`fastapi.testclient.TestClient`
- 数据库：每次测试使用临时 SQLite 数据库
- ORM：`SQLAlchemy`

当前没有引入：

- 浏览器端 E2E 测试框架
- 覆盖率工具
- 压测工具

## 3. 当前测试文件

### 3.1 `tests/test_pages.py`

验证静态页面中仍然存在关键区域和角色流程代码。

覆盖内容：

- 学生申请区
- 借还记录区
- 教师审批区
- 管理员库存调整区
- 登录页的公开注册提示

### 3.2 `tests/test_workflows.py`

验证核心业务流程。

当前覆盖：

- 学生借用申请提交后，审批前不扣库存
- 教师审批通过后扣减库存
- 教师拒绝申请后库存不变
- 管理员直接库存调整
- 学生不能审批
- 教师能查看待审批列表
- 正常归还后库存回补
- 损坏归还进入隔离/维护并生成维护任务
- 部分丢失归还减少总量并生成追责/补录任务
- `return_time < borrow_time` 时拒绝归还
- 非法提交不会留下脏写入

### 3.3 `tests/test_agent_enhanced.py`

验证本次升级新增的安全、Agent、增强接口和证据流。

当前覆盖：

- 登录返回 JWT Bearer token
- `/agent/chat` 未登录时拒绝访问
- Agent 确认后可创建借用申请
- Agent 会话 owner 绑定
- 调度接口返回推荐时段
- analytics/files 等接口已启用鉴权
- 盘点视觉入口可返回差异与建议
- 增强 Agent 接口返回实时数据
- 增强分析仅管理员可访问
- 增强需求预测返回新 schema

### 3.4 `tests/test_follow_up_tasks.py`

验证闭环任务中心与智能体任务执行链路。

当前覆盖：

- 学生可查看并处理自己被指派的闭环任务
- 学生不能更新未分配给自己的闭环任务
- 教师可查看全局闭环任务状态
- Agent 可通过“确认执行”更新闭环任务状态

## 4. 当前通过情况

本地最近一次运行结果：

```bash
pytest -q
```

本仓库一次回归结果（2026-04-01）：

```text
38 passed
```

建议提交前在你的环境再跑一遍全量用例确认。

## 5. 如何运行测试

### 5.1 运行全部测试

```bash
pytest -q
```

### 5.2 运行单个测试文件

```bash
pytest tests/test_workflows.py -q
pytest tests/test_agent_enhanced.py -q
pytest tests/test_pages.py -q
pytest tests/test_follow_up_tasks.py -q
```

### 5.3 运行单个测试用例

```bash
pytest tests/test_workflows.py::test_damaged_return_moves_item_to_quarantine_and_creates_maintenance -q
```

### 5.4 按关键字筛选

```bash
pytest -q -k return
pytest -q -k agent
pytest -q -k analytics
```

## 6. 测试环境说明

所有接口测试都通过 `tests/conftest.py` 中的 `test_env` fixture 启动。

它做了这些事情：

- 创建临时 SQLite 数据库
- 调用 `ensure_database_schema()` 初始化和迁移 schema
- 注入 FastAPI 的测试数据库依赖
- 自动插入测试用户和资源
- 提供默认借用和领用 payload

测试默认账号：

- `admin / admin123`
- `teacher1 / 123456`
- `student1 / 123456`

## 7. 关键 fixture 和辅助函数

### 7.1 `test_env`

位置：

- `tests/conftest.py`

返回内容包括：

- `client`
- `SessionLocal`
- `borrow_payload`
- `consume_payload`

### 7.2 `login_as`

作用：

- 通过 `/auth/login` 登录
- 自动返回带 `Authorization` 头的 headers

示例：

```python
headers, user = login_as(client, "student1", "123456")
```

## 8. 已覆盖的风险点

### 8.1 认证与权限

- 明文 token 退场，登录返回 JWT
- 受保护接口需要鉴权
- 学生不能审批
- 增强分析仅管理员可访问
- Agent 会话无法被其他用户读取

### 8.2 借还与库存

- 借用审批前不扣库存
- 审批通过后扣库存
- 归还后库存回补
- 设备资源自动生成/绑定实例
- 异常归还时库存与实例状态同步

### 8.3 异常归还

- `damaged` 不再直接回到可用库存
- `partial_lost` 会减少总量
- 会创建维护、追责、补录等任务
- 时间顺序校验生效

### 8.4 Agent 与增强能力

- Agent 可先提议动作，再等待确认
- 确认后能真正提交借用申请
- 增强 Agent 返回 `real_time_data`
- 增强分析返回新指标字段

### 8.5 证据流

- 七牛相关接口已进入鉴权体系
- 盘点视觉入口可输出差异和建议

## 9. 目前未覆盖或覆盖较弱的部分

下面这些点当前还没有完整自动化覆盖，后续如果你要继续完善，建议优先补：

- 真实七牛上传和私有链接签名的集成测试
- 真实 LLM 联通与容错测试
- 多用户并发借用冲突测试
- 旧数据库迁移到新 schema 的回归样本测试
- 前端实际点击流的浏览器 E2E 测试
- 调度算法与增强分析结果的统计学回归测试
- FollowUpTask 列表接口本身

## 10. 推荐补测顺序

如果你准备继续扩展功能，建议按下面顺序补：

1. `lost` 登记的更多实例级边界
2. `ResourceItem` 手工编辑后的库存同步
3. Agent 执行补货、报失、审批驳回三类动作
4. 七牛上传失败和未配置场景
5. 增强分析在复杂历史数据下的结果稳定性

## 11. 编写新测试的建议

### 11.1 优先测“状态变化”

不要只测 HTTP 200，更要测：

- 数据库记录是否创建
- 库存是否变化
- 实例状态是否变化
- 任务/维护记录/预警是否生成

### 11.2 优先测“权限边界”

每个新增接口至少写两类用例：

- 有权限用户可以执行
- 无权限用户被拒绝

### 11.3 Agent 功能一定测确认链路

Agent 是“提议 -> 确认 -> 执行”的双阶段流程，新增工具时至少要覆盖：

- 未确认时不写库
- 确认后正确写库

### 11.4 尽量复用 `test_env`

除非你要构造特殊迁移场景，否则优先沿用 `test_env`，可以减少样板代码和测试不一致。

## 12. 常见测试问题

### 12.1 登录相关测试失败

优先检查：

- 是否使用 `login_as`
- 是否正确携带 `Authorization`
- 是否改动了 JWT 生成/解析逻辑

### 12.2 库存断言不稳定

优先检查：

- 测试是否正确 `expire_all()`
- 设备实例状态是否同步影响了聚合库存
- 是否错误地在审批前就断言库存已扣减

### 12.3 Agent 测试失败

优先检查：

- 是否拿到了 `session_id`
- 是否执行了“确认”第二步
- 是否有权限执行对应工具动作

## 13. 发布前最小测试清单

建议每次提交前至少运行：

```bash
pytest tests/test_workflows.py -q
pytest tests/test_agent_enhanced.py -q
```

正式演示或提交比赛前，运行：

```bash
pytest -q
```

如果全部通过，当前版本的主链路基本可以认为是稳定可演示的。
