# ServerHub 产品级功能设计文档

> 日期: 2026-04-05
> 目标: 将 ServerHub 从个人实验室工具升级为可通用部署的服务器管理平台
> 部署规模: 单机 → 中等规模 (50台)，功能按需解锁
> 安装方式: Docker one-liner + 脚本安装双路径

---

## 实施策略

**方案: 基础设施优先**

```
Phase 1: RBAC 权限矩阵           ← 所有功能的权限基座
Phase 2: 统一运维监控与告警平台    ← 替代散落的 Bash 脚本，系统化收编
Phase 3: Web 文件管理器           ← 图形化文件浏览/编辑/上传
Phase 4: Fleet 批量操作           ← 多服务器并行执行与进度追踪
```

依赖链: Phase 1 → Phase 2/3/4 (RBAC 是基座，后三者可半并行)

---

## Phase 1: RBAC 权限矩阵

### 问题

当前只有 `admin` / `user` 二元角色，硬编码在 `require_role("admin")` 中:
- 不能创建"只管 Docker 不碰用户管理"的运维角色
- 不能限制某个用户只能看到特定服务器
- Agent 工具权限与 Web API 权限是两套独立逻辑
- 通用部署时每个团队的权限需求都不同

### 数据模型

**角色 → 权限集 → 资源范围**:

```
User ──M:N──> Role ──1:N──> Permission
                              ├── resource: docker|services|users|cron|servers|files|agents|alerts|system
                              ├── action:   read|write|execute|admin
                              └── scope:    *|server:srv-01|path:/home/*|group:production
```

### 数据库表

```sql
CREATE TABLE roles (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT,
    description TEXT,
    builtin INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE role_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id TEXT REFERENCES roles(id) ON DELETE CASCADE,
    resource TEXT NOT NULL,
    action TEXT NOT NULL,
    scope TEXT DEFAULT '*',
    UNIQUE(role_id, resource, action, scope)
);

CREATE TABLE user_roles (
    user_id TEXT NOT NULL,
    role_id TEXT REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);
```

### 内置角色

| 角色 | 权限 | 场景 |
|------|------|------|
| `super-admin` | 全部资源 * 全部操作 | 系统管理员 |
| `operator` | docker/services/cron/servers + read/write/execute | 运维人员 |
| `viewer` | 全部资源 + read only | 只读监控 (当前 user 角色升级) |
| `agent-user` | agents + read/execute, system + read | 只能用 AI 助手 |

管理员可创建自定义角色 (如 `docker-admin`、`server-group-a-ops`)。

### 权限检查接口

```python
# 新的依赖注入 — 替代 require_role()
def require_permission(resource: str, action: str = "read"):
    async def checker(user=Depends(get_current_user)):
        if not await has_permission(user["id"], resource, action):
            raise HTTPException(403, f"缺少权限: {resource}:{action}")
        return user
    return Depends(checker)

# 向后兼容: require_role("admin") 内部映射为 has_permission("*", "admin")
```

### Agent 工具权限统一

工具通过 metadata 声明所需权限:
```python
@tool(metadata={"resource": "docker", "action": "write"})
async def docker_container_action(...): ...
```

`get_server_tools(user_id)` 按 RBAC 权限过滤:
```python
def get_server_tools(user_id: str) -> list:
    permissions = get_user_permissions(user_id)
    return [t for t in all_tools if tool_matches_permissions(t, permissions)]
```

### 迁移策略

- 现有 `admin` 用户 → 自动分配 `super-admin`
- 现有 `user` 用户 → 自动分配 `viewer`
- `require_role("admin")` 保持工作，内部映射
- 零停机: `init_tables()` 检测旧表 → 创建角色表 → 迁移用户

### 前端

- 角色管理页: `/settings/roles` — CRUD + 权限矩阵勾选表
- 用户管理增强: 用户详情中分配角色
- 侧边栏: 按权限动态过滤菜单项

---

## Phase 2: 统一运维监控与告警平台

### 目标

将散落在 `~/scripts/` 的 Bash 脚本功能完全系统化收编到 ServerHub 中。脚本保留作为备份，只去除 cron 调度。

### 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                    ServerHub 统一运维平台                    │
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │
│  │ 指标采集引擎 │  │ 告警评估引擎 │  │ 自动化动作引擎      │  │
│  └─────┬──────┘  └──────┬─────┘  └─────────┬──────────┘  │
│        ▼               ▼                   ▼              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              统一通知分发管道                          │  │
│  │  Telegram | 站内通知 | Webhook | (未来: 邮件/IM)     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              前端: 运维中心                            │  │
│  │  告警面板 | 通知中心 | 规则管理 | 每日报告 | 历史     │  │
│  └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 2.1 指标采集引擎

