/**
 * FollowUpSuggestions — 推荐追问标签
 *
 * 显示在输入框上方，3 个可点击的建议胶囊
 */
import { useState } from 'react'
import { X, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FollowUpSuggestionsProps {
  suggestions: string[]
  onSelect: (text: string) => void
  onDismiss: () => void
}

export function FollowUpSuggestions({ suggestions, onSelect, onDismiss }: FollowUpSuggestionsProps) {
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || suggestions.length === 0) return null

  const handleDismiss = () => {
    setDismissed(true)
    onDismiss()
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 transition-all duration-300">
      <Sparkles size={14} className="text-accent/60 shrink-0" />
      <div className="flex flex-wrap gap-1.5 flex-1 min-w-0">
        {suggestions.map((text) => (
          <button
            key={text}
            type="button"
            onClick={() => onSelect(text)}
            className={cn(
              'px-3 py-1 rounded-full text-xs',
              'bg-accent/10 text-accent border border-accent/20',
              'hover:bg-accent/20 hover:border-accent/40',
              'transition-all duration-150 cursor-pointer',
              'truncate max-w-[200px]',
            )}
            title={text}
          >
            {text}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={handleDismiss}
        className="p-0.5 rounded text-text3 hover:text-text2 hover:bg-bg2 transition-colors shrink-0 cursor-pointer"
        title="关闭建议"
      >
        <X size={12} />
      </button>
    </div>
  )
}
