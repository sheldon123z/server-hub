# Deer-Flow Artifacts 系统参考文档

> 从 `~/exps/deer-flow/` 项目提取的 Artifacts 实现分析，用于指导 ServerHub Agent 对话窗口实现类似功能。

## 1. 架构总览

### Deer-Flow 技术栈

| 层 | 技术 |
|---|------|
| 框架 | Next.js 16 + React 19 + App Router |
| 状态 | React Context + @tanstack/react-query + LangGraph SDK `useStream` |
| 样式 | Tailwind CSS v4 (OKLCH 色彩空间) |
| Markdown | **Streamdown** 库 (流式渲染) + rehype/remark 插件 |
| 代码高亮 | Shiki (静态) + CodeMirror (交互编辑) |
| 布局 | ResizablePanelGroup (react-resizable-panels) |
| UI 基础 | Radix UI primitives + 25+ 自定义组件 |

### ServerHub 当前技术栈 (对照)

| 层 | 技术 |
|---|------|
| 框架 | React 18 + TypeScript + Vite |
| 状态 | Zustand (chatStore) + TanStack Query |
| 样式 | Tailwind CSS v3 |
| Markdown | marked.js + highlight.js + mermaid.js + DOMPurify |
| 布局 | 固定三栏 (侧边栏 + 聊天 + 右栏) |
| SSE 事件 | 7 种: message/tool_call/tool_result/todo_update/approval_request/done/error |

---

## 2. Artifacts 系统架构

### 2.1 核心数据流

```
Agent 后端 (LangGraph)
    │
    ├── thread.values.artifacts: string[]  ← 文件路径列表
    │     例: ["/mnt/data/report.py", "/mnt/data/chart.png"]
    │
    └── SSE/Stream → 前端更新 thread state
              │
              ▼
     ArtifactsProvider (React Context)
        ├── artifacts: string[]          ← 当前会话的所有 artifact 路径
        ├── selectedArtifact: string|null ← 当前选中的文件
        ├── open: boolean                ← 面板是否打开
        └── autoSelect / autoOpen        ← 自动行为控制
              │
              ├── ArtifactTrigger  → 触发按钮 (仅 artifacts 非空时显示)
              ├── ArtifactFileList → 文件网格 (缩略卡片)
              └── ArtifactFileDetail → 文件详情查看器
```

### 2.2 ArtifactsProvider (Context)

**文件**: `components/workspace/artifacts/context.tsx`

```typescript
interface ArtifactsContextType {
  artifacts: string[]              // 文件路径列表
  setArtifacts: (a: string[]) => void
  selectedArtifact: string | null  // 当前选中
  autoSelect: boolean             // 自动选中新文件?
  select: (artifact: string, autoSelect?: boolean) => void
  deselect: () => void
  open: boolean                   // 面板打开状态
  autoOpen: boolean               // 自动打开面板?
  setOpen: (open: boolean) => void
}
```

**关键行为**:
- 选择 artifact 时自动关闭侧边栏 (空间让位)
- 手动关闭面板会禁用 autoOpen 和 autoSelect
- deselect 重置所有状态

**ServerHub 适配**: 可用 Zustand store 替代 Context，与现有 chatStore 集成:
```typescript
// stores/artifactStore.ts
interface ArtifactState {
  artifacts: string[]
  selected: string | null
  panelOpen: boolean
  setArtifacts: (files: string[]) => void
  select: (file: string) => void
  togglePanel: () => void
}
```

### 2.3 Artifact URL 解析

**文件**: `core/artifacts/utils.ts`

```typescript
// URL 模式: /api/threads/{thread_id}/artifacts{filepath}
function urlOfArtifact({ filepath, threadId, download }) {
  return `${BASE_URL}/api/threads/${threadId}/artifacts${filepath}${download ? "?download=true" : ""}`
}

// 从 thread state 提取 artifacts 列表
function extractArtifactsFromThread(thread) {
  return thread.values.artifacts ?? []
}
```

**ServerHub 适配**: 需要:
1. 后端新增 artifact 端点: `GET /api/agents/conversations/{id}/artifacts{filepath}`
2. Agent 工具 (write_file) 产生的文件存到 `data/artifacts/{conversation_id}/` 目录
3. 前端通过 conversation_id 拼接 URL

### 2.4 Artifact 内容加载

**文件**: `core/artifacts/loader.ts` + `hooks.ts`

两种加载方式:

1. **服务端文件** — 通过 HTTP GET 获取:
   ```typescript
   const { data } = useQuery({
     queryKey: ["artifact", filepath, threadId],
     queryFn: () => fetch(urlOfArtifact({ filepath, threadId })).then(r => r.text()),
     staleTime: 5 * 60 * 1000, // 5分钟缓存
   })
   ```

