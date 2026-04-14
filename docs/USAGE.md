# 项目使用说明

## 1. 项目概述

本项目面向创新实践基地、实验室、创客空间等场景，用来管理共享设备和物料。当前版本已经具备以下核心能力：

- 资源类型层与资源实例层分离
  - `Resource` 负责类别库存。
  - `ResourceItem` 负责设备实例，记录资产编号、序列号、二维码、状态、当前位置、借用人和维护记录。
- 完整借还流程
  - 借用和领用先申请、后审批。
  - 损坏归还进入 `maintenance/quarantine`。
  - 部分丢失会减少实例或库存，并自动生成追责与补录任务。
- 可执行工具代理
  - 聊天助手不只是回答问题，还可以在确认后执行申请、审批、排程、补货、报失等动作。
- 增强分析
  - 公平性指标、逾期未还、黄金时段垄断、项目预计用量 vs 实际用量、按人/项目/资源异常分数。
- 七牛证据流
  - 借还、盘点、损坏、丢失均可记录 `evidence_url` 和 `evidence_type`。
  - 提供简化的盘点视觉入口，用于“上传盘点照片/文本识别结果 -> 比较库存 -> 输出差异建议”。

## 2. 当前推荐展示路径

为了避免“旧页面”“半挂载增强版”“文档和实际路由不一致”的问题，当前建议按下面路径展示：

1. `GET /login`
   - 用户登录页。
2. `GET /dashboard-main`
   - 当前正式控制台。
3. `POST /agent/chat`
   - 稳定的聊天入口，前端默认使用它。
4. `POST /enhanced-agent/ask`
   - 正式挂载的增强工具代理接口。
5. `GET /enhanced-analytics/comprehensive`
   - 正式挂载的增强分析总览。
6. `POST /files/evidence/inventory-vision`
   - 七牛证据流中的视觉/盘点入口。
7. `GET /system/readiness`
   - 可选系统自检 API（readiness score + 风险项，默认不在主控制台展示）。

说明：

- `GET /dashboard` 仍保留为旧演示页，不建议作为正式展示页。
- `/agent/chat` 与 `/enhanced-agent/ask` 都可用。
- 如果你只想对外给一个“最稳”的聊天入口，优先使用 `/agent/chat`。
- `/dashboard-main` 默认面向日常使用模式，不展示“决赛就绪检查”面板。

## 3. 运行环境

建议环境：

- Python 3.9 及以上
- Windows、Linux、macOS 均可
- 默认数据库为 SQLite

依赖安装：

```bash
pip install -r requirements.txt
```

## 4. 环境变量配置

复制模板：

```bash
copy .env.example .env
```

`.env.example` 中主要参数如下：

### 4.1 应用

- `APP_NAME`
- `APP_ENV`

### 4.2 数据库

- `DATABASE_URL`
  - 默认：`sqlite:///./smart_lab.db`

### 4.3 安全

- `JWT_SECRET`
  - JWT 签名密钥，生产环境必须修改。
- `JWT_EXPIRE_MINUTES`
  - Token 过期时间，默认 720 分钟。

### 4.4 七牛

- `QINIU_ACCESS_KEY`
- `QINIU_SECRET_KEY`
- `QINIU_BUCKET`
- `QINIU_DOMAIN`
- `QINIU_UPLOAD_TOKEN_EXPIRE`

### 4.5 大模型

- `LLM_ENABLED`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_TIMEOUT`

### 4.6 治理与安全运行参数

- `ALERT_DEDUP_WINDOW_SECONDS`
- `NOTIFY_IN_APP_ENABLED`
- `NOTIFY_WEBHOOK_ENABLED`
- `NOTIFY_WEBHOOK_URL`
- `NOTIFY_TIMEOUT`
- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_MAX_REQUESTS`

说明：

- 不配置 LLM 时，Agent 仍可使用规则和业务工具工作。
- 不配置七牛时，文件上传接口会返回 `enabled: false`，但不会影响主业务流程。

