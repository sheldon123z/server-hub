# Changelog

ServerHub 变更日志，按时间倒序排列。

---

## 2026-03-29

### docs: Issue #25 — 文档更新

- 修正前端技术栈引用（Jinja2/HTMX/Alpine.js -> React 19 + TypeScript + Tailwind CSS + Vite）
- 更新数据库文档表数（16 -> 36，含 FTS5）
- 创建 servers 模块 API 文档 (`docs/api/servers.md`)
- 补全模块列表（servers、playbooks）
- 更新工具数量（22 -> 50）和 SubAgent 数量（4 -> 6）
- 更新 AGENTS.md 架构引用为 React SPA
- architecture.md 补充多服务器架构和运维剧本引擎章节

## 2026-03-28

### feat: P0 工程基建

- Ruff 配置统一代码风格
- 日志持久化机制
- 数据库备份 cron job
- Pre-commit hooks

## 2026-03-27

### fix: Issue #27 — 前端优化

- 包体积拆分（React.lazy 代码分割）
- ErrorBoundary 全局错误边界
- TypeScript 类型安全加固

### fix: Issue #26 — 代码质量统一化

- 修复吞异常问题
- f-string 日志格式化
- API 规范一致性

### fix: Issue #23 — 安全加固 Phase 1

- 速率限制
- 安全响应头
- Agent Teams 沙箱加固

### feat: Issue #24 — CI/CD 流水线

- GitHub Actions CI/CD
- systemd 服务加固
- SQLite 自动备份
- workers 断言保护

### fix: Issue #22 — P0 Bug 修复

- quota 签名校验
- SQL 注入防护
- 路径穿越修复

## 2026-03-26

### feat: 智能体组队系统 (Agent Teams)

- 三种拓扑编排引擎（Pipeline / Debate / MapReduce）
- 团队成员管理和消息通信
- 执行记录和状态追踪

### feat: Agent Studio Skills Runtime

- Agent Studio 运行时
- Skill 安装/版本管理体系
- Run 生命周期管理

## 2026-03-25

### fix: Issues #14/#16/#17

- 远程监控功能完善
- 性能优化
- 可访问性改进

### feat: 多服务器管理 Phase 1-4

- Hub-Agent 架构实现
- 服务器注册/分组/心跳
- Agent Client (Fernet Token 加密鉴权)
- 远程指标采集 (并行 executemany)
- Fleet Dashboard 舰队总览
- server_id 全栈贯穿

### feat: 全站 React 前端迁移

- Jinja2 + HTMX + Alpine.js -> React 19 + TypeScript + Tailwind CSS
- React Router v7 (19 条路由 + 代码分割)
- TanStack Query + Zustand 状态管理
- SSE 流式对话 + WebSocket 实时指标
- AI 对话增强 + 运维剧本系统
