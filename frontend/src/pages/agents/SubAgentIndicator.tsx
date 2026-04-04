import React, { useState, useCallback } from 'react'
import { ChevronDown, ChevronUp, Bot, Loader2, Check, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SubAgentItem } from '@/types/agent'
import { MarkdownContent } from './MarkdownContent'

function extractContent(data: Record<string, unknown>): string {
  if (data.task_instructions) return String(data.task_instructions)
  if (data.prompt) return String(data.prompt)
  return JSON.stringify(data, null, 2)
}

interface SubAgentIndicatorProps {
  subAgent: SubAgentItem
}

const StatusIcon: React.FC<{ status: SubAgentItem['status'] }> = ({ status }) => {
  switch (status) {
    case 'pending':
      return <Loader2 className="h-4 w-4 animate-spin text-accent" />
    case 'completed':
      return <Check className="h-4 w-4 text-green-500" />
    case 'error':
      return <AlertCircle className="h-4 w-4 text-red-500" />
    case 'interrupted':
      return <AlertCircle className="h-4 w-4 text-yellow-500" />
    default:
      return null
  }
}

export const SubAgentIndicator = React.memo<SubAgentIndicatorProps>(
  ({ subAgent }) => {
    const [expanded, setExpanded] = useState(false)

    const handleToggle = useCallback(() => {
      setExpanded((prev) => !prev)
    }, [])

    return (
      <div className="space-y-0">
        <button
          onClick={handleToggle}
          className={cn(
            'w-full flex items-center gap-2 rounded-lg border px-3 py-2 transition-colors',
            'bg-bg2 border-border hover:bg-bg2/80',
            expanded && 'rounded-b-none'
          )}
        >
          <Bot className="h-4 w-4 flex-shrink-0" />
          <span className="flex-1 text-left font-semibold text-sm text-text">
            {subAgent.subAgentName}
          </span>
          <StatusIcon status={subAgent.status} />
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-text2" />
          ) : (
            <ChevronDown className="h-4 w-4 text-text2" />
          )}
        </button>

        {expanded && (
          <div className="rounded-b-lg border border-t-0 border-border bg-bg/30 p-3 space-y-4">
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-text3 mb-2">
                Input
              </h4>
              <div className="text-sm">
                <MarkdownContent content={extractContent(subAgent.input)} />
              </div>
            </div>

            {subAgent.output && (
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-text3 mb-2">
                  Output
                </h4>
                <div className="text-sm">
                  <MarkdownContent content={extractContent(subAgent.output)} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    )
  }
)

SubAgentIndicator.displayName = 'SubAgentIndicator'