## 5. 启动项目

启动服务：

```bash
python -m uvicorn app.main:app --reload
```

Windows PowerShell 如未配置 `python` 命令，可使用：

```bash
py -m uvicorn app.main:app --reload
```

启动后可访问：

- Swagger 文档：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`
- 登录页：`http://127.0.0.1:8000/login`
- 主控制台：`http://127.0.0.1:8000/dashboard-main`

## 6. 初始化演示数据

项目已经补了命令行入口，可直接执行：

```bash
python -m app.seed
```

决赛演示推荐使用固定场景重置脚本（可复现正常借还、损坏、丢失、逾期）：

```bash
python -m app.seed_scenarios
```

默认演示账号：

- 管理员
  - 用户名：`admin`
  - 密码：`admin123`
- 教师
  - 用户名：`teacher1`
  - 密码：`123456`
- 学生
  - 用户名：`student1`
  - 密码：`123456`
- 学生
  - 用户名：`student2`
  - 密码：`123456`

说明：

- 密码现在以哈希形式存储，不再是明文。
- 如果数据库中已经有资源数据，种子脚本不会重复插入。

## 7. 登录与鉴权

### 7.1 登录

接口：

`POST /auth/login`

请求示例：

```json
{
  "username": "student1",
  "password": "123456"
}
```

响应示例：

```json
{
  "token": "Bearer <jwt>",
  "user": {
    "id": 3,
    "username": "student1",
    "real_name": "Student Zhang",
    "student_id": "S001",
    "email": "student@test.local",
    "role": "student",
    "is_active": true,
    "created_at": "2026-03-27T00:00:00"
  }
}
```

之后所有受保护接口都需要带：

```http
Authorization: Bearer <jwt>
```

### 7.2 注册

接口：

`POST /auth/register`

说明：

- 公开注册只会创建学生账号。
- 教师和管理员建议通过种子数据或后台方式维护。

### 7.3 当前用户

接口：

`GET /auth/me`

## 8. 角色权限

### 8.1 学生

- 登录系统
- 查看资源和自己的流水
- 提交借用申请
- 提交领用申请
- 归还自己借出的设备
- 使用聊天助手和自己的会话

### 8.2 教师

- 拥有学生全部能力
- 审批学生申请
- 直接登记资源丢失
- 查看审批汇总

### 8.3 管理员

- 管理资源类型
- 管理设备实例
- 管理维护记录
- 支持资源归档删除与恢复（撤回误删）
- 直接补货
- 直接库存调整
- 使用增强分析接口

## 9. 数据模型说明

### 9.1 Resource

资源类型层，表示某一类设备或物料。

关键字段：

- `name`
- `category`
  - `device`
  - `material`
- `subtype`
- `location`
- `total_count`
- `available_count`
- `min_threshold`
- `status`

### 9.2 ResourceItem

资源实例层，主要用于设备。

关键字段：

- `asset_number`
- `serial_number`
- `qr_code`
- `status`
  - `available`
  - `borrowed`
  - `maintenance`
  - `quarantine`
  - `lost`
  - `disabled`
- `current_location`
- `current_borrower_id`
- `maintenance_notes`

### 9.3 Transaction

资源流水。

支持动作：

- `borrow`
- `consume`
- `replenish`
- `lost`
- `adjust`

补充字段：

- `project_name`
- `estimated_quantity`
- `evidence_url`
- `evidence_type`
- `condition_return`

### 9.4 MaintenanceRecord

实例级维护或隔离记录。

### 9.5 FollowUpTask

异常后续任务，例如：

- `maintenance`
- `loss_investigation`
- `accountability`
- `registry_backfill`

## 10. 核心业务流程

### 10.1 学生提交借用申请

接口：

`POST /transactions`

请求示例：

```json
{
  "resource_id": 1,
  "action": "borrow",
  "quantity": 1,
  "purpose": "course project",
  "project_name": "ProjectAlpha",
  "estimated_quantity": 1,
  "note": "Need for prototype",
  "borrow_time": "2026-03-28T09:00:00",
  "expected_return_time": "2026-03-28T11:00:00"
}
```

