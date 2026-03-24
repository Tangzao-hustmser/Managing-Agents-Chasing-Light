# 创新实践基地共享设备和物料管理智能体（基于七牛云）

这是一个面向高校创新实践基地的管理智能体项目，目标是让 3D 打印机、激光切割机、电子元器件、开发板、万用表等共享资源实现**开放管理、自主使用、可追溯审计、风险预警**。

## 1. 这个项目能解决什么问题

- 资源利用率不高：通过占用率统计和预警，帮助协调预约时段。
- 占用不均：自动识别高占用设备，提醒管理员做分流。
- 耗材浪费：对异常大批量领用行为自动告警。
- 工具丢失：支持 `lost` 丢失登记并生成高优先级预警。
- 资料留痕难：所有借还、领用、补货都写入流水，便于追责与复盘。

## 2. 核心能力

1. **资源管理**：设备/物料统一管理（名称、分类、库存、阈值、状态）。
2. **借还与领用**：支持 borrow / return / consume / replenish / lost 五类动作。
3. **规则引擎**：
   - 低库存预警（`low_inventory`）
   - 高占用预警（`high_occupancy`）
   - 疑似浪费预警（`possible_waste`）
   - 工具丢失预警（`resource_lost`）
4. **智能体问答**：自然语言提问（例如“哪些资源快缺货了？”）。
5. **对话式智能体**：支持 `session_id` 多轮追问、上下文记忆、会话历史管理。
6. **七牛云集成**：支持上传 token + 私有空间限时下载链接。
7. **数据看板**：总览指标、高占用设备排行、疑似浪费风险统计。

## 3. 技术架构

- 后端：FastAPI
- 数据库：SQLite（可改 MySQL/PostgreSQL）
- ORM：SQLAlchemy
- 智能体：规则 + 轻量意图识别（可扩展接入大模型）
- 对象存储：七牛云（上传凭证模式）

## 4. 目录结构

```text
.
├── app
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 环境配置
│   ├── database.py             # 数据库连接
│   ├── models.py               # ORM 模型
│   ├── schemas.py              # 请求响应模型
│   ├── seed.py                 # 初始化演示数据
│   ├── routers
│   │   ├── resources.py        # 资源管理接口
│   │   ├── transactions.py     # 借还领用接口
│   │   ├── alerts.py           # 预警查询接口
│   │   └── files.py            # 七牛云 token 接口
│   └── services
│       ├── agent_service.py    # 智能体问答编排
│       ├── rules_engine.py     # 预警规则引擎
│       └── qiniu_service.py    # 七牛云服务
├── .env.example
├── requirements.txt
└── README.md
```

## 5. 快速启动（5 分钟）

### 5.1 安装依赖

```bash
pip install -r requirements.txt
```

### 5.2 配置环境变量

```bash
cp .env.example .env
```

然后编辑 `.env`，至少填入以下七牛云参数：

- `QINIU_ACCESS_KEY`
- `QINIU_SECRET_KEY`
- `QINIU_BUCKET`
- `QINIU_DOMAIN`

如果你要启用真正的大模型对话（推荐），还要填写：

- `LLM_ENABLED=true`
- `LLM_BASE_URL`（例如你的网关是 `https://api.qiaigc.com/v1`）
- `LLM_API_KEY`（控制台里创建的 key）
- `LLM_MODEL`（例如 `gpt-4o-mini` / `qwen-plus`，以平台支持为准）

### 5.3 启动服务

```bash
uvicorn app.main:app --reload
```

如果你在 Windows 下出现 `uvicorn` 命令找不到，请改用：

```bash
python -m uvicorn app.main:app --reload
```

### 5.4 初始化演示数据（可选）

```bash
python -m app.seed
```

启动后访问：

- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 前端面板：[http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)

## 6. 关键接口说明

### 6.1 新增资源

`POST /resources`

示例请求体：

```json
{
  "name": "创想三维 Ender-3",
  "category": "device",
  "subtype": "3D打印机",
  "location": "A栋创新工坊",
  "total_count": 4,
  "available_count": 2,
  "unit_cost": 1999,
  "min_threshold": 1,
  "status": "active",
  "description": "支持 PLA 打印"
}
```

### 6.2 创建借还/领用流水

`POST /transactions`

`action` 支持：

- `borrow` 借用
- `return` 归还
- `consume` 领用耗材
- `replenish` 补货
- `lost` 丢失登记

### 6.3 智能体问答

`POST /agent/ask`

示例请求：

```json
{
  "question": "当前哪些资源库存紧张？"
}
```

### 6.4 对话式智能体（多轮）

`POST /agent/chat`

第一轮（不带 session_id）：

```json
{
  "message": "帮我看下当前哪些设备占用率高"
}
```

返回示例：

```json
{
  "session_id": "b7d85a5f04e948f99a0f7f6f4932a6b2",
  "reply": "......",
  "used_model": true
}
```

第二轮追问（带同一个 `session_id`）：

```json
{
  "session_id": "b7d85a5f04e948f99a0f7f6f4932a6b2",
  "message": "按优先级给我一个本周处理计划"
}
```

### 6.5 七牛云上传凭证

`GET /files/qiniu-token?key=records/photo-001.jpg`

