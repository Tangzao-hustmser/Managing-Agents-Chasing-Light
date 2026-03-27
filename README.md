# Managing-Agents-Chasing-Light

面向“创新实践基地共享设备和物料管理”场景的智能体系统。  
项目聚焦命题 D：对 3D 打印机、激光切割机、开发板、电子元器件、万用表等共享资源进行开放管理与自主使用，并治理利用率不高、占用不均、耗材浪费、工具丢失等问题。

## 1. 体验方式（符合性说明）

本项目当前状态如下：

- 在线体验访问链接：`暂无公网在线地址`
- 本地部署方式：`已提供（见第 2 节）`
- 可执行二进制文件：`暂未提供`


## 2. 本地部署（推荐）

### 2.1 环境要求

- Python `3.9+`
- pip
- Windows / Linux / macOS

### 2.2 安装与启动

```bash
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload
```

如果你是 Linux/macOS，可将 `copy` 改为：

```bash
cp .env.example .env
```

### 2.3 初始化演示数据（可选）

```bash
python -m app.seed
```

### 2.4 访问入口

- Swagger：`http://127.0.0.1:8000/docs`
- 登录页：`http://127.0.0.1:8000/login`
- 主控制台：`http://127.0.0.1:8000/dashboard-main`

## 3. 项目核心能力

- 资源双层模型：`Resource`（类型库存）+ `ResourceItem`（设备实例）
- 全流程闭环：借用、领用、审批、归还、补货、报失、异常追踪
- 智能体执行：不仅问答，还可发起业务动作（确认后执行）
- 调度推荐：支持“有无空档 + 推荐时段 + 推荐理由”
- 治理分析：公平性、逾期未还、异常评分、预计 vs 实际偏差
- 证据链：支持文件证据与盘点视觉入口（Qiniu）

## 4. 智能体与大模型能力

### 4.1 智能体入口

- 稳定聊天入口：`POST /agent/chat`
- 增强工具代理：`POST /enhanced-agent/ask`

### 4.2 用户自定义大模型接入（答辩友好）

`/dashboard-main` 内置“启用自定义大模型”配置，可填写：

- `Base URL`
- `Model`
- `API Key`
- `Timeout`

特点：

- 按请求传入 `llm_options`，优先使用用户配置
- 模型不可用时自动回退规则引擎，保证可用性
- 前端仅保存在浏览器 `localStorage`，后端不落库

## 5. 推荐展示路径

1. 登录 `/login`
2. 进入 `/dashboard-main`
3. 查看资源、审批、预警与流水
4. 通过智能体提问空档/治理建议
5. 演示确认执行（如借用申请、审批等）
6. 查看增强分析 `GET /enhanced-analytics/comprehensive`

## 6. 测试

运行：

```bash
pytest -q
```

当前本地回归结果：`32 passed`

## 7. 文档入口

- 使用说明：[docs/USAGE.md](docs/USAGE.md)
- 测试文档：[docs/TESTING.md](docs/TESTING.md)
