/**
 * ChatInputSubmit — 发送 / 停止按钮
 */
import { ArrowUp, Square } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useChatInput } from './ChatInput'

interface ChatInputSubmitProps {
  className?: string
}

export function ChatInputSubmit({ className }: ChatInputSubmitProps) {
  const { input, isStreaming, handleSubmit, handleStop } = useChatInput()

  if (isStreaming) {
    return (
      <button
        type="button"
        onClick={handleStop}
        className={cn(
          'p-1.5 rounded-lg bg-red-500/20 text-red-400',
          'hover:bg-red-500/30 transition-colors cursor-pointer',
          className,
        )}
        title="停止生成"
      >
        <Square size={16} fill="currentColor" />
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={handleSubmit}
      disabled={!input.trim()}
      className={cn(
        'p-1.5 rounded-lg transition-colors cursor-pointer',
        input.trim()
          ? 'bg-accent text-[#0f172a] hover:bg-accent/90'
          : 'bg-bg2 text-text3 cursor-not-allowed',
        className,
      )}
      title="发送 (Enter)"
    >
      <ArrowUp size={16} />
    </button>
  )
}
