/**
 * TodoPanel - Collapsible task progress panel shown at bottom of chat.
 * Reads todo items from chatStore.
 */

import { useState } from 'react'
import { useChatStore } from '@/stores/chatStore'
import { cn, ensureArray } from '@/lib/utils'

export function TodoPanel() {
  const rawTodos = useChatStore((s) => s.todos)
  const todos = ensureArray<typeof rawTodos[number]>(rawTodos)
  const [collapsed, setCollapsed] = useState(false)

  if (todos.length === 0) return null

  const completed = todos.filter((t) => t.status === 'completed').length
  const total = todos.length
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0

  return (
    <div className="border-t border-border bg-bg2 shrink-0">
      {/* Header */}
      <button
        className="flex items-center justify-between w-full px-3 py-2 text-xs text-text2 hover:text-text transition-colors"
        onClick={() => setCollapsed((v) => !v)}
      >
        <span className="font-medium">
          任务规划
          <span className="ml-2 text-text3">
            {completed}/{total}
          </span>
        </span>
        <svg
          className={cn('w-3.5 h-3.5 transition-transform', collapsed && '-rotate-90')}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {!collapsed && (
        <div className="px-3 pb-3 space-y-1.5">
          {/* Progress bar */}
          <div className="h-1.5 rounded-full bg-bg overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>

          {/* Item list */}
          <ul className="space-y-1 max-h-32 overflow-y-auto">
            {todos.map((item, i) => {
              const isCompleted = item.status === 'completed'
              const isInProgress = item.status === 'in_progress'

              return (
                <li
                  key={`${i}-${item.content}`}
                  className={cn(
                    'flex items-start gap-2 text-xs py-0.5 rounded px-1',
                    isCompleted && 'text-text3 line-through',
                    isInProgress && 'text-accent',
                    item._justCompleted && 'animate-flash-green',
                  )}
                >
                  <span className="shrink-0 mt-0.5">
                    {isCompleted ? (
                      <span className="text-green">&#x2705;</span>
                    ) : isInProgress ? (
                      <span className="todo-pulse">&#x1F504;</span>
                    ) : (
                      <span className="text-text3">&#x2B1C;</span>
                    )}
                  </span>
                  <span className="break-all">{item.content}</span>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      <style>{`
        @keyframes flash-green {
          0% { background: rgba(74, 222, 128, 0.25); }
          100% { background: transparent; }
        }
        .animate-flash-green {
          animation: flash-green 0.6s ease-out;
        }
        @keyframes pulse-todo {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        .todo-pulse {
          animation: pulse-todo 1.5s infinite;
        }
      `}</style>
    </div>
  )
}