2. **write-file 类型** — 直接从 thread 消息中提取 (无需网络请求):
   ```typescript
   // URL 格式: write-file:?tool_call_id=xxx&message_id=yyy
   // 从对应 AI message 的 tool_calls 中找到 args.content
   const toolCall = thread.messages
     .find(m => m.id === messageId)?.tool_calls
     .find(tc => tc.id === toolCallId)
   return toolCall.args.content
   ```

**ServerHub 适配**: ServerHub 的 SSE 事件中已有 `tool_call` 事件，可以从 tool_call 的 args 中提取文件内容。同时需要新增 HTTP 端点用于下载持久化的文件。

---

## 3. 布局系统: ResizablePanelGroup

### 3.1 ChatBox 布局结构

**文件**: `components/workspace/chats/chat-box.tsx`

```tsx
<ResizablePanelGroup direction="horizontal" onLayout={handleLayout}>
  {/* 聊天面板: 60-100% */}
  <ResizablePanel defaultSize={70} minSize={60}>
    <div className="flex h-full flex-col">
      {/* 顶部工具栏 */}
      <header>
        <ArtifactTrigger />    {/* artifacts 触发按钮 */}
        <ModeSelector />       {/* 模式选择 */}
      </header>

      {/* 消息列表 */}
      <MessageList thread={thread} threadId={threadId} />

      {/* 输入框 */}
      <InputBox onSubmit={handleSubmit} />
    </div>
  </ResizablePanel>

  {/* 分割线 */}
  <ResizableHandle />

  {/* Artifacts 面板: 0-40% */}
  <ResizablePanel
    defaultSize={30}
    minSize={30}
    maxSize={50}
    // 面板关闭时设为 0
  >
    {selectedArtifact ? (
      <ArtifactFileDetail filepath={selectedArtifact} threadId={threadId} />
    ) : (
      <ArtifactFileList files={artifacts} threadId={threadId} />
    )}
  </ResizablePanel>
</ResizablePanelGroup>
```

### 3.2 ServerHub 当前布局对比

ServerHub 当前是**固定三栏**:
```
侧边栏(180px) | 聊天(1fr) | 右栏(1fr, 按标签切换 [巡检][管理])
```

**适配方案**: 将右栏改为可切换的 Artifacts 面板:
- 默认: 右栏隐藏 (聊天占满)
- 有 artifacts 时: 显示触发按钮
- 点击触发: 右栏展开为 ArtifactFileList 或 ArtifactFileDetail
- 可选: 引入 react-resizable-panels 实现可拖拽分栏

---

## 4. 核心组件详解

### 4.1 ArtifactTrigger — 触发按钮

```tsx
// 仅当 artifacts 非空时渲染
if (!artifacts || artifacts.length === 0) return null

<Button variant="ghost" onClick={() => setArtifactsOpen(true)}>
  <FilesIcon />
  Artifacts ({artifacts.length})
</Button>
```

### 4.2 ArtifactFileList — 文件网格

每个文件渲染为 Card，包含:
- 文件图标 (按扩展名匹配)
- 文件名
- 文件类型描述
- 下载按钮
- `.skill` 文件额外显示安装按钮

```tsx
<ul className="flex flex-col gap-4">
  {files.map(file => (
    <Card className="cursor-pointer" onClick={() => selectArtifact(file)}>
      <CardHeader>
        <CardTitle>
          {getFileIcon(file)}
          {getFileName(file)}
        </CardTitle>
        <CardDescription>{getFileExtensionDisplayName(file)}</CardDescription>
        <CardAction>
          {/* 下载按钮 */}
          <a href={urlOfArtifact({ filepath: file, download: true })}>
            <DownloadIcon /> Download
          </a>
        </CardAction>
      </CardHeader>
    </Card>
  ))}
</ul>
```

### 4.3 ArtifactFileDetail — 文件详情查看器 (最复杂)

**三种查看模式**:

| 模式 | 条件 | 实现 |
|------|------|------|
| Code View | 代码文件 (.py, .js, .ts, etc.) | CodeMirror 编辑器 (语法高亮) |
| Preview | HTML / Markdown | Streamdown 渲染 (iframe 或直接渲染) |
| iframe | 非代码文件 (图片等) | `<iframe src={url} sandbox />` |

**工具栏操作**:
- 复制内容到剪贴板
- 下载文件
- 在新窗口打开
- Code/Preview 模式切换 (仅 HTML/Markdown)
- 文件选择器下拉菜单 (多 artifacts 切换)

**语言检测逻辑**:
```typescript
// checkCodeFile(filepath) → { isCodeFile: boolean, language: string }
// .skill 文件视为 markdown (内部包含 SKILL.md)
// HTML 和 Markdown 额外支持 Preview 模式
```

### 4.4 消息中的 Artifact 链接

