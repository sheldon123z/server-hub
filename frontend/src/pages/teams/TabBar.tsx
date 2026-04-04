/**
 * 通用标签栏组件
 */

import { cn } from '@/lib/utils'

export function TabBar({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="flex gap-4 border-b border-border mb-4">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            'pb-2 px-1 text-sm font-medium transition-colors',
            active === t.key ? 'border-b-2 border-accent text-accent' : 'border-b-2 border-transparent text-text3 hover:text-text',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
