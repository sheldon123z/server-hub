/**
 * ChatInputFooter — 输入框底部工具栏
 */
import { cn } from '@/lib/utils'

interface ChatInputFooterProps {
  children: React.ReactNode
  className?: string
}

export function ChatInputFooter({ children, className }: ChatInputFooterProps) {
  return (
    <div className={cn('flex items-center justify-between px-3 py-2', className)}>
      {children}
    </div>
  )
}
