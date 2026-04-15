# 登录与入口说明（统一版）

## 正式入口

- 登录页：`http://127.0.0.1:8000/login`
- 控制台：`http://127.0.0.1:8000/dashboard-main`

## 默认账号

- 管理员：`admin / admin123`
- 教师：`teacher1 / 123456`
- 学生：`student1 / 123456`
- 学生：`student2 / 123456`

## 说明

- 答辩与正式演示统一使用 `/dashboard-main`。
- `/dashboard` 为历史页面，不作为主展示路径。
- 登录后 token 保存在浏览器 `localStorage`，受保护接口自动携带 `Authorization`。

## 常见问题

1. 登录失败：先确认是否执行过 `python -m app.seed`。
2. 页面无法访问：确认服务是否已启动在 `:8000`。
3. token 失效：重新登录即可。
