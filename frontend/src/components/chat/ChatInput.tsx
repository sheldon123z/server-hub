/**
 * ChatInput — Compound Component 模式的聊天输入框
 *
 * 管理: 文本状态, submit 逻辑, 快捷键, 自动高度调整
 * 子组件通过 Context 通信
 */
import { createContext, useContext, useState, useRef, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'

interface ChatInputContextValue {
  input: string
  setInput: (v: string) => void
  isStreaming: boolean
  handleSubmit: () => void
  handleStop: () => void
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
}

const ChatInputContext = createContext<ChatInputContextValue | null>(null)

export function useChatInput() {
  const ctx = useContext(ChatInputContext)
  if (!ctx) throw new Error('useChatInput must be used within ChatInput')
  return ctx
}

interface ChatInputProps {
  onSend: (text: string) => void
  onStop?: () => void
  isStreaming?: boolean
  placeholder?: string
  children?: React.ReactNode
  className?: string
  /** 外部控制的 input 值（用于从外部设置文本，如点击建议） */
  externalInput?: string
  onExternalInputConsumed?: () => void
}

export function ChatInput({
  onSend,
  onStop,
  isStreaming = false,
  placeholder = '输入消息... (/ 查看快捷指令)',
  children,
  className,
  externalInput,
  onExternalInputConsumed,
}: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const autoResize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }, [])

  // 处理外部输入（如点击建议）
  useEffect(() => {
    if (externalInput !== undefined && externalInput !== '') {
      setInput(externalInput)
      onExternalInputConsumed?.()
      // 聚焦并调整高度
      setTimeout(() => {
        textareaRef.current?.focus()
        autoResize()
      }, 0)
    }
  }, [externalInput, onExternalInputConsumed, autoResize])

  const handleSubmit = useCallback(() => {
    const text = input.trim()
    if (!text || isStreaming) return
    onSend(text)
    setInput('')
    // 重置高度
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }, 0)
  }, [input, isStreaming, onSend])

  const handleStop = useCallback(() => {
    onStop?.()
  }, [onStop])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault()
        handleSubmit()
      }
    },
    [handleSubmit],
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInput(e.target.value)
      autoResize()
    },
    [autoResize],
  )

  return (
    <ChatInputContext.Provider value={{ input, setInput, isStreaming, handleSubmit, handleStop, textareaRef }}>
      <div className={cn('flex flex-col border-t border-border bg-bg', className)}>
        {/* Textarea */}
        <div className="px-3 pt-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            className={cn(
              'w-full resize-none bg-transparent text-sm text-text',
              'placeholder:text-text3 outline-none',
              'max-h-[200px] scrollbar-thin',
            )}
          />
        </div>
        {/* 子组件区域（Footer 等） */}
        {children}
      </div>
    </ChatInputContext.Provider>
  )
}
