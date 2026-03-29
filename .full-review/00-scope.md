# Review Scope

## Target

ServerHub 全项目深度审查 — 检查前后端代码规范统一性、后端功能前端覆盖度、安全与性能问题。

## Backend (Python/FastAPI)

- `modules/` — 15 个模块 (agents, assets, audit, cron, dashboard, docker, logs, monitoring, network, notifications, panel_users, playbooks, proxy, servers, services, settings, users)
- `modules/agents/teams/` — 新增智能体组队系统
- `database.py` — SQLite schema (34+ 张表)
- `main.py` — 启动入口 + lifespan
- `config.py` — 全局配置
- `auth/` — JWT 认证
- 共 128 个 Python 文件

## Frontend (React 18 + TypeScript + Tailwind CSS)

- `frontend/src/pages/` — 17 个页面组件
- `frontend/src/components/` — 布局/侧边栏/TopBar
- `frontend/src/hooks/` — useSSEChat, useWebSocket 等
- `frontend/src/api/` — Axios client
- `frontend/src/stores/` — Zustand stores
- 共 55 个 TS/TSX 文件

## Review Focus

1. **代码规范统一性** — 前后端命名、风格、API 约定是否一致
2. **功能覆盖度** — 后端 API 端点是否全部有对应的前端页面/交互
3. **安全审计** — OWASP Top 10, 认证/授权, 输入验证
4. **性能分析** — N+1 查询, 前端渲染, 打包体积
5. **架构一致性** — 模块模式, 路由约定, 状态管理

## Flags

- Security Focus: no
- Performance Critical: no
- Strict Mode: **yes**
- Framework: **react**

## Review Phases

1. Code Quality & Architecture
2. Security & Performance
3. Testing & Documentation
4. Best Practices & Standards
5. Consolidated Report
