# 项目状态（决赛版）

## 当前状态

- 后端服务：可启动
- 正式前端：`/dashboard-main`
- 智能体：支持确认执行与 `analysis_steps`
- 自检：支持 `/system/readiness`

## 推荐访问路径

1. `http://127.0.0.1:8000/login`
2. `http://127.0.0.1:8000/dashboard-main`
3. `http://127.0.0.1:8000/docs`

## 默认演示账号

- `admin / admin123`
- `teacher1 / 123456`
- `student1 / 123456`
- `student2 / 123456`

## 快速检查清单

- 能登录并进入 `dashboard-main`
- 学生可提交申请，教师/管理员可审批
- 归还后库存与状态正确变化
- 闭环任务与预警可见、可处理
- 智能体可执行确认动作并显示执行链路
- readiness 返回 score/checks/recommendations

## 回归测试

```bash
py -m pytest -q
```

## 决赛场景重置（可选）

```bash
python -m app.seed_scenarios
```