说明：

- `borrow` 只允许对 `device` 类型资源发起。
- 借用申请不会立即扣减库存。
- 需要教师或管理员审批后才会占用库存和设备实例。
- 同一时间段仅在“并发借用数量超过设备总容量”时才会返回 `400`。

### 10.2 学生提交领用申请

接口：

`POST /transactions`

请求示例：

```json
{
  "resource_id": 2,
  "action": "consume",
  "quantity": 3,
  "purpose": "lab material",
  "project_name": "ProjectAlpha",
  "estimated_quantity": 3,
  "note": "normal use"
}
```

说明：

- `consume` 只允许对 `material` 类型资源发起。
- 也需要审批后才会真正扣减库存。

### 10.3 教师审批申请

查询待审批：

`GET /approvals?status=pending`

审批接口：

`POST /approvals/{approval_id}/approve`

请求示例：

```json
{
  "approved": true,
  "reason": "ok"
}
```

或驳回：

```json
{
  "approved": false,
  "reason": "not needed"
}
```

幂等建议：

- 对审批写操作建议携带请求头 `Idempotency-Key: <unique-key>`。
- 若因为网络重试或重复点击导致同键重复请求，系统会返回第一次成功审批的结果，不重复扣减库存。

### 10.4 学生归还设备

接口：

`PATCH /transactions/{transaction_id}/return`

#### 正常归还

```json
{
  "condition_return": "good",
  "note": "all good",
  "return_time": "2026-03-28T10:30:00"
}
```

#### 损坏归还

```json
{
  "condition_return": "damaged",
  "note": "screen cracked",
  "return_time": "2026-03-28T10:30:00",
  "evidence_url": "qiniu://damage/photo-1.jpg",
  "evidence_type": "image"
}
```

行为：

- 不会回到可用库存。
- 会进入 `maintenance/quarantine`。
- 会生成维护记录和后续任务。

#### 部分丢失

```json
{
  "condition_return": "partial_lost",
  "lost_quantity": 1,
  "note": "one accessory missing",
  "return_time": "2026-03-28T10:30:00"
}
```

行为：

- 会减少实例或聚合库存。
- 会生成 `accountability` 和 `registry_backfill` 任务。

约束：

- `return_time` 必须大于等于 `borrow_time`。
- 当 `condition_return` 为 `damaged` 或 `partial_lost` 时，建议同时提供 `evidence_url + evidence_type`。
- 若异常归还缺失证据，系统会自动创建 `evidence_backfill` 闭环任务并生成 `evidence_missing` 预警。
- 对归还写操作建议携带 `Idempotency-Key`，可避免重复提交导致的二次归还报错或状态漂移。

### 10.5 直接补货

接口：

`POST /transactions`

请求示例：

```json
{
  "resource_id": 2,
  "action": "replenish",
  "quantity": 5,
  "purpose": "admin replenish",
  "note": "weekly restock"
}
```

说明：

- 仅管理员可用。
- 直接生效，不走审批。

### 10.6 丢失登记

接口：

`POST /transactions`

请求示例：

```json
{
  "resource_id": 1,
  "action": "lost",
  "quantity": 1,
  "note": "reported missing after workshop",
  "purpose": "loss registration",
  "resource_item_ids": [1],
  "evidence_url": "qiniu://loss/photo-1.jpg",
  "evidence_type": "image"
}
```

说明：

- 仅教师和管理员可用。
- 设备类资源会优先按实例登记。
- 会产生追责任务。
- 若缺失证据字段（`evidence_url/evidence_type`），系统会自动创建 `evidence_backfill` 任务和预警。

### 10.7 直接库存调整

接口：

`POST /resources/{resource_id}/inventory-adjustments`

请求示例：

