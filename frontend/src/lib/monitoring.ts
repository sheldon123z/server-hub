import type { AlertData, GpuProcess, MetricsData } from '@/hooks/useWebSocket'
import { ensureArray, ensureRecord } from '@/lib/utils'

const MB = 1024 * 1024

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function toString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

export function normalizeTimestamp(value: unknown): string {
  if (typeof value === 'string') {
    const parsed = new Date(value)
    if (!Number.isNaN(parsed.getTime())) return parsed.toISOString()
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    const ms = value < 1e12 ? value * 1000 : value
    const parsed = new Date(ms)
    if (!Number.isNaN(parsed.getTime())) return parsed.toISOString()
  }
  return new Date().toISOString()
}

function parseUptimeSeconds(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return 0

  const parts = [...value.matchAll(/(\d+)\s*([dhms])/g)]
  if (parts.length === 0) return toNumber(value, 0)

  let seconds = 0
  for (const [, rawNumber, unit] of parts) {
    const amount = Number(rawNumber)
    if (!Number.isFinite(amount)) continue
    if (unit === 'd') seconds += amount * 86400
    if (unit === 'h') seconds += amount * 3600
    if (unit === 'm') seconds += amount * 60
    if (unit === 's') seconds += amount
  }
  return seconds
}

export function normalizeGpuProcesses(value: unknown): GpuProcess[] {
  return ensureArray<Record<string, unknown>>(value).map((item) => ({
    pid: toNumber(item.pid),
    name: toString(item.name, 'unknown'),
    gpu_memory_usage:
      typeof item.gpu_memory_usage === 'string'
        ? item.gpu_memory_usage
        : toNumber(item.gpu_memory_usage ?? item.gpu_mem_mb) * MB,
  }))
}

export function normalizeDockerContainers(
  value: unknown,
): Array<{ name: string; state: string; image: string; status: string }> {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : record.containers
  return ensureArray<Record<string, unknown>>(items).map((item) => ({
    name: toString(item.name, toString(item.Names, 'unknown')),
    state: toString(item.state, toString(item.State, 'unknown')),
    image: toString(item.image, toString(item.Image, '')),
    status: toString(item.status, toString(item.Status, '')),
  }))
}

export function normalizeTopProcesses(
  value: unknown,
): Array<{ pid: number; name: string; user: string; cpu_percent: number; mem_rss_mb: number; cmdline: string }> {
  return ensureArray<Record<string, unknown>>(value).map((item) => ({
    pid: toNumber(item.pid),
    name: toString(item.name, 'unknown'),
    user: toString(item.user, toString(item.username, '')),
    cpu_percent: toNumber(item.cpu_percent),
    mem_rss_mb: toNumber(item.mem_rss_mb),
    cmdline: toString(item.cmdline, toString(item.cmd, '')),
  }))
}

export function normalizeAlertData(value: unknown): AlertData | null {
  const record = ensureRecord(value)
  if (Object.keys(record).length === 0) return null

  const level = toString(record.level, toString(record.severity, 'info')) as AlertData['level']
  return {
    id: toString(record.id),
    level: level === 'critical' || level === 'warning' ? level : 'info',
    title: toString(record.title, toString(record.rule_name, '告警')),
    message: toString(record.message, ''),
    timestamp: normalizeTimestamp(record.timestamp ?? record.created_at),
  }
}

export function normalizeMetricsSnapshot(value: unknown): MetricsData | null {
  const record = ensureRecord(value)
  if (Object.keys(record).length === 0) return null

  const systemInfo = ensureRecord(record.system_info)
  const cpu = ensureRecord(record.cpu)
  const memory = ensureRecord(record.memory)
  const ram = ensureRecord(memory.ram)
  const swap = ensureRecord(memory.swap ?? record.swap)
  const rawDisk = record.disk
  const diskItems = Array.isArray(rawDisk) ? rawDisk : ensureRecord(rawDisk).partitions
  const network = ensureRecord(record.network)
  const networkTotals = ensureRecord(network.totals)
  const load = ensureRecord(cpu.load_avg ?? record.load)
  const gpu = ensureRecord(record.gpu)
  const gpuProcesses = normalizeGpuProcesses(gpu.processes)

  const utilization = toNumber(gpu.utilization ?? gpu.util)
  const memoryUsed = toNumber(gpu.memory_used ?? gpu.mem_used) * MB
  const memoryTotal = toNumber(gpu.memory_total ?? gpu.mem_total) * MB
  const temperature = toNumber(gpu.temperature ?? gpu.temp)
  const hasGpu = Boolean(gpu.available) || utilization > 0 || memoryTotal > 0 || gpuProcesses.length > 0

  return {
    cpu: {
      overall_percent: toNumber(cpu.overall_percent),
      count: toNumber(cpu.count),
      per_cpu: ensureArray<number>(cpu.per_cpu ?? cpu.per_cpu_percent).map((item) => toNumber(item)),
      model: toString(cpu.model, toString(systemInfo.cpu_model)),
    },
    memory: {
      total: toNumber(ram.total),
      used: toNumber(ram.used),
      available: toNumber(ram.available),
      percent: toNumber(ram.percent),
    },
    swap: {
      total: toNumber(swap.total),
      used: toNumber(swap.used),
      percent: toNumber(swap.percent),
    },
    disk: {
      partitions: ensureArray<Record<string, unknown>>(diskItems).map((item) => ({
        mountpoint: toString(item.mountpoint, '/'),
        total: toNumber(item.total),
        used: toNumber(item.used),
        percent: toNumber(item.percent),
      })),
    },
    network: {
      bytes_sent: toNumber(network.bytes_sent ?? networkTotals.bytes_sent ?? networkTotals.bytes_sent_rate),
      bytes_recv: toNumber(network.bytes_recv ?? networkTotals.bytes_recv ?? networkTotals.bytes_recv_rate),
    },
    load: {
      '1min': toNumber(load['1min']),
      '5min': toNumber(load['5min']),
      '15min': toNumber(load['15min']),
    },
    gpu: hasGpu
      ? {
          name: toString(gpu.name, 'GPU'),
          utilization,
          memory_used: memoryUsed,
          memory_total: memoryTotal,
          temperature,
          processes: gpuProcesses,
        }
      : undefined,
    uptime: parseUptimeSeconds(record.uptime),
    hostname: toString(record.hostname, toString(systemInfo.hostname, '--')),
    timestamp: normalizeTimestamp(record.timestamp),
    os: toString(record.os, toString(systemInfo.os)),
    kernel: toString(record.kernel, toString(systemInfo.kernel)),
    platform: toString(record.platform, toString(systemInfo.os)),
  }
}
