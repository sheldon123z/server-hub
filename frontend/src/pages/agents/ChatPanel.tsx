import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Send, Square, Sparkles } from 'lucide-react'
import { useStickToBottom } from 'use-stick-to-bottom'
import { useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { cn, ensureArray } from '@/lib/utils'
import client from '@/api/client'
import { useChatStore } from '@/stores/chatStore'
import { useSSEChat } from '@/hooks/useSSEChat'
import type { ChatMessage, ProcessedMessage, SkillRecommendation } from '@/types/agent'
import { useProcessedMessages } from '@/hooks/useProcessedMessages'
import { hasToolCalls, hasSubAgents, getToolResultSummary } from '@/lib/message-utils'
import { MessageGroup } from '@/components/chat/MessageGroup'
import { ToolCallCard } from '@/components/chat/ToolCallCard'
import { FollowUpSuggestions } from '@/components/chat/FollowUpSuggestions'
import { SkeletonMessage } from '@/components/chat/SkeletonMessage'
import { useFollowUpSuggestions } from '@/hooks/useFollowUpSuggestions'
import { MessageBubble } from './MessageBubble'
import { ToolApprovalInterrupt } from './ToolApprovalInterrupt'
import { SubAgentIndicator } from './SubAgentIndicator'
import { TodoPanel } from './TodoPanel'
import { SlashCommandMenu, type SlashCommandMenuHandle, generateHelpText } from './SlashCommandMenu'
import { ArtifactCard } from './ArtifactCard'
import { SkillLoadedCard } from './SkillLoadedCard'

function pageContextFromPath(pathname: string): string {
  const seg = pathname.replace(/^\//, '').split('/')[0]
  return seg || 'dashboard'
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
    return sessionStorage.getItem('serverhub-chat-draft') || ''
  })
  const [showSlashMenu, setShowSlashMenu] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const slashMenuRef = useRef<SlashCommandMenuHandle>(null)
  const { scrollRef, contentRef, isAtBottom } = useStickToBottom()
  const pageContext = pageContextFromPath(location.pathname)
  const processedMessages = useProcessedMessages()
  const { suggestions: followUpSuggestions, hasSuggestions, clearSuggestions } = useFollowUpSuggestions()

  const trimmedInput = input.trim()

  const { data: recommendations } = useQuery({
    queryKey: ['skill-recommendations', pageContext, trimmedInput],
    queryFn: async () => {
      if (!trimmedInput) return [] as SkillRecommendation[]
      const { data } = await client.get<{ items: SkillRecommendation[] }>('/api/agents/skills/recommendations', {
        params: { message: trimmedInput, page_context: pageContext },
      })
      return ensureArray<SkillRecommendation>(data.items)
    },
    enabled: trimmedInput.length >= 2,
    staleTime: 15_000,
  })

  const selectedRecommendation = useMemo(
    () => recommendations?.find((item) => item.id === selectedSkillId) ?? null,
    [recommendations, selectedSkillId],
  )


  // 草稿自动保存（防抖 500ms）
  useEffect(() => {
    const timer = setTimeout(() => {
      if (input) sessionStorage.setItem('serverhub-chat-draft', input)
      else sessionStorage.removeItem('serverhub-chat-draft')
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
      sessionStorage.removeItem('serverhub-chat-draft')
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

  function renderProcessedMessage(pm: ProcessedMessage) {
    const { message: msg } = pm

    // Skill loaded card
    if (msg.role === 'skill_loaded' && msg.skillInfo) {
      return (
        <div key={msg._id} className="px-3">
          <SkillLoadedCard skillInfo={msg.skillInfo} />
        </div>
      )
    }

    // User or assistant message
    if (msg.role === 'user' || msg.role === 'assistant') {
      return (
        <div key={msg._id} className="px-3">
          <MessageBubble
            message={msg}
            onDelete={handleDelete}
            onResend={msg.role === 'user' ? handleResend : undefined}
          />
          {/* Tool calls — MessageGroup 折叠包裹 */}
          {hasToolCalls(pm) && (() => {
            const regularToolCalls = pm.toolCalls.filter(tc => !tc.args?.subagent_type)
            if (regularToolCalls.length === 0) return null
            const lastTc = regularToolCalls[regularToolCalls.length - 1]
            return (
              <>
                <MessageGroup
                  type="processing"
                  toolCalls={regularToolCalls}
                  lastResultSummary={getToolResultSummary(lastTc?.result)}
                >
                  {regularToolCalls.map(tc => (
                    <ToolCallCard key={tc.id} toolCall={tc} />
                  ))}
                </MessageGroup>
                {/* Artifact 卡片 - 在工具调用组之后显示 */}
                {(() => {
                  const fileOps = regularToolCalls.filter(
                    tc => tc.name === 'write_file' || tc.name === 'edit_file'
                  )
                  if (!fileOps.length) return null
                  // 按路径去重，保留最后一个
                  const unique = new Map<string, typeof fileOps[0]>()
                  for (const tc of fileOps) {
                    const fp = (tc.args?.file_path as string) || (tc.args?.path as string)
                    if (fp) unique.set(fp, tc)
                  }
                  if (!unique.size) return null
                  return (
                    <div className="flex flex-wrap gap-1.5 mt-1.5 ml-1">
                      {[...unique.entries()].map(([fp, tc]) => (
                        <ArtifactCard key={fp} filePath={fp} action={tc.name as 'write_file' | 'edit_file'} />
                      ))}
                    </div>
                  )
                })()}
              </>
            )
          })()}
          {/* SubAgent indicators — MessageGroup 折叠包裹 */}
          {hasSubAgents(pm) && (
            <MessageGroup type="subagent" subAgents={pm.subAgents}>
              {pm.subAgents.map(sa => (
                <SubAgentIndicator key={sa.id} subAgent={sa} />
              ))}
            </MessageGroup>
          )}
        </div>
      )
    }

    // Approval message — use new 3-way approval component
    if (msg.role === 'approval') {
      return (
        <div key={msg._id} className="flex justify-start px-3">
          <div className="max-w-[85%]">
            <ToolApprovalInterrupt
              approvalId={msg.approval_id || ''}
              description={msg.description}
              actions={msg.actions}
              onResolved={() => {
                useChatStore.getState().removeMessage(msg._id)
              }}
            />
          </div>
        </div>
      )
    }

    // UI component or fallback
    return (
      <div key={msg._id} className="px-3">
        <MessageBubble message={msg} onDelete={handleDelete} />
      </div>
    )
  }

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="relative flex-1 overflow-y-auto py-3" ref={scrollRef}>
        <div ref={contentRef}>
          {messages.length === 0 && !isStreaming && (
            <div className="flex h-full items-center justify-center" style={{ minHeight: '60vh' }}>
              <div className="text-center text-text3">
                <div className="mb-2 text-3xl">&#129302;</div>
                <div className="text-sm">OpsAgent 运维助手</div>
                <div className="mt-1 text-xs">输入消息开始对话</div>
              </div>
            </div>
          )}
          <div className="flex flex-col gap-2.5">{processedMessages.map(renderProcessedMessage)}</div>
          {isStreaming && <div className="px-3"><SkeletonMessage /></div>}
        </div>
        {!isAtBottom && messages.length > 0 && (
          <button
            onClick={() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })}
            className="sticky bottom-3 left-1/2 -translate-x-1/2 z-10 bg-accent text-[#0f172a] px-3 py-1 rounded-full text-sm shadow-lg hover:bg-accent/80 transition-colors"
          >
            ↓ 新消息
          </button>
        )}
      </div>

      <TodoPanel />

      {hasSuggestions && (
        <FollowUpSuggestions
          suggestions={followUpSuggestions}
          onSelect={(text) => {
            clearSuggestions()
            handleSend(text)
          }}
          onDismiss={clearSuggestions}
        />
      )}

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
