/**
 * StatusCard — displays a status card with title, status badge,
 * metric grid, and optional details text.
 */

import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Metric {
  label: string
  value: string | number
  unit?: string
  trend?: 'up' | 'down' | 'stable'
}

interface CardComponent {
  id: string
  type: 'card'
  title: string
  status: 'healthy' | 'warning' | 'error' | 'unknown'
  metrics: Metric[]
  details?: string
}

interface StatusCardProps {
  component: CardComponent
}

/* ── Status config ─────────────────────────────── */

const STATUS_MAP: Record<string, { label: string; color: string; bg: string; border: string }> = {
  healthy: { label: '健康', color: 'text-green', bg: 'bg-green/20', border: 'border-green/30' },
  warning: { label: '警告', color: 'text-yellow', bg: 'bg-yellow/20', border: 'border-yellow/30' },
  error:   { label: '错误', color: 'text-red', bg: 'bg-red/10', border: 'border-red/30' },
  unknown: { label: '未知', color: 'text-text3', bg: 'bg-bg3', border: 'border-border' },
}

function TrendIcon({ trend }: { trend?: 'up' | 'down' | 'stable' }) {
  if (trend === 'up') return <TrendingUp className="w-3.5 h-3.5 text-red" />
  if (trend === 'down') return <TrendingDown className="w-3.5 h-3.5 text-green" />
  if (trend === 'stable') return <Minus className="w-3.5 h-3.5 text-text3" />
  return null
}

/* ── Component ─────────────────────────────────── */

export function StatusCard({ component }: StatusCardProps) {
  const { title, status, metrics, details } = component
  const cfg = STATUS_MAP[status] ?? STATUS_MAP.unknown

  const gridCols = metrics.length <= 2 ? 'grid-cols-2' : metrics.length <= 4 ? 'grid-cols-2 sm:grid-cols-2' : 'grid-cols-3'

  return (
    <div className="border border-border bg-card rounded-lg p-4">
      {/* Header: title + status badge */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-text">{title}</span>
        <span className={cn('inline-flex items-center rounded px-2 py-0.5 text-xs border', cfg.color, cfg.bg, cfg.border)}>
          {cfg.label}
        </span>
      </div>

      {/* Metrics grid */}
      {metrics.length > 0 && (
        <div className={cn('grid gap-3', gridCols)}>
          {metrics.map((m, i) => (
            <div key={i} className="flex flex-col">
              <span className="text-xs text-text3 mb-0.5">{m.label}</span>
              <div className="flex items-baseline gap-1">
                <span className="text-base font-semibold text-text tabular-nums">
                  {m.value}
                </span>
                {m.unit && <span className="text-xs text-text3">{m.unit}</span>}
                <TrendIcon trend={m.trend} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Details */}
      {details && (
        <p className="mt-3 pt-3 border-t border-border text-xs text-text2 leading-relaxed">
          {details}
        </p>
      )}
    </div>
  )
}