```json
{
  "target_total_count": 26,
  "target_available_count": 23,
  "reason": "restock",
  "evidence_url": "qiniu://audit/check-20260327.jpg",
  "evidence_type": "image"
}
```

说明：

- 仅管理员可用。
- 只要 `target_total_count` 或 `target_available_count` 任一项发生变化即可提交，不要求两项同时变化。
- 对实例化设备，若仅调整可用量，系统会优先释放维护/隔离实例，再按管理员覆盖规则同步状态。
- 对库存调整写操作建议携带 `Idempotency-Key`；同键同载荷重试会重放首个成功结果，同键不同载荷会返回 `409`。

## 11. 资源与实例管理

### 11.1 资源类型接口

- `POST /resources`
- `GET /resources`
- `GET /resources/{resource_id}`
- `PATCH /resources/{resource_id}`
- `DELETE /resources/{resource_id}`（管理员归档删除）
- `POST /resources/{resource_id}/restore`（管理员恢复归档）
- `POST /resources/{resource_id}/inventory-adjustments`

### 11.2 实例接口

- `GET /resources/{resource_id}/items`
- `POST /resources/{resource_id}/items`
- `PATCH /resources/items/{item_id}`
- `GET /resources/items/{item_id}/maintenance`
- `POST /resources/items/{item_id}/maintenance`

### 11.3 创建设备实例示例

```json
{
  "asset_number": "R0001-0004",
  "serial_number": "SN-2026-0004",
  "qr_code": "qr://resource/1/item/4",
  "status": "available",
  "current_location": "Room 101",
  "maintenance_notes": ""
}
```

## 12. 聊天助手与工具代理

### 12.1 稳定聊天入口

接口：

`POST /agent/chat`

请求示例：

```json
{
  "message": "帮我申请借用 3D Printer 1台 明天下午 2小时 项目 Alpha",
  "llm_options": {
    "enabled": true,
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-xxx",
    "model": "gpt-4o-mini",
    "timeout": 30
  }
}
```

说明：

- `llm_options` 可选，用于“当前请求”覆盖服务端默认 LLM 配置。
- 若不传 `llm_options`，将回退到 `.env` 中的 `LLM_*` 配置。
- 即使模型不可用，业务工具仍可回退规则引擎给出稳定答案。

典型行为：

1. Agent 先返回待确认动作。
2. 响应中包含：
   - `confirmation_required`
   - `pending_action`
   - `session_id`
3. 你再发送确认消息。

确认示例：

```json
{
  "message": "确认",
  "session_id": "session-id-from-previous-step"
}
```

### 12.2 Agent 支持的典型能力

- 查询库存
- 查询审批状态
- 推荐空档/排程
- 生成借用申请
- 生成领用申请
- 执行补货
- 执行报失
- 执行审批/驳回
- 将治理建议转成动作（如“按建议补货”生成补货审批单）

### 12.5 治理建议自动落地（新增）

可直接对智能体说：

- `按建议补货`
- `帮我生成补货审批单`

行为：

- Agent 会先生成待确认动作 `create_replenish_approval`。
- 你确认后，系统会创建一条 `replenish` 类型审批单（pending），等待审批通过后再执行入库。

### 12.3 会话接口

- `GET /agent/sessions`
- `GET /agent/sessions/{session_id}/messages`
- `DELETE /agent/sessions/{session_id}`

说明：

- 会话与 owner 绑定。
- 用户无法访问他人的 Agent 会话。

### 12.4 增强工具代理

接口：

- `POST /enhanced-agent/ask`
- `POST /enhanced-agent/chat`

请求格式：

```json
{
  "question": "查一下 3D Printer 的库存",
  "session_id": null,
  "confirm": false,
  "confirmation_token": null,
  "llm_options": {
    "enabled": true,
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-xxx",
    "model": "gpt-4o-mini",
    "timeout": 30
  }
}
```

返回会额外包含：

- `real_time_data`
- `analysis_steps`（感知-推理-执行高层步骤）
- `confirmation_required`
- `pending_action`
- `executed_tools`
- `multi_agent_trace`（调度代理/治理代理/证据代理分工轨迹）
- `orchestration_summary`（多代理汇总结论）