前端拿到 token 后可直接上传到七牛云，适合上传：

- 借还凭证照片
- 工具损坏/丢失现场图
- 耗材盘点附件

### 6.6 七牛私有空间访问链接

`GET /files/qiniu-private-url?key=records/photo-001.jpg&expire_seconds=3600`

返回示例：

```json
{
  "enabled": true,
  "bucket": "material-management-database",
  "key": "records/photo-001.jpg",
  "expires_in": 3600,
  "private_url": "https://xxx?e=...&token=..."
}
```

### 6.7 会话管理接口

- `GET /agent/sessions`：查看最近会话 ID
- `GET /agent/sessions/{session_id}/messages`：查看会话消息
- `DELETE /agent/sessions/{session_id}`：清空某个会话

### 6.8 数据看板接口

- `GET /analytics/overview`：总览指标
- `GET /analytics/top-occupied-devices`：设备占用排行榜
- `GET /analytics/waste-risk`：疑似浪费统计

### 6.9 大模型诊断接口（排障用）

- `GET /debug/llm-check`：一键检查 LLM 连通性
  - `reason=config_incomplete`：配置缺失
  - `reason=dns_error`：网关域名解析失败
  - `reason=http_error`：网关有响应但鉴权/模型参数错误
  - `reason=success`：调用正常

## 7. 如何在七牛云控制台查看配置（非常重要）

你当前项目需要 4 个核心配置：`AccessKey`、`SecretKey`、`Bucket`、`CDN 域名`。

### 7.1 查看 AK/SK

1. 登录七牛云控制台。
2. 点击右上角头像（或账号中心）。
3. 进入 **密钥管理 / API Key 管理**。
4. 复制：
   - `AccessKey` -> 填到 `QINIU_ACCESS_KEY`
   - `SecretKey` -> 填到 `QINIU_SECRET_KEY`

> 注意：`SecretKey` 只在后端保存，不要提交到 Git 仓库。

### 7.2 查看 Bucket 名称

1. 进入 **对象存储 Kodo**。
2. 在存储空间列表里找到你创建的空间。
3. 记录空间名（Bucket 名）-> 填到 `QINIU_BUCKET`。

### 7.3 查看/配置访问域名

1. 进入对应 Bucket 的详情页。
2. 打开 **域名管理 / 空间域名**。
3. 找到测试域名或你绑定的 CDN 域名。
4. 填到 `QINIU_DOMAIN`，格式如：`https://cdn.xxx.com`。

### 7.4 本地快速自检

启动服务后，访问：

`GET /files/qiniu-token?key=test/demo.jpg`

- 如果返回 `enabled: true`，说明七牛配置正确。
- 如果返回 `enabled: false`，说明 `.env` 仍缺参数。

## 8. 接入你截图里的大模型网关（OpenAI 兼容）

你的截图显示可用 `OpenAI BaseURL`，通常可按下面配置：

```env
LLM_ENABLED=true
LLM_BASE_URL=https://api.qiaigc.com/v1
LLM_API_KEY=sk-xxxxxxxx
LLM_MODEL=请填你平台已开通的模型名
```

然后重启后端，调用 `POST /agent/chat` 即可使用模型多轮对话。

如果模型名不确定：

1. 在你截图这个平台的 API 文档查看“模型列表”。
2. 复制一个可用模型名填入 `LLM_MODEL`。
3. 若报错，我可以根据报错帮你精确修正。

## 9. 推荐演示流程（答辩 5 分钟版）

1. 先展示 `GET /analytics/overview`，说明系统实时掌握基地全局状态。
2. 再展示 `GET /analytics/top-occupied-devices`，说明能识别占用不均。
3. 调用 `POST /transactions` 连续制造一次高领用行为，再查 `GET /alerts`。
4. 调用 `POST /agent/chat` 让智能体给出“本周治理建议”。
5. 上传一张现场图片并获取 `GET /files/qiniu-private-url`，展示私有空间安全访问。

## 10. 前端管理面板功能说明

访问 `http://127.0.0.1:8000/dashboard`，你会看到：

1. **顶部指标卡片**：资源总数、低库存数、预警总数、流水总数。
2. **资源列表**：展示当前设备/物料可用量与位置。
3. **最新预警**：按时间显示高优先级异常信息。
4. **对话式智能体区域**：支持多轮提问，自动维护 `session_id`。
5. **七牛私有链接生成**：输入对象 `key` 即可生成限时访问 URL。

> 页面是纯静态 HTML + 原生 JS，便于快速演示和后续改造成 Vue/React。

## 11. 比赛答辩可扩展方向（建议）

1. 接入大模型（如 Qwen / DeepSeek）替换当前关键词意图识别。
2. 增加用户角色（学生/管理员/导师）和审批流。
3. 增加预约时间段冲突检测和自动排班建议。
4. 接入消息系统（企业微信/飞书/短信）做预警推送。
5. 增加成本看板（耗材成本、设备维护成本、利用率趋势）。

## 12. 项目说明

- 代码已按“可读优先”编写，并在关键位置加入注释，便于课程项目二次开发。
- 默认数据库为 SQLite，适合演示；生产环境建议切换 MySQL/PostgreSQL。
- 七牛云采用上传凭证方案，避免把文件经过后端中转，降低服务器压力。
