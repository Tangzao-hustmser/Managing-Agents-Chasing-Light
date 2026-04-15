# 项目目录结构说明

本文件用于统一项目结构认知，减少“文件散乱、入口不清、临时产物混入”的问题。

## 1. 顶层目录职责

```text
Managing-Agents-Chasing-Light/
├─ app/                  # FastAPI 应用（路由、服务、模型、静态页面）
├─ tests/                # pytest 测试
├─ scripts/              # 自动化脚本（决赛流程、维护脚本）
├─ docs/                 # 使用文档、计划、答辩材料、报告
├─ agent_eval/           # 智能体评测集与评测脚本
├─ README.md             # 项目总入口
├─ START_HERE.md         # 快速启动入口
├─ requirements.txt      # Python 依赖
└─ pytest.ini            # pytest 配置
```

## 2. app 目录分层

```text
app/
├─ main.py               # 应用入口与路由挂载
├─ config.py             # 配置项定义
├─ database.py           # 数据库初始化与迁移补丁
├─ models.py             # SQLAlchemy 模型
├─ schemas.py            # Pydantic schema
├─ seed.py               # 基础演示数据
├─ seed_scenarios.py     # 决赛固定场景数据
├─ routers/              # API 路由层（按业务模块拆分）
├─ services/             # 业务服务层（规则、调度、审计、通知等）
└─ static/               # 前端页面（login / dashboard-main）
```

## 3. docs 目录建议

```text
docs/
├─ README.md             # 文档总导航
├─ USAGE.md              # 接口与使用说明（主文档）
├─ TESTING.md            # 测试说明
├─ PROJECT_STRUCTURE.md  # 本文件（结构说明）
├─ archive/              # 历史材料归档（非主流程）
├─ plans/                # 规划与执行计划
├─ finals/               # 答辩材料
└─ reports/              # 生成型报告（流水线输出）
```

建议：

- `docs/reports/` 只放“机器生成结果”。
- 过程性说明统一归档到 `docs/plans/`，避免散落到根目录。
- 非主流程但需要保留的历史文件统一放到 `docs/archive/`。
- 建议从 `docs/README.md` 进入，按角色（开发/答辩/评估）选择阅读路径。

## 4. 维护规范

- 不把 `__pycache__`、`.pytest_cache`、临时 DB、日志提交到仓库。
- 运行前后若目录变脏，执行清理脚本：

```powershell
pwsh ./scripts/maintenance/cleanup_workspace.ps1
```

- 如需连数据库一起清理（会删 `smart_lab.db`）：

```powershell
pwsh ./scripts/maintenance/cleanup_workspace.ps1 -IncludeDatabases
```

## 5. 最小根目录原则

根目录仅保留：

- 启动入口文档（`README.md`、`START_HERE.md`）
- 依赖与测试配置（`requirements.txt`、`pytest.ini`）
- 核心源码和文档目录（`app/`、`tests/`、`scripts/`、`docs/`、`agent_eval/`）

其他阶段性材料优先放到 `docs/` 下对应子目录，避免顶层继续膨胀。