时间理解增强（排程问答）：

- 支持 `今天/明天/后天/大后天`
- 支持 `周X/下周X`
- 支持 `下午3点半`、`14:30`、`YYYY-MM-DD` 组合表达

## 13. 调度与分析

### 13.1 调度

- `POST /scheduler/optimal-slots`
- `GET /scheduler/demand-prediction/{resource_id}`
- `GET /scheduler/optimize-allocation`
- `GET /scheduler/fairness-policy`
- `PATCH /scheduler/fairness-policy`

`/scheduler/optimize-allocation` 仅管理员可访问。

`/scheduler/fairness-policy` 说明：

- 所有登录用户可查看当前公平策略配置。
- 仅管理员可更新策略开关与阈值（黄金时段配额、连续占用限制、高频用户降权）。
- `optimal-slots` 返回中新增 `fairness_penalty` 与 `fairness_reasons`，用于解释公平约束如何影响排程分数。

### 13.2 基础分析

- `GET /analytics/overview`
- `GET /analytics/top-occupied-devices`
- `GET /analytics/waste-risk`
- `GET /analytics/kpi-dashboard`

### 13.3 增强分析

- `GET /enhanced-analytics/comprehensive`
- `GET /enhanced-analytics/demand-prediction/{resource_id}`

增强分析当前包含：

- 总览统计
- 资源使用分析
- 用户行为分析
- 成本分析
- 趋势分析
- 推荐项
- 公平性指标
- 超时未归还列表
- 黄金时段垄断
- 项目预计 vs 实际用量偏差
- 用户/项目/资源异常分数

说明：

- 增强分析仅管理员可访问。

### 13.4 KPI 看板（新增）

接口：

- `GET /analytics/kpi-dashboard?days=30`

说明：

- 教师/管理员可访问。
- 输出分为三部分：
  - `period`：当前评测窗口与基线窗口。
  - `metrics`：每个 KPI 的基线值、当前值、改善值、改善百分比、趋势与解释。
  - `dictionary`：指标定义字典（公式、方向、单位、业务解释）。
- 当前固化 KPI：
  - `utilization_rate`（利用率）
  - `overdue_rate`（逾期率）
  - `waste_rate`（浪费率）
  - `loss_rate`（报失率）
  - `fairness_index`（公平指数）

### 13.5 智能体能力评测集（P3-2）

入口文件：

- `agent_eval/cases.json`
- `agent_eval/run_eval.py`

运行方式：

```bash
py -m agent_eval.run_eval --output docs/reports/agent_eval_latest.json --fail-under 100
```

说明：

- 覆盖五类能力：问答、执行、拒绝、澄清、异常处理。
- 结果输出包含总分和分类分，便于每次改动后回归对比。
- `--fail-under` 默认 `100`，低于阈值时命令返回非零退出码（适合 CI 卡口）。

## 14. 七牛与证据流

### 14.1 获取上传 Token

`GET /files/qiniu-token`

查询参数：

- `key`
- `scene`
- `evidence_type`

示例：

`GET /files/qiniu-token?key=returns/photo-001.jpg&scene=return&evidence_type=image`

### 14.2 获取私有下载链接

`GET /files/qiniu-private-url?key=returns/photo-001.jpg&expire_seconds=3600`

### 14.3 盘点视觉入口

`POST /files/evidence/inventory-vision`

请求示例：

```json
{
  "resource_id": 1,
  "evidence_url": "qiniu://audit/photo-3.jpg",
  "evidence_type": "image",
  "observed_count": 2
}
```

或传 OCR 文本：

```json
{
  "resource_id": 1,
  "evidence_url": "qiniu://audit/photo-3.jpg",
  "evidence_type": "image",
  "ocr_text": "现场盘点结果：2台"
}
```

返回结果会包含：

