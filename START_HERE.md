# 快速开始（决赛版）

## 1. 启动

```bash
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload
```

PowerShell 若无 `python` 命令可改用：

```bash
py -m uvicorn app.main:app --reload
```

## 2. 入口（统一口径）

- 登录页：`http://127.0.0.1:8000/login`
- 正式控制台：`http://127.0.0.1:8000/dashboard-main`
- API 文档：`http://127.0.0.1:8000/docs`
- 可选系统自检 API：`http://127.0.0.1:8000/system/readiness`

说明：
- `dashboard-main` 是正式展示页。
- `dashboard` 仅作为历史页面保留，不作为答辩主入口。

## 3. 演示账号

- 管理员：`admin / admin123`
- 教师：`teacher1 / 123456`
- 学生：`student1 / 123456`
- 学生：`student2 / 123456`

## 4. 5 分钟演示路径

1. 登录 `/login`
2. 进入 `/dashboard-main`
3. 提交一条借用申请（学生）
4. 审批通过（教师/管理员）
5. 执行归还（正常或异常）
6. 查看“异常闭环任务”和“系统预警”
7. 在“智能体助手”演示确认执行与执行链路
8. 如需环境诊断，单独调用 `/system/readiness`（可选）

## 5. 常用命令

重置演示数据：

```bash
del smart_lab.db
python -m app.seed
```

生成决赛固定场景数据（推荐演示前执行）：

```bash
python -m app.seed_scenarios
```

运行回归测试：

```bash
py -m pytest -q
```

清理缓存与临时产物（推荐每次演示前执行）：

```powershell
pwsh ./scripts/maintenance/cleanup_workspace.ps1
```

项目结构说明：`docs/PROJECT_STRUCTURE.md`

文档总导航：`docs/README.md`
