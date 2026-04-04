/**
 * ToolCallCard — 升级版工具调用卡片
 *
 * 替代 ToolCallBox，提供：
 * - 工具分类图标和颜色
 * - 状态徽章（pending/completed/error）
 * - 可展开的参数区和结果区
 * - 结果区支持长文本截断
 */
import { useState, useMemo } from 'react'
import {
  ChevronDown,
  Loader2,
  CheckCircle2,
  AlertCircle,
  StopCircle,
  Wrench, Box, Activity, Terminal, FileText, Users, Server,
  Settings, Shield, Clock, Search, Globe, Brain, Bell,
  BarChart3, Table, HardDrive, Network, Layers, Play,
  BookOpen, Trash2, GitBranch, UserCog, XCircle, Monitor,
  AlertTriangle, PlusCircle, CheckCircle, ToggleLeft,
  ShieldCheck, TrendingUp, ExternalLink, FolderOpen,
  FilePlus, FileEdit, ListTodo, FormInput, CreditCard,
  PlayCircle, Wifi,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { getToolDisplayInfo } from '@/lib/message-utils'
import type { ToolCallItem } from '@/types/agent'

// 图标名称到组件的映射
const ICON_MAP: Record<string, React.ElementType> = {
  Wrench, Box, Activity, Terminal, FileText, Users, Server,
  Settings, Shield, Clock, Search, Globe, Brain, Bell,
  BarChart3, Table, HardDrive, Network, Layers, Play,
  BookOpen, Trash2, GitBranch, UserCog, XCircle, Monitor,
  AlertTriangle, PlusCircle, CheckCircle, ToggleLeft,
  ShieldCheck, TrendingUp, ExternalLink, FolderOpen,
  FilePlus, FileEdit, ListTodo, FormInput, CreditCard,
  PlayCircle, Wifi,
}

// 状态图标映射
const STATUS_CONFIG = {
  pending: { icon: Loader2, color: 'text-text3', animate: 'animate-spin', label: '执行中' },
  completed: { icon: CheckCircle2, color: 'text-green-500', animate: '', label: '已完成' },
  error: { icon: AlertCircle, color: 'text-red-500', animate: '', label: '失败' },
  interrupted: { icon: StopCircle, color: 'text-orange-400', animate: '', label: '已中断' },
} as const

interface ToolCallCardProps {
  toolCall: ToolCallItem
  defaultExpanded?: boolean
  compact?: boolean
}

export function ToolCallCard({ toolCall, defaultExpanded = false, compact = false }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const displayInfo = useMemo(() => getToolDisplayInfo(toolCall.name), [toolCall.name])

  const ToolIcon = ICON_MAP[displayInfo.icon] ?? Wrench
  const statusConfig = STATUS_CONFIG[toolCall.status] ?? STATUS_CONFIG.pending
  const StatusIcon = statusConfig.icon

  // 参数列表
  const argEntries = useMemo(() => {
    if (!toolCall.args) return []
    return Object.entries(toolCall.args).filter(([k]) => k !== 'subagent_type')
  }, [toolCall.args])

  // 结果摘要
  const resultPreview = useMemo(() => {
    if (!toolCall.result) return null
    const text = toolCall.result.trim()
    if (text.length <= 200) return text
    return text.slice(0, 200) + '...'
  }, [toolCall.result])

  if (compact) {
    // 紧凑模式：单行
    return (
      <div className="flex items-center gap-2 px-2 py-1 text-xs text-text2">
        <ToolIcon size={12} className={cn('shrink-0', displayInfo.color)} />
        <span className="truncate">{displayInfo.label}</span>
        <StatusIcon size={12} className={cn('ml-auto shrink-0', statusConfig.color, statusConfig.animate)} />
      </div>
    )
  }

  return (
    <div className={cn(
      'rounded-lg border transition-colors',
      toolCall.status === 'error'
        ? 'border-red-500/30 bg-red-500/5'
        : 'border-border bg-bg2/50',
    )}>
      {/* 标题栏 */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-full flex items-center gap-2 px-3 py-2 text-left',
          'hover:bg-bg2/80 transition-colors rounded-lg cursor-pointer',
        )}
      >
        <ToolIcon size={15} className={cn('shrink-0', displayInfo.color)} />
        <span className="text-sm font-medium text-text truncate">{displayInfo.label}</span>
        <span className="text-[11px] text-text3 font-mono truncate">{toolCall.name}</span>

        <div className="ml-auto flex items-center gap-1.5 shrink-0">
          <StatusIcon size={14} className={cn(statusConfig.color, statusConfig.animate)} />
          <ChevronDown
            size={14}
            className={cn(
              'text-text3 transition-transform duration-200',
              expanded && 'rotate-180',
            )}
          />
        </div>
      </button>

      {/* 展开区域 */}
      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-border/50">
          {/* 参数区 */}
          {argEntries.length > 0 && (
            <div className="pt-2">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-text3 mb-1">
                参数
              </div>
              <div className="space-y-1">
                {argEntries.map(([key, value]) => (
                  <div key={key} className="flex gap-2 text-xs">
                    <span className="shrink-0 text-text3 font-mono">{key}:</span>
                    <span className="text-text2 break-all font-mono">
                      {typeof value === 'string' ? value : JSON.stringify(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 结果区 */}
          {toolCall.result && (
            <div className="pt-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-text3 mb-1">
                结果
              </div>
              <pre className={cn(
                'text-xs font-mono whitespace-pre-wrap break-all rounded-md p-2 max-h-60 overflow-y-auto',
                toolCall.status === 'error' ? 'bg-red-500/10 text-red-300' : 'bg-bg text-text2',
              )}>
                {expanded ? toolCall.result : resultPreview}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