扩展现有 `modules/monitoring/scheduler.py` 的 60s 采集循环:

| 采集项 | 替代的脚本 | 间隔 |
|--------|-----------|------|
| CPU/内存/Swap/磁盘/网络 | `server-health-check.sh` | 60s (已有) |
| GPU 使用率/显存/温度 | `gpu-monitor.sh` | 60s (已有) |
| 每用户资源用量 | `monitor-all-users.sh` | 60s |
| Docker 容器状态/资源 | `docker-watchdog.sh` | 60s |
| 进程 Top N | `long-running-processes.sh` | 300s |
| 用户空闲检测 | `idle-user-monitor.sh` | 300s |
| Systemd 服务状态 | 新增 | 120s |

采集器采用插件化架构:

```python
# modules/monitoring/collectors/
collectors/
├── __init__.py        # CollectorRegistry 自动发现
├── base.py            # BaseCollector ABC
├── system.py          # CPU/内存/Swap/磁盘/网络 (重构已有)
├── gpu.py             # GPU 指标 (重构已有)
├── user_resources.py  # 每用户资源用量 (新)
├── docker.py          # 容器状态/重启次数 (新)
├── services.py        # Systemd 服务状态 (新)
└── processes.py       # Top N + 长时间运行进程 (新)

class BaseCollector(ABC):
    name: str
    interval_seconds: int = 60
    
    @abstractmethod
    async def collect(self, server_id: str = "local") -> list[MetricPoint]: ...
```

### 2.2 告警规则引擎

```sql
CREATE TABLE alert_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    -- 目标
    resource TEXT NOT NULL,
    server_scope TEXT DEFAULT '*',
    -- 条件
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold REAL,
    duration_seconds INT DEFAULT 60,
    -- 行为
    severity TEXT DEFAULT 'warning',
    cooldown_seconds INT DEFAULT 300,
    -- 自动化动作
    auto_action TEXT,
    auto_action_config TEXT,
    -- 通知
    notification_channels TEXT,
    notification_template TEXT,
    -- 审计
    created_by TEXT,
    updated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT REFERENCES alert_rules(id),
    server_id TEXT DEFAULT 'local',
    status TEXT NOT NULL,
    value REAL,
    message TEXT,
    fired_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMP
);
```

**内置告警规则 (替代脚本硬编码阈值)**:

| # | 规则 | 替代 | 严重度 | 自动动作 |
|---|------|------|--------|---------|
| 1 | Swap > 50% 持续 5min | `swap-alert.sh` | warning | - |
| 2 | 用户内存 > 配额 | `memory-emergency.sh` | critical | kill_user_processes |
| 3 | 容器异常退出 > 3次/h | `docker-watchdog.sh` | warning | - |
| 4 | 用户空闲 > 6h | `idle-user-monitor.sh` | info | notify_user |
| 5 | 磁盘 > 85% | 新增 | warning | - |
| 6 | 磁盘 > 95% | 新增 | critical | - |
| 7 | GPU 温度 > 85C | 新增 | critical | - |

**告警状态机**:

```
OK ──(条件满足 duration)──> Pending ──(确认)──> Firing ──(条件恢复)──> Resolved
                                                  │
                                             auto_action
                                             通知发送
                                             cooldown
```

### 2.3 统一通知管道

```python
# modules/notifications/
notifications/
├── __init__.py
├── dispatcher.py      # 通知分发器
├── channels/
│   ├── base.py        # BaseChannel ABC
│   ├── telegram.py    # Telegram Bot API (原生 Python, 替代 shell 脚本)
│   ├── inapp.py       # 站内通知 (WebSocket + DB)
│   └── webhook.py     # 通用 Webhook (JSON POST)
├── templates.py       # 模板引擎 (支持 {{metric}}/{{value}}/{{threshold}} 变量)
└── digest.py          # 每日摘要生成器 (替代 --morning-report)
```

**通知渠道配置**:
```sql
CREATE TABLE notification_channels (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    config TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    test_status TEXT,
    created_by TEXT
);
```

**站内通知**:
```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    severity TEXT DEFAULT 'info',
    read INTEGER DEFAULT 0,
    related_alert_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**每日早报** (替代 `send-telegram-report.sh --morning-report`):
通过特殊告警规则调度 (每天 08:00)，聚合 24h 内关键指标和告警。

### 2.4 前端运维中心

| 组件 | 路由 | 功能 |
|------|------|------|
| 告警面板 | `/alerts` | 活跃告警 + 历史 + 趋势图 |
| 规则管理 | `/alerts/rules` | CRUD + 启停 + 测试 |
| 通知渠道 | `/settings/channels` | 渠道配置 + 发送测试 |
| 通知中心 | TopBar 铃铛 | 未读列表 + 标记已读 |
| 每日报告 | `/reports/daily` | 历史早报 + 手动生成 |
| Dashboard 增强 | 现有页面 | 阈值线叠加 + 告警卡片 |

### 2.5 Agent 集成

```python
@tool(metadata={"resource": "alerts", "action": "read"})
async def list_active_alerts(...): """查看当前活跃告警"""

