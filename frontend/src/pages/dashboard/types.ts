import type { LucideIcon } from 'lucide-react'

export interface AlertSummary {
  active_rules: number
  critical: number
  warning: number
  info: number
  total_24h: number
}

export interface RecentAlert {
  id: number
  rule_name: string
  level: string
  message: string
  created_at: string
}

export type CardId = 'host' | 'cpu' | 'memory' | 'swap' | 'disk' | 'network' | 'diskio' | 'docker' | 'gpu'

export interface CardConfig {
  id: CardId
  label: string
  icon: LucideIcon
}

export type HistoryPeriod = '1' | '6' | '24' | '72'

export interface HistoryPoint {
  timestamp: string
  value: {
    cpu?: { overall_percent: number }
    memory?: { percent: number }
    swap?: { percent: number }
    gpu?: { utilization: number }
    network?: { bytes_recv: number; bytes_sent: number }
    disk?: { partitions: Array<{ mountpoint: string; total?: number; used?: number; percent: number }> }
  }
}