Markdown 渲染时，自动检测 `citation:` 前缀链接:
```tsx
// markdown-content.tsx 中的 components.a 处理
if (typeof children === "string") {
  const match = /^citation:(.+)$/.exec(children)
  if (match) return <CitationLink>{text}</CitationLink>
}
```

图片 URL 自动解析为 artifact 后端地址:
```
![](artifact:/mnt/data/chart.png)
→ http://backend/api/threads/{id}/artifacts/mnt/data/chart.png
```

---

## 5. 消息分组系统

### 5.1 groupMessages() 分组策略

**文件**: `core/messages/utils.ts`

消息按角色和内容类型分组:

| 分组类型 | 说明 | 渲染方式 |
|----------|------|---------|
| `human` | 用户消息 | MessageListItem (右对齐) |
| `assistant` | AI 回复 | MessageListItem (左对齐, Markdown) |
| `assistant:clarification` | 追问 | MarkdownContent |
| `assistant:present-files` | 文件展示 | Markdown + ArtifactFileList |
| `assistant:subagent` | 子任务 | SubtaskCard (可折叠) |

### 5.2 ServerHub 对照

ServerHub 的 `useProcessedMessages` 已有类似分组:
- 将 `tool_call` / `tool_result` 挂到前一个 assistant 消息下
- 识别 subagent 风格的 tool calls (有 `subagent_type` 字段)

**需要新增**: `present-files` 类型的识别 — 当 AI 回复中包含文件输出时，提取文件列表并触发 artifact 面板。

---

## 6. SubAgent 任务卡片

### 6.1 SubtaskCard 设计

```tsx
<ChainOfThought open={!collapsed}>
  {/* 头部: 描述 + 状态图标 + 展开/折叠 */}
  <Button onClick={toggle}>
    <ChainOfThoughtStep label={description} icon={<ClipboardListIcon />} />
    {collapsed && <StatusBadge status={task.status} />}
  </Button>

  {/* 内容: prompt + 执行状态 + 结果/错误 */}
  <ChainOfThoughtContent>
    <ChainOfThoughtStep label={task.prompt} />          {/* 原始指令 */}
    {status === "in_progress" && <SpinnerStep />}       {/* 执行中 */}
    {status === "completed" && <MarkdownContent result />}
    {status === "failed" && <ErrorStep error={error} />}
  </ChainOfThoughtContent>
</ChainOfThought>
```

**视觉特效**:
- 执行中: ShineBorder 彩色边框动画 (渐变 border)
- 执行中: Shimmer 文字闪烁效果
- 状态图标: CheckCircle (完成) / XCircle (失败) / Loader2 (旋转中)
- 展开/折叠: ChevronUp 旋转 180°

**ServerHub 适配**: ServerHub 已有 `SubAgentIndicator.tsx`，但功能较简单。可参考 deer-flow 的 ChainOfThought 组件升级为可折叠卡片。

---

## 7. Markdown 渲染对比

### Deer-Flow (Streamdown)

- **库**: `streamdown` (专为流式 AI 对话设计)
- **插件系统**: remarkPlugins + rehypePlugins
- **流式优化**: 逐字显示动画 (`rehypeSplitWordsIntoSpans`)
- **特性**: GFM + LaTeX (KaTeX) + 代码高亮 (Shiki) + citation 链接

### ServerHub (当前)

- **库**: marked.js + highlight.js + mermaid.js + DOMPurify
- **特性**: 代码高亮 + Mermaid 图表 + XSS 过滤
- **流式**: SSE 逐 chunk 拼接

### 适配建议

不需要更换 markdown 库。在现有基础上:
1. 新增 artifact 图片 URL 解析 (在 `MarkdownContent.tsx` 中)
2. 新增 citation 链接渲染
3. Artifacts 通过 SSE `tool_call` 事件中的文件路径列表驱动

---

## 8. 实现路线图 (ServerHub 适配)

### Phase 1: 基础 Artifact 基础设施

**后端**:
- [ ] 新增 `data/artifacts/{conversation_id}/` 目录
- [ ] Agent `write_file` / `execute` 工具产出的文件路径记录到 conversation metadata
- [ ] 新增 `GET /api/agents/conversations/{id}/artifacts/{filepath}` 端点
- [ ] SSE 事件中增加 `artifacts` 字段 (文件列表更新通知)

**前端**:
- [ ] 新增 `stores/artifactStore.ts` (Zustand)
- [ ] 新增 `components/agent/ArtifactPanel.tsx` (文件列表 + 详情)
- [ ] ChatPanel 中集成 artifact 触发按钮

### Phase 2: 文件查看器

- [ ] 文件列表网格 (卡片式)
- [ ] 文件详情: 代码查看器 (用 CodeMirror 或现有 highlight.js)
- [ ] 文件详情: 图片预览
- [ ] 文件详情: Markdown 预览
- [ ] 复制/下载/新窗口操作

