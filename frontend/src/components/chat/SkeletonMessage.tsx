/**
 * SkeletonMessage — AI 响应等待时的骨架屏加载动画
 *
 * 替代当前的三点弹跳 TypingIndicator，
 * 使用交错动画的条形骨架更专业
 */
import { cn } from '@/lib/utils'

const STAGGER_MS = 60

function SkeletonBar({ index, width }: { index: number; width: string }) {
  return (
    <div
      className="opacity-0 animate-in fade-in slide-in-from-left-2"
      style={{ animationDelay: `${index * STAGGER_MS}ms`, animationFillMode: 'forwards' }}
    >
      <div
        className={cn('h-3 rounded-md bg-text3/10 animate-pulse')}
        style={{ width }}
      />
    </div>
  )
}

export function SkeletonMessage() {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-xl rounded-bl-sm px-4 py-3 bg-bg2 border border-border space-y-2.5">
        <SkeletonBar index={0} width="85%" />
        <SkeletonBar index={1} width="70%" />
        <SkeletonBar index={2} width="55%" />
      </div>
    </div>
  )
}
