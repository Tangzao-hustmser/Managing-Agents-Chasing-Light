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

说明：

- `GET /dashboard` 仍保留为旧演示页，不建议作为正式展示页。
- `/agent/chat` 与 `/enhanced-agent/ask` 都可用。
- 如果你只想对外给一个“最稳”的聊天入口，优先使用 `/agent/chat`。

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

说明：

- 不配置 LLM 时，Agent 仍可使用规则和业务工具工作。
- 不配置七牛时，文件上传接口会返回 `enabled: false`，但不会影响主业务流程。

## 5. 启动项目

启动服务：

```bash
python -m uvicorn app.main:app --reload
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
- 同一时间段如果和已批准借用冲突，会返回 `400`。

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
- 当前更适合物料类资源。
- 对实例化设备，建议优先通过实例管理和真实归还/报失流程维护。

## 11. 资源与实例管理

### 11.1 资源类型接口

- `POST /resources`
- `GET /resources`
- `GET /resources/{resource_id}`
- `PATCH /resources/{resource_id}`
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
- `confirmation_required`
- `pending_action`
- `executed_tools`

## 13. 调度与分析

### 13.1 调度

- `POST /scheduler/optimal-slots`
- `GET /scheduler/demand-prediction/{resource_id}`
- `GET /scheduler/optimize-allocation`

`/scheduler/optimize-allocation` 仅管理员可访问。

### 13.2 基础分析

- `GET /analytics/overview`
- `GET /analytics/top-occupied-devices`
- `GET /analytics/waste-risk`

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

## 15. 预警与审批汇总

### 15.1 预警

`GET /alerts`

### 15.2 审批

- `GET /approvals`
- `GET /approvals/{approval_id}`
- `POST /approvals/{approval_id}/approve`
- `GET /approvals/stats/summary`

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
