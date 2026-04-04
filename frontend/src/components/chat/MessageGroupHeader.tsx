/**
 * MessageGroupHeader — 消息分组标题栏
 */
import { ChevronDown, Wrench, Bot, Layers } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { MessageGroupType } from '@/types/agent'

interface MessageGroupHeaderProps {
  type: MessageGroupType
  count: number
  isOpen: boolean
  label?: string
}

const GROUP_CONFIG: Record<MessageGroupType, { icon: React.ElementType; defaultLabel: string; color: string }> = {
  processing: { icon: Wrench, defaultLabel: '个工具', color: 'text-text2' },
  subagent: { icon: Bot, defaultLabel: '个子智能体', color: 'text-accent' },
  mixed: { icon: Layers, defaultLabel: '个操作', color: 'text-text2' },
  content: { icon: Layers, defaultLabel: '', color: 'text-text2' },
}

export function MessageGroupHeader({ type, count, isOpen, label }: MessageGroupHeaderProps) {
  const config = GROUP_CONFIG[type] ?? GROUP_CONFIG.processing
  const Icon = config.icon

  return (
    <div className={cn(
      'flex items-center gap-2 px-3 py-1.5 rounded-md text-xs',
      'hover:bg-bg2/50 transition-colors cursor-pointer select-none',
      config.color,
    )}>
      <Icon size={14} className="shrink-0 opacity-70" />
      <span className="font-medium">
        {label ?? `使用了 ${count} ${config.defaultLabel}`}
      </span>
      <ChevronDown
        size={14}
        className={cn(
          'ml-auto shrink-0 opacity-50 transition-transform duration-200',
          isOpen && 'rotate-180',
        )}
      />
    </div>
  )
}
