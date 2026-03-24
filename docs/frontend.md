# 前端架构

ServerHub 使用服务端渲染（Jinja2）+ 轻量交互（HTMX + Alpine.js）的技术栈，避免引入复杂的前端构建流程。

---

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Jinja2 | FastAPI 内置 | 服务端模板渲染 |
| HTMX | 2.x | 局部 HTML 刷新（无需编写 JS fetch）|
| Alpine.js | 3.x | 客户端交互状态（对话、设置、下拉）|
| Chart.js | 4.x | 监控图表（折线图、仪表盘）|
| xterm.js | 5.x | WebSocket 终端（WebTerminal）|

所有 JS/CSS 以静态文件形式存储在 `static/` 目录，无需构建步骤。

---

## CSS 变量体系

所有颜色和尺寸通过 CSS 自定义属性（CSS Variables）定义在 `static/css/app.css` 中，支持暗色主题。

### 颜色变量

| 变量 | 用途 |
|------|------|
| `--bg` | 背景色（页面底层）|
| `--bg2` | 次级背景色（卡片、消息气泡）|
| `--card` | 卡片背景 |
| `--border` | 边框颜色 |
| `--text` | 主文本颜色 |
| `--text2` | 次级文本颜色 |
| `--text3` | 三级文本（时间戳、提示）|
| `--accent` | 强调色（蓝色，用于按钮、链接、高亮）|
| `--accent-dim` | 强调色半透明版（激活状态背景）|
| `--green` | 成功/正常状态 |
| `--yellow` | 警告状态 |
| `--red` | 错误/危险状态 |

### 尺寸变量

| 变量 | 值 | 用途 |
|------|---|------|
| `--sidebar-w` | 200px | 侧边栏宽度 |
| `--header-h` | 56px | 顶栏高度 |
| `--radius` | 8px | 卡片圆角 |

---

## 页面模板结构

### 模板继承链

```
base.html
    ├── dashboard.html     （仪表盘）
    ├── monitoring.html    （监控图表）
    ├── users.html         （用户管理）
    ├── docker.html        （Docker 管理）
    ├── services.html      （服务管理）
    ├── network.html       （网络管理）
    ├── logs.html          （日志查看）
    ├── notifications.html （通知记录）
    ├── audit.html         （审计日志）
    ├── panel_users.html   （面板用户）
    ├── proxy.html         （代理管理）
    ├── settings.html      （系统设置）
    ├── agents.html        （AI 助手）
    ├── assets.html        （资产台账）
    ├── cron.html          （定时任务）
    └── login.html         （登录页，不继承 base）
```

### base.html 提供的结构

```html
<body x-data="{ sidebarOpen: true }">
  <!-- 侧边栏 -->
  <aside class="sidebar">
    <div class="sidebar-header">       <!-- 品牌 Logo + 主机名 -->
    <nav class="sidebar-nav">          <!-- 模块列表（Jinja2 循环渲染）-->
    <div class="sidebar-footer">       <!-- 用户名 + 退出 -->
  </aside>

  <!-- 主内容区 -->
  <div class="main-wrapper">
    <header class="top-bar">           <!-- 页面标题 + 操作按钮 -->
    <main class="main-content">        <!-- 页面内容（block content）-->
  </div>

  <!-- Toast 通知容器 -->
  <div id="toast-container">
</body>
```

### Jinja2 Block 定义

| Block 名称 | 用途 |
|-----------|------|
| `title` | 浏览器标签页标题 |
| `page_title` | 顶栏页面标题文字 |
| `top_actions` | 顶栏右侧按钮（可选）|
| `content` | 页面主体内容 |

### 渲染上下文

所有页面通过 `main.py:_page_context()` 获取公共上下文：

```python
{
    "user": UserInfo,           # 当前登录用户
    "sidebar_items": list,      # 侧边栏模块列表（按 order 排序）
    "active_module": str,       # 当前激活模块名
}
```

---

## 交互模式

### HTMX（局部刷新）

适用于需要从服务端获取数据、局部更新 DOM 的场景：

```html
<!-- 每 15 秒自动刷新指标卡片 -->
<div hx-get="/api/dashboard/metrics-cards"
     hx-trigger="every 15s"
     hx-swap="innerHTML">
  ...
</div>

<!-- 按钮触发操作 -->
<button hx-post="/api/docker/containers/nginx/restart"
        hx-swap="none"
        hx-on::after-request="showToast('重启成功')">
  重启
</button>
```

**HTMX SSE**：AI 对话使用 `htmx-sse.js` 扩展接收 Server-Sent Events 流：

```html
<div hx-ext="sse"
     sse-connect="/api/agents/chat/stream?conversation_id=xxx"
     sse-swap="message">
  ...
</div>
```

### Alpine.js（客户端交互）

适用于纯客户端状态管理（表单、对话框、下拉选择）：

```html
<!-- 内联状态定义 -->
<div x-data="{ show: false, selected: null }">
  <button @click="show = !show">切换</button>
  <div x-show="show">内容</div>
</div>

<!-- 跨元素共享状态（通过 $store 或 x-data 外提）-->
```

agents.html 的主 Alpine 状态包含：

