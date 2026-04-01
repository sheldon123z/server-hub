import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import DOMPurify from 'dompurify'
import { cn } from '@/lib/utils'
import { renderMarkdown } from '@/lib/markdown'
import client from '@/api/client'

/* ── Types ────────────────────────────────────────── */

/**
 * 聊天消息结构
 */
interface ChatMessage {
  id: string
  /** 消息角色：用户、助手、工具调用、工具结果、审批请求 */
  role: 'user' | 'assistant' | 'tool' | 'tool_result' | 'approval'
  /** 消息文本内容 */
  content: string
  /** 工具名称（仅 role=tool 时有值） */
  toolName?: string
  /** SSE 去重用的服务端消息 ID */
  _serverId?: string
  /** 审批请求 ID（仅 role=approval 时有值） */
  approvalId?: string
  /** 审批是否已处理（批准或拒绝） */
  approvalResolved?: boolean
}

interface ContentBlock {
  type: string
  text?: string
}

interface PanelPosition {
  x: number
  y: number
}

/* ── Helpers ──────────────────────────────────────── */

const STORAGE_KEY_POS = 'chatwidget-position'
const STORAGE_KEY_CONV = 'chatwidget-conversation-id'

function generateId(): string {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function loadPosition(): PanelPosition | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY_POS)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function savePosition(pos: PanelPosition) {
  try {
    sessionStorage.setItem(STORAGE_KEY_POS, JSON.stringify(pos))
  } catch {
    /* noop */
  }
}

function loadConversationId(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY_CONV)
  } catch {
    return null
  }
}

function saveConversationId(id: string) {
  try {
    sessionStorage.setItem(STORAGE_KEY_CONV, id)
  } catch {
    /* noop */
  }
}

/**
 * 从 URL 路径提取当前页面上下文标识，作为 page_context 传给 Agent 后端
 * 例如 "/docker/containers" → "docker"
 */
function pageContextFromPath(pathname: string): string {
  const seg = pathname.replace(/^\//, '').split('/')[0]
  return seg || 'dashboard'
}

/* ── SSE Parser ───────────────────────────────────── */

/**
 * SSE 流式聊天请求
 * 向 /api/agents/chat 发起 POST 请求，逐行解析 SSE 事件并回调
 *
 * @param body - 请求体，包含消息文本、会话 ID、安全模式和页面上下文
 * @param onEvent - SSE 事件回调，参数为事件类型和解析后的 data（JSON 对象或原始字符串）
 * @param signal - AbortSignal，用于中断请求
 */
async function streamChat(
  body: { message: string; conversation_id: string; safety_mode: string; page_context: string },
  onEvent: (type: string, data: unknown) => void,
  signal: AbortSignal,
) {
  const res = await fetch('/api/agents/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
    signal,
  })

  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    let eventType = 'message'
    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        const raw = line.slice(5).trim()
        if (!raw) continue
        try {
          onEvent(eventType, JSON.parse(raw))
        } catch {
          onEvent(eventType, raw)
        }
      } else if (line.trim() === '') {
        // Empty line marks end of an SSE event — reset eventType
        eventType = 'message'
      }
    }
  }
}

/* ── Component ────────────────────────────────────── */

/**
 * 浮动聊天组件入口
 * 在 /agents 页面隐藏（该页面有独立的聊天 UI），其余页面显示右下角浮动气泡
 */
export default function ChatWidget() {
  const location = useLocation()

  // Hide on /agents page
  if (location.pathname === '/agents') return null

  return <ChatWidgetInner />
}