@tool(metadata={"resource": "alerts", "action": "write"})
async def acknowledge_alert(...): """确认/静默告警"""

@tool(metadata={"resource": "alerts", "action": "admin"})
async def manage_alert_rule(...): """创建/修改告警规则"""

@tool(metadata={"resource": "notifications", "action": "write"})
async def send_notification_tool(...): """通过指定渠道发送通知"""
```

### 2.6 脚本退役清单

所有脚本保留不删除，只去除 cron 调度:

| 现有脚本 | ServerHub 替代 | 操作 |
|---------|---------------|------|
| `monitoring/swap-alert.sh` | 内置规则 #1 | 去除 cron |
| `monitoring/memory-emergency.sh` | 规则 #2 + auto_action | 去除 cron |
| `monitoring/docker-watchdog.sh` | Docker collector + 规则 #3 | 去除 cron |
| `monitoring/gpu-monitor.sh` | GPU collector + 告警规则 | 去除 cron |
| `monitoring/monitor-all-users.sh` | user_resources collector | 去除 cron |
| `monitoring/server-health-check.sh` | 全部 collectors | 去除 cron |
| `monitoring/long-running-processes.sh` | processes collector | 去除 cron |
| `resource-control/idle-user-monitor.sh` | 规则 #4 + auto_action | 去除 cron |
| `notification/send-telegram-report.sh` | TelegramChannel + DailyDigest | 去除 cron |
| `notification/notify-students.sh` | 通知管道 + InAppChannel | 去除 cron |
| `notification/auto-notify-logout.sh` | auto_action: notify_then_logout | 去除 cron |

迁移策略: 每替代一个脚本，先并行运行 1 周验证结果一致，再去除 cron 条目。

---

## Phase 3: Web 文件管理器

### 核心能力

| 功能 | 说明 |
|------|------|
| 目录浏览 | 树形/列表视图，排序 (名称/大小/时间) |
| 文件预览 | 代码高亮、Markdown 渲染、图片、日志 tail |
| 文件编辑 | Monaco Editor，保存即写入 |
| 上传/下载 | 拖拽上传、批量 zip 下载 |
| 文件操作 | 新建/重命名/复制/移动/删除、权限查看 |
| 搜索 | 文件名搜索 + 内容 grep |

### 后端 API

```
模块: modules/files/

