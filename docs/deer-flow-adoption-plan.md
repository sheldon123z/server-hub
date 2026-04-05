# DeerFlow 优点吸收 — 全栈实施计划

> 来源：deer-flow (`~/exps/deer-flow/`) 前后端对比分析
> 目标：server-hub (`~/scripts/server-hub/`) Agent 体验全面升级
> 优先级：P0(必须) → P1(重要) → P2(锦上添花)
> 范围：前端 6 项 + 后端 5 项，共 11 项改进

---

# 第一部分：前端改进

## 前端总体架构影响

```
frontend/src/
├── components/
│   ├── chat/                    # 🆕 新建：聊天组件目录
│   │   ├── ChatInput.tsx        # FE-4: Compound 输入框
│   │   ├── ChatInputAttachments.tsx
│   │   ├── ChatInputFooter.tsx
│   │   ├── ChatInputSubmit.tsx
│   │   ├── MessageGroup.tsx     # FE-2: 消息分组容器
│   │   ├── MessageGroupHeader.tsx
│   │   ├── ToolCallCard.tsx     # FE-5: 重构自 ToolCallBox
│   │   ├── FollowUpSuggestions.tsx  # FE-3: 推荐追问
│   │   └── StreamingText.tsx    # FE-1: 逐字流式文本
│   ├── ui/                      # 🆕 新建：通用 UI 组件
│   │   └── Collapsible.tsx      # 折叠/展开容器
│   └── agent/                   # 已有：Agent UI 组件
├── hooks/
│   ├── useSSEChat.ts            # ✏️ 改造：支持新 SSE 事件类型
│   ├── useProcessedMessages.ts  # ✏️ 改造：消息分组逻辑
│   ├── useFollowUpSuggestions.ts # 🆕 新建
│   └── useStreamingText.ts      # 🆕 新建：逐字动画 hook
├── lib/
│   ├── markdown.ts              # ✏️ 改造：流式渲染支持
│   ├── message-utils.ts         # 🆕 新建：类型守卫 + 分组工具
│   └── utils.ts                 # 已有
├── pages/agents/
│   ├── ChatPanel.tsx            # ✏️ 改造：使用新组件
│   ├── MessageBubble.tsx        # ✏️ 改造：集成 StreamingText
│   ├── ToolCallBox.tsx          # ✏️ 改造 → 逐步替换为 ToolCallCard
│   └── ...                      # 其余不动
└── types/
    └── agent.ts                 # ✏️ 改造：新增类型定义
```

# 第二部分：后端改进

## 后端总体架构影响

```
modules/agents/
├── middleware/                   # 🆕 新建：自定义中间件目录
│   ├── __init__.py
│   ├── loop_detection.py        # BE-1: 循环检测中间件
│   ├── dangling_toolcall.py     # BE-2: 残缺工具调用修补
│   └── auto_title.py            # BE-3: 自动对话标题生成
├── tools/
│   ├── __init__.py              # ✏️ 改造：工具分组注册
│   ├── tool_groups.py           # 🆕 新建：工具分组定义 + DeferredToolRegistry
│   └── tool_search.py           # 🆕 新建：延迟工具搜索工具
├── memory/                      # 🆕 新建：结构化记忆系统
│   ├── __init__.py
│   ├── structured_store.py      # 结构化记忆读写
│   └── memory_updater.py        # 对话结束后提取事实
├── deep_agent.py                # ✏️ 改造：注册新中间件 + 延迟工具
├── safety.py                    # 不变
└── routes/
    └── chat.py                  # ✏️ 改造：suggestions SSE 事件（配合 FE-3）
```

---

## P0-1: 流式 Markdown 逐字渲染

### 当前问题
- `lib/markdown.ts` 使用 `marked.js` 整段解析 → 整段输出
- SSE 收到 `message` 事件时，整条 `content` 重新渲染
- 用户看到的是「空白 → 突然出现一大段」，没有渐进感

### DeerFlow 方案
- 使用 `streamdown` 库 + `rehypeSplitWordsIntoSpans` 插件
- 每个 token 到达时只追加新内容，不重新渲染整段
- CJK 字符跳过分词，直接逐字显示

### ServerHub 实施方案

**核心思路**：不引入新依赖，基于现有 `marked.js` 实现增量渲染。

**Step 1: 新建 `useStreamingText.ts` hook**

```typescript
// frontend/src/hooks/useStreamingText.ts
// 核心逻辑：
// - 维护一个 contentRef（当前累积的全部文本）
// - 每次 SSE message 事件追加 delta
// - 用 requestAnimationFrame 逐字符展示（不是逐 token）
// - 提供 displayedContent（已展示的部分）给渲染层

interface UseStreamingTextOptions {
  charDelay?: number      // 每字符延迟(ms)，默认 15
  enabled?: boolean       // 是否启用动画
}

function useStreamingText(fullContent: string, options?: UseStreamingTextOptions) {
  // Returns: { displayedContent: string, isAnimating: boolean }
}
```

**Step 2: 改造 `MarkdownContent.tsx`**

```
当前：<MarkdownContent content={msg.content} />
改为：
  - streaming 时：<MarkdownContent content={displayedContent} streaming />
  - 非 streaming：<MarkdownContent content={msg.content} />

新增 streaming 模式：
  - 不使用 dangerouslySetInnerHTML，改用分段渲染
  - 检测最后一个未闭合的代码块/表格，延迟渲染
  - 代码块在 streaming 期间只显示文本，完成后高亮
```

**Step 3: 改造 `useSSEChat.ts`**

当前 SSE 处理 `message` 事件时是 `store.pushMsg(content)` 整条替换。
需要改为：
- 追踪 `streamingMessageId`（当前正在流式输出的消息 ID）
- 收到 `message` 事件时：如果 streamingMessageId 存在 → updateMsg；不存在 → pushMsg
- 收到 `done` 事件时：清除 streamingMessageId，触发最终 markdown 完整渲染

**涉及文件**：
- `frontend/src/hooks/useStreamingText.ts` — 新建
- `frontend/src/pages/agents/MarkdownContent.tsx` — 改造
- `frontend/src/hooks/useSSEChat.ts` — 改造 message 事件处理
- `frontend/src/stores/chatStore.ts` — 新增 updateStreamingMsg 方法

**注意事项**：
- `marked.js` 对不完整 markdown 的容错性差，streaming 期间可能产生闪烁
- 方案 A（推荐）：streaming 期间用纯文本 + 逐字显示，`done` 后切到 markdown 渲染
- 方案 B（复杂但体验好）：引入 `streamdown` 库处理流式 markdown（需新增依赖）

---

## P0-2: 消息分组 + 折叠

### 当前问题
- `useProcessedMessages.ts` 已有基础的 tool_call → assistant 分组
- 但渲染是扁平的：ToolCallBox 列表平铺在消息下方
- 多个连续工具调用无法折叠，占用大量视觉空间
- 推理过程（thinking）没有专门展示

