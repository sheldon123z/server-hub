# 前端架构

ServerHub 使用 React 19 + TypeScript + Tailwind CSS 构建 SPA 前端，通过 Vite 构建工具链开发，FastAPI 作为静态文件服务和 API 后端。

---

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19.2 | UI 组件框架 |
| TypeScript | ~5.9 | 类型安全 |
| Vite | 8.0 | 构建工具 + HMR |
| Tailwind CSS | 4.2 | 样式系统（`@tailwindcss/vite` 插件） |
| TanStack Query | 5.x | 服务端状态管理（API 缓存 + 自动刷新） |
| Zustand | 5.x | 客户端状态（认证、聊天、侧边栏） |
| React Router | 7.x | 客户端路由 + 代码分割 |
| ECharts | 6.x (echarts-for-react) | 仪表盘图表 |
| marked.js | 17.x | Markdown 渲染 |
| highlight.js | 11.x | 代码语法高亮 |
| mermaid.js | 11.x | 流程图/拓扑图渲染 |
| DOMPurify | 3.x | HTML 安全净化 |
| @xterm/xterm | 6.x | WebSocket 终端 |
| Tabler Icons | 3.x | 侧边栏图标 (CDN Webfont) |
| react-hot-toast | 2.x | Toast 通知 |
| react-hook-form + zod | 7.x + 4.x | 表单校验 |
| Axios | 1.x | HTTP 客户端 |
| Lucide React | 1.x | 页面内图标 |

---

## 开发命令

```bash
cd frontend

# 安装依赖
npm install

# 开发模式 (HMR, 端口 5173, API 代理到 localhost:9900)
npm run dev

# 类型检查 + 生产构建
npm run build

# 预览生产构建
npm run preview

# ESLint 检查
npm run lint
```

开发模式下 Vite 将 `/api` 和 `/ws` 请求代理到 `http://localhost:9900`（FastAPI 后端）。

---

## 项目结构

```
frontend/src/
├── main.tsx              # 入口：StrictMode + QueryClientProvider + BrowserRouter + Toaster
├── App.tsx               # 路由表 + ProtectedRoute + 懒加载
├── index.css             # Tailwind @theme 变量定义 + 全局样式
├── api/
│   ├── client.ts         # Axios 实例（baseURL、Cookie 认证、401 拦截）
│   └── auth.ts           # 认证 API（login/logout/me/refresh）
├── components/
│   ├── Layout.tsx         # 全局布局：Sidebar + TopBar + Outlet + ChatWidget
│   ├── Sidebar.tsx        # 侧边栏：从 /api/sidebar 获取菜单，fallback 到静态列表
│   ├── TopBar.tsx         # 顶栏：页面标题
│   ├── ChatWidget.tsx     # 浮动对话气泡（SSE 流式、可拖拽、最小化）
│   └── ErrorBoundary.tsx  # React 错误边界
├── hooks/
│   ├── useAuth.ts         # 认证初始化 + 定时刷新 token
│   ├── useSSEChat.ts      # AgentsPage 聊天 SSE 流（7 种事件类型）
│   └── useWebSocket.ts    # 实时指标 WebSocket（60 点循环缓冲）
├── stores/
│   ├── authStore.ts       # Zustand：用户信息 + isAdmin() + isLoading
│   ├── chatStore.ts       # Zustand：对话消息 + Todo + 流式状态 + 去重
│   └── sidebarStore.ts    # Zustand：侧边栏折叠状态
├── pages/
│   ├── LoginPage.tsx
│   ├── DashboardPage.tsx
│   ├── UsersPage.tsx
│   ├── DockerPage.tsx
│   ├── ServicesPage.tsx
│   ├── CronPage.tsx
│   ├── NetworkPage.tsx
│   ├── ProxyPage.tsx
│   ├── LogsPage.tsx
│   ├── NotificationsPage.tsx
│   ├── SettingsPage.tsx
│   ├── AuditPage.tsx
│   ├── PanelUsersPage.tsx
│   ├── AssetsPage.tsx
│   └── agents/
│       ├── AgentsPage.tsx          # 三栏主页面
│       ├── ConversationSidebar.tsx  # 对话列表
│       ├── ChatPanel.tsx           # 聊天主区域
│       ├── MessageBubble.tsx       # 消息气泡（hover 操作栏）
│       ├── MarkdownRenderer.tsx    # Markdown + Mermaid + Artifact 渲染
│       ├── TodoPanel.tsx           # Todo 进度面板
│       ├── SlashCommandMenu.tsx    # 快捷指令菜单
│       ├── PatrolPanel.tsx         # 巡检标签页
│       ├── AdminPanel.tsx          # 管理标签页
│       ├── TerminalPanel.tsx       # xterm.js 终端
│       └── SafetyToggle.tsx        # 安全模式切换
├── lib/
│   ├── markdown.ts        # marked.js 配置 + DOMPurify 净化
│   ├── utils.ts           # cn() 等工具函数
│   └── constants.ts       # 常量定义
└── types/
    ├── api.ts             # SidebarItem 等公共类型
    ├── agent.ts           # ChatMessage, TodoItem 等 Agent 类型
    ├── docker.ts          # Docker 相关类型
    └── user.ts            # 用户相关类型
```

