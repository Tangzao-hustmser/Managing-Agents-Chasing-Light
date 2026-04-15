# 报告目录说明

本目录用于存放“脚本自动生成”的结果报告，原则上不手工编辑。

## 当前关键文件

- `agent_eval_latest.json`  
  智能体能力评测得分。
- `kpi_dashboard_latest.json`  
  KPI 看板数据。
- `defense_reports_summary.json`  
  答辩报告摘要索引。
- `finals_release_check.json`  
  决赛总验收结果。
- `finals_pipeline_summary.json`  
  一键流水线执行摘要。

## 生成命令

```bash
py -m scripts.finals.run_finals_pipeline --output-dir docs/reports --kpi-days 30
```

## 说明

- 文件会被新一轮执行覆盖，属于可再生产物。
- 若需留存历史快照，建议复制到带日期后缀的文件名。