- 识别数量
- 系统可用库存
- 系统总库存
- 差异值
- 建议动作
- 融合置信度 `recognition_confidence`
- 识别来源 `recognized_sources`
- 候选计数 `extracted_candidates`
- 多源分歧指数 `disagreement_index`

补充说明：

- 若盘点请求缺失证据字段（`evidence_url/evidence_type`），系统会自动创建 `evidence_backfill` 任务，避免证据链中断。

## 15. 预警与审批汇总

### 15.1 预警

`GET /alerts`

预警处置接口（教师/管理员）：

- `POST /alerts/{alert_id}/acknowledge`（确认）
- `POST /alerts/{alert_id}/resolve`（消除）

说明：

- 默认 `GET /alerts` 仅返回未消除预警。
- `GET /alerts?include_resolved=true` 可查看历史已消除预警。
- 预警新增去重字段：`dedup_key`、`last_seen_at`、`occurrence_count`。
- 同类事件在去重窗口内会累计 `occurrence_count`，不重复生成多条预警。

### 15.3 系统自检 API（可选）

`GET /system/readiness?probe_llm=false`

说明：

- 返回 `readiness_score`、`readiness_level`、`checks`、`stats`。
- `probe_llm=true` 时会主动探测模型连通性（可能增加一次外部请求开销）。
- 该能力可直接通过 API 调用，主控制台默认不展示独立“决赛就绪检查”面板。

### 15.2 审批

- `GET /approvals`
- `GET /approvals/{approval_id}`
- `POST /approvals/{approval_id}/approve`
- `GET /approvals/stats/summary`

### 15.4 通知投递日志（新增）

接口：

- `GET /notifications/deliveries`

说明：

- 教师/管理员可查看通知投递日志。
- 关键事件（待审批、超期任务升级、补证任务）会自动触发站内通知日志。
- 可用 `event_type` 过滤，如 `approval_pending`、`follow_up_sla_overdue`、`evidence_backfill_required`。

### 15.5 操作审计日志（新增）

接口：

- `GET /audit-logs`

说明：

- 教师/管理员可查看关键写操作审计日志。
- 支持按 `action`、`entity_type`、`actor_user_id` 过滤。
- 审计日志记录操作人、动作类型、对象类型/ID、请求路径、幂等键和细节 JSON。

## 16. 常见错误与处理

### 16.1 401 Unauthorized

原因：

- 未携带 `Authorization` 头
- Token 无效
- Token 过期

处理：

- 重新登录并带上 `Bearer <jwt>`

### 16.2 403 Forbidden

原因：

- 角色权限不足
- 访问了他人的会话或审批资源

### 16.3 400 Bad Request

常见原因：

- 借用缺少 `borrow_time` 或 `expected_return_time`
- 借用时间冲突
- `return_time < borrow_time`
- `partial_lost` 缺少 `lost_quantity`
- 设备实例数量与聚合库存不一致

### 16.4 409 Conflict

常见原因：

- 同一个 `Idempotency-Key` 被复用于不同请求载荷。

处理：

- 为每次新的业务写入生成新的 `Idempotency-Key`，仅在“同一请求重试”时复用原键。

### 16.5 429 Too Many Requests

常见原因：

- 命中关键写接口限流策略（短窗口内操作过于频繁）。

处理：

- 按响应头 `Retry-After` 等待后重试。

## 17. 推荐演示脚本

一个完整演示可以按下面顺序进行：

1. 登录 `admin` 或 `teacher1`
2. 打开 `/dashboard-main`
3. 查看 `/analytics/overview`
4. 查看 `/resources` 和 `/resources/{id}/items`
5. 用 `student1` 提交借用申请
6. 用 `teacher1` 审批
7. 用 `student1` 执行损坏归还或部分丢失归还
8. 查看 `/alerts`、维护记录和追责任务
9. 调用 `/agent/chat` 发起一个可确认执行的业务动作
10. 调用 `/enhanced-analytics/comprehensive`
11. 调用 `/files/evidence/inventory-vision` 展示证据流

