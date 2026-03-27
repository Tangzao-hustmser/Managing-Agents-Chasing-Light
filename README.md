# Managing-Agents-Chasing-Light

创新实践基地共享设备与物料管理系统，基于 FastAPI、SQLAlchemy 和 SQLite，支持：

- 资源类型 + 资源实例两层模型
- 借用、领用、补货、报失、归还异常处理
- 审批流与实例级追踪
- 可执行工具代理聊天助手
- 增强分析与异常评分
- 七牛证据流与简易盘点视觉入口

## 文档入口

- 使用说明：[docs/USAGE.md](docs/USAGE.md)
- 测试文档：[docs/TESTING.md](docs/TESTING.md)

## 官方展示路径

- 登录页：`/login`
- 主控制台：`/dashboard-main`
- 稳定聊天入口：`POST /agent/chat`
- 增强工具代理：`POST /enhanced-agent/ask`
- 增强分析：`GET /enhanced-analytics/comprehensive`
- 盘点视觉入口：`POST /files/evidence/inventory-vision`

`/dashboard` 仍保留为旧演示页，不建议作为当前正式展示入口。

## 大模型体验（推荐）

- 在 `/dashboard-main` 的「智能体助手」区域可勾选“启用自定义大模型”。
- 支持直接输入 `Base URL`、`Model`、`API Key`、`Timeout`，用于当前用户的会话请求。
- 前端仅保存在浏览器 `localStorage`，后端按请求使用，不会落库。

## 快速开始

```bash
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload
```

可选初始化演示数据：

```bash
python -m app.seed
```

启动后访问：

- Swagger：`http://127.0.0.1:8000/docs`
- 登录页：`http://127.0.0.1:8000/login`
- 主控制台：`http://127.0.0.1:8000/dashboard-main`

## 运行测试

```bash
pytest -q
```

当前本地通过结果：`29 passed`。