---

## 暗色主题系统

所有颜色和尺寸通过 Tailwind CSS 4 的 `@theme` 指令定义在 `src/index.css` 中，在组件中通过 `bg-bg`、`text-accent`、`border-border` 等 Tailwind 类名直接使用。

### 颜色变量

| Tailwind 类名 | 值 | 用途 |
|---------------|-----|------|
| `bg` | `#0a0f1a` | 页面底层背景 |
| `bg2` | `#0f172a` | 次级背景（侧边栏、顶栏、消息气泡） |
| `card` | `#1e293b` | 卡片背景 |
| `card-hover` | `#253347` | 卡片悬停背景 |
| `border` | `#334155` | 边框颜色 |
| `border-light` | `#475569` | 次级边框 |
| `accent` | `#38bdf8` | 强调色（按钮、链接、活跃状态） |
| `accent-dim` | `rgba(56,189,248,0.15)` | 强调色半透明（选中背景） |
| `green` | `#4ade80` | 成功/正常状态 |
| `yellow` | `#fbbf24` | 警告状态 |
| `red` | `#f87171` | 错误/危险状态 |
| `orange` | `#fb923c` | 次级警告 |
| `purple` | `#a78bfa` | 辅助色 |
| `text` | `#e2e8f0` | 主文本颜色 |
| `text2` | `#94a3b8` | 次级文本颜色 |
| `text3` | `#64748b` | 三级文本（时间戳、提示） |

### 尺寸变量

| Tailwind 类名 | 值 | 用途 |
|---------------|-----|------|
| `sidebar` (spacing) | 220px | 侧边栏宽度（`w-sidebar`, `ml-sidebar`） |
| `header` (spacing) | 56px | 顶栏高度 |
| `default` (radius) | 8px | 默认圆角 |

---

## 页面路由表

所有页面组件通过 `React.lazy()` 懒加载，由 `<Suspense>` 包裹显示加载状态。受保护路由通过 `<ProtectedRoute>` 检查 `authStore.user` 状态。

| 路径 | 组件 | 说明 |
|------|------|------|
| `/login` | `LoginPage` | 登录页（不套 Layout） |
| `/` | → `/dashboard` | 重定向 |
| `/dashboard` | `DashboardPage` | 仪表盘（含 ErrorBoundary） |
| `/users` | `UsersPage` | 用户管理 |
| `/docker` | `DockerPage` | Docker 管理 |
| `/services` | `ServicesPage` | 服务管理 |
| `/cron` | `CronPage` | 定时任务 |
| `/network` | `NetworkPage` | 网络状态 |
| `/proxy` | `ProxyPage` | 代理管理 |
| `/logs` | `LogsPage` | 日志查看 |
| `/notifications` | `NotificationsPage` | 通知管理 |
| `/settings` | `SettingsPage` | 系统设置 |
| `/audit` | `AuditPage` | 审计日志 |
| `/panel_users` | `PanelUsersPage` | 面板用户 |
| `/assets` | `AssetsPage` | 资产管理 |
| `/agents` | `AgentsPage` | AI OpsAgent |
| `/monitoring` | → `/dashboard` | 重定向（兼容旧路由） |