### DeerFlow 方案
- 6 种消息分组类型：`human`, `assistant:content`, `assistant:processing`, `assistant:clarification`, `assistant:subagent`, `assistant:present-files`
- `MessageGroup` 组件：标题栏 + 折叠体 + 展开动画
- Tool call 链：只展开最后一个，其余折叠

### ServerHub 实施方案

**Step 1: 新建 `lib/message-utils.ts`（类型守卫）**

```typescript
// 从 deer-flow 移植的类型守卫模式
export function hasToolCalls(msg: ProcessedMessage): boolean
export function hasSubAgents(msg: ProcessedMessage): boolean
export function hasContent(msg: ProcessedMessage): boolean
export function isThinking(msg: ProcessedMessage): boolean
export function getMessageGroupType(msg: ProcessedMessage): MessageGroupType

type MessageGroupType =
  | 'content'           // 纯文本回复
  | 'processing'        // 工具调用链（可折叠）
  | 'subagent'          // SubAgent 任务
  | 'mixed'             // 文本 + 工具混合
```

**Step 2: 新建 `components/chat/MessageGroup.tsx`**

```tsx
// 消息分组容器组件
// Props: groupType, toolCalls[], subAgents[], isCollapsible, defaultExpanded
//
// 渲染逻辑：
// - content 类型：直接显示 MarkdownContent
// - processing 类型：
//   - 标题栏：「使用了 N 个工具」+ 展开/折叠图标
//   - 折叠体：ToolCallCard 列表
//   - 默认折叠（只显示最后一个工具调用结果）
//   - 最近一条不折叠，其余折叠
// - subagent 类型：
//   - 标题栏：SubAgent 名称 + 状态指示
//   - 折叠体：子任务列表 + 进度
// - mixed 类型：先显示文本，再显示可折叠的工具调用区
```

**Step 3: 新建 `components/ui/Collapsible.tsx`**

```
简单的折叠/展开容器，用 CSS transition 实现高度动画
（如果不想引入 Radix UI，可以手写；否则用 @radix-ui/react-collapsible）
Props: open, onOpenChange, children, header
```

**Step 4: 新建 `components/chat/MessageGroupHeader.tsx`**

```
分组标题栏：图标 + 文字 + 展开箭头
- processing：「🔧 调用了 3 个工具」
- subagent：「🤖 研究员正在搜索...」
```

**Step 5: 改造 `ChatPanel.tsx`**

```
当前：遍历 ProcessedMessage[]，对每条渲染 MessageBubble + ToolCallBox 列表
改为：遍历 ProcessedMessage[]，根据 groupType 用 MessageGroup 包裹

渲染逻辑变更：
- assistant 消息：
  <MessageGroup type="processing" toolCalls={msg.toolCalls}>
    <MessageBubble message={msg} />   {/* assistant 文本 */}
    {msg.toolCalls.map(tc => <ToolCallCard />)}  {/* 折叠区 */}
  </MessageGroup>
- user 消息：不变
```

**涉及文件**：
- `frontend/src/lib/message-utils.ts` — 新建
- `frontend/src/components/chat/MessageGroup.tsx` — 新建
- `frontend/src/components/chat/MessageGroupHeader.tsx` — 新建
- `frontend/src/components/ui/Collapsible.tsx` — 新建
- `frontend/src/pages/agents/ChatPanel.tsx` — 改造渲染逻辑
- `frontend/src/types/agent.ts` — 新增 MessageGroupType

---

## P0-3: Follow-up Suggestions（推荐追问）

### 当前问题
- AI 回复后用户需要自己想下一步问什么
- 没有任何引导性提示

### DeerFlow 方案
- AI 完成回复后自动生成 3 条建议
- 显示在输入框上方，点击即可发送
- 有 dismiss 按钮

### ServerHub 实施方案

**方案 A（推荐）：后端生成 suggestions**

**Step 1: 后端新增 SSE 事件类型**

在 `modules/agents/routes/chat.py` 的 SSE 流中新增 `suggestions` 事件：
```python
# 在 agent 完成（on_done）时，用 LLM 快速生成 3 条建议
# 或者由 agent 工具调用 generate_suggestions 生成
event: suggestions
data: {"suggestions": ["检查 Docker 容器状态", "查看系统资源使用", "最近有什么异常？"]}
```

**Step 2: 新建 `components/chat/FollowUpSuggestions.tsx`**

```tsx
// Props: suggestions: string[], onSelect: (text: string) => void, onDismiss: () => void
// 渲染：输入框上方 3 个可点击的建议标签（pill/chip 样式）
// 交互：点击 → onSelect(text) → 发送消息；× → onDismiss()
// 样式：圆角胶囊标签，hover 高亮，有淡入动画
```

**Step 3: 新建 `hooks/useFollowUpSuggestions.ts`**

```typescript
// 从 chatStore 读取 suggestions
// 提供 dismissSuggestions(), selectSuggestion(text) 方法
// 选择后自动调用 sendMessage
```

**Step 4: 改造 `useSSEChat.ts`**

在 SSE 事件处理中新增 `suggestions` 事件类型：
```typescript
case 'suggestions':
  store.setSuggestions(data.suggestions)
  break
```

**Step 5: 改造 `chatStore.ts`**

新增状态：
```typescript
suggestions: string[]
setSuggestions: (s: string[]) => void
clearSuggestions: () => void
```

**Step 6: 改造 `ChatPanel.tsx` / `ChatInput`**

在输入框上方渲染 `<FollowUpSuggestions />`

**涉及文件**：
- `frontend/src/components/chat/FollowUpSuggestions.tsx` — 新建
- `frontend/src/hooks/useFollowUpSuggestions.ts` — 新建
- `frontend/src/hooks/useSSEChat.ts` — 新增 suggestions 事件处理
- `frontend/src/stores/chatStore.ts` — 新增 suggestions 状态
- `frontend/src/pages/agents/ChatPanel.tsx` — 渲染位置
- `modules/agents/routes/chat.py` — 新增 suggestions SSE 事件（可选后端方案）

**方案 B（纯前端，快速上线）**：
- 不改后端，前端根据当前页面上下文和最后一条回复生成硬编码建议
- 用关键词匹配：如果提到 Docker → 建议查看容器/镜像；提到用户 → 建议查看配额/登录历史
- 优点：无需后端改动，立即上线
- 缺点：建议质量低

---

## P1-4: Compound Component 模式的聊天输入框

### 当前问题
- 聊天输入逻辑内嵌在 `ChatWidget.tsx`（644行）中
- 添加新功能（文件上传、模式切换、模型选择）需要改核心代码
- 没有清晰的组合接口

### DeerFlow 方案
```tsx
<PromptInput>
  <PromptInputBody>
    <PromptInputTextarea />
  </PromptInputBody>
  <PromptInputFooter>
    <PromptInputTools>
      <PromptInputButton />     {/* 附件 */}
      <PromptInputActionMenu>   {/* 模式选择 */}
      <ModelSelector />         {/* 模型选择 */}
    </PromptInputTools>
    <PromptInputSubmit />       {/* 发送/停止 */}
  </PromptInputFooter>
</PromptInput>
```

