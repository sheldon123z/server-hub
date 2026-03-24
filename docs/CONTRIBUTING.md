# ServerHub 开发规范

本文档是 ServerHub 项目的开发规范指南，所有贡献者在编写代码、设计 API、编写文档时均应遵循此规范。

---

## 目录

1. [编码风格](#1-编码风格)
2. [API 设计规范](#2-api-设计规范)
3. [数据库规范](#3-数据库规范)
4. [模块开发规范](#4-模块开发规范)
5. [前端规范](#5-前端规范)
6. [Git 提交规范](#6-git-提交规范)
7. [文档更新规范](#7-文档更新规范)

---

## 1. 编码风格

### 1.1 命名约定

| 类型 | 规范 | 示例 |
|------|------|------|
| 函数/方法 | `snake_case` | `get_user_stats()`, `list_containers()` |
| 类 | `PascalCase` | `SafeLocalShellBackend`, `Settings` |
| 常量 | `UPPER_CASE` | `DEFAULT_PATROLS`, `PROVIDERS` |
| 变量 | `snake_case` | `user_role`, `patrol_id` |
| 模块目录 | `snake_case`（小写） | `modules/panel_users/`, `modules/agents/` |
| 模板文件 | `kebab-case` | `agents.html`, `panel-users.html` |
| 静态文件 | `kebab-case` | `main.css`, `chat-utils.js` |

### 1.2 Python 代码风格

- 遵循 PEP 8，缩进 4 空格，不使用 Tab
- 每行最大长度 120 字符
- 文件头部注释使用三引号说明模块功能
- 导入顺序：标准库 → 第三方库 → 本地模块，各组之间空一行
- 每个模块在文件顶层定义 logger：

```python
import logging
logger = logging.getLogger(__name__)
```

- 类型注解优先用于函数参数和返回值，但内部局部变量可省略
- 异步函数统一使用 `async def`，不混用同步/异步

### 1.3 Python 版本特性

项目使用 Python 3.11，注意以下限制：

- **f-string 不支持反斜杠**：需要正则匹配时，先提取 match 对象再在 f-string 中引用

```python
# 错误写法
msg = f"结果: {re.match(r'\d+', text).group()}"

# 正确写法
m = re.match(r'\d+', text)
msg = f"结果: {m.group() if m else '无'}"
```

---

## 2. API 设计规范

### 2.1 URL 规则

- **路径段**：`kebab-case`，如 `/api/panel-users/`, `/api/agent-patrols/`
- **查询参数**：`snake_case`，如 `?user_id=1&page_size=20`
- **路径参数**：`snake_case`，如 `/api/users/{user_id}`
- 每个模块的 APIRouter 统一使用 `/api/模块名` 前缀

```python
router = APIRouter(prefix="/api/users", tags=["users"])
```

### 2.2 响应格式

**写操作（POST/PUT/DELETE）**：返回 `{"ok": true, ...}` 格式

```python
# 成功响应
return {"ok": True, "message": "操作成功", "id": new_id}

# 批量操作
return {"ok": True, "count": affected_rows}
```

**GET 查询**：直接返回数据，不包装额外层

```python
# 列表
return [{"id": 1, "name": "xxx"}, ...]

# 单个对象
return {"id": 1, "name": "xxx", "status": "active"}

# 带分页
return {"items": [...], "total": 100, "page": 1}
```

### 2.3 错误处理

统一使用 `HTTPException`，提供有意义的 `detail` 说明：

```python
from fastapi import HTTPException

# 资源不存在
raise HTTPException(status_code=404, detail="用户不存在")

# 权限不足
raise HTTPException(status_code=403, detail="需要管理员权限")

# 参数错误
raise HTTPException(status_code=422, detail="interval_minutes 必须大于 0")

# 服务端错误
raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")
```

不要抛出裸异常或返回 `{"error": "..."}` 格式，保持 HTTP 语义一致。

### 2.4 认证与授权

- 使用依赖注入声明认证需求，不在 handler 内手动解析 token
- `get_current_user`：验证登录状态，返回用户对象
- `require_role("admin")`：验证管理员权限

```python
from auth.dependencies import get_current_user, require_role

@router.get("/sensitive")
async def sensitive_endpoint(
    user=Depends(require_role("admin"))
):
    ...

@router.get("/public-for-users")
async def user_endpoint(
    user=Depends(get_current_user)
):
    ...
```

### 2.5 审计日志

所有写操作（POST/PUT/DELETE）由 `AuditMiddleware` 自动记录到 `audit_log` 表，无需在 handler 内手动记录。

---

## 3. 数据库规范

### 3.1 数据库访问

- 使用 `get_db()` 获取主数据库单例连接，不创建额外连接
- 数据库在 `database.py:init_tables()` 中统一初始化，新增表在此函数中添加

```python
from database import get_db

async def my_service():
    db = await get_db()
    rows = await db.execute("SELECT ...")
    ...
```

### 3.2 SQL 书写规范

- **SQL 关键字大写**：`SELECT`, `FROM`, `WHERE`, `INSERT INTO`, `UPDATE`, `DELETE`
- **参数化查询**：使用 `?` 占位符，禁止字符串拼接（防 SQL 注入）

```python
# 正确
await db.execute(
    "SELECT * FROM users WHERE id = ? AND role = ?",
    (user_id, role)
)

# 错误（SQL 注入风险）
await db.execute(f"SELECT * FROM users WHERE id = {user_id}")
```

- **时间比较**：使用 SQLite 内置函数，不在 Python 层做时间计算后传入

```python
# 查询最近 N 分钟的记录
await db.execute(
    "SELECT * FROM metrics WHERE created_at > datetime('now', '-? minutes')",
    (minutes,)
)

# 查询最近 N 天
await db.execute(
    "SELECT * FROM audit_log WHERE created_at > datetime('now', '-? days')",
    (days,)
)
```

### 3.3 事务规范

写操作后先 `commit`，再做通知等副作用（避免副作用成功但数据库回滚的不一致）：

```python
async def create_record(data: dict):
    db = await get_db()
    await db.execute("INSERT INTO ...", (...))
    await db.commit()                    # 先提交
    await send_notification(data)        # 再做副作用
```

### 3.4 三个数据库文件

| 文件 | 用途 | 访问方式 |
|------|------|---------|
| `data/server-hub.db` | 应用主数据 | `get_db()` |
| `data/agent-checkpoints.db` | LangGraph 会话 checkpoint | 框架内部管理 |
| `data/agent-store.db` | Agent 结构化长期存储 | 框架内部管理 |

不要直接读写 `agent-checkpoints.db` 和 `agent-store.db`，这两个由 Deep Agents 框架管理。

---

## 4. 模块开发规范

### 4.1 模块目录结构

每个功能模块放在 `modules/<name>/` 目录下，至少包含：

```
modules/my_module/
├── __init__.py      # 导出 MODULE_INFO + router（必须）
├── routes.py        # FastAPI 路由 Handler（必须）
└── services.py      # 业务逻辑（推荐，复杂模块必须）
```

### 4.2 `__init__.py` 导出规范

```python
from modules.my_module.routes import router

MODULE_INFO = {
    "name": "my-module",           # URL 路由名，kebab-case
    "display_name": "我的模块",     # 侧边栏显示名称
    "icon": "icon-name",           # Tabler Icons 图标名（去掉 ti- 前缀）
    "category": "系统",             # 侧边栏分类：系统 / 运维 / AI / 用户
    "required_role": "admin",      # 访问角色："admin" 或 "user"
    "order": 50,                   # 侧边栏排序（数字越小越靠前）
}
```

模块注册是自动的：`main.py` 的 `lifespan` 调用 `discover_modules()` 扫描所有 `modules/*/` 目录，只要导出了 `MODULE_INFO` 和 `router` 就会自动注册。

### 4.3 routes.py 与 services.py 分离原则

- **routes.py**：只负责 HTTP 层（接收请求、校验参数、返回响应），不包含业务逻辑
- **services.py**：包含实际业务逻辑（数据库操作、系统调用、数据处理）

```python
# routes.py — 薄层，只做路由
@router.post("/restart/{service_name}")
async def restart_service(
    service_name: str,
    user=Depends(require_role("admin"))
):
    result = await services.restart_service(service_name)
    return {"ok": True, "result": result}

# services.py — 厚层，包含逻辑
async def restart_service(service_name: str) -> str:
    if service_name not in settings.managed_services:
        raise HTTPException(404, "服务不在管理列表中")
    proc = await asyncio.create_subprocess_exec(
        "sudo", "systemctl", "restart", service_name, ...
    )
    ...
```

### 4.4 框架优先原则

在实现新功能前，必须先确认 Deep Agents 框架是否已提供该能力：

1. 查阅 `deepagents` 包源码
2. 优先使用框架提供的机制（如代码执行通过 `write_file` + `execute`，而非自造 `run_code` 工具）
3. 需要定制时，继承框架类并 override 方法，不绕过框架

---

## 5. 前端规范

### 5.1 Alpine.js 组件

所有 Alpine.js 组件统一使用 `init()` 方法进行初始化，不在 `x-data` 对象外直接调用异步操作：

```html
<!-- 正确 -->
<div x-data="{
    items: [],
    loading: false,
    async init() {
        this.loading = true;
        const resp = await fetch('/api/items');
        this.items = await resp.json();
        this.loading = false;
    }
}">
```

### 5.2 CSS 命名规范

- **功能语义命名**，不以视觉效果命名
- 使用 CSS 变量定义主题色，暗色模式变量在 `base.html` 中统一定义

```css
/* 正确 — 功能语义 */
.status-badge { ... }
.metric-card { ... }
.sidebar-item { ... }

/* 错误 — 视觉描述 */
.green-badge { ... }
.big-card { ... }
```

### 5.3 Modal 位置规范

Modal 弹窗必须放置在页面 Grid 布局容器**之外**，避免被 `overflow: hidden` 裁剪：

```html
<body>
    <!-- 主内容 Grid -->
    <div class="app-grid">
        <aside>...</aside>
        <main>...</main>
    </div>

    <!-- Modal 放在 Grid 外 -->
    <div id="confirm-modal" class="modal-overlay" x-show="showModal">
        ...
    </div>
</body>
```

### 5.4 HTMX 使用原则

- 仪表盘卡片、Docker 状态等**只需局部刷新**的区域使用 HTMX
- 需要复杂交互逻辑的页面使用 Alpine.js
- 不混合两者处理同一个交互，避免状态冲突

### 5.5 模板继承

所有页面模板继承 `base.html`：

```html
{% extends "base.html" %}

{% block title %}页面标题{% endblock %}

{% block content %}
<!-- 页面内容 -->
{% endblock %}
```

不要在页面模板中重复定义侧边栏、顶栏、主题 CSS 变量。

---

## 6. Git 提交规范

### 6.1 提交消息格式

```
<类型>: <中文描述>

[可选的详细说明]
```

**类型前缀**：

| 类型 | 用途 |
|------|------|
| `feat` | 新增功能 |
| `fix` | 修复 Bug |
| `docs` | 文档更新 |
| `refactor` | 重构（不改变功能） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖变更 |
| `style` | 代码格式（不影响逻辑） |

**示例**：

```
feat: SubAgent 支持自定义工具集配置
fix: 巡检任务并发调度时 checkpoint 冲突问题
docs: 更新 Agent 工具列表文档
refactor: 将 LLM 初始化逻辑移至独立函数
```

### 6.2 分支策略

- `main`：稳定分支，直接部署生产
- 功能开发在 `main` 基础上创建功能分支：`feat/功能名`
- Bug 修复：`fix/问题描述`

### 6.3 PR 工作流

1. 从 `main` 创建功能分支
2. 实现功能，确保本地可运行（`python main.py`）
3. 更新相关文档（见第 7 节）
4. 提交 PR，描述改动内容和测试方法
5. 合并前确认无敏感信息（API Key、密码）泄露

---

## 7. 文档更新规范

### 7.1 新增 API 时

新增 API 端点必须在 `docs/api/` 目录下对应模块文档中更新，包含：

- 端点 URL 和 HTTP 方法
- 请求参数（路径参数、查询参数、请求体）
- 响应格式示例
- 权限要求

### 7.2 新增 Agent 工具时

新增 `@tool` 工具必须更新 `docs/agents/tools.md`，包含：

- 工具名称和功能描述
- 参数说明
- 返回格式示例
- 安全级别（只读 / 操作 / 危险）

### 7.3 新增模块时

新增功能模块需同步更新：

- `docs/overview.md`：功能全景表格中添加新模块
- `docs/architecture.md`：如有架构变化则更新
- 对应的 `docs/api/<module>.md` API 文档

### 7.4 CLAUDE.md 维护

`CLAUDE.md` 是开发者指引，当以下内容变化时需要同步更新：

- 架构设计有重大变更
- 新增/删除关键配置项
- 开发约定或原则发生变化

注意：`AGENTS.md` 是 AI 运维助手的长期记忆（由框架 MemoryMiddleware 加载），不要混淆两者。

---

## 附录：敏感文件清单

以下文件**禁止读取或输出内容**，包含敏感凭证：

| 文件 | 说明 |
|------|------|
| `.env` | 应用环境变量 |
| `~/.api_keys` | API 密钥集合 |
| `~/.telegram_config` | Telegram Bot Token |
| `~/config.yaml` | Clash 代理节点配置 |
| `scripts/config/lobe.env` | LobeChat 含密钥环境变量 |