function ChatWidgetInner() {
  const location = useLocation()
  const [isOpen, setIsOpen] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputText, setInputText] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [conversationId, setConversationId] = useState<string>(
    () => loadConversationId() || generateId(),
  )

  // Dragging state
  const [position, setPosition] = useState<PanelPosition>(
    () => loadPosition() || { x: -1, y: -1 },
  )
  const isDragging = useRef(false)
  const dragOffset = useRef({ x: 0, y: 0 })

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const seenServerIds = useRef(new Set<string>())

  // Persist conversation id
  useEffect(() => {
    saveConversationId(conversationId)
  }, [conversationId])

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  // Cleanup abort on unmount
  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  /* ── New conversation ────────────────────────────── */

  const startNewConversation = useCallback(() => {
    abortRef.current?.abort()
    const newId = generateId()
    setConversationId(newId)
    setMessages([])
    setInputText('')
    setIsTyping(false)
    seenServerIds.current.clear()
  }, [])

  /* ── Approval handling ───────────────────────────── */

  const handleApproval = useCallback(async (approvalId: string, action: 'approve' | 'reject') => {
    try {
      await client.post(`/api/agents/approvals/${approvalId}`, { action, reason: '' })
      setMessages((prev) =>
        prev.map((m) =>
          m.approvalId === approvalId
            ? { ...m, approvalResolved: true, content: `${m.content}\n[${action === 'approve' ? '已批准' : '已拒绝'}]` }
            : m,
        ),
      )
    } catch {
      // Show error inline
      setMessages((prev) =>
        prev.map((m) =>
          m.approvalId === approvalId
            ? { ...m, content: `${m.content}\n[操作失败，请重试]` }
            : m,
        ),
      )
    }
  }, [])

  /* ── Drag handlers ─────────────────────────────── */

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    // Only allow dragging from the header area
    const target = e.target as HTMLElement
    if (target.closest('button') || target.closest('textarea')) return

    isDragging.current = true
    const panelEl = (e.currentTarget as HTMLElement).closest('[data-chat-panel]') as HTMLElement
    if (!panelEl) return

    const rect = panelEl.getBoundingClientRect()
    dragOffset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }

    const handleMouseMove = (ev: MouseEvent) => {
      if (!isDragging.current) return
      const newX = Math.max(0, Math.min(window.innerWidth - 320, ev.clientX - dragOffset.current.x))
      const newY = Math.max(0, Math.min(window.innerHeight - 480, ev.clientY - dragOffset.current.y))
      setPosition({ x: newX, y: newY })
    }

    const handleMouseUp = () => {
      if (isDragging.current) {
        isDragging.current = false
        setPosition((prev) => {
          savePosition(prev)
          return prev
        })
      }
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [])

  /* ── Send message ──────────────────────────────── */

  const sendMessage = useCallback(async () => {
    const text = inputText.trim()
    if (!text || isTyping) return

    const userMsg: ChatMessage = { id: generateId(), role: 'user', content: text }
    setMessages((prev) => [...prev, userMsg])
    setInputText('')
    setIsTyping(true)

    const abortCtrl = new AbortController()
    abortRef.current = abortCtrl

    let assistantId = generateId()
    let assistantContent = ''

    try {
      await streamChat(
        {
          message: text,
          conversation_id: conversationId,
          safety_mode: 'supervised',
          page_context: pageContextFromPath(location.pathname),
        },
        (type, data: unknown) => {
          const obj = data as Record<string, unknown>

          // Deduplication
          if (obj && typeof obj === 'object' && obj._serverId) {
            const sid = String(obj._serverId)
            if (seenServerIds.current.has(sid)) return
            seenServerIds.current.add(sid)
          }

          if (type === 'run.started') {
            return
          }

          if (type === 'message' || type === 'message.final') {
            const rawContent = obj?.content ?? obj?.text ?? ''
            const content = typeof rawContent === 'string' ? rawContent
              : Array.isArray(rawContent) ? rawContent.map((b: ContentBlock | string) => typeof b === 'string' ? b : b?.text ?? '').join('')
              : String(rawContent)
            if (!content) return
            assistantContent += content
            setMessages((prev) => {
              const existing = prev.find((m) => m.id === assistantId)
              if (existing) {
                return prev.map((m) =>
                  m.id === assistantId ? { ...m, content: assistantContent } : m,
                )
              }
              return [...prev, { id: assistantId, role: 'assistant', content: assistantContent }]
            })
          } else if (type === 'tool_call' || type === 'tool.call') {
            const toolName = String(obj?.name ?? obj?.tool ?? 'tool')
            setMessages((prev) => [
              ...prev,
              { id: generateId(), role: 'tool', content: '', toolName },
            ])
          } else if (type === 'tool_result' || type === 'tool.result') {
            const resultContent = typeof data === 'string' ? data : String(obj?.content ?? obj?.result ?? '')
            if (resultContent) {
              setMessages((prev) => [
                ...prev,
                { id: generateId(), role: 'tool_result', content: resultContent },
              ])
            }
          } else if (type === 'approval_request' || type === 'approval.request') {
            const description = String(obj?.description ?? obj?.message ?? '需要您的审批')
            const approvalId = String(obj?.approval_id ?? obj?.id ?? '')
            setMessages((prev) => [
              ...prev,
              { id: generateId(), role: 'approval', content: description, approvalId },
            ])
          } else if (type === 'todo.update') {
            return
          } else if (type === 'run.completed') {
            return
          } else if (type === 'done') {
            // Stream complete
          } else if (type === 'error' || type === 'run.error') {
            const errMsg = typeof data === 'string' ? data : String(obj?.message ?? '请求出错')
            setMessages((prev) => [
              ...prev,
              { id: generateId(), role: 'assistant', content: errMsg },
            ])
          }
        },
        abortCtrl.signal,
      )
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        setMessages((prev) => [
          ...prev,
          { id: generateId(), role: 'assistant', content: '连接失败，请稍后重试' },
        ])
      }
    } finally {
      setIsTyping(false)
      abortRef.current = null
      // Reset for next assistant message
      assistantId = generateId()
      assistantContent = ''
    }
  }, [inputText, isTyping, conversationId, location.pathname])

  /* ── Panel positioning ─────────────────────────── */

  const panelStyle: React.CSSProperties =
    position.x >= 0 && position.y >= 0
      ? { position: 'fixed', left: position.x, top: position.y, zIndex: 50 }
      : { position: 'fixed', right: 20, bottom: 80, zIndex: 50 }

  /* ── Render ─────────────────────────────────────── */

  return (
    <>
      {/* Floating button */}
      {!isOpen && !isMinimized && (
        <button
          className="fixed bottom-5 right-5 z-50 w-12 h-12 rounded-full bg-accent text-[#0f172a] shadow-lg hover:opacity-90 transition-opacity flex items-center justify-center"
          onClick={() => setIsOpen(true)}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
        </button>
      )}

      {/* Minimized bar */}
      {isMinimized && !isOpen && (
        <div
          data-chat-panel
          className="w-80 bg-card border border-border rounded-xl shadow-2xl overflow-hidden"
          style={panelStyle}
        >
          <div
            className="flex items-center justify-between px-4 py-3 bg-bg2 cursor-move select-none"
            onMouseDown={handleMouseDown}
          >
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent" />
              <span className="text-sm font-medium text-text">OpsAgent</span>
              {messages.length > 0 && (
                <span className="text-xs text-text3">({messages.length})</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                className="p-1 rounded hover:bg-card text-text3 hover:text-text transition-colors"
                title="展开"
                onClick={() => {
                  setIsMinimized(false)
                  setIsOpen(true)
                }}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
                </svg>
              </button>
              <button
                className="p-1 rounded hover:bg-card text-text3 hover:text-text transition-colors"
                title="关闭"
                onClick={() => {
                  setIsMinimized(false)
                  abortRef.current?.abort()
                }}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Chat panel */}
      {isOpen && (
        <div
          data-chat-panel
          className="w-80 h-[480px] bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden"
          style={panelStyle}
        >
          {/* Header (draggable) */}
          <div
            className="flex items-center justify-between px-4 py-3 border-b border-border bg-bg2 cursor-move select-none shrink-0"
            onMouseDown={handleMouseDown}
          >
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent" />
              <span className="text-sm font-medium text-text">OpsAgent</span>
            </div>
            <div className="flex items-center gap-1">
              {/* New conversation */}
              <button
                className="p-1 rounded hover:bg-card text-text3 hover:text-text transition-colors"
                title="新对话"
                onClick={startNewConversation}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                </svg>
              </button>
              {/* Minimize */}
              <button
                className="p-1 rounded hover:bg-card text-text3 hover:text-text transition-colors"
                title="最小化"
                onClick={() => {
                  setIsOpen(false)
                  setIsMinimized(true)
                }}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {/* Close (fully hide) */}
              <button
                className="p-1 rounded hover:bg-card text-text3 hover:text-text transition-colors"
                title="关闭"
                onClick={() => {
                  setIsOpen(false)
                  setIsMinimized(false)
                  abortRef.current?.abort()
                }}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {messages.length === 0 && (
              <div className="text-center text-text3 text-xs pt-8">
                向 OpsAgent 发送消息开始对话
              </div>
            )}
            {messages.map((msg) => {
              if (msg.role === 'tool') {
                return (
                  <div key={msg.id} className="flex justify-start">
                    <div className="bg-bg border border-border rounded-md px-2.5 py-1.5 text-xs text-text3 flex items-center gap-1.5">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                      {msg.toolName}
                    </div>
                  </div>
                )
              }

              if (msg.role === 'tool_result') {
                return (
                  <div key={msg.id} className="flex justify-start">
                    <div className="max-w-[85%] bg-bg border border-border rounded-md px-2.5 py-1.5 text-xs text-text3 font-mono whitespace-pre-wrap break-all max-h-24 overflow-y-auto">
                      {msg.content}
                    </div>
                  </div>
                )
              }

              if (msg.role === 'approval') {
                return (
                  <div key={msg.id} className="flex justify-start">
                    <div className="max-w-[85%] rounded-lg px-3 py-2 border border-yellow/30 bg-yellow/10">
                      <div className="text-sm text-yellow font-medium mb-1">需要审批</div>
                      <div className="text-sm text-text2 mb-2">{msg.content}</div>
                      {!msg.approvalResolved && msg.approvalId && (
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleApproval(msg.approvalId!, 'approve')}
                            className="px-3 py-1 rounded text-xs font-medium bg-green/20 text-green hover:bg-green/30 transition-colors"
                          >
                            批准
                          </button>
                          <button
                            onClick={() => handleApproval(msg.approvalId!, 'reject')}
                            className="px-3 py-1 rounded text-xs font-medium bg-red/20 text-red hover:bg-red/30 transition-colors"
                          >
                            拒绝
                          </button>
                        </div>
                      )}
                      {msg.approvalResolved && (
                        <div className="text-xs text-text3 italic">
                          {msg.content.includes('已批准') ? '已批准' : '已拒绝'}
                        </div>
                      )}
                    </div>
                  </div>
                )
              }

              const isUser = msg.role === 'user'
              return (
                <div key={msg.id} className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
                  <div
                    className={cn(
                      'max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed',
                      isUser
                        ? 'bg-accent text-[#0f172a]'
                        : 'bg-bg2 text-text chat-markdown',
                    )}
                    dangerouslySetInnerHTML={
                      isUser ? undefined : { __html: renderMarkdown(msg.content) }
                    }
                  >
                    {isUser ? msg.content : undefined}
                  </div>
                </div>
              )
            })}

            {isTyping && (
              <div className="flex justify-start">
                <div className="bg-bg2 text-text3 rounded-lg px-3 py-2 text-sm">
                  <span className="inline-flex gap-1">
                    <span className="w-1.5 h-1.5 bg-text3 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 bg-text3 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 bg-text3 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border p-3 shrink-0">
            <div className="flex items-end gap-2">
              <textarea
                className="flex-1 bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text placeholder:text-text3 resize-none focus:border-accent focus:outline-none"
                rows={1}
                placeholder="输入消息..."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    sendMessage()
                  }
                }}
              />
              <button
                className="bg-accent text-[#0f172a] p-2 rounded-lg hover:opacity-90 disabled:opacity-50 shrink-0"
                disabled={!inputText.trim() || isTyping}
                onClick={sendMessage}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
