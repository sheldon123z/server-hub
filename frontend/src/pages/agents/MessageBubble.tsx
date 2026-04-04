/**
 * MessageBubble — renders a single chat message with role-specific styling
 * and hover action bar (copy / delete / resend).
 *
 * Tool calls, tool results, and approvals are now rendered by ChatPanel
 * via ToolCallBox and ToolApprovalInterrupt respectively.
 */

import React, { useCallback } from 'react'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'
import type { ChatMessage, UIComponentMessage } from '@/types/agent'
import { isUIComponentMessage } from '@/lib/message-utils'
import { useStreamingText } from '@/hooks/useStreamingText'
import { MarkdownContent } from './MarkdownContent'
import { UICard } from '@/components/agent/UICard'
import { UIComponentErrorBoundary } from '@/components/agent/UIComponentErrorBoundary'
import { useChatStore } from '@/stores/chatStore'

/* ── Props ──────────────────────────────────────────── */

interface MessageBubbleProps {
  message: ChatMessage
  onDelete?: (id: string) => void
  onResend?: (content: string, id: string) => void
}

/* ── Sub-components ─────────────────────────────────── */

function ActionBar({
  onCopy,
  onDelete,
  onResend,
}: {
  onCopy: () => void
  onDelete?: () => void
  onResend?: () => void
}) {
  return (
    <div
      className={cn(
        'absolute -top-8 right-0 flex items-center gap-1',
        'rounded-md bg-card/90 border border-border px-1.5 py-0.5',
        'opacity-0 group-hover:opacity-100 transition-opacity duration-150',
        'pointer-events-none group-hover:pointer-events-auto',
        'z-10 text-xs',
      )}
    >
      <button onClick={onCopy} className="hover:text-accent px-1.5 py-0.5 text-text2" title="复制">
        复制
      </button>
      {onResend && (
        <button onClick={onResend} className="hover:text-accent px-1.5 py-0.5 text-text2" title="重发">
          重发
        </button>
      )}
      {onDelete && (
        <button onClick={onDelete} className="hover:text-red px-1.5 py-0.5 text-text2" title="删除">
          删除
        </button>
      )}
    </div>
  )
}

/* ── Main component ─────────────────────────────────── */

export const MessageBubble = React.memo(function MessageBubble({ message, onDelete, onResend }: MessageBubbleProps) {
  const { role, content, _id } = message

  // Streaming state (hooks must be at top level)
  const streamingMessageId = useChatStore((s) => s.streamingMessageId)
  const isCurrentlyStreaming = role === 'assistant' && _id === streamingMessageId
  const { displayedContent, isAnimating } = useStreamingText(content, {
    enabled: isCurrentlyStreaming,
    segmentDelay: 12,
  })

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content).then(() => toast.success('已复制')).catch(() => toast.error('复制失败'))
  }, [content])

  const handleDelete = onDelete ? () => onDelete(_id) : undefined
  const handleResend = onResend ? () => onResend(content, _id) : undefined

  /* ── User message ─────────────────────────────── */
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="group relative max-w-[85%]">
          <ActionBar onCopy={handleCopy} onDelete={handleDelete} onResend={handleResend} />
          <div
            className={cn(
              'rounded-xl rounded-br-sm px-4 py-2.5',
              'bg-accent text-[#0f172a]',
              'text-sm leading-relaxed whitespace-pre-wrap break-words',
            )}
          >
            {content}
          </div>
        </div>
      </div>
    )
  }

  /* ── Assistant message ────────────────────────── */
  if (role === 'assistant') {
    return (
      <div className="flex justify-start">
        <div className="group relative max-w-[85%]">
          <ActionBar onCopy={handleCopy} onDelete={handleDelete} />
          <div
            className={cn(
              'rounded-xl rounded-bl-sm px-4 py-2.5',
              'bg-bg2 border border-border',
              'text-sm leading-relaxed',
            )}
          >
            {isCurrentlyStreaming ? (
              <>
                <span className="whitespace-pre-wrap">{displayedContent}</span>
                {isAnimating && (
                  <span className="inline-block w-1.5 h-4 bg-accent/60 ml-0.5 animate-pulse rounded-sm align-text-bottom" />
                )}
              </>
            ) : (
              <MarkdownContent content={content} />
            )}
          </div>
        </div>
      </div>
    )
  }

  /* ── UI Component ─────────────────────────────── */
  if (role === 'ui_component' && isUIComponentMessage(message)) {
    const handleUIAction = (actionId: string, payload?: Record<string, unknown>) => {
      fetch('/api/agents/ui/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          component_id: message.data?.id,
          component_type: message.componentType,
          action_id: actionId,
          action_type: 'agent',
          payload: payload ?? {},
          conversation_id: useChatStore.getState().conversationId,
          run_id: useChatStore.getState().currentRunId,
        }),
      }).catch(console.error)
    }

    return (
      <div className="flex justify-start">
        <div className="group relative max-w-[95%]">
          <ActionBar onCopy={handleCopy} onDelete={handleDelete} />
          <UIComponentErrorBoundary componentId={(message.data?.id as string) ?? 'unknown'}>
            <UICard
              component={message.data as UIComponentMessage['data']}
              onAction={handleUIAction}
            />
          </UIComponentErrorBoundary>
        </div>
      </div>
    )
  }

  /* ── Fallback ─────────────────────────────────── */
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-lg bg-bg2 border border-border px-3 py-2 text-sm text-text2">
        {content}
      </div>
    </div>
  )
})