### ServerHub 实施方案

**Step 1: 从 ChatWidget 中提取聊天输入**

```
当前 ChatWidget.tsx 职责：
  - 渲染消息列表（保留）
  - 渲染输入框 + 发送按钮（提取）
  - SSE 连接管理（保留在 useSSEChat）
  - 模式切换（提取）
  - 快捷指令菜单（提取到 ChatInputFooter）

提取后的 ChatWidget 只做：
  <div className="chat-container">
    <MessageList messages={...} />
    <FollowUpSuggestions />
    <ChatInput onSend={sendMessage} />
  </div>
```

**Step 2: 新建 `components/chat/ChatInput.tsx`（Compound 模式）**

```tsx
// 顶层容器组件
// 管理：输入文本状态、submit 逻辑、快捷键
// 渲染子组件通过 React.Children 或 render props

interface ChatInputProps {
  onSend: (text: string, options?: SendOptions) => void
  onStop?: () => void
  streaming?: boolean
  children?: React.ReactNode  // 允许自定义 footer 内容
}

// 子组件（独立文件，通过 props 通信）
ChatInput.TextArea    — 输入区域（textarea + 自动高度 + 快捷键）
ChatInput.Attachments — 文件附件区（预留）
ChatInput.Footer      — 底部工具栏容器
ChatInput.ModeToggle  — supervised/autonomous 切换
ChatInput.SkillMenu   — 技能快捷菜单（已有 SlashCommandMenu 迁移）
ChatInput.Submit      — 发送/停止按钮
```

**Step 3: 新建各子组件**

| 文件 | 职责 |
|------|------|
| `ChatInputAttachments.tsx` | 附件预览区（预留接口，暂不实现上传） |
| `ChatInputFooter.tsx` | 底部工具栏 flex 容器 |
| `ChatInputSubmit.tsx` | 发送（ArrowUp）/ 停止（Square）按钮 |

**Step 4: 改造 `ChatWidget.tsx`**

```tsx
// 从 644 行缩减到 ~150 行
// 核心结构：
<div className="flex flex-col h-full">
  <MessageList />
  <FollowUpSuggestions />
  <ChatInput onSend={sendMessage} onStop={stopStreaming} streaming={streaming}>
    <ChatInput.Footer>
      <SafetyToggle />       {/* 已有组件 */}
      <SlashCommandMenu />   {/* 已有组件 */}
      <ChatInput.Submit />
    </ChatInput.Footer>
  </ChatInput>
</div>
```

**涉及文件**：
- `frontend/src/components/chat/ChatInput.tsx` — 新建
- `frontend/src/components/chat/ChatInputAttachments.tsx` — 新建
- `frontend/src/components/chat/ChatInputFooter.tsx` — 新建
- `frontend/src/components/chat/ChatInputSubmit.tsx` — 新建
- `frontend/src/components/agent/ChatWidget.tsx` — 大幅简化

---

## P1-5: Tool Call 卡片化

### 当前问题
- `ToolCallBox.tsx` 是单行紧凑样式（`flex items-center`）
- 只显示工具名 + 3 个参数预览 + 状态图标
- 结果文本不可展开查看
- 没有区分不同工具类型的视觉差异

### DeerFlow 方案
- 每个工具调用是独立卡片
- 不同工具类型有不同的图标和颜色
- 可展开查看完整参数和返回值
- 搜索工具有结果预览
- 文件操作有文件图标

### ServerHub 实施方案

**Step 1: 新建 `components/chat/ToolCallCard.tsx`**

```
替代现有 ToolCallBox.tsx 的升级版

视觉设计：
┌──────────────────────────────────────┐
│ 🔧 docker_ps    ✅ 已完成    ▼ 展开  │
│                                      │
│ [展开区域]                            │
│ 参数:                                 │
│   container: "docker-api-1"          │
│   action: "logs"                     │
│ 结果:                                 │
│   2024-01-15 10:30:00 Server start.. │
└──────────────────────────────────────┘

Props:
  - toolCall: ToolCallItem
  - defaultExpanded?: boolean  // 默认折叠
  - compact?: boolean          // 紧凑模式（用于折叠区内的列表项）
```

**Step 2: 工具分类图标映射**

```typescript
// lib/message-utils.ts 中新增
const TOOL_ICONS: Record<string, { icon: LucideIcon; color: string }> = {
  // Docker 类
  list_containers: { icon: Box, color: 'text-blue' },
  docker_container_exec: { icon: Terminal, color: 'text-blue' },
  // 系统类
  get_system_overview: { icon: Activity, color: 'text-green' },
  get_disk_usage: { icon: HardDrive, color: 'text-orange' },
  // 用户类
  manage_linux_user: { icon: Users, color: 'text-purple' },
  // 服务类
  manage_service: { icon: Settings, color: 'text-yellow' },
  // 通用
  execute: { icon: Play, color: 'text-text2' },
  read_file: { icon: FileText, color: 'text-cyan' },
  // 默认
  _default: { icon: Wrench, color: 'text-text3' },
}
```

**Step 3: 结果预览优化**

```
- 文本结果：截断显示前 200 字符，展开查看全部
- JSON 结果：格式化显示（2 空格缩进）
- 错误结果：红色边框 + 错误图标
- 长结果：虚拟滚动或 lazy 渲染（超过 1000 行时）
```

**涉及文件**：
- `frontend/src/components/chat/ToolCallCard.tsx` — 新建
- `frontend/src/lib/message-utils.ts` — 新增 TOOL_ICONS 映射
- `frontend/src/pages/agents/ChatPanel.tsx` — 引用 ToolCallCard 替换 ToolCallBox
- `frontend/src/pages/agents/ToolCallBox.tsx` — 保留（向后兼容），标记 @deprecated

---

## P1-6: 消息类型守卫函数

### 当前问题
- `agent.ts` 中有类型定义但没有运行时判断
- `useProcessedMessages.ts` 中大量 `msg.args?.xxx` 链式访问
- `MessageBubble.tsx` 中 `as UIComponentMessage` 强转
- `extractContent()` 函数散布在多处处理 `string | ContentPart[]` 问题

### DeerFlow 方案
- 统一的 `hasContent()`, `hasToolCalls()`, `isClarification()` 等守卫函数
- 消息工具函数集中在 `core/messages/utils.ts`
- 类型守卫返回 `msg is XXX` 类型缩窄

### ServerHub 实施方案

**Step 1: 扩展 `lib/message-utils.ts`**