```javascript
{
    // 对话相关
    conversations: [],
    currentConvId: null,
    messages: [],
    input: '',
    isStreaming: false,

    // 安全模式
    safetyMode: 'supervised',

    // 右侧标签页
    activeTab: 'patrol',  // 'patrol' | 'admin'

    // 快捷指令
    slashMenuVisible: false,
    slashQuery: '',
    slashIndex: 0,

    // Todo 列表
    todos: [],
    todoCollapsed: false,

    // 审批
    pendingApproval: null,
}
```

---

## agents.html 特殊布局

agents.html 是最复杂的页面，采用三栏 Grid 布局 + 子标签页设计。

### 三栏 Grid 布局

```css
.agent-main {
    display: grid;
    grid-template-columns: 180px 1fr 1fr;
    /* 左栏：对话列表 | 中栏：聊天（始终可见）| 右栏：子标签切换 */
}
```

```
┌──────────────┬─────────────────────┬──────────────────────┐
│  对话列表     │    聊天主区域         │   右侧标签面板         │
│  (180px)     │    (1fr, 始终可见)   │   (1fr, 按标签切换)   │
│              │                     │                      │
│  • 对话 1    │  [消息气泡]          │  [巡检] [管理]        │
│  • 对话 2    │  [工具调用卡片]      │                      │
│  • 对话 3    │  [审批卡片]          │  巡检列表 + 详情      │
│              │  [Todo 面板]        │  或管理面板            │
│  + 新建对话  │  [输入框 + 按钮]     │                      │
└──────────────┴─────────────────────┴──────────────────────┘
```

### 聊天区域组件

**消息气泡**：用户消息（右对齐蓝色）vs 助手消息（左对齐灰色）。助手消息渲染 Markdown（pre 代码块、table 表格）。

**工具调用卡片**（.tool-card）：
```
[工具名: get_system_overview]
↳ 工具输出（最大高度 120px，可滚动）
```

**审批卡片**（.approval-card）：
```
⚠ 待审批：kill_user_processes
参数：{"username": "wangtao"}
风险级别：danger

[批准] [拒绝]
```

**Todo 面板**（.todo-panel）：
- 进度条（已完成数 / 总数）
- 任务列表（in_progress 时图标脉冲动画，just-completed 时绿色闪烁）
- 可折叠（点击标题切换）

### 右侧标签页

| 标签 | 内容 | CSS Class |
|------|------|-----------|
| 巡检 | 巡检任务列表 + 详情 + 历史 | `right-panel.active`（当 activeTab=='patrol'）|
| 管理 | 系统提示词 / SubAgent / 记忆 / 巡检 / 告警规则 | `right-panel.active`（当 activeTab=='admin'）|

### 终端

通过聊天头部的"终端"按钮调出，使用 xterm.js 渲染，通过 WebSocket 连接到 `/ws/terminal`（`terminal.py:WebTerminal` 使用 `pty.fork()` 实现）。

### 快捷指令菜单

输入 `/` 时触发，展示 10 个内置指令（模糊搜索 + 键盘导航）：

| 指令 | 说明 |
|------|------|
| /status | 查看系统状态 |
| /docker | 列出所有容器 |
| /gpu | 查看 GPU 状态 |
| /disk | 检查磁盘空间 |
| /users | 查看用户资源使用 |
| /services | 检查服务状态 |
| /logs | 查看最近日志 |
| /patrol | 立即触发全量巡检 |
| /compliance | 运行安全合规检查 |
| /trend | 分析资源趋势 |

### 自主模式确认弹窗

切换到 autonomous 模式时显示页内 modal（不使用 `window.confirm`），避免浏览器对话框被屏蔽：

```html
<!-- 由 Alpine.js x-show 控制显示 -->
<div class="confirm-modal" x-show="showAutonomousConfirm">
  <div class="confirm-card">
    <h3>切换到自主模式</h3>
    <p>自主模式下，Agent 将自动执行操作，不再等待您的审批...</p>
    <div class="actions">
      <button @click="confirmAutonomous()">确认切换</button>
      <button @click="showAutonomousConfirm = false">取消</button>
    </div>
  </div>
</div>
```

---

## 侧边栏模块注册

侧边栏条目由各模块的 `MODULE_INFO` 驱动，在 `main.py:lifespan` 时通过 `discover_modules()` 自动发现：

```python
MODULE_INFO = {
    "name": "agents",           # URL 路径段：/agents
    "display_name": "AI 助手",  # 侧边栏显示名
    "icon": "robot",            # Tabler Icons 名称（暂未使用）
    "category": "智能运维",      # 侧边栏分组标题
    "required_role": "admin",   # 访问所需角色
    "order": 10,                # 排序权重
}
```

模块注册流程：
1. `discover_modules()` 扫描 `modules/*/` 子目录
2. 导入每个模块的 `__init__.py`，获取 `MODULE_INFO` 和 `router`
3. `app.include_router(router)` 注册 FastAPI 路由
4. `sidebar_items` 按 `order` 排序后传入每个页面的渲染上下文

---

## 静态文件

```
static/
├── css/
│   ├── app.css        # 全局样式 + CSS 变量体系
│   └── xterm.min.css  # xterm.js 样式
└── js/
    ├── htmx.min.js    # HTMX 核心
    ├── htmx-sse.js    # HTMX SSE 扩展
    ├── alpine.min.js  # Alpine.js（defer 加载）
    ├── chart.min.js   # Chart.js
    ├── xterm.min.js   # xterm.js
    └── app.js         # 应用级工具函数（showToast, formatBytes 等）
```
