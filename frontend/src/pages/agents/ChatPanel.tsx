import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Send, ShieldAlert, Square, Sparkles } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import client from '@/api/client'
import { useChatStore } from '@/stores/chatStore'
import { useSSEChat } from '@/hooks/useSSEChat'
import type { ChatMessage, SkillRecommendation } from '@/types/agent'
import { MessageBubble } from './MessageBubble'
import { TodoPanel } from './TodoPanel'
import { SlashCommandMenu, type SlashCommandMenuHandle, generateHelpText } from './SlashCommandMenu'

function pageContextFromPath(pathname: string): string {
  const seg = pathname.replace(/^\//, '').split('/')[0]
  return seg || 'dashboard'
}

function ApprovalCard({
  msg,
  onResolve,
}: {
  msg: ChatMessage
  onResolve: (id: string, action: 'approve' | 'reject') => void
}) {
  const [loading, setLoading] = useState(false)

  async function handle(action: 'approve' | 'reject') {
    if (!msg.approval_id) return
    setLoading(true)
    await onResolve(msg.approval_id, action)
    setLoading(false)
  }

  return (
    <div className="flex justify-start px-3">
      <div className="max-w-[85%] rounded-lg border border-yellow/40 bg-yellow/10 px-3 py-2.5">
        <div className="mb-1.5 flex items-center gap-2 text-xs font-medium text-yellow">
          <ShieldAlert size={14} />
          <span>需要审批</span>
        </div>
        <div className="mb-2 text-sm text-text">{msg.description || '确认执行此操作？'}</div>
        {msg.actions && msg.actions.length > 0 && (
          <div className="mb-2 rounded bg-bg/50 px-2 py-1 font-mono text-xs text-text3">
            {msg.actions.map((a, i) => (
              <div key={i}>
                {a.name}({JSON.stringify(a.args)})
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <button
            onClick={() => handle('approve')}
            disabled={loading}
            className="rounded bg-green/20 px-3 py-1 text-xs text-green transition-colors hover:bg-green/30 disabled:opacity-50"
          >
            批准
          </button>
          <button
            onClick={() => handle('reject')}
            disabled={loading}
            className="rounded bg-red/20 px-3 py-1 text-xs text-red transition-colors hover:bg-red/30 disabled:opacity-50"
          >
            拒绝
          </button>
        </div>
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex justify-start px-3">
      <div className="flex items-center gap-1 rounded-lg border border-border bg-bg2 px-3 py-2">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text3 [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text3 [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text3 [animation-delay:300ms]" />
      </div>
    </div>
  )
}

export function ChatPanel() {
  const location = useLocation()
  const {
    messages,
    isStreaming,
    removeMessage,
    pushMsg,
    selectedSkillId,
    setSelectedSkillId,
  } = useChatStore()
  const { sendMessage, cancel } = useSSEChat()
  const [input, setInput] = useState(() => {
    return localStorage.getItem('serverhub-chat-draft') || ''
  })
  const [showSlashMenu, setShowSlashMenu] = useState(false)
  const [isNearBottom, setIsNearBottom] = useState(true)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const slashMenuRef = useRef<SlashCommandMenuHandle>(null)
  const pageContext = pageContextFromPath(location.pathname)

  const trimmedInput = input.trim()

  const { data: recommendations } = useQuery({
    queryKey: ['skill-recommendations', pageContext, trimmedInput],
    queryFn: async () => {
      if (!trimmedInput) return [] as SkillRecommendation[]
      const { data } = await client.get<{ items: SkillRecommendation[] }>('/api/agents/skills/recommendations', {
        params: { message: trimmedInput, page_context: pageContext },
      })
      return data.items
    },
    enabled: trimmedInput.length >= 2,
    staleTime: 15_000,
  })

  const selectedRecommendation = useMemo(
    () => recommendations?.find((item) => item.id === selectedSkillId) ?? null,
    [recommendations, selectedSkillId],
  )

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollHeight, scrollTop, clientHeight } = containerRef.current
    setIsNearBottom(scrollHeight - scrollTop - clientHeight < 100)
  }, [])

  useEffect(() => {
    if (isNearBottom) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isStreaming, isNearBottom])

  // 草稿自动保存（防抖 500ms）
  useEffect(() => {
    const timer = setTimeout(() => {
      if (input) localStorage.setItem('serverhub-chat-draft', input)
      else localStorage.removeItem('serverhub-chat-draft')
    }, 500)
    return () => clearTimeout(timer)
  }, [input])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '44px'
    el.style.height = Math.min(el.scrollHeight, 150) + 'px'
  }, [input])

  const handleSend = useCallback(
    (text?: string) => {
      const msg = (text ?? input).trim()
      if (!msg || isStreaming) return
      setInput('')
      setShowSlashMenu(false)
      localStorage.removeItem('serverhub-chat-draft')
      sendMessage(msg, { pageContext, skillId: selectedSkillId })
    },
    [input, isStreaming, pageContext, selectedSkillId, sendMessage],
  )

  const handleDelete = useCallback((id: string) => {
    useChatStore.getState().removeMessage(id)
  }, [])

  const handleResend = useCallback(
    (content: string, id: string) => {
      useChatStore.getState().removeMessagesFrom(id)
      sendMessage(content, { pageContext, skillId: selectedSkillId })
    },
    [pageContext, selectedSkillId, sendMessage],
  )

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    setInput(value)
    setShowSlashMenu(value.startsWith('/'))
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (showSlashMenu && slashMenuRef.current?.handleKeyDown(e)) return
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleSlashSelect(prompt: string) {
    if (!prompt) return
    setShowSlashMenu(false)
    if (prompt === '__HELP__') {
      pushMsg({ role: 'assistant', content: generateHelpText() })
      setInput('')
      return
    }
    setInput(prompt)
    if (!prompt.endsWith(': ') && !prompt.endsWith(' ')) {
      handleSend(prompt)
    } else {
      textareaRef.current?.focus()
    }
  }

  async function handleApproval(approvalId: string, action: 'approve' | 'reject') {
    try {
      const { data } = await client.post(`/api/agents/approvals/${approvalId}`, { action, reason: '' })
      const approvalMsg = messages.find((m) => m.approval_id === approvalId)
      if (approvalMsg) removeMessage(approvalMsg._id)
      pushMsg({
        role: 'assistant',
        content: data?.result || (action === 'approve' ? '操作已批准，正在执行...' : '操作已被拒绝'),
      })
    } catch {
      pushMsg({ role: 'assistant', content: '审批请求处理失败' })
    }
  }

  function renderMessage(msg: ChatMessage) {
    switch (msg.role) {
      case 'user':
      case 'assistant':
      case 'tool_call':
      case 'tool_result':
        return (
          <div key={msg._id} className="px-3">
            <MessageBubble
              message={msg}
              onDelete={handleDelete}
              onResend={msg.role === 'user' ? handleResend : undefined}
            />
          </div>
        )
      case 'approval':
        return <ApprovalCard key={msg._id} msg={msg} onResolve={handleApproval} />
      default:
        return null
    }
  }

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="relative flex-1 overflow-y-auto py-3" ref={containerRef} onScroll={handleScroll}>
        {messages.length === 0 && !isStreaming && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-text3">
              <div className="mb-2 text-3xl">&#129302;</div>
              <div className="text-sm">OpsAgent 运维助手</div>
              <div className="mt-1 text-xs">输入消息开始对话</div>
            </div>
          </div>
        )}
        <div className="flex flex-col gap-2.5">{messages.map(renderMessage)}</div>
        {isStreaming && <TypingIndicator />}
        <div ref={bottomRef} />
        {!isNearBottom && messages.length > 0 && (
          <button
            onClick={() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' })}
            className="sticky bottom-3 left-1/2 -translate-x-1/2 z-10 bg-accent text-[#0f172a] px-3 py-1 rounded-full text-sm shadow-lg hover:bg-accent/80 transition-colors"
          >
            ↓ 新消息
          </button>
        )}
      </div>

      <TodoPanel />

      <div className="border-t border-border px-3 py-2.5">
        {!!recommendations?.length && (
          <div className="mb-2 flex flex-wrap gap-2">
            {recommendations.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedSkillId(item.id)}
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-colors',
                  selectedSkillId === item.id
                    ? 'border-accent bg-accent-dim text-accent'
                    : 'border-border bg-bg2 text-text2 hover:border-accent/40 hover:text-text',
                )}
              >
                <Sparkles size={12} />
                {item.name}
              </button>
            ))}
            {selectedSkillId && (
              <button
                type="button"
                onClick={() => setSelectedSkillId(null)}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-text3 transition-colors hover:text-text"
              >
                清除技能
              </button>
            )}
          </div>
        )}
        {selectedRecommendation && (
          <div className="mb-2 rounded-lg border border-accent/30 bg-accent-dim/40 px-3 py-2 text-xs text-text2">
            <div className="mb-0.5 font-medium text-accent">{selectedRecommendation.name}</div>
            <div>{selectedRecommendation.summary}</div>
          </div>
        )}
        <div className="relative flex items-end gap-2">
          <SlashCommandMenu
            ref={slashMenuRef}
            inputText={input}
            onSelect={handleSlashSelect}
            visible={showSlashMenu}
            onClose={() => setShowSlashMenu(false)}
          />
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (Shift+Enter 换行)"
            rows={1}
            className={cn(
              'flex-1 resize-none rounded-lg border border-border bg-bg2 px-3 py-2.5 text-sm text-text',
              'placeholder:text-text3 focus:border-accent focus:outline-none',
            )}
            style={{ minHeight: '44px', maxHeight: '150px' }}
          />
          {isStreaming ? (
            <button
              onClick={() => void cancel()}
              className="shrink-0 rounded-lg bg-red/20 p-2.5 text-red transition-colors hover:bg-red/30"
              title="取消"
            >
              <Square size={18} />
            </button>
          ) : (
            <button
              onClick={() => handleSend()}
              disabled={!input.trim()}
              className={cn(
                'shrink-0 rounded-lg p-2.5 transition-colors',
                !input.trim() ? 'cursor-not-allowed bg-border text-text3' : 'bg-accent text-[#0f172a] hover:bg-accent/80',
              )}
              title="发送"
            >
              <Send size={18} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