```typescript
// ===== 类型守卫 =====

/** 判断消息是否有可见文本内容 */
export function hasContent(msg: ChatMessage | ProcessedMessage): boolean {
  const content = 'message' in msg ? msg.message.content : msg.content
  return typeof content === 'string' ? content.trim().length > 0 : Array.isArray(content) && content.length > 0
}

/** 判断 ProcessedMessage 是否有工具调用 */
export function hasToolCalls(msg: ProcessedMessage): boolean {
  return msg.toolCalls != null && msg.toolCalls.length > 0
}

/** 判断 ProcessedMessage 是否有 SubAgent */
export function hasSubAgents(msg: ProcessedMessage): boolean {
  return msg.subAgents != null && msg.subAgents.length > 0
}

/** 提取消息的文本内容（统一处理 string | ContentPart[]） */
export function extractTextContent(content: string | ContentPart[] | undefined): string {
  if (!content) return ''
  if (typeof content === 'string') return content
  return content
    .filter((part): part is TextContentPart => part.type === 'text')
    .map((part) => part.text)
    .join('')
}

// ===== 消息分组辅助 =====

/** 判断工具调用是否已完成 */
export function isToolCallCompleted(tc: ToolCallItem): boolean {
  return tc.result !== undefined && tc.result !== null
}

/** 判断 SubAgent 是否已完成 */
export function isSubAgentCompleted(sa: SubAgentItem): boolean {
  return sa.status === 'completed'
}

/** 获取工具的显示图标和颜色 */
export function getToolDisplayInfo(toolName: string): { icon: string; color: string; label: string }
```

**Step 2: 在各组件中使用守卫替换手动检查**

```
改造前：
  if (msg.toolCalls && msg.toolCalls.length > 0) { ... }

改造后：
  if (hasToolCalls(msg)) { ... }
```

**Step 3: 消除 `as` 强转**

```typescript
// 改造前
const uiMsg = message as UIComponentMessage

// 改造后
function isUIComponentMessage(msg: ChatMessage): msg is UIComponentMessage {
  return msg.role === 'ui_component' && 'componentType' in msg
}

if (isUIComponentMessage(message)) {
  // 此处 message 自动缩窄为 UIComponentMessage
}
```

**涉及文件**：
- `frontend/src/lib/message-utils.ts` — 新建/扩展
- `frontend/src/hooks/useProcessedMessages.ts` — 用守卫替换手动检查
- `frontend/src/pages/agents/MessageBubble.tsx` — 消除 as 强转
- `frontend/src/pages/agents/ChatPanel.tsx` — 用守卫简化条件渲染

---

---

## BE-1: LoopDetection 中间件（循环检测与打断）

### 当前问题
- Agent 在某些场景下会重复调用相同工具（如反复 `get_system_overview` 而不采取行动）
- `ModelCallLimitMiddleware` 只限制总轮数（50/100），不检测**重复模式**
- 用户只能干等，直到轮数耗尽才停止，浪费 token 和时间

### DeerFlow 方案
```python
# LoopDetectionMiddleware — 检测连续相同/相似的工具调用模式
# 当检测到循环时：
#   1. 向 agent 注入一条 "你似乎在重复调用相同工具，请改变策略" 的提示
#   2. 如果连续 3 次注入后仍循环，自动终止并返回最后一条消息
```

### ServerHub 实施方案

**Step 1: 新建 `modules/agents/middleware/__init__.py`**

```python
# 中间件子包，统一导出
from modules.agents.middleware.loop_detection import LoopDetectionMiddleware
from modules.agents.middleware.dangling_toolcall import DanglingToolCallMiddleware
from modules.agents.middleware.auto_title import AutoTitleMiddleware
```

**Step 2: 新建 `modules/agents/middleware/loop_detection.py`**

```python
"""
LoopDetectionMiddleware — 检测 agent 重复工具调用循环

检测逻辑：
1. 维护最近 N 轮的工具调用历史（滑动窗口，默认 6 轮）
2. 计算「重复率」：相同工具名 + 相似参数的调用占比
3. 重复率超过阈值（默认 60%）时触发干预
4. 干预方式：注入一条 AIMessage 提醒 agent 改变策略
5. 连续干预 3 次仍循环 → 强制终止，返回当前最佳回复

实现方式：
- 继承 LangChain BaseMiddleware（与现有 ModelRetryMiddleware 同级）
- 在 on_tool_call 回调中记录工具调用
- 在 on_llm_start 回调中检查循环模式
- 参数化配置：window_size=6, threshold=0.6, max_interventions=3
"""

class LoopDetectionMiddleware:
    """检测并打断 agent 的工具调用循环"""
    
    def __init__(self, window_size=6, threshold=0.6, max_interventions=3):
        self.window_size = window_size       # 滑动窗口大小
        self.threshold = threshold           # 重复率阈值
        self.max_interventions = max_interventions  # 最大干预次数
        self._history: list[str] = []        # 工具调用签名历史
        self._intervention_count = 0         # 已干预次数
    
    def _compute_signature(self, tool_name: str, args: dict) -> str:
        """计算工具调用的签名（工具名 + 参数 key 集合，忽略具体值）"""
        # 例如: "get_system_overview:{server_id}" 
        # 而非: "get_system_overview:{server_id:'local',verbose:true}"
        keys = sorted(args.keys()) if args else []
        return f"{tool_name}:{','.join(keys)}"
    
    def _detect_loop(self) -> bool:
        """在滑动窗口内检测循环模式"""
        if len(self._history) < 3:
            return False
        window = self._history[-self.window_size:]
        if not window:
            return False
        # 计算最频繁签名的占比
        from collections import Counter
        counter = Counter(window)
        most_common_count = counter.most_common(1)[0][1]
        return (most_common_count / len(window)) >= self.threshold
```

**Step 3: 注册到 `deep_agent.py`**

在 `_build_extra_middleware()` 中添加：
```python
from modules.agents.middleware import LoopDetectionMiddleware

# 6. 循环检测 — 防止 agent 重复调用相同工具
extra.append(LoopDetectionMiddleware(
    window_size=6,        # 检测最近 6 轮
    threshold=0.6,        # 60% 重复率触发
    max_interventions=3,  # 最多干预 3 次
))
```

**涉及文件**：
- `modules/agents/middleware/__init__.py` — 新建
- `modules/agents/middleware/loop_detection.py` — 新建
- `modules/agents/deep_agent.py` — 注册中间件

---

## BE-2: DanglingToolCall 修补中间件

### 当前问题
- 当工具调用抛出未捕获异常时，LangGraph 期望收到对应的 `ToolMessage`，但异常导致消息缺失
- 此时 agent 图直接报错 `Expected ToolMessage for tool_call_id xxx`，对话中断
- 用户看到的是一串错误日志，而非 agent 的回复

### DeerFlow 方案
```python
# DanglingToolCallMiddleware — 在 agent 输出后检查是否有未匹配的 tool_call
# 如果发现 dangling tool_call（有 call 无 result），自动补充一条 ToolMessage
# 内容为错误提示，让 agent 能继续推理
```

### ServerHub 实施方案

**Step 1: 新建 `modules/agents/middleware/dangling_toolcall.py`**

