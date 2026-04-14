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

Windows PowerShell 若提示找不到 `python`，请改用：

```bash
py -m uvicorn app.main:app --reload
```

如果你是 Linux/macOS，可将 `copy` 改为：

```bash
cp .env.example .env
```

### 2.3 初始化演示数据（可选）

```bash
python -m app.seed
```

如果你要做决赛演示，建议使用固定场景数据（可复现借还/损坏/丢失/逾期）：

```bash
python -m app.seed_scenarios
```

### 2.4 访问入口

- Swagger：`http://127.0.0.1:8000/docs`
- 登录页：`http://127.0.0.1:8000/login`
- 主控制台：`http://127.0.0.1:8000/dashboard-main`

## 3. 项目核心能力

- 资源双层模型：`Resource`（类型库存）+ `ResourceItem`（设备实例）
- 管理端资源治理：支持资源新增、编辑与删除（归档）
- 全流程闭环：借用、领用、审批、归还、补货、报失、异常追踪
- 闭环任务中心：异常自动生成 `FollowUpTask`，支持查询、跟进、完成
- 闭环任务审计：支持 `updated_at/closed_at/result/outcome_score` 与 SLA 升级追踪
- 智能体执行：不仅问答，还可发起业务动作（确认后执行）
- 治理建议可执行：支持“按建议补货”一键生成补货审批单
- 调度推荐：支持“有无空档 + 推荐时段 + 推荐理由”
- 公平治理调度：支持黄金时段配额、连续占用限制、高频用户降权策略并可配置
- 治理分析：公平性、逾期未还、异常评分、预计 vs 实际偏差
- 证据链：支持文件证据与盘点视觉入口（Qiniu），高风险动作缺证据会自动生成补证任务
- 多智能体协作视图：增强路由可返回调度/治理/证据代理协作轨迹与汇总决策
- 多模态盘点融合：融合人工计数、OCR 文本和证据元数据，输出置信度与分歧指数
- 主动通知闭环：关键事件自动写入通知投递日志（待审批、超期任务、补证任务）
- 预警降噪去重：同类事件按窗口去重并累计 `occurrence_count`

## 4. 智能体与大模型能力

### 4.1 智能体入口

- 稳定聊天入口：`POST /agent/chat`
- 增强工具代理：`POST /enhanced-agent/ask`
- 决赛诊断入口：`GET /system/readiness`
- 公平策略配置：`GET/PATCH /scheduler/fairness-policy`

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

### 4.3 智能体可解释链路（决赛展示友好）

`/agent/chat` 与 `/enhanced-agent/ask` 响应新增 `analysis_steps`，展示高层“感知-推理-执行”步骤，便于答辩时说明：

- 如何识别输入意图和资源对象
- 如何基于冲突/容量/评分做排程推理
- 为什么给出当前推荐时段或治理建议

## 5. 推荐展示路径

1. 登录 `/login`
2. 进入 `/dashboard-main`
3. 查看资源、审批、预警与流水
4. 查看闭环任务列表并演示状态流转（open → in_progress → done）
5. 通过智能体提问空档/治理建议或执行“完成任务 #ID”
6. 演示确认执行（如借用申请、审批、闭环任务处理）
7. 查看增强分析 `GET /enhanced-analytics/comprehensive`

## 6. 测试

运行：

```bash
pytest -q
```

建议在提交前运行全量回归，确保新增功能通过。

智能体能力评测集（P3-2）回归评分：

```bash
py -m agent_eval.run_eval --output docs/reports/agent_eval_latest.json --fail-under 100
```

该命令会执行 `agent_eval/cases.json`，输出总分与分类分（问答、执行、拒绝、澄清、异常处理）。

决赛总验收（建议答辩前执行）：

```bash
py -m scripts.finals.run_release_checks --output docs/reports/finals_release_check.json
```

该验收会包含比赛四条要求自动核查项：`competition_requirements_4x`。

决赛一键流水线（推荐，单命令生成全部答辩报告并做总验收）：

```bash
py -m scripts.finals.run_finals_pipeline --output-dir docs/reports --kpi-days 30
```

## 7. 文档入口

- 使用说明：[docs/USAGE.md](docs/USAGE.md)
- 测试文档：[docs/TESTING.md](docs/TESTING.md)
- 头脑风暴与优化路径：[docs/BRAINSTORM_OPTIMIZATION_2026-03-31.md](docs/BRAINSTORM_OPTIMIZATION_2026-03-31.md)
- 决赛答辩资产包：
  - [docs/finals/2026-04-12-defense-evidence-chain.md](docs/finals/2026-04-12-defense-evidence-chain.md)
  - [docs/finals/2026-04-12-defense-ppt-outline.md](docs/finals/2026-04-12-defense-ppt-outline.md)
  - [docs/finals/2026-04-12-defense-ppt.md](docs/finals/2026-04-12-defense-ppt.md)
  - [docs/finals/2026-04-12-defense-demo-script.md](docs/finals/2026-04-12-defense-demo-script.md)
  - [docs/finals/2026-04-12-competition-requirements-checklist.md](docs/finals/2026-04-12-competition-requirements-checklist.md)

## 8. 本轮优化（2026-03-31）

