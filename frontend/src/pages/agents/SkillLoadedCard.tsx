/**
 * SkillLoadedCard — 技能加载卡片
 *
 * 当用户通过 /skill:xxx 手动触发或 agent 自动加载技能时，
 * 在聊天流中渲染一个优雅的技能加载指示卡片。
 */

import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp, Sparkles, Wrench, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SkillInfo {
  skillId: string
  name: string
  description: string
  allowedTools?: string[]
  trigger: 'command' | 'auto'
}

interface SkillLoadedCardProps {
  skillInfo: SkillInfo
}

export function SkillLoadedCard({ skillInfo }: SkillLoadedCardProps) {
  const [expanded, setExpanded] = useState(false)
  const hasDetails = !!skillInfo.description || (skillInfo.allowedTools && skillInfo.allowedTools.length > 0)

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-xl border',
        'bg-gradient-to-r from-accent/5 via-transparent to-purple-500/5',
        'border-accent/20',
        'transition-all duration-300',
        expanded && 'shadow-sm shadow-accent/10',
      )}
    >
      {/* 顶部装饰线 */}
      <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-accent/60 via-purple-500/40 to-accent/20" />

      {/* 主体 */}
      <div className="px-3.5 pt-3 pb-2.5">
        {/* 标题行 */}
        <div className="flex items-center gap-2">
          <div className={cn(
            'flex items-center justify-center w-7 h-7 rounded-lg',
            'bg-accent/10 text-accent',
          )}>
            {skillInfo.trigger === 'command' ? (
              <BookOpen size={14} />
            ) : (
              <Sparkles size={14} />
            )}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-accent">
                {skillInfo.trigger === 'command' ? '已加载技能' : '自动激活技能'}
              </span>
              <Zap size={10} className="text-accent/50" />
            </div>
            <span className="text-sm font-semibold text-text truncate block">
              {skillInfo.name}
            </span>
          </div>

          {hasDetails && (
            <button
              onClick={() => setExpanded(!expanded)}
              className={cn(
                'flex items-center justify-center w-6 h-6 rounded-md',
                'text-text3 hover:text-text2 hover:bg-bg2',
                'transition-colors duration-150',
              )}
            >
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
        </div>

        {/* 描述（折叠区域） */}
        {expanded && hasDetails && (
          <div className="mt-2.5 pt-2.5 border-t border-border/50 space-y-2">
            {skillInfo.description && (
              <p className="text-xs text-text2 leading-relaxed">
                {skillInfo.description}
              </p>
            )}

            {skillInfo.allowedTools && skillInfo.allowedTools.length > 0 && (
              <div className="flex items-start gap-1.5">
                <Wrench size={11} className="text-text3 mt-0.5 shrink-0" />
                <div className="flex flex-wrap gap-1">
                  {skillInfo.allowedTools.map((tool) => (
                    <span
                      key={tool}
                      className={cn(
                        'inline-block px-1.5 py-0.5 rounded text-[10px]',
                        'bg-bg2 text-text3 border border-border/50',
                      )}
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