```python
"""
DanglingToolCallMiddleware — 修补缺失的 ToolMessage

触发时机：agent 节点输出后、写入 checkpoint 前
检测逻辑：遍历消息列表，找到有 tool_calls 的 AIMessage，
         检查每个 tool_call 是否有对应的 ToolMessage
修补策略：对缺失的 tool_call_id，补充一条 ToolMessage：
         content="[工具执行失败: 未收到结果，请重试或换一种方式]"
         tool_call_id=<缺失的id>
"""

class DanglingToolCallMiddleware:
    """修补缺失的 ToolMessage，防止 LangGraph 报错中断对话"""
    
    def patch_state(self, state: dict) -> dict:
        """在 agent 输出后修补 dangling tool calls"""
        messages = state.get("messages", [])
        if not messages:
            return state
        
        # 找出所有 tool_call_id
        expected_ids = set()
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    expected_ids.add(tc.get("id"))
        
        # 找出所有已回复的 tool_call_id
        replied_ids = set()
        for msg in messages:
            if isinstance(msg, ToolMessage):
                replied_ids.add(getattr(msg, "tool_call_id", None))
        
        # 找出 dangling 的
        dangling = expected_ids - replied_ids - {None}
        
        if dangling:
            # 补充 ToolMessage
            patch_messages = [
                ToolMessage(
                    content="[工具执行异常: 未收到返回结果，请尝试其他方式完成任务]",
                    tool_call_id=tid,
                )
                for tid in dangling
            ]
            state["messages"] = messages + patch_messages
            logger.warning("修补了 %d 个 dangling tool calls: %s", len(dangling), dangling)
        
        return state
```

**Step 2: 注册到 `deep_agent.py`**

```python
from modules.agents.middleware import DanglingToolCallMiddleware

# 7. Dangling ToolCall 修补 — 防止工具异常导致对话中断
extra.append(DanglingToolCallMiddleware())
```

**涉及文件**：
- `modules/agents/middleware/dangling_toolcall.py` — 新建
- `modules/agents/deep_agent.py` — 注册中间件

---

## BE-3: AutoTitleMiddleware（自动对话标题）

### 当前问题
- 新对话的标题默认是 "新对话" 或第一条消息的截断
- 没有根据对话内容自动生成有意义的标题
- 侧边栏对话列表难以区分不同对话

### DeerFlow 方案
```python
# TitleMiddleware — 在 agent 完成第一轮回复后，用 LLM 生成简短标题
# 标题存入 thread metadata，前端自动刷新显示
# 用的是最快的模型（flash/haiku），成本极低
```

### ServerHub 实施方案

**Step 1: 新建 `modules/agents/middleware/auto_title.py`**

```python
"""
AutoTitleMiddleware — 自动生成对话标题

触发条件：对话的前 2 轮内（避免每次都生成）
生成方式：用轻量模型（patrol model 或 haiku）对消息摘要生成标题
持久化：写入 conversations 表的 title 字段
"""

# 标题生成 prompt（极简，减少 token）
TITLE_PROMPT = """根据以下对话内容，生成一个 10 字以内的简短标题。
只输出标题本身，不要引号、不要解释。

用户: {user_msg}
助手: {assistant_msg}

标题:"""

class AutoTitleMiddleware:
    """对话第一轮结束后自动生成标题"""
    
    def __init__(self):
        self._titled_conversations: set[str] = set()  # 已生成标题的对话
    
    async def maybe_generate_title(
        self,
        conversation_id: str,
        messages: list,  # 当前对话的消息列表
    ) -> str | None:
        """检查是否需要生成标题，如果需要则调用 LLM 生成
        
        Returns: 生成的标题，或 None（不需要生成）
        """
        # 已生成过标题 → 跳过
        if conversation_id in self._titled_conversations:
            return None
        
        # 至少有 1 轮对话（user + assistant）才生成
        user_msgs = [m for m in messages if isinstance(m, HumanMessage)]
        assistant_msgs = [m for m in messages if isinstance(m, AIMessage)]
        if not user_msgs or not assistant_msgs:
            return None
        
        # 用轻量模型生成标题
        from modules.agents.llm import get_chat_model
        model = get_chat_model("patrol")  # 用便宜模型
        
        prompt = TITLE_PROMPT.format(
            user_msg=str(user_msgs[0].content)[:200],
            assistant_msg=str(assistant_msgs[-1].content)[:200],
        )
        
        try:
            result = await model.ainvoke(prompt)
            title = str(result.content).strip().strip('"').strip("'")[:30]
            self._titled_conversations.add(conversation_id)
            return title
        except Exception as e:
            logger.warning("标题生成失败: %s", e)
            return None
```

**Step 2: 在 SSE 流结束时触发生成**

在 `modules/agents/routes/chat.py` 的 `event_generator` 中，`run.completed` 事件之前：

```python
# 检查并生成标题
title_middleware = AutoTitleMiddleware()  # 或从 agent 获取实例
title = await title_middleware.maybe_generate_title(conversation_id, all_messages)
if title:
    # 更新数据库
    await db.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))
    await db.commit()
    # 发送标题更新事件给前端
    yield {"event": "title.update", "data": json.dumps({"title": title, "conversation_id": conversation_id})}
```

**Step 3: 前端处理 `title.update` 事件**

在 `useSSEChat.ts` 中新增：
```typescript
case 'title.update':
  // 更新 chatStore 中的对话标题
  store.setConversationTitle(data.title)
  // 触发侧边栏刷新
  queryClient.invalidateQueries({ queryKey: ['conversations'] })
  break
```

**涉及文件**：
- `modules/agents/middleware/auto_title.py` — 新建
- `modules/agents/routes/chat.py` — SSE 流结束前触发
- `frontend/src/hooks/useSSEChat.ts` — 新增 title.update 事件
- `frontend/src/stores/chatStore.ts` — 新增 setConversationTitle

---

## BE-4: DeferredToolRegistry（延迟工具加载）

### 当前问题
- `get_server_tools()` 一次性加载 **45+ 个工具**到 agent 上下文
- 每个工具的 name + description 在 system prompt 中占用 token（估计 3000-5000 tokens）
- 大部分对话只用到 3-5 个工具，剩余的工具描述是浪费
- 工具越多，模型选择工具的准确率越低

### DeerFlow 方案
```python
# 将工具分为「核心组」和「延迟组」
# 核心组：始终加载（execute, read_file, list_containers 等高频工具）
# 延迟组：注册到 DeferredToolRegistry，通过 tool_search 按需加载
# agent 需要时调用 tool_search("docker") → 返回匹配的工具描述 → 动态注入
```

### ServerHub 实施方案

**Step 1: 新建 `modules/agents/tools/tool_groups.py`（工具分组定义）**