---

## 全局布局

`Layout.tsx` 定义了所有受保护页面的统一结构：

```
┌──────────────────────────────────────────────────────┐
│  Sidebar (fixed, 220px)  │  TopBar (标题)            │
│                          ├──────────────────────────│
│  按分组渲染菜单            │                          │
│  (从 /api/sidebar 获取)   │  <Outlet /> 页面内容      │
│                          │                          │
└──────────────────────────┴──────────────────────────┘
                           + ChatWidget (浮动气泡)
```

- **Sidebar**: 通过 TanStack Query 从 `GET /api/sidebar` 获取菜单项，失败时 fallback 到硬编码的静态列表（按角色过滤）。使用 `<NavLink>` 自动高亮当前页面。
- **TopBar**: 根据 `location.pathname` 映射页面标题（`PAGE_TITLES` 常量）。
- **ChatWidget**: 除 `/agents` 页面外始终渲染的浮动对话气泡。

---

## 认证与鉴权

### 认证流程

1. `main.tsx` 创建 `QueryClientProvider`，全局 staleTime 30s
2. `App.tsx` 调用 `useAuth()` hook，通过 TanStack Query 请求 `GET /api/auth/me`
3. 返回用户信息写入 `authStore`；401/403 清空用户状态
4. `ProtectedRoute` 组件检查 `authStore.user`，未登录重定向到 `/login`
5. 定时每 20 分钟调用 `POST /api/auth/refresh` 无感续期 access_token

### 状态管理

```typescript
// authStore.ts
interface AuthState {
  user: UserInfo | null
  isLoading: boolean
  setUser: (user) => void
  setLoading: (loading) => void
  isAdmin: () => boolean     // 快捷判断角色
}
```

### Cookie 自动携带

Axios 实例 (`api/client.ts`) 配置 `withCredentials: true`，浏览器自动携带 `access_token` Cookie。SSE 请求使用 `fetch()` 的 `credentials: 'include'`。

---

## 数据获取模式

### 读取数据 (TanStack Query)

```typescript
// 标准 GET 请求 — 自动缓存、重试、后台刷新
const { data, isLoading } = useQuery({
  queryKey: ['docker', 'containers'],
  queryFn: () => client.get('/api/docker/containers').then(r => r.data),
  refetchInterval: 15_000,  // 可选：轮询
})
```

### 写入操作 (useMutation)

```typescript
const mutation = useMutation({
  mutationFn: (body) => client.post('/api/docker/containers/nginx/restart', body),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['docker'] })  // 刷新相关缓存
    toast.success('操作成功')
  },
})
```

### 缓存失效模式

- 写操作成功后调用 `queryClient.invalidateQueries()` 刷新相关查询
- SSE 聊天结束后刷新 `['conversations']` 查询
- 全局 `staleTime: 30s`，侧边栏 `staleTime: 5min`

---

## 实时通信

### WebSocket: useWebSocket

连接 `/ws/metrics`，接收服务器实时指标。

```typescript
const { metrics, history, connected, alerts } = useWebSocket()
```

- **消息类型**: `metrics` / `metrics_full`（指标数据）、`alert`（告警推送）
- **循环缓冲**: 维护最近 60 个数据点的 `history` 数组，用于 sparkline 趋势图
- **自动重连**: 指数退避（1s → 2s → 4s → ... → 30s 上限）
- **开发模式**: 直连 `hostname:9900`（绕过 Vite WS proxy 不稳定问题）

### SSE: useSSEChat

AgentsPage 的聊天使用 `POST /api/agents/chat` 发起 SSE 流。

```typescript
const { sendMessage } = useSSEChat()
```

**7 种 SSE 事件类型**:

| 事件 | 说明 | 处理方式 |
|------|------|---------|
| `message` | 助手文本消息 | 追加到消息列表 |
| `tool_call` | 工具调用 | 显示工具名称卡片 |
| `tool_result` | 工具返回结果 | 显示折叠的输出内容 |
| `todo_update` | Todo 列表变更 | 更新 TodoPanel（含完成闪绿动画） |
| `approval_request` | 待审批操作 | 显示审批卡片（批准/拒绝按钮） |
| `done` | 流结束 | 更新 conversationId，刷新对话列表 |
| `error` | 错误信息 | 显示错误消息 |

**去重机制**: `chatStore` 通过 `_seenIds: Set<string>` 按 `_serverId` 去重，防止重复消息。

---

## AI 对话页面 (AgentsPage)

AgentsPage 是最复杂的页面，采用三栏 Grid 布局（admin 视图）或两栏布局（user 视图）。

### 三栏 Grid 布局

```
┌──────────────┬─────────────────────┬──────────────────────┐
│  对话列表     │    聊天主区域         │   右侧面板            │
│  (180px)     │    (1fr, 始终可见)   │   (1fr, admin only)  │
│              │                     │                      │
│  • 对话 1    │  [消息气泡]          │  [巡检] [管理] 标签   │
│  • 对话 2    │  [工具调用卡片]      │  或 [终端]            │
│  • 对话 3    │  [审批卡片]          │                      │
│              │  [Todo 面板]        │  巡检列表 / 管理面板   │
│  + 新建对话  │  [快捷指令菜单]     │  / 终端面板            │
└──────────────┴─────────────────────┴──────────────────────┘
```

### 顶部控制栏

位于 Grid 上方的固定栏（42px），包含：
- 左侧：绿色状态圆点 + "OpsAgent" 标题
- 右侧（admin）：安全模式切换（SafetyToggle） + 终端按钮 + 巡检/管理标签切换

### 11 个子组件

| 组件 | 文件 | 功能 |
|------|------|------|
| `ConversationSidebar` | `ConversationSidebar.tsx` | 对话列表（创建/切换/删除） |
| `ChatPanel` | `ChatPanel.tsx` | 聊天主区域（消息列表 + 输入框） |
| `MessageBubble` | `MessageBubble.tsx` | 单条消息渲染 + hover 操作栏 |
| `MarkdownRenderer` | `MarkdownRenderer.tsx` | Markdown + Mermaid + Artifact 渲染 |
| `TodoPanel` | `TodoPanel.tsx` | Todo 进度面板（进度条 + 任务列表） |
| `SlashCommandMenu` | `SlashCommandMenu.tsx` | 快捷指令菜单（模糊搜索 + 键盘导航） |
| `PatrolPanel` | `PatrolPanel.tsx` | 巡检任务列表 + 详情 + 历史 |
| `AdminPanel` | `AdminPanel.tsx` | 系统提示词 / SubAgent / 记忆管理 |
| `TerminalPanel` | `TerminalPanel.tsx` | xterm.js WebSocket 终端 |
| `SafetyToggle` | `SafetyToggle.tsx` | supervised/autonomous 模式切换 |

### 安全模式

- **supervised**（默认）：危险操作触发审批卡片，需用户批准/拒绝
- **autonomous**：自动执行，不中断（切换时弹 confirm 提示）

状态存储在 `chatStore.safetyMode`，随聊天请求通过 `safety_mode` 参数传递给后端。

---

## AI 对话增强功能

### 消息操作

`MessageBubble` 组件在 hover 时显示操作栏：

| 操作 | 说明 |
|------|------|
| 复制 | 复制消息文本内容到剪贴板 |
| 删除 | 从消息列表中移除该消息 |
| 重发 | 删除该消息及之后的所有消息，重新发送（仅用户消息） |

### Markdown 渲染

`lib/markdown.ts` 配置 marked.js 的自定义 renderer：