## 18. 开发备注

- 当前默认数据库是 SQLite，适合答辩与本地演示。
- 数据库启动时会自动执行轻量 schema 维护与设备实例补齐。
- 如果你已经有旧库，项目会在启动时补齐新表和新增字段。
- 静态前端页面仍可继续迭代，但当前后端接口已经是正式版本。

## 19. 用户自定义大模型接入（答辩推荐）

- 打开 `/dashboard-main`，在「智能体助手」中勾选“启用自定义大模型”。
- 填写 `Base URL`、`Model`、`API Key`、`Timeout` 后即可直接体验模型推理能力。
- 前端仅将配置保存在浏览器本地；后端按请求临时使用，不写入数据库。
- 当模型配置不完整或不可达时，系统会自动回退到规则引擎与业务工具，保证可用性。

## 20. 异常闭环任务中心（新增）

### 20.1 任务查询

接口：
`GET /follow-up-tasks`

常用参数：
- `status`：`open / in_progress / done / cancelled / all`
- `assigned`：`me / all`
- `task_type`：可选，例如 `maintenance / accountability / registry_backfill / loss_investigation`

说明：
- 教师/管理员可用 `assigned=all` 查看全局任务。
- 学生仅可查看自己被指派或与自己借用记录关联的任务。

### 20.2 任务状态更新

接口：
`PATCH /follow-up-tasks/{task_id}`

请求示例：
```json
{
  "status": "done",
  "note": "已核对并补录完成"
}
```

说明：
- 仅教师/管理员，或该任务负责人可更新状态。
- `note` 会追加到任务描述中，形成简易处理轨迹。
- 支持附带 `result` 和 `outcome_score`，用于记录闭环结果质量。
- 任务对象含 `updated_at/closed_at/escalation_level/escalated_at/sla_status`，可用于审计与治理看板。

### 20.4 闭环任务 SLA 升级机制（新增）

- 对 `open/in_progress` 且超期任务，系统会自动触发 SLA 升级。
- 升级后任务会标记 `escalation_level` 与 `escalated_at`。
- 同时生成去重预警 `follow_up_sla_overdue`，可在 `/alerts` 中追踪处置闭环。

### 20.3 智能体联动

你可以直接对智能体说：
- `查看闭环任务`
- `完成任务 #12`
- `开始任务 #12`

智能体会先给出确认，再执行任务状态变更，形成“发现异常 -> 指派任务 -> 确认执行 -> 闭环完成”的完整链路。

## 21. 决赛答辩资产包（P3-3）

答辩资料入口：

- `docs/finals/2026-04-12-defense-evidence-chain.md`
- `docs/finals/2026-04-12-defense-ppt-outline.md`
- `docs/finals/2026-04-12-defense-ppt.md`
- `docs/finals/2026-04-12-defense-demo-script.md`
- `docs/finals/2026-04-12-competition-requirements-checklist.md`

一键导出答辩报告：

```bash
py -m scripts.finals.export_defense_reports --output-dir docs/reports --kpi-days 30
```

输出文件：

- `docs/reports/agent_eval_latest.json`
- `docs/reports/kpi_dashboard_latest.json`
- `docs/reports/defense_reports_summary.json`

总验收检查（建议答辩前执行）：

```bash
py -m scripts.finals.run_release_checks --output docs/reports/finals_release_check.json
```

说明：

- 会在临时隔离数据库中执行 `agent_eval + readiness + agent执行 + multi-agent + KPI` 五类验收。
- 会额外输出比赛四条要求核查项：`competition_requirements_4x`。
- `all_ok=true` 表示本地答辩包关键能力可复现。

一键流水线（推荐）：

```bash
py -m scripts.finals.run_finals_pipeline --output-dir docs/reports --kpi-days 30
```

输出补充：

- `docs/reports/finals_pipeline_summary.json`

说明：

- 该命令会顺序执行导出报告和总验收检查，是答辩前最简操作路径。