GET    /api/files/list?path=&sort=name     # 列出目录
GET    /api/files/read?path=               # 读取内容
PUT    /api/files/write                     # 写入/保存
POST   /api/files/upload                    # 上传 (multipart)
GET    /api/files/download?path=            # 下载
POST   /api/files/action                    # mkdir/rename/copy/move/delete
GET    /api/files/search?path=&query=       # 文件名搜索
GET    /api/files/grep?path=&pattern=       # 内容搜索
GET    /api/files/stat?path=                # 元信息
```

### 安全层 (与 RBAC 集成)

三层安全:
1. **RBAC 权限**: `require_permission("files", "read")` / `"write"`
2. **路径范围**: RBAC scope `path:/home/*` 限制可访问目录
3. **敏感文件保护**: `.env`、`.api_keys`、`*.key`、`*.pem` 等始终拒绝

```python
PROTECTED_PATTERNS = [
    "**/.env", "**/.api_keys", "**/.telegram_config",
    "**/config.yaml", "**/*.key", "**/*.pem",
    "**/id_rsa*", "**/.ssh/authorized_keys",
]
```

### 前端

```
pages/files/
├── FileBrowserPage.tsx      # 主页面: 左侧树 + 右侧内容
├── FileTree.tsx             # 懒加载目录树
├── FileList.tsx             # 列表视图
├── FilePreview.tsx          # 预览 (代码/Markdown/图片/日志)
├── FileEditor.tsx           # Monaco Editor
├── FileUpload.tsx           # 拖拽上传
├── FileSearch.tsx           # 搜索
└── FileActions.tsx          # 右键菜单/工具栏
```

布局:
```
┌─────────────────────────────────────────────────┐
│ 路径导航: /home/zhengxiaodong/scripts/          │
│ [上传] [新建] [搜索]                             │
├──────────────┬──────────────────────────────────┤
│ 目录树        │  文件列表 / 预览 / 编辑器         │
│ ├─ home/     │                                   │
│ │  ├─ scripts│                                   │
│ │  └─ exps/  │                                   │
│ └─ var/log/  │                                   │
├──────────────┴──────────────────────────────────┤
│ 状态栏: 23 文件, 4 目录 | 已选 2 项              │
└─────────────────────────────────────────────────┘
```

### 限制

- 预览/编辑: <= 5MB
- 上传: <= 100MB (单文件)
- 下载: <= 500MB (zip 打包)

---

## Phase 4: Fleet 批量操作

### 核心模型

```sql
CREATE TABLE batch_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,              -- command|service_action|docker_action|script|playbook
    payload TEXT NOT NULL,           -- JSON
    server_ids TEXT NOT NULL,        -- JSON array
    strategy TEXT DEFAULT 'parallel', -- parallel|serial|rolling(N)
    rolling_batch_size INT DEFAULT 1,
    stop_on_failure INT DEFAULT 0,
    status TEXT DEFAULT 'pending',
    progress TEXT,                   -- JSON
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE batch_job_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES batch_jobs(id) ON DELETE CASCADE,
    server_id TEXT NOT NULL,
    status TEXT NOT NULL,
    output TEXT,
    error TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER
);
```

### 执行策略

| 策略 | 行为 | 场景 |
|------|------|------|
| `parallel` | 全部并发 | 查状态、采集信息 |
| `serial` | 逐台等待 | 有依赖顺序 |
| `rolling(N)` | 每批 N 台 | 滚动重启 (保可用性) |

### 后端 API

```
POST   /api/servers/batch/execute          # 创建批量任务
GET    /api/servers/batch/{job_id}         # 查询状态
POST   /api/servers/batch/{job_id}/cancel  # 取消
GET    /api/servers/batch/history          # 历史列表
SSE    /api/servers/batch/{job_id}/stream  # 实时进度 (复用 StreamBridge)
```

### 执行引擎

```python
class BatchExecutor:
    async def execute(self, job: BatchJob) -> None:
        if job.strategy == "parallel":
            await self._parallel(job)
        elif job.strategy == "serial":
            await self._serial(job)
        elif job.strategy.startswith("rolling"):
            await self._rolling(job, batch_size=job.rolling_batch_size)
    
    async def _execute_on_server(self, job, server_id):
        # 复用 agent_client.py 结构化端点
```

### 预置模板

| 模板 | 类型 | 默认策略 |
|------|------|---------|
| 批量系统信息 | command | parallel |
| 批量服务重启 | service_action | rolling(1) |
| 批量 Docker 清理 | docker_action | parallel |
| 批量安全检查 | script | parallel |
| 自定义命令 | command | 用户选择 |

### 前端

```
pages/fleet/
├── BatchOperationPage.tsx    # 入口
├── BatchJobWizard.tsx        # 向导: 选服务器 → 选操作 → 选策略 → 确认
├── BatchJobProgress.tsx      # 实时进度面板
├── ServerSelector.tsx        # 多选 (分组/标签筛选)
└── BatchHistory.tsx          # 历史列表
```

### 与 RBAC 关系

- `servers:execute` — 允许发起批量操作
- scope `server:srv-01,srv-02` — 限制可操作服务器
- scope `group:production` — 按分组限制

---

## 预估规模

| Phase | 功能 | 后端 | 前端 | 总计 |
|-------|------|------|------|------|
| 1 | RBAC 权限矩阵 | ~1200 行 | ~800 行 | ~2000 行 |
| 2 | 统一运维监控与告警 | ~2500 行 | ~1500 行 | ~4000 行 |
| 3 | Web 文件管理器 | ~1000 行 | ~1500 行 | ~2500 行 |
| 4 | Fleet 批量操作 | ~1200 行 | ~800 行 | ~2000 行 |
| **合计** | | **~5900 行** | **~4600 行** | **~10500 行** |

## RBAC 权限矩阵总览

| 资源 | read | write | execute | admin |
|------|------|-------|---------|-------|
| system | 查看指标 | - | - | 系统设置 |
| docker | 查看容器 | 启停/操作 | exec 进入 | 清理/网络 |
| services | 查看服务 | 启停/重启 | - | enable/disable |
| users | 查看用户 | 修改配额 | kill 进程 | 增删用户 |
| cron | 查看任务 | 创建/修改 | - | 删除 |
| servers | 查看列表 | 注册/编辑 | 批量操作 | 删除 |
| files | 浏览/预览 | 编辑/上传 | - | 删除 |
| agents | 查看对话 | 发送消息 | 工具调用 | 配置管理 |
| alerts | 查看告警 | 确认/静默 | - | 规则管理 |
| notifications | 查看通知 | - | - | 渠道管理 |