- **代码块**: highlight.js 语法高亮 + 语言标签 + 复制按钮（`data-code` 属性存储原始代码）
- **表格**: 包裹 `.table-wrapper` 实现横向滚动
- **链接**: 自动添加 `target="_blank" rel="noopener noreferrer"`
- **GFM**: 启用 GitHub Flavored Markdown + 自动换行
- **净化**: DOMPurify 过滤 XSS，保留 `data-code`、`class` 等白名单属性

### Mermaid 图

`MarkdownRenderer.tsx` 在渲染后扫描 `.mermaid-block` 占位元素，调用 `mermaid.render()` 生成 SVG 内联渲染。Mermaid 配置为 dark 主题，颜色与 Tailwind @theme 变量一致。

### HTML Artifacts

`html:artifact` 或 `html` 语言标记的代码块生成 `.artifact-block` 占位元素，由 `MarkdownRenderer` 渲染为 iframe sandbox（`allow-scripts`），用于展示 Agent 生成的交互式 HTML。

### 代码块

- highlight.js 自动检测或按指定语言高亮
- 每个代码块顶部显示语言标签和"复制"按钮
- 点击复制按钮通过 `navigator.clipboard.writeText()` 复制原始代码

---

## 浮动对话气泡 (ChatWidget)

`ChatWidget` 组件渲染在 Layout 中，除 `/agents` 页面外始终可用。提供轻量级的 AI 对话入口。

### 三种状态

| 状态 | 视觉表现 |
|------|---------|
| 关闭 | 右下角圆形浮动按钮 |
| 最小化 | 可拖拽的窄条标题栏（显示消息数） |
| 展开 | 320×480px 聊天面板 |

### 功能特性

- **SSE 流式对话**: 复用 `streamChat()` 函数，支持 7 种事件类型
- **可拖拽**: header 区域支持鼠标拖拽，位置持久化到 localStorage
- **去重**: `seenServerIds` Set 按 `_serverId` 防止重复消息
- **新建对话**: header 按钮可开启新对话，清空消息和中止当前流
- **审批处理**: 审批卡片内直接批准/拒绝，调用 `POST /api/agents/approvals/{id}`
- **页面上下文**: 自动将当前页面路径作为 `page_context` 传递，让 Agent 了解用户所在页面
- **对话持久化**: `conversationId` 存储在 localStorage，刷新页面后恢复

---

## 侧边栏模块注册

侧边栏数据通过 `GET /api/sidebar` 从后端获取，后端按用户角色过滤模块列表。

```typescript
interface SidebarItem {
  name: string          // URL 路径段：/agents
  display_name: string  // 显示名：OpsAgent
  icon: string          // Tabler Icons 名称
  category: string      // 分组标题
  required_role: string // 访问所需角色
  order: number         // 排序权重
}
```

**Fallback 机制**: 当 `/api/sidebar` 请求失败时，Sidebar 组件使用硬编码的 14 个静态菜单项（按角色过滤）。

**图标系统**: 使用 [Tabler Icons](https://tabler.io/icons) Webfont，通过 CDN 引入，在模板中使用 `<i class="ti ti-icon-name" />`。

---

## 构建与部署

### 构建流程

```bash
cd frontend
npm run build    # tsc -b && vite build → frontend/dist/
```

构建产物输出到 `frontend/dist/`，包含 `index.html` + 代码分割后的 JS/CSS chunks。

### Vite 配置要点

- **路径别名**: `@` → `./src`（简化导入路径）
- **Tailwind CSS**: 通过 `@tailwindcss/vite` 插件集成（非 PostCSS 方式）
- **开发代理**: `/api` → `http://localhost:9900`，`/ws` → `ws://localhost:9900`

### 生产部署

FastAPI 后端配置静态文件服务和 SPA catch-all 路由：

1. `/frontend/dist/assets/` 作为静态资源目录
2. 所有非 API、非 WebSocket 的 GET 请求 fallback 到 `frontend/dist/index.html`
3. React Router 在客户端接管路由

### Toast 通知

使用 `react-hot-toast`，全局 `<Toaster>` 在 `main.tsx` 中渲染，配色与暗色主题一致（card 背景 + text 文字色 + border 边框）。
