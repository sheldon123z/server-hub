/**
 * ReasoningBlock — AI 推理/思考过程的折叠展示
 *
 * 设计参考 DeerFlow 的 reasoning.tsx：
 * - 思考中：显示 "正在思考..." + shimmer 动画 + 计时
 * - 完成后：自动折叠为 "思考了 N 秒"，可手动展开
 * - 展开内容用浅色文字渲染
 */
import { useState, useEffect, useRef } from 'react'
import { Brain, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ReasoningBlockProps {
  /** 思考内容 */
  content: string
  /** 是否正在思考（streaming 中） */
  isStreaming?: boolean
  /** 默认是否展开 */
  defaultOpen?: boolean
}

export function ReasoningBlock({ content, isStreaming = false, defaultOpen = false }: ReasoningBlockProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen || isStreaming)
  const [duration, setDuration] = useState(0)
  const startTimeRef = useRef<number | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval>>(0 as unknown as ReturnType<typeof setInterval>)

  // 计时器
  useEffect(() => {
    if (isStreaming) {
      if (!startTimeRef.current) {
        startTimeRef.current = Date.now()
      }
      timerRef.current = setInterval(() => {
        setDuration(Math.floor((Date.now() - (startTimeRef.current ?? Date.now())) / 1000))
      }, 1000)
    } else {
      clearInterval(timerRef.current)
      // 完成后延迟 1 秒自动折叠
      if (startTimeRef.current) {
        setDuration(Math.floor((Date.now() - startTimeRef.current) / 1000))
        const collapseTimer = setTimeout(() => setIsOpen(false), 1000)
        return () => clearTimeout(collapseTimer)
      }
    }
    return () => clearInterval(timerRef.current)
  }, [isStreaming])

  const toggleOpen = () => setIsOpen((v) => !v)

  return (
    <div className="my-1">
      {/* 标题栏 */}
      <button
        type="button"
        onClick={toggleOpen}
        className={cn(
          'flex items-center gap-2 px-3 py-1.5 rounded-md w-full text-left',
          'hover:bg-bg2/50 transition-colors cursor-pointer',
        )}
      >
        <Brain size={14} className={cn('shrink-0', isStreaming ? 'text-violet-400' : 'text-text3')} />

        {isStreaming ? (
          <span className="text-xs text-violet-400 font-medium">
            <span className="inline-block animate-pulse">正在思考</span>
            <span className="text-text3 ml-1.5">{duration > 0 && `${duration}s`}</span>
          </span>
        ) : (
          <span className="text-xs text-text3">
            思考了 {duration > 0 ? `${duration} 秒` : '片刻'}
          </span>
        )}

        <ChevronDown
          size={14}
          className={cn(
            'ml-auto shrink-0 text-text3/50 transition-transform duration-200',
            isOpen && 'rotate-180',
          )}
        />
      </button>

      {/* 展开内容 */}
      <div
        className={cn(
          'overflow-hidden transition-all duration-200 ease-in-out',
          isOpen ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0',
        )}
      >
        <div className={cn(
          'mx-3 px-3 py-2 rounded-md',
          'border-l-2 border-violet-400/30',
          'text-xs text-text3 leading-relaxed whitespace-pre-wrap',
          isStreaming && 'bg-violet-400/5',
        )}>
          {content || '...'}
          {isStreaming && (
            <span className="inline-block w-1.5 h-3.5 bg-violet-400/60 ml-0.5 animate-pulse rounded-sm" />
          )}
        </div>
      </div>
    </div>
  )
}