```python
"""
工具分组 — 核心工具始终加载，其余按需搜索加载

分组策略：
- core: 始终加载（agent 的基本能力）
- system: 系统监控类（按需）
- docker: 容器管理类（按需）
- services: 服务管理类（按需）
- users: 用户管理类（按需）
- cron: 定时任务类（按需）
- security: 安全合规类（按需）
- knowledge: RAG 知识库（按需）
- servers: 舰队管理（按需）
- ui: UI 渲染（按需）
- playbook: 运维剧本（按需）
"""

# 核心工具 — 始终加载（约 10 个，覆盖 80% 的日常对话）
CORE_TOOLS = [
    # 框架内置: execute, read_file, write_file, edit_file, ls, glob, grep
    # 下面是自定义高频工具
    "get_system_overview",
    "get_disk_info",
    "list_docker_containers",
    "get_container_logs",
    "list_systemd_services",
    "get_service_logs",
    "get_user_resources",
    "send_notification",
    "get_page_data",
]

# 按需加载的工具组
DEFERRED_GROUPS = {
    "system": {
        "description": "系统资源分析与趋势监控工具",
        "tools": ["analyze_resource_trend", "check_compliance", "auto_fix_compliance"],
    },
    "docker": {
        "description": "Docker 容器高级管理（操作、exec、网络、清理）",
        "tools": [
            "docker_container_action",
            "docker_compose_action",
            "docker_container_exec",
            "docker_prune",
            "list_docker_networks",
        ],
    },
    "services": {
        "description": "Systemd 服务控制（启停、enable/disable、依赖分析）",
        "tools": ["service_control", "service_enable_disable_tool", "get_service_dependencies_tool"],
    },
    "users": {
        "description": "用户管理（增删改、配额、进程管理、登录历史）",
        "tools": [
            "manage_linux_user",
            "update_user_quotas",
            "get_user_quotas",
            "kill_user_processes",
            "kill_single_process_tool",
            "get_user_login_history_tool",
            "get_active_sessions_tool",
            "get_user_full_processes",
            "check_quota_violations",
        ],
    },
    "cron": {
        "description": "定时任务管理（CRUD、启禁、表达式验证）",
        "tools": [
            "list_cron_jobs",
            "create_cron_job",
            "modify_cron_schedule",
            "toggle_cron_job_tool",
            "delete_cron_job_tool",
            "validate_cron_expr",
        ],
    },
    "security": {
        "description": "安全合规检查与自动修复",
        "tools": ["check_compliance", "auto_fix_compliance"],
    },
    "knowledge": {
        "description": "RAG 知识库（检索运维知识、故障案例）",
        "tools": ["retrieve_knowledge", "reindex_knowledge_base", "search_fault_cases", "save_fault_case"],
    },
    "assets": {
        "description": "资产清单与拓扑关系",
        "tools": ["get_asset_inventory", "get_asset_topology"],
    },
    "servers": {
        "description": "多服务器舰队管理",
        "tools": ["server_list", "server_test_connectivity"],
    },
    "ui": {
        "description": "前端 UI 组件渲染（图表、表格、表单、卡片）",
        "tools": ["render_chart", "render_table", "render_form", "render_card"],
    },
    "playbook": {
        "description": "运维剧本与远程执行",
        "tools": ["ssh_execute_command", "playbook_create", "playbook_execute", "playbook_list", "playbook_search"],
    },
    "scripts": {
        "description": "预定义运维脚本执行",
        "tools": ["execute_ops_script"],
    },
}
```

**Step 2: 新建 `modules/agents/tools/tool_search.py`（延迟搜索工具）**

```python
"""
tool_search — 按需搜索和加载延迟工具

当 agent 需要使用未加载的工具时，调用此工具搜索匹配的工具。
搜索后工具会被动态注入到当前会话中（或直接返回工具描述让 agent 了解能力）。

使用场景：
  agent: "我需要管理 cron 任务" 
  → 调用 tool_search("cron")
  → 返回 cron 组的 6 个工具描述
  → agent 知道可以调用哪些工具，在下一步使用
"""
from langchain_core.tools import tool

# 全局延迟工具注册表
_registry: dict[str, dict] = {}

def register_deferred(group_name: str, tools: list, description: str):
    """注册一组延迟工具"""
    _registry[group_name] = {
        "description": description,
        "tools": {t.name: t for t in tools},
        "keywords": _extract_keywords(group_name, description),
    }

def _extract_keywords(group_name: str, description: str) -> set[str]:
    """从组名和描述中提取搜索关键词"""
    keywords = {group_name}
    # 补充同义词
    synonyms = {
        "docker": {"容器", "container", "docker", "compose", "镜像", "image"},
        "services": {"服务", "service", "systemd", "进程", "process"},
        "users": {"用户", "user", "账号", "account", "权限", "permission"},
        "cron": {"定时", "cron", "计划", "schedule", "任务"},
        "security": {"安全", "security", "合规", "compliance"},
        "knowledge": {"知识", "knowledge", "RAG", "文档", "document"},
        "servers": {"服务器", "server", "远程", "remote", "舰队", "fleet"},
        "playbook": {"剧本", "playbook", "运维", "自动化", "SSH"},
    }
    return keywords | synonyms.get(group_name, set())

@tool
async def tool_search(query: str) -> str:
    """搜索可用的运维工具。
    
    当你需要使用当前未列出的工具时，用此工具搜索。
    输入关键词或功能描述，返回匹配的工具列表及其使用说明。
    
    Args:
        query: 搜索关键词，如 "docker"、"用户管理"、"定时任务"、"cron"
    """
    results = []
    query_lower = query.lower()
    
    for group_name, group_data in _registry.items():
        # 匹配：组名、描述、关键词
        if (query_lower in group_name or 
            query_lower in group_data["description"].lower() or
            any(query_lower in kw for kw in group_data["keywords"])):
            
            tool_descriptions = []
            for tool_name, tool_obj in group_data["tools"].items():
                desc = tool_obj.description.split("\n")[0] if tool_obj.description else ""
                tool_descriptions.append(f"  - {tool_name}: {desc}")
            
            results.append(
                f"【{group_name}】{group_data['description']}\n"
                + "\n".join(tool_descriptions)
            )
    
    if not results:
        return f"未找到与 '{query}' 相关的工具。可用工具组: {', '.join(_registry.keys())}"
    
    return "\n\n".join(results)
```

**Step 3: 改造 `modules/agents/tools/__init__.py`**

```python
def get_server_tools(user_role: str = "admin", deferred: bool = False) -> list:
    """返回服务器管理工具列表
    
    Args:
        user_role: "admin" 返回全部工具，"user" 只返回只读安全工具
        deferred: True 时只返回核心工具 + tool_search，延迟工具通过 tool_search 按需加载
    """
    # ... 构建完整的 all_tools 列表（同现有逻辑）
    
    if user_role != "admin":
        # 普通用户：只返回 SAFE 级别工具（不变）
        return [t for t in all_tools if ...]
    
    if not deferred:
        # 向后兼容：返回全部工具
        return all_tools
    
    # === 延迟加载模式 ===
    from modules.agents.tools.tool_groups import CORE_TOOLS, DEFERRED_GROUPS
    from modules.agents.tools.tool_search import register_deferred, tool_search
    
    # 核心工具
    core = [t for t in all_tools if t.name in CORE_TOOLS]
    
    # 注册延迟工具
    for group_name, group_config in DEFERRED_GROUPS.items():
        group_tools = [t for t in all_tools if t.name in group_config["tools"]]
        if group_tools:
            register_deferred(group_name, group_tools, group_config["description"])
    
    return core + [tool_search]
```

