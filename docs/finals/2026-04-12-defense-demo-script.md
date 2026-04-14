# 决赛 8-10 分钟演示脚本（P3-3）

## 0. 演示前准备（1 分钟内）

1. 初始化固定场景（可选）：`python -m app.seed_scenarios`
2. 启动服务：`py -m uvicorn app.main:app --reload`
3. 导出证据报告：`py -m scripts.finals.export_defense_reports --output-dir docs/reports --kpi-days 30`
4. 打开页面：`http://127.0.0.1:8000/dashboard-main`
5. 运行总验收检查：`py -m scripts.finals.run_release_checks --output docs/reports/finals_release_check.json`
6. 或直接单命令：`py -m scripts.finals.run_finals_pipeline --output-dir docs/reports --kpi-days 30`

## 1. 讲解节奏（8-10 分钟）

| 时间 | 操作 | 讲解重点 | 预期可见结果 |
|---|---|---|---|
| 00:00-00:40 | 开场说明命题D | 系统目标是“治理型智能体”，不是普通问答 | 明确三类痛点：占用不均/浪费/丢失 |
| 00:40-01:30 | 展示 `/system/readiness` | 先做可行性自检，保证现场稳定 | readiness 分数与建议 |
| 01:30-03:00 | 在智能体输入“按建议补货，生成补货审批单”并确认 | 智能体能“提议动作 -> 显式确认 -> 执行” | `pending_action` + `executed_tools` |
| 03:00-04:20 | 调用 `POST /enhanced-agent/ask` | 多智能体协作创新（调度/治理/证据代理） | `multi_agent_trace` + `orchestration_summary` |
| 04:20-05:30 | 展示盘点证据入口 `/files/evidence/inventory-vision` | 多模态证据融合，低置信自动建议复核 | `recognition_confidence`、`disagreement_index` |
| 05:30-06:30 | 展示公平策略接口 `/scheduler/fairness-policy` | 公平治理可配置、可解释 | 策略参数 + 排程解释字段 |
| 06:30-07:40 | 展示 `docs/reports/kpi_dashboard_latest.json` | 实用性量化：KPI 基线/当前/趋势 | 五个 KPI 指标与趋势 |
| 07:40-08:40 | 展示 `docs/reports/agent_eval_latest.json` | 每次改动可回归评分，保证能力稳定 | 五类能力 100 分 |
| 08:40-09:30 | 总结与落地 | 问题-方案-结果闭环，技术可行可复制 | 结论页 |

## 2. 现场口播要点（可直接读）

1. “我们的系统不是只回答问题，而是能给出治理动作并在确认后执行。”  
2. “这一步展示的是多智能体协作轨迹，评委可以看到调度、治理、证据三路分工。”  
3. “这里用 KPI 和能力评测集证明系统不仅可演示，而且可量化、可回归。”  
4. “即使外部大模型不可用，也会回退到规则+业务工具，保证现场稳定。”  

## 3. 失败兜底话术

- 若智能体外部模型超时：  
“当前自动回退到本地规则引擎，核心业务动作仍可执行，我们继续演示闭环能力。”  

- 若页面加载波动：  
“我切换到 Swagger 接口演示，同一后端能力，证据链和日志结果保持一致。”  

- 若时间被压缩到 4 分钟：  
“我走最小闭环：readiness -> 智能体执行动作 -> 多智能体轨迹 -> KPI+agent_eval。”  

## 4. 演示后可提交材料

- `docs/finals/2026-04-12-defense-evidence-chain.md`
- `docs/finals/2026-04-12-defense-ppt.md`
- `docs/finals/2026-04-12-competition-requirements-checklist.md`
- `docs/finals/2026-04-12-defense-ppt-outline.md`
- `docs/reports/defense_reports_summary.json`
- `docs/reports/agent_eval_latest.json`
- `docs/reports/kpi_dashboard_latest.json`
- `docs/reports/finals_release_check.json`
- `docs/reports/finals_pipeline_summary.json`
