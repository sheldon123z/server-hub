import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

export function toString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i]
}

export function formatPercent(value: number): string {
  return Math.round(value) + '%'
}

export function barColor(percent: number): string {
  if (percent >= 85) return 'var(--color-red)'
  if (percent >= 60) return 'var(--color-yellow)'
  return 'var(--color-green)'
}

export function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}

/**
 * Coerce unknown API responses into a typed array.
 * - If `value` is already an array, returns it directly.
 * - If `value` is an object with an `items` or `data` array property,
 *   returns that nested array (auto-unwraps common API wrapper shapes).
 * - Otherwise returns `[]`.
 */
export function ensureArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[]
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    if (Array.isArray(record.items)) return record.items as T[]
    if (Array.isArray(record.data)) return record.data as T[]
  }
  return []
}

export function ensureRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return {}
}

/** 从未知错误中提取用户友好的错误消息，兼容 Axios error 格式 */
export function getErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null) {
    const e = err as { response?: { data?: { detail?: string } }; message?: string }
    if (e.response?.data?.detail) return e.response.data.detail
    if (e.message) return e.message
  }
  return fallback
}