- 新增闭环任务 API：
  - `GET /follow-up-tasks`
  - `PATCH /follow-up-tasks/{task_id}`
- 智能体新增闭环任务能力：
  - 可查询闭环任务
  - 可通过确认链路执行“任务处理中/任务完成”
- 控制台新增“异常闭环任务”看板：
  - 教师/管理员可看全局任务
  - 学生可看并处理自己被指派的任务
- 新增自动化测试：`tests/test_follow_up_tasks.py`

## 9. 稳定性优化（2026-04-01）

- 修复设备类库存调整失败问题：
  - 管理员可在库存调整入口直接调整设备类资源（如万用表）
  - 后端自动走实例协调逻辑并保留 `adjust` 审计流水
- 修复库存调整界面“自动刷新打断编辑”问题：
  - 轮询在输入中自动暂停
  - 资源下拉与已编辑状态在刷新后保持稳定，不再跳回首项
- 修复学生归还时报错 `offset-naive vs offset-aware datetimes`：
  - 后端统一将入参时间规范为 UTC 无时区格式再比较/入库
  - 覆盖前端 `toISOString()` 场景，归还流程可正常完成

## 10. 决赛增强（2026-04-09）

- 智能体时间理解增强：
  - 新增对 `下周三下午3点半`、`周X`、`大后天`、`YYYY-MM-DD` 等表达的解析
  - 排程建议在语义理解后再做冲突与评分
- 智能体可解释性增强：
  - 问答响应新增 `analysis_steps`（感知-推理-执行），更符合“智能体”评审标准
- 工程稳定性增强：
  - 新增 `GET /system/readiness`，输出 readiness score、核心检查项、演示建议
  - 新增 `pytest.ini`，统一测试入口为 `tests/`，避免非测试脚本被误收集影响评测
- 管理端可用性增强：
  - 资源总览新增子类展示和显式“编辑/删除”操作按钮
  - 新增“撤回上次删除”与归档资源恢复，降低管理员误操作恢复成本
  - 库存调整支持“仅修改可用量”即可提交，不要求总量与可用量同时变化
  - 系统预警新增“确认/消除”处置操作，支持未闭环预警快速治理

## 11. 决赛治理增强（2026-04-12）

- 自动治理建议 -> 动作：
  - 智能体支持将治理建议直接落地为动作（如“按建议补货”生成补货审批单）
  - 新增执行动作：`create_replenish_approval`
- 证据链可信度增强：
  - `报失登记`、`异常归还（damaged/partial_lost）`、`盘点`缺少证据字段时自动生成 `evidence_backfill` 任务
  - 同时生成 `evidence_missing` 预警，便于治理闭环追踪

## 12. 决赛创新增强（2026-04-12）

- 多智能体协作（P2-2）：
  - `POST /enhanced-agent/ask` 新增 `multi_agent_trace` 与 `orchestration_summary`
  - 内置调度代理、治理代理、证据代理三路分工，并输出统一建议
- 多模态盘点增强（P2-1）：
  - `POST /files/evidence/inventory-vision` 新增融合字段：`recognition_confidence`、`recognized_sources`、`extracted_candidates`、`disagreement_index`
  - 识别置信度低或多源分歧大时给出人工复核建议

## 13. 决赛工程增强（2026-04-12）

- 主动通知闭环（P2-3）：
  - 新增 `NotificationDelivery` 投递日志
  - 新增查询接口：`GET /notifications/deliveries`（教师/管理员）
  - 关键事件自动触发通知：`approval_pending`、`follow_up_sla_overdue`、`evidence_backfill_required`
- 并发与一致性治理（P2-4）：
  - 审批、归还、库存调整接口支持 `Idempotency-Key`，重复提交可重放首个成功响应
  - 关键写路径增加实体级写锁，避免并发场景库存与状态漂移
  - 新增并发与幂等测试覆盖：`tests/test_idempotency_concurrency.py`
- 预警降噪与去重（P2-5）：
  - 新增告警去重键 `dedup_key`、`last_seen_at`、`occurrence_count`
  - 同类高频告警窗口去重，避免短时间重复刷屏
- 安全与审计强化（P2-6）：
  - 新增 `AuditLog` 与查询接口 `GET /audit-logs`（教师/管理员）
  - 关键写接口接入操作审计（审批、归还、库存调整、告警处置、闭环任务更新）
  - 新增关键写接口限流（超限返回 `429` + `Retry-After`）
  - 新增测试覆盖：`tests/test_security_audit.py`
- 评测指标体系（P3-1）：
  - 新增 KPI 看板接口：`GET /analytics/kpi-dashboard`
  - 固化指标字典：利用率、逾期率、浪费率、报失率、公平指数
  - 每个 KPI 输出基线值、当前值、改善值、改善百分比与解释文本
  - 新增测试覆盖：`tests/test_kpi_dashboard.py`
- 智能体能力评测集（P3-2）：
  - 新增评测数据集：`agent_eval/cases.json`
  - 新增回归评分脚本：`py -m agent_eval.run_eval`
  - 覆盖问答、执行、拒绝、澄清、异常处理五类能力
  - 新增测试覆盖：`tests/test_agent_eval_suite.py`
