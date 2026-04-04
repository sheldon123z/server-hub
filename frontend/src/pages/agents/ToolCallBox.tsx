/**
 * ToolCallBox - compact card showing a tool invocation name, args summary, and status.
 */

import { Wrench, Check, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ToolCall {
  id: string
  name: string
  args: Record<string, unknown>
  result?: string
}

interface ToolCallBoxProps {
  toolCall: ToolCall
}

export function ToolCallBox({ toolCall }: ToolCallBoxProps) {
  const hasResult = toolCall.result !== undefined
  const argsPreview = Object.keys(toolCall.args)
    .filter((k) => k !== 'subagent_type' && k !== 'subagent_name')
    .slice(0, 3)
    .map((k) => `${k}=${JSON.stringify(toolCall.args[k]).slice(0, 30)}`)
    .join(', ')

  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs',
        hasResult
          ? 'border-green/20 bg-green/5 text-text2'
          : 'border-border bg-bg2 text-text3',
      )}
    >
      <Wrench size={13} className="shrink-0" />
      <span className="font-medium text-text">{toolCall.name}</span>
      {argsPreview && (
        <span className="truncate max-w-[200px] text-text3">({argsPreview})</span>
      )}
      <span className="ml-auto shrink-0">
        {hasResult ? (
          <Check size={13} className="text-green" />
        ) : (
          <Loader2 size={13} className="animate-spin text-text3" />
        )}
      </span>
    </div>
  )
}