### Phase 3: 布局集成

- [ ] 右栏切换: 管理面板 ↔ Artifacts 面板
- [ ] 可选: 引入 `react-resizable-panels` 实现可拖拽分栏
- [ ] 消息中的 artifact 引用链接
- [ ] 自动打开/选择行为

### Phase 4: 增强体验

- [ ] SubAgent 任务卡片升级 (参考 ChainOfThought)
- [ ] 流式文字动画效果
- [ ] ShineBorder / Shimmer 执行中动画
- [ ] 文件类型图标系统

---

## 9. 关键文件索引 (Deer-Flow)

### Artifacts 核心
| 文件 | 功能 |
|------|------|
| `src/core/artifacts/utils.ts` | URL 拼接、artifact 提取 |
| `src/core/artifacts/loader.ts` | 内容加载 (HTTP / 从 tool_call 提取) |
| `src/core/artifacts/hooks.ts` | useArtifactContent (react-query 缓存) |
| `src/components/workspace/artifacts/context.tsx` | ArtifactsProvider (状态管理) |
| `src/components/workspace/artifacts/artifact-trigger.tsx` | 触发按钮 |
| `src/components/workspace/artifacts/artifact-file-list.tsx` | 文件列表网格 |
| `src/components/workspace/artifacts/artifact-file-detail.tsx` | 文件详情查看器 (code/preview/iframe) |

### 消息渲染
| 文件 | 功能 |
|------|------|
| `src/components/workspace/messages/message-list.tsx` | 消息列表 (分组渲染) |
| `src/components/workspace/messages/message-list-item.tsx` | 单条消息 |
| `src/components/workspace/messages/markdown-content.tsx` | Markdown 渲染 (citation 链接) |
| `src/components/workspace/messages/subtask-card.tsx` | SubAgent 任务卡片 |
| `src/core/messages/utils.ts` | 消息分组、内容提取 |

### 布局
| 文件 | 功能 |
|------|------|
| `src/components/workspace/chats/chat-box.tsx` | ResizablePanelGroup 布局 |
| `src/components/workspace/input-box.tsx` | 输入框 |

### Markdown/渲染
| 文件 | 功能 |
|------|------|
| `src/core/streamdown/plugins.ts` | Streamdown 插件配置 |
| `src/core/rehype/index.ts` | Rehype 逐字动画插件 |
| `src/components/workspace/citations/artifact-link.tsx` | Artifact 链接渲染 |
| `src/components/ai-elements/code-block.tsx` | Shiki 代码高亮 |
| `src/components/ai-elements/reasoning.tsx` | 思维过程折叠 |
| `src/components/ai-elements/conversation.tsx` | Conversation 容器组件 |
| `src/components/ai-elements/message.tsx` | Message 基础组件 |

### ServerHub 现有相关文件
| 文件 | 功能 | 需改动 |
|------|------|--------|
| `frontend/src/pages/agents/ChatPanel.tsx` | 聊天面板主组件 | 集成 artifact 触发 |
| `frontend/src/pages/agents/MessageBubble.tsx` | 消息气泡 | 添加 artifact 链接 |
| `frontend/src/pages/agents/MarkdownContent.tsx` | Markdown 渲染 | 添加 artifact URL 解析 |
| `frontend/src/hooks/useProcessedMessages.ts` | 消息分组 | 添加 artifact 类型识别 |
| `frontend/src/stores/chatStore.ts` | 聊天状态 | 添加 artifacts 字段 |
| `frontend/src/components/agent/UICard.tsx` | 通用卡片 | 可复用 |

---

## 10. 设计亮点与取舍

### Deer-Flow 的优秀设计

1. **双模式内容加载**: 服务端文件走 HTTP，write-file 走内存提取 → 减少不必要请求
2. **autoSelect/autoOpen**: 新文件自动打开面板，用户手动关闭后停止自动行为 → 智能但不过度打扰
3. **ResizablePanel**: 用户可自由调整聊天与 artifact 面板比例 → 灵活
4. **消息分组系统**: 5 种分组类型精确匹配不同渲染需求 → 清晰
5. **.skill 文件处理**: ZIP 包自动提取 SKILL.md 预览 → 完善的文件类型支持

### ServerHub 不需要照搬的部分

1. **Streamdown 库**: ServerHub 的 marked.js 已满足需求，流式场景通过 SSE 拼接实现
2. **LangGraph SDK useStream**: ServerHub 有自己的 SSE hook (useSSEChat)
3. **Next.js App Router**: ServerHub 是 SPA，不需要路由系统
4. **Sidebar 联动**: ServerHub 有独立的三栏布局，不需要侧边栏让位逻辑
