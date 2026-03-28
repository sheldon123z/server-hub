import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, ShieldAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useChatStore } from '@/stores/chatStore'
import { useSSEChat } from '@/hooks/useSSEChat'
import client from '@/api/client'
import type { ChatMessage } from '@/types/agent'
import { MessageBubble } from './MessageBubble'
import { TodoPanel } from './TodoPanel'
import { SlashCommandMenu, type SlashCommandMenuHandle, generateHelpText } from './SlashCommandMenu'

// --- ApprovalCard ---
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
    onResolve(msg.approval_id, action)
  }

  return (
    <div className="flex justify-start px-3">
      <div className="max-w-[85%] rounded-lg border border-yellow/40 bg-yellow/10 px-3 py-2.5">
        <div className="flex items-center gap-2 text-yellow text-xs font-medium mb-1.5">
          <ShieldAlert size={14} />
          <span>需要审批</span>
        </div>
        <div className="text-sm text-text mb-2">{msg.description || '确认执行此操作？'}</div>
        {msg.actions && msg.actions.length > 0 && (
          <div className="text-xs text-text3 mb-2 font-mono bg-bg/50 rounded px-2 py-1">
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
            className="px-3 py-1 text-xs rounded bg-green/20 text-green hover:bg-green/30 transition-colors disabled:opacity-50 cursor-pointer"
          >
            批准
          </button>
          <button
            onClick={() => handle('reject')}
            disabled={loading}
            className="px-3 py-1 text-xs rounded bg-red/20 text-red hover:bg-red/30 transition-colors disabled:opacity-50 cursor-pointer"
          >
            拒绝
          </button>
        </div>
      </div>
    </div>
  )
}

// --- TypingIndicator ---
function TypingIndicator() {
  return (
    <div className="flex justify-start px-3">
      <div className="flex items-center gap-1 bg-bg2 border border-border rounded-lg px-3 py-2">
        <span className="w-1.5 h-1.5 rounded-full bg-text3 animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-text3 animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-text3 animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  )
}

// --- Main ChatPanel ---
export function ChatPanel() {
  const { messages, isStreaming, removeMessage, pushMsg } = useChatStore()
  const { sendMessage } = useSSEChat()

  const [input, setInput] = useState('')
  const [showSlashMenu, setShowSlashMenu] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const slashMenuRef = useRef<SlashCommandMenuHandle>(null)

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isStreaming])

  // Auto-resize textarea
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
      sendMessage(msg)
    },
    [input, isStreaming, sendMessage],
  )

  const handleDelete = useCallback((id: string) => {
    useChatStore.getState().removeMessage(id)
  }, [])

  const handleResend = useCallback(
    (content: string, id: string) => {
      useChatStore.getState().removeMessagesFrom(id)
      sendMessage(content)
    },
    [sendMessage],
  )

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    setInput(value)
    if (value.startsWith('/')) {
      setShowSlashMenu(true)
    } else {
      setShowSlashMenu(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Let slash menu handle navigation keys first
    if (showSlashMenu && slashMenuRef.current?.handleKeyDown(e)) {
      return
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleSlashSelect(prompt: string) {
    if (!prompt) return
    setShowSlashMenu(false)

    // /help: inject formatted help as an assistant message locally
    if (prompt === '__HELP__') {
      pushMsg({ role: 'assistant', content: generateHelpText() })
      setInput('')
      return
    }

    setInput(prompt)
    // Auto-send if prompt is complete (no trailing space/colon suggesting user needs to add more)
    if (!prompt.endsWith(': ') && !prompt.endsWith(' ')) {
      handleSend(prompt)
    } else {
      // Focus textarea for user to complete the command
      textareaRef.current?.focus()
    }
  }

  async function handleApproval(approvalId: string, action: 'approve' | 'reject') {
    try {
      await client.post(`/api/agents/approvals/${approvalId}`, {
        action,
        reason: '',
      })
      // Remove the approval message
      const approvalMsg = messages.find((m) => m.approval_id === approvalId)
      if (approvalMsg) removeMessage(approvalMsg._id)

      // Add result message
      pushMsg({
        role: 'assistant',
        content: action === 'approve' ? '操作已批准，正在执行...' : '操作已被拒绝',
      })
    } catch {
      pushMsg({
        role: 'assistant',
        content: '审批请求处理失败',
      })
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
        return (
          <ApprovalCard
            key={msg._id}
            msg={msg}
            onResolve={handleApproval}
          />
        )

      default:
        return null
    }
  }

  return (
    <div className="flex flex-col h-full min-w-0">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-2.5 py-3">
        {messages.length === 0 && !isStreaming && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-text3">
              <div className="text-3xl mb-2">&#129302;</div>
              <div className="text-sm">OpsAgent 运维助手</div>
              <div className="text-xs mt-1">输入消息开始对话</div>
            </div>
          </div>
        )}

        {messages.map(renderMessage)}

        {isStreaming && <TypingIndicator />}

        <div ref={bottomRef} />
      </div>

      {/* Todo panel */}
      <TodoPanel />

      {/* Input area */}
      <div className="border-t border-border px-3 py-2.5">
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
              'flex-1 resize-none rounded-lg px-3 py-2.5',
              'bg-bg2 border border-border text-sm text-text',
              'placeholder:text-text3 focus:outline-none focus:border-accent',
              'transition-colors',
            )}
            style={{ minHeight: '44px', maxHeight: '150px' }}
          />
          <button
            onClick={() => handleSend()}
            disabled={isStreaming || !input.trim()}
            className={cn(
              'shrink-0 p-2.5 rounded-lg transition-colors cursor-pointer',
              isStreaming || !input.trim()
                ? 'bg-border text-text3 cursor-not-allowed'
                : 'bg-accent text-[#0f172a] hover:bg-accent/80',
            )}
            title="发送"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
