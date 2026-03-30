# Changelog

ServerHub 变更日志，按时间倒序排列。

---

## 2026-03-30

### docs: 全面更新文档体系

- 更新全部 9 个文档文件，同步 66 个 commit 的变更
- 新增：一键部署 API 文档、RoboRev 管道说明、Agent Teams 安全机制
- 更新：工具计数（49 自定义 + 14 子模块）、数据库表计数（36+1 FTS5）、前端路由表（21 条）
- 新增：Smoke Test、Cookie 安全配置、systemd 安全加固说明

### feat: Agent Studio 增强

- Skills 详情面板：版本历史、安装状态、绑定关系
- SubAgents 在线编辑：工具集、模型、提示词配置
- TS 类型修复（`ensureArray unknown[]` 兼容）

### feat: 一键部署远程服务器

- `POST /api/servers/deploy` 端点：注册 → SSH 安装 Agent → 验证连通
- 前端部署向导 UI：SSH 密码输入 + 自动部署 + 日志实时显示
- `scripts/add-server.sh` 命令行一键部署脚本
- SSH 密码认证修复（`client_keys=[]` + `preferred_auth` 强制密码优先）

### feat: RoboRev 自动评审管道

- commit 级自动代码评审（Claude Code hook）
- 评审发现自动创建 Issue → 触发 Claude Code 后台修复 → 生成 PR
- worktree 隔离运行，避免与用户工作冲突
- 无限循环防护（roborev 自身 commit 不触发评审）
- `gh-cleanup.sh` 每小时自动合并/关闭 roborev PR + 清理分支

### feat: Smoke Test 集成验证

- `scripts/smoke-test.sh` 关键端点健康检查
- 支持指定地址测试，退出码 0/1

### feat: 前端聊天 UX 优化

- 智能滚动：`requestAnimationFrame` 合并 + `isNearBottom` 阈值检测
- 草稿保存：Zustand 持久化未发送内容
- 删除确认：消息/对话删除前弹 confirm
- `React.memo` 优化 MessageBubble 组件
- 工具卡片改进：风险级别标签 + 可折叠
- 快捷指令分组显示

### fix: Agent Teams 安全加固

- 成员工具权限隔离：`user_role` 贯穿图构建全链路
- Swarm handoff 循环检测：`deque` 滑动窗口替代 list，修复单 agent 误触发
- 异步执行超时保护：deadline 机制
- 团队工具安全层：Shell 黑名单 + DANGER 阻止 + 环境变量剥离

### fix: 全栈修复合集

- SPA catch-all 覆盖 API 路由的严重 Bug 修复
- Cookie Secure 默认值改回 `auto`，修复 HTTP 环境登录失败
- Agent 401 认证修复 + systemd API keys 加载
- systemd `NoNewPrivileges=no` 允许 sudo 读 root crontab
- `CapabilityBoundingSet` 补偿控制
- Terminal resize JSON 解析修复
- 前端构建修复（tsconfig + NetworkPage undefined 防护）

### refactor: 架构重构

- monitoring 模块分层（scheduler/metrics_store/collectors）
- chat.py 拆分为 9 个 routes 子模块
- init_tables 拆分为独立函数

### perf: 性能优化

- SQLite pragma 调优（WAL + cache_size）
- `metrics_latest` 表避免全量查询
- CPU 采集优化
- Agent checkpoint 定期清理

### test: 测试覆盖补全

- Auth 模块测试
- Agent Teams 安全专项测试
- 前端 Vitest 测试框架接入

### fix: 安全加固 Phase 2

- Docker exec 命令过滤
- Terminal WebSocket 限制
- TLS 支持

### chore: 代码质量

- Ruff 全部 125 个存量 lint issue 清零
- 代码格式化自动化（Claude hook）
- CI/CD 修复（manualChunks + Ruff 豁免）

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