**Step 4: 改造 `deep_agent.py` 的 `build_agent()`**

```python
# 在 build_agent 中根据配置决定是否启用延迟加载
agent = create_deep_agent(
    ...
    tools=get_server_tools(user_role, deferred=True),  # 启用延迟加载
    ...
)
```

**涉及文件**：
- `modules/agents/tools/tool_groups.py` — 新建
- `modules/agents/tools/tool_search.py` — 新建
- `modules/agents/tools/__init__.py` — 改造 get_server_tools
- `modules/agents/deep_agent.py` — 启用 deferred=True

**预期收益**：
- System prompt 中工具描述从 ~4500 tokens 降至 ~1200 tokens
- 模型选工具的准确率提升（选择空间从 45+ 降至 ~15）
- 搜索操作只消耗一次额外 LLM 调用

---

## BE-5: 结构化记忆系统

### 当前问题
- `data/agent-memory.md` 是纯文本，agent 通过 `edit_file()` 手动更新
- 没有结构化的事实提取（用户偏好、系统配置、历史故障）
- 跨会话记忆质量完全依赖 agent 的写入能力
- 记忆文件可能被 agent 误写或覆盖

### DeerFlow 方案
```json
{
  "user": {
    "workContext": {"summary": "...", "updatedAt": "..."},
    "personalContext": {"summary": "..."},
    "topOfMind": {"summary": "..."}
  },
  "facts": [
    {"id": "fact_abc", "content": "...", "category": "context",
     "confidence": 0.8, "source": "thread_id", "createdAt": "..."}
  ]
}
```
- 异步队列 + 去抖更新
- LLM 自动从对话中提取 facts
- 置信度过滤 + 事实去重

### ServerHub 实施方案

**核心思路**：利用现有 `AsyncSqliteStore` 做 KV 存储，不用新增数据库文件。

**Step 1: 新建 `modules/agents/memory/__init__.py`**

```python
from modules.agents.memory.structured_store import StructuredMemoryStore
from modules.agents.memory.memory_updater import MemoryUpdater
```

**Step 2: 新建 `modules/agents/memory/structured_store.py`**

```python
"""
StructuredMemoryStore — 基于 AsyncSqliteStore 的结构化记忆

存储结构（namespace: ("memory", "facts")）：
  key: fact_id → value: {"content": "...", "category": "...", "confidence": 0.8, "source": "conv_id", "created_at": "..."}

分类（namespace: ("memory", "categories")）：
  key: category_name → value: {"summary": "...", "fact_count": N, "updated_at": "..."}

分类定义：
  - server_config: 服务器配置偏好（如「Docker 容器默认不自动重启」）
  - user_preference: 管理员操作偏好（如「wangtao 只允许工作日 8-22 点登录」）
  - known_issue: 已知问题记录（如「Dify worker 频繁重启，原因是 OOM」）
  - routine: 日常运维惯例（如「每周日 3:00 自动更新 LobeChat」）
  - environment: 环境信息（如「Clash 代理端口 7890，配置文件 ~/config.yaml」）
"""

import json
import time
from langgraph.store.sqlite import AsyncSqliteStore

FACTS_NAMESPACE = ("memory", "facts")

class StructuredMemoryStore:
    def __init__(self, store: AsyncSqliteStore):
        self._store = store
    
    async def add_fact(self, content: str, category: str, source: str, confidence: float = 0.7) -> str:
        """添加一条事实，自动去重"""
        import uuid
        fact_id = f"fact_{uuid.uuid4().hex[:8]}"
        
        # 去重：检查相似内容
        existing = await self._store.asearch(FACTS_NAMESPACE, query=content)
        for item in existing:
            if item.value.get("content") == content:
                return item.key  # 已存在
        
        await self._store.aput(
            FACTS_NAMESPACE,
            fact_id,
            {
                "content": content,
                "category": category,
                "confidence": confidence,
                "source": source,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        return fact_id
    
    async def search_facts(self, query: str, limit: int = 5) -> list[dict]:
        """语义搜索相关事实"""
        results = await self._store.asearch(FACTS_NAMESPACE, query=query, limit=limit)
        return [{"id": r.key, **r.value} for r in results]
    
    async def get_all_facts(self, category: str | None = None) -> list[dict]:
        """获取所有事实（可按类别过滤）"""
        items = await self._store.alist(FACTS_NAMESPACE)
        facts = [{"id": i.key, **i.value} for i in items]
        if category:
            facts = [f for f in facts if f.get("category") == category]
        return facts
    
    async def delete_fact(self, fact_id: str) -> bool:
        """删除一条事实"""
        await self._store.adelete(FACTS_NAMESPACE, fact_id)
        return True
    
    async def to_prompt_text(self, max_facts: int = 20) -> str:
        """将记忆格式化为可注入系统提示词的文本"""
        facts = await self.get_all_facts()
        if not facts:
            return ""
        
        # 按类别分组
        grouped: dict[str, list] = {}
        for f in facts[:max_facts]:
            cat = f.get("category", "other")
            grouped.setdefault(cat, []).append(f["content"])
        
        lines = ["## 长期记忆（已知事实）"]
        for cat, items in grouped.items():
            lines.append(f"\n### {cat}")
            for item in items:
                lines.append(f"- {item}")
        
        return "\n".join(lines)
```

**Step 3: 新建 `modules/agents/memory/memory_updater.py`**

```python
"""
MemoryUpdater — 对话结束后从消息中提取事实

两种模式：
1. 自动模式（推荐）：对话结束时，用轻量 LLM 从对话中提取关键事实
2. 工具模式：agent 主动调用 save_memory_fact 工具保存

自动模式的 prompt（极简，减少 token）：
"""

EXTRACT_FACTS_PROMPT = """从以下运维对话中提取关键事实。只提取有长期价值的信息，忽略临时性内容。

事实类别：
- server_config: 服务器配置/架构决策
- user_preference: 管理员操作偏好/策略
- known_issue: 已知问题及其原因/解决方案
- routine: 常规运维惯例/定时任务
- environment: 环境信息/端口/路径

格式（每行一条）：
[类别] 事实内容 | 置信度(0-1)

对话摘要:
{conversation_summary}

提取的事实:"""

class MemoryUpdater:
    def __init__(self, store: StructuredMemoryStore):
        self._store = store
        self._queue: asyncio.Queue | None = None  # 异步队列
    
    async def queue_extraction(self, conversation_id: str, messages_summary: str):
        """将事实提取任务加入异步队列（不阻塞对话流）"""
        if self._queue is None:
            self._queue = asyncio.Queue()
            asyncio.create_task(self._process_queue())
        await self._queue.put((conversation_id, messages_summary))
    
    async def _process_queue(self):
        """后台处理队列中的事实提取任务"""
        while True:
            conv_id, summary = await self._queue.get()
            try:
                await self._extract_and_save(conv_id, summary)
            except Exception as e:
                logger.warning("事实提取失败 (conv=%s): %s", conv_id, e)
    
    async def _extract_and_save(self, conversation_id: str, messages_summary: str):
        """用 LLM 提取事实并保存"""
        from modules.agents.llm import get_chat_model
        model = get_chat_model("patrol")
        
        prompt = EXTRACT_FACTS_PROMPT.format(conversation_summary=messages_summary[:2000])
        result = await model.ainvoke(prompt)
        
        # 解析结果
        for line in str(result.content).strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                # 格式: [category] content | confidence
                if line.startswith("["):
                    bracket_end = line.index("]")
                    category = line[1:bracket_end].strip()
                    rest = line[bracket_end + 1:].strip()
                    if "|" in rest:
                        content, conf_str = rest.rsplit("|", 1)
                        confidence = float(conf_str.strip())
                    else:
                        content = rest
                        confidence = 0.7
                    
                    if confidence >= 0.5:  # 只保存置信度 >= 0.5 的事实
                        await self._store.add_fact(
                            content=content.strip(),
                            category=category,
                            source=conversation_id,
                            confidence=confidence,
                        )
            except (ValueError, IndexError):
                continue
```

