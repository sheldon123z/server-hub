/**
 * Dashboard card components - MiniStat, AlertBar, and StatCard
 * used in the main dashboard grid view.
 */

import type { AlertData } from '@/hooks/useWebSocket'
import type { CardConfig } from './types'
import { cn } from '@/lib/utils'
import { Sparkline } from './charts'
import { statusColor, statusHex } from './utils'
import type { AlertSummary } from './types'

// ---------------------------------------------------------------------------
// Mini stat label
// ---------------------------------------------------------------------------
export function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg2 border border-border rounded-lg px-3 py-2">
      <div className="text-[10px] text-text3 uppercase tracking-wider">{label}</div>
      <div className="text-sm font-semibold text-text mt-0.5 truncate">{value}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Alert bar
// ---------------------------------------------------------------------------
export function AlertBar({ summary, connected, alerts }: { summary: AlertSummary | null; connected: boolean; alerts: AlertData[] }) {
  const hasCritical = (summary?.critical ?? 0) > 0 || alerts.some((a) => a.level === 'critical')
  const hasWarning = (summary?.warning ?? 0) > 0 || alerts.some((a) => a.level === 'warning')

  return (
    <div className={cn(
      'flex items-center justify-between px-4 py-2 rounded-lg mb-4 border text-sm',
      hasCritical ? 'bg-red/10 border-red/30 text-red' :
      hasWarning ? 'bg-yellow/10 border-yellow/30 text-yellow' :
      'bg-green/5 border-green/20 text-green',
    )}>
      <div className="flex items-center gap-3">
        {hasCritical ? (
          <span>严重告警 {summary?.critical ?? 0} | 警告 {summary?.warning ?? 0}</span>
        ) : hasWarning ? (
          <span>警告 {summary?.warning ?? 0} | 24h 告警数 {summary?.total_24h ?? 0}</span>
        ) : (
          <span>系统正常</span>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-text3">
        <span className={cn('inline-block w-2 h-2 rounded-full', connected ? 'bg-green animate-pulse' : 'bg-red')} />
        {connected ? 'WS 已连接' : 'WS 断开'}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------
export function StatCard({
  config,
  value,
  sub,
  percent,
  sparkData,
  color,
  onClick,
}: {
  config: CardConfig
  value: string
  sub: string
  percent: number
  sparkData: number[]
  color: string
  onClick: () => void
}) {
  const Icon = config.icon
  const showBar = percent >= 0

  return (
    <div
      onClick={onClick}
      className="bg-card border border-border rounded-lg p-4 cursor-pointer hover:border-accent/30 transition-colors group relative overflow-hidden"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon size={16} className="text-text3 group-hover:text-accent transition-colors" />
          <span className="text-xs text-text3 font-medium">{config.label}</span>
        </div>
      </div>

      <div className={cn('text-2xl font-bold tracking-tight', showBar ? statusColor(percent) : 'text-text')}>
        {value}
      </div>
      <div className="text-xs text-text3 mt-0.5 truncate">{sub}</div>

      {showBar && (
        <div className="mt-2 h-1 rounded-full bg-border overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${Math.min(percent, 100)}%`, backgroundColor: statusHex(percent) }}
          />
        </div>
      )}

      {sparkData.length > 1 && (
        <div className="mt-2 -mx-1">
          <Sparkline data={sparkData} color={color} />
        </div>
      )}
    </div>
  )
}
