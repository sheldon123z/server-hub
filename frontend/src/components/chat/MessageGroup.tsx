/**
 * MessageGroup — 消息分组容器（折叠/展开工具调用和 SubAgent）
 */
import { useState } from 'react'
import type { MessageGroupType, ToolCallItem, SubAgentItem } from '@/types/agent'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/Collapsible'
import { MessageGroupHeader } from './MessageGroupHeader'
import { cn } from '@/lib/utils'

interface MessageGroupProps {
  type: MessageGroupType
  toolCalls?: ToolCallItem[]
  subAgents?: SubAgentItem[]
  /** 折叠区域内的子元素（ToolCallCard / SubAgentIndicator 列表） */
  children: React.ReactNode
  /** 始终显示的最后一个结果摘要 */
  lastResultSummary?: string
  /** 默认是否展开 */
  defaultOpen?: boolean
  className?: string
}

export function MessageGroup({
  type,
  toolCalls = [],
  subAgents = [],
  children,
  lastResultSummary,
  defaultOpen = false,
  className,
}: MessageGroupProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  const count = type === 'subagent' ? subAgents.length : toolCalls.length

  // 如果只有 1 个工具调用，默认展开
  const shouldDefaultOpen = count <= 1

  return (
    <div className={cn('mt-1', className)}>
      <Collapsible
        open={shouldDefaultOpen ? true : isOpen}
        onOpenChange={shouldDefaultOpen ? undefined : setIsOpen}
      >
        {/* 标题栏（可点击折叠/展开） */}
        {!shouldDefaultOpen && (
          <CollapsibleTrigger>
            <MessageGroupHeader
              type={type}
              count={count}
              isOpen={isOpen}
            />
          </CollapsibleTrigger>
        )}

        {/* 折叠内容 */}
        {shouldDefaultOpen ? (
          <div className="flex flex-col gap-1 pl-3">{children}</div>
        ) : (
          <>
            {/* 折叠时显示最后一个结果摘要 */}
            {!isOpen && lastResultSummary && (
              <div className="px-3 py-1 text-xs text-text3 truncate">
                {lastResultSummary}
              </div>
            )}
            <CollapsibleContent>
              <div className="flex flex-col gap-1 pl-3 pt-1">{children}</div>
            </CollapsibleContent>
          </>
        )}
      </Collapsible>
    </div>
  )
}