**Step 4: 新增 agent 工具 `save_memory_fact`**

在 `modules/agents/tools/` 中新增，让 agent 也能主动保存重要事实：

```python
@tool
async def save_memory_fact(content: str, category: str = "environment") -> str:
    """保存一条运维知识到长期记忆。用于记录重要的配置、已知问题、运维惯例等。
    
    Args:
        content: 事实内容，如 "Dify worker 因 OOM 频繁重启，解决方案是增加 memory limit 到 4G"
        category: 事实类别: server_config | user_preference | known_issue | routine | environment
    """
    store = await get_structured_memory_store()
    fact_id = await store.add_fact(content, category, source="agent_manual", confidence=0.9)
    return f"已保存到长期记忆: {content[:50]}... (id: {fact_id})"
```

**Step 5: 集成到 `deep_agent.py`**

```python
# 记忆注入：在构建 system_prompt 时加入结构化记忆
memory_store = StructuredMemoryStore(store)
memory_text = await memory_store.to_prompt_text()
if memory_text:
    system_prompt += "\n\n" + memory_text
```

**Step 6: 在 `routes/chat.py` SSE 流结束时触发提取**

```python
# 在 run.completed 事件之前
if memory_updater:
    # 异步提取，不阻塞响应
    summary = _summarize_conversation(all_messages)
    await memory_updater.queue_extraction(conversation_id, summary)
```

**涉及文件**：
- `modules/agents/memory/__init__.py` — 新建
- `modules/agents/memory/structured_store.py` — 新建
- `modules/agents/memory/memory_updater.py` — 新建
- `modules/agents/tools/` — 新增 save_memory_fact 工具
- `modules/agents/deep_agent.py` — 记忆注入到 system_prompt
- `modules/agents/routes/chat.py` — 流结束时触发提取
- `frontend/src/pages/agents/AdminPanel.tsx` — 新增记忆管理标签（可选）

---

# 第三部分：实施路线图

## 全局实施顺序（前后端交叉）

```
Phase 0（后端基础，1 天）：
  BE-2: DanglingToolCall 修补     → 最简单的防护，立竿见影
  BE-1: LoopDetection 中间件     → 与 BE-2 同属 middleware 目录，一起建
  BE-3: AutoTitle 标题生成       → 前后端都需改动，但不依赖其他特性

Phase 1（前端基础，1-2 天）：
  FE-6: 消息类型守卫函数          → 其他前端功能的基础设施
  FE-1: 流式 Markdown 逐字渲染   → 用户感知最强的改进

Phase 2（体验核心，2-3 天）：
  FE-2: 消息分组 + 折叠          → 需要 FE-6 的守卫函数
  FE-5: Tool Call 卡片化         → 分组的子组件
  FE-3: Follow-up Suggestions    → 需要后端配合新增 SSE 事件

Phase 3（架构优化，2-3 天）：
  BE-4: DeferredToolRegistry     → 独立后端改动，不依赖前端
  BE-5: 结构化记忆系统           → 最复杂的后端改动
  FE-4: Compound 输入框          → 需要先完成其他前端组件再重构
```

## 依赖关系图

```
BE-2 (DanglingToolCall) ──┐
BE-1 (LoopDetection)    ──┤ Phase 0: 后端防护
BE-3 (AutoTitle)        ──┘
                           │
FE-6 (类型守卫) ───────────┤ Phase 1: 前端基础
FE-1 (流式渲染) ───────────┘
        │
        ├── FE-2 (消息分组) ──── FE-5 (ToolCall 卡片)
        │
        └── FE-3 (Suggestions) ── 需要 BE-3 (AutoTitle) 的 SSE 模式

BE-4 (DeferredTools) ──────── 独立
BE-5 (结构化记忆)   ──────── 独立
FE-4 (Compound输入) ──────── 依赖 FE-2/5 完成
```

## 新增依赖

### npm（前端）
```
无需新增（所有功能基于现有 marked.js + Lucide + Tailwind）
如选择流式 Markdown 方案 B，需安装：streamdown
```

### pip（后端）
```
无需新增（所有功能基于现有 LangChain + aiosqlite）
```

## 风险与注意事项

### 后端风险

1. **中间件注册顺序**：LoopDetection 和 DanglingToolCall 的执行顺序很重要——先修补 dangling，再检测循环，否则修补操作会被误判为循环
2. **AutoTitle 性能**：每次对话多一次 LLM 调用生成标题，用 patrol 模型（便宜）且限制输入 200 字符，成本可忽略
3. **DeferredTools 兼容性**：`tool_search` 是异步工具，agent 需要两步（搜索 → 调用），可能增加一轮 LLM 调用。但整体 token 节省（-3000 tokens system prompt）远大于这额外一轮
4. **结构化记忆准确性**：LLM 提取的事实可能有误，设 `confidence >= 0.5` 阈值 + agent 可手动删除事实
5. **SQLite Store 并发**：`AsyncSqliteStore` 的 `asearch` 是语义搜索（非向量），对大量事实的搜索质量有限。如果事实超过 100 条，考虑迁移到向量数据库

### 前端风险

6. **SSE 事件兼容性**：FE-1 和 FE-3 都需要改 `useSSEChat.ts` 的事件处理，改动要在同一个分支上避免冲突
7. **chatStore 状态膨胀**：新增 suggestions、streamingMessageId 等状态，注意不影响现有消息去重逻辑（`_msgSeq`, `_seenIds`）
8. **CSS 动画性能**：折叠/展开用 `max-height` transition 而非 JS 操作 DOM，避免触发布局抖动
9. **Markdown 闪烁**：streaming 期间频繁调用 `marked.parse()` 可能导致内容跳动，考虑 debounce 或 requestAnimationFrame 节流
10. **向后兼容**：ToolCallBox 暂保留，新组件 ToolCallCard 并行存在，通过 feature flag 或属性切换
