/**
 * MessageBubble — renders a single chat message with role-specific styling
 * and hover action bar (copy / delete / resend).
 */

import { useState, useCallback } from 'react'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'
import type { ChatMessage } from '@/types/agent'
import { MarkdownRenderer } from './MarkdownRenderer'

/* ── Props ──────────────────────────────────────────── */

interface MessageBubbleProps {
  message: ChatMessage
  onDelete?: (id: string) => void
  onResend?: (content: string, id: string) => void
  onApprove?: (approvalId: string) => void
  onReject?: (approvalId: string) => void
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

/* ── Tool call / result card ────────────────────────── */

function ToolCard({
  icon,
  label,
  content,
  borderColor,
  bgColor,
}: {
  icon: string
  label: string
  content: string
  borderColor: string
  bgColor: string
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className={cn(
        'max-w-[90%] rounded-lg border px-3 py-2 text-sm',
        borderColor,
        bgColor,
      )}
    >
      <div
        className="flex items-center gap-1.5 font-medium text-text cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <span>{icon}</span>
        <span>{label}</span>
        <span className="ml-auto text-text3 text-xs">{expanded ? '收起' : '展开'}</span>
      </div>
      <div
        className={cn(
          'mt-1.5 font-mono text-xs text-text2 whitespace-pre-wrap break-all overflow-hidden transition-all duration-200',
          expanded ? 'max-h-[600px] overflow-y-auto' : 'max-h-[80px]',
        )}
      >
        {content}
      </div>
    </div>
  )
}

/* ── Main component ─────────────────────────────────── */

export function MessageBubble({ message, onDelete, onResend, onApprove, onReject }: MessageBubbleProps) {
  const { role, content, _id } = message

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
            <MarkdownRenderer content={content} />
          </div>
        </div>
      </div>
    )
  }

  /* ── Tool call ────────────────────────────────── */
  if (role === 'tool_call') {
    const argsStr = message.args ? JSON.stringify(message.args, null, 2) : content
    return (
      <div className="flex justify-start">
        <ToolCard
          icon="🔧"
          label={message.tool || '工具调用'}
          content={argsStr}
          borderColor="border-[rgba(56,189,248,0.2)]"
          bgColor="bg-[rgba(56,189,248,0.08)]"
        />
      </div>
    )
  }

  /* ── Tool result ──────────────────────────────── */
  if (role === 'tool_result') {
    return (
      <div className="flex justify-start">
        <ToolCard
          icon="📋"
          label={message.tool || '结果'}
          content={content}
          borderColor="border-[rgba(56,189,248,0.2)]"
          bgColor="bg-[rgba(56,189,248,0.08)]"
        />
      </div>
    )
  }

  /* ── Approval request ─────────────────────────── */
  if (role === 'approval') {
    return (
      <div className="flex justify-start">
        <div
          className={cn(
            'max-w-[90%] rounded-lg border px-4 py-3 text-sm',
            'border-yellow bg-[rgba(251,191,36,0.1)]',
          )}
        >
          <div className="flex items-center gap-1.5 font-semibold text-yellow mb-2">
            <span>⚠️</span>
            <span>需要审批</span>
          </div>
          {message.description && (
            <p className="text-text2 text-xs mb-3 whitespace-pre-wrap">{message.description}</p>
          )}
          <div className="flex items-center gap-2">
            {onApprove && message.approval_id && (
              <button
                onClick={() => onApprove(message.approval_id!)}
                className={cn(
                  'px-3 py-1 rounded text-xs font-medium',
                  'bg-green/20 text-green border border-green/30',
                  'hover:bg-green/30 transition-colors',
                )}
              >
                批准
              </button>
            )}
            {onReject && message.approval_id && (
              <button
                onClick={() => onReject(message.approval_id!)}
                className={cn(
                  'px-3 py-1 rounded text-xs font-medium',
                  'bg-red/20 text-red border border-red/30',
                  'hover:bg-red/30 transition-colors',
                )}
              >
                拒绝
              </button>
            )}
          </div>
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
}
