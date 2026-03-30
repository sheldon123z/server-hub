/**
 * SlashCommandMenu - Quick command menu triggered by typing `/` in textarea.
 * Supports fuzzy matching, keyboard navigation (Up/Down/Enter/Tab/Escape).
 *
 * Usage: parent passes `onKeyDown` ref and calls it from textarea's onKeyDown.
 */

import { useState, useEffect, useRef, useMemo, useImperativeHandle, forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface SlashCommand {
  cmd: string
  desc: string
  prompt: string
  category: string
  hasArg?: boolean
  argHint?: string
}

const COMMAND_CATEGORIES = ['系统监控', 'AI 分析', '运维操作', '帮助'] as const

const SLASH_COMMANDS: SlashCommand[] = [
  { cmd: '/status', desc: '系统概况', prompt: '请给出当前系统状态概要', category: '系统监控' },
  { cmd: '/docker', desc: 'Docker 状态', prompt: '检查所有 Docker 容器状态', category: '系统监控' },
  { cmd: '/services', desc: '服务状态', prompt: '检查所有 systemd 服务状态', category: '系统监控' },
  { cmd: '/users', desc: '用户资源', prompt: '检查所有用户资源使用情况', category: '系统监控' },
  { cmd: '/disk', desc: '磁盘使用', prompt: '检查磁盘使用情况', category: '系统监控' },
  { cmd: '/gpu', desc: 'GPU 状态', prompt: '检查 GPU 使用状态', category: '系统监控' },
  { cmd: '/logs', desc: '查看日志', prompt: '查看系统关键日志', category: '运维操作' },
  { cmd: '/search', desc: '搜索日志', prompt: '搜索日志: ', category: '运维操作', hasArg: true, argHint: '关键词' },
  { cmd: '/health', desc: '健康检查', prompt: '执行完整的系统健康检查', category: '运维操作' },
  { cmd: '/security', desc: '安全审计', prompt: '执行安全审计检查', category: '运维操作' },
  { cmd: '/deep-research', desc: '深度调研 (异步)', prompt: '深度调研: ', category: 'AI 分析', hasArg: true, argHint: '调研主题' },
  { cmd: '/deep-audit', desc: '深度审计 (异步)', prompt: '深度安全审计: ', category: 'AI 分析', hasArg: true, argHint: '审计范围' },
  { cmd: '/deep-analysis', desc: '深度分析 (异步)', prompt: '深度关联分析: ', category: 'AI 分析', hasArg: true, argHint: '分析目标' },
  { cmd: '/tasks', desc: '异步任务列表', prompt: '显示当前所有异步任务的状态', category: 'AI 分析' },
  { cmd: '/help', desc: '帮助', prompt: '__HELP__', category: '帮助' },
]

/** Generate a formatted help text listing all slash commands. */
export function generateHelpText(): string {
  const lines = ['**可用快捷指令：**\n']
  for (const cat of COMMAND_CATEGORIES) {
    if (cat === '帮助') continue
    const cmds = SLASH_COMMANDS.filter((c) => c.category === cat && c.cmd !== '/help')
    if (cmds.length === 0) continue
    lines.push(`**${cat}**`)
    for (const c of cmds) {
      const argPart = c.hasArg ? ` <${c.argHint ?? '参数'}>` : ''
      lines.push(`\`${c.cmd}${argPart}\` — ${c.desc}`)
    }
    lines.push('')
  }
  lines.push('输入 `/` 后可模糊搜索指令。')
  return lines.join('\n')
}

export interface SlashCommandMenuProps {
  inputText: string
  onSelect: (prompt: string) => void
  visible: boolean
  onClose: () => void
}

export interface SlashCommandMenuHandle {
  handleKeyDown: (e: React.KeyboardEvent) => boolean
}

export const SlashCommandMenu = forwardRef<SlashCommandMenuHandle, SlashCommandMenuProps>(
  function SlashCommandMenu({ inputText, onSelect, visible, onClose }, ref) {
    const [activeIndex, setActiveIndex] = useState(0)
    const listRef = useRef<HTMLDivElement>(null)

    /* Filter commands by fuzzy match on input after '/' */
    const filtered = useMemo(() => {
      if (!visible) return []
      const query = inputText.startsWith('/') ? inputText.slice(1).toLowerCase() : ''
      if (!query) return SLASH_COMMANDS
      return SLASH_COMMANDS.filter(
        (c) =>
          c.cmd.toLowerCase().includes(query) ||
          c.desc.toLowerCase().includes(query),
      )
    }, [inputText, visible])

    /* Reset active index when filtered list changes */
    useEffect(() => {
      setActiveIndex(0)
    }, [filtered.length])

    /* Scroll active item into view */
    useEffect(() => {
      const container = listRef.current?.querySelector('.slash-list')
      const el = container?.children[activeIndex] as HTMLElement | undefined
      el?.scrollIntoView({ block: 'nearest' })
    }, [activeIndex])

    /* Expose keyboard handler to parent via ref */
    useImperativeHandle(ref, () => ({
      handleKeyDown(e: React.KeyboardEvent): boolean {
        if (!visible || filtered.length === 0) return false

        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setActiveIndex((i) => (i + 1) % filtered.length)
          return true
        } else if (e.key === 'ArrowUp') {
          e.preventDefault()
          setActiveIndex((i) => (i - 1 + filtered.length) % filtered.length)
          return true
        } else if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault()
          const cmd = filtered[activeIndex]
          if (cmd) {
            onSelect(cmd.prompt)
            onClose()
          }
          return true
        } else if (e.key === 'Escape') {
          e.preventDefault()
          onClose()
          return true
        }
        return false
      },
    }), [visible, filtered, activeIndex, onSelect, onClose])

    if (!visible || filtered.length === 0) return null

    // Build grouped items with category headers for rendering; track flat index for keyboard nav
    const groupedItems: { type: 'header'; label: string }[] | { type: 'cmd'; cmd: SlashCommand; flatIndex: number }[] = []
    const renderItems: Array<{ type: 'header'; label: string } | { type: 'cmd'; cmd: SlashCommand; flatIndex: number }> = []
    let flatIdx = 0
    for (const cat of COMMAND_CATEGORIES) {
      const cmds = filtered.filter((c) => c.category === cat)
      if (cmds.length === 0) continue
      renderItems.push({ type: 'header', label: cat })
      for (const cmd of cmds) {
        renderItems.push({ type: 'cmd', cmd, flatIndex: flatIdx })
        flatIdx++
      }
    }

    return (
      <div
        className="absolute bottom-full left-0 right-0 mb-1 bg-card border border-border rounded-lg shadow-xl overflow-hidden z-50"
        ref={listRef}
      >
        <div className="slash-list max-h-60 overflow-y-auto py-1">
          {renderItems.map((item, i) => {
            if (item.type === 'header') {
              return (
                <div key={'hdr-' + item.label} className="px-3 pt-2 pb-1 text-[11px] font-medium text-text3 uppercase tracking-wider select-none">
                  {item.label}
                </div>
              )
            }
            const { cmd, flatIndex } = item
            return (
              <button
                key={cmd.cmd}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors',
                  flatIndex === activeIndex
                    ? 'bg-accent-dim text-accent'
                    : 'text-text hover:bg-bg2',
                )}
                onMouseEnter={() => setActiveIndex(flatIndex)}
                onMouseDown={(e) => {
                  e.preventDefault()
                  onSelect(cmd.prompt)
                  onClose()
                }}
              >
                <code className="font-mono text-xs text-accent shrink-0 w-20">
                  {cmd.cmd}
                </code>
                <span className="text-text2 text-xs truncate">{cmd.desc}</span>
                {cmd.hasArg && (
                  <span className="ml-auto text-text3 text-xs italic">
                    {cmd.argHint}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>
    )
  },
)
