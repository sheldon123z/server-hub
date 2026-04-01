import { describe, it, expect } from 'vitest'
import {
  normalizeTimestamp,
  normalizeMetricsSnapshot,
  normalizeDockerContainers,
  normalizeTopProcesses,
  normalizeGpuProcesses,
  normalizeAlertData,
} from '@/lib/monitoring'

// ---------------------------------------------------------------------------
// normalizeTimestamp
// ---------------------------------------------------------------------------
describe('normalizeTimestamp', () => {
  it('parses ISO string', () => {
    const result = normalizeTimestamp('2025-06-15T12:00:00Z')
    expect(result).toBe('2025-06-15T12:00:00.000Z')
  })

  it('parses Unix seconds (small number < 1e12)', () => {
    // 1718448000 = 2024-06-15T08:00:00Z
    const result = normalizeTimestamp(1718448000)
    expect(new Date(result).getTime()).toBe(1718448000_000)
  })

  it('parses Unix milliseconds (large number >= 1e12)', () => {
    const ms = 1718448000000
    const result = normalizeTimestamp(ms)
    expect(new Date(result).getTime()).toBe(ms)
  })

  it('returns current-time ISO for null', () => {
    const result = normalizeTimestamp(null)
    expect(typeof result).toBe('string')
    // Should be a valid ISO string close to now
    const diff = Date.now() - new Date(result).getTime()
    expect(Math.abs(diff)).toBeLessThan(5000)
  })

  it('returns current-time ISO for undefined', () => {
    const result = normalizeTimestamp(undefined)
    const diff = Date.now() - new Date(result).getTime()
    expect(Math.abs(diff)).toBeLessThan(5000)
  })

  it('returns current-time ISO for empty string', () => {
    const result = normalizeTimestamp('')
    const diff = Date.now() - new Date(result).getTime()
    expect(Math.abs(diff)).toBeLessThan(5000)
  })

  it('returns current-time ISO for invalid string', () => {
    const result = normalizeTimestamp('not-a-date')
    const diff = Date.now() - new Date(result).getTime()
    expect(Math.abs(diff)).toBeLessThan(5000)
  })
})

// ---------------------------------------------------------------------------
// normalizeMetricsSnapshot
// ---------------------------------------------------------------------------
describe('normalizeMetricsSnapshot', () => {
  it('returns null for null input', () => {
    expect(normalizeMetricsSnapshot(null)).toBeNull()
  })

  it('returns null for undefined input', () => {
    expect(normalizeMetricsSnapshot(undefined)).toBeNull()
  })

  it('returns null for empty object', () => {
    expect(normalizeMetricsSnapshot({})).toBeNull()
  })

  it('normalizes a flat metrics object (agent fast format)', () => {
    const data = {
      cpu_percent: 45.2,
      memory_percent: 62.1,
      memory_total: 67_108_864,  // 64 GB in KB
      memory_used: 41_568_256,
      timestamp: 1718448000,
      hostname: 'test-host',
      uptime: 86400,
    }
    const result = normalizeMetricsSnapshot(data)
    expect(result).not.toBeNull()
    expect(result!.cpu.overall_percent).toBe(45.2)
    expect(result!.memory.percent).toBe(62.1)
    expect(result!.hostname).toBe('test-host')
    expect(result!.uptime).toBe(86400)
    // normalizeTimestamp treats Unix seconds as ms * 1000, producing a Date via new Date(ms)
    // which is timezone-agnostic; just verify it produced a valid ISO string
    expect(typeof result!.timestamp).toBe('string')
    expect(result!.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('normalizes a nested metrics object (hub format)', () => {
    const data = {
      cpu: {
        overall_percent: 30,
        count: 8,
        per_cpu: [30, 25, 35, 28, 32, 29, 31, 27],
        model: 'Intel Xeon',
      },
      memory: {
        ram: { total: 67108864, used: 33554432, available: 33554432, percent: 50 },
        swap: { total: 8388608, used: 0, percent: 0 },
      },
      disk: {
        partitions: [
          { mountpoint: '/', total: 1048576, used: 524288, percent: 50 },
        ],
      },
      network: { bytes_sent: 1000, bytes_recv: 2000 },
      load_avg: [1.5, 1.2, 0.8],
      gpu: { available: false },
      timestamp: '2025-06-15T12:00:00Z',
      hostname: 'hub-host',
      uptime: '2d 3h 15m',
    }
    const result = normalizeMetricsSnapshot(data)
    expect(result).not.toBeNull()
    expect(result!.cpu.overall_percent).toBe(30)
    expect(result!.cpu.count).toBe(8)
    expect(result!.cpu.model).toBe('Intel Xeon')
    expect(result!.cpu.per_cpu).toEqual([30, 25, 35, 28, 32, 29, 31, 27])
    expect(result!.memory.percent).toBe(50)
    expect(result!.swap.percent).toBe(0)
    expect(result!.disk.partitions).toHaveLength(1)
    expect(result!.disk.partitions[0].mountpoint).toBe('/')
    expect(result!.network.bytes_sent).toBe(1000)
    expect(result!.load['1min']).toBe(1.5)
    expect(result!.uptime).toBe(2 * 86400 + 3 * 3600 + 15 * 60)
    expect(result!.gpu).toBeUndefined()
  })

  it('includes GPU data when present', () => {
    const data = {
      cpu: { overall_percent: 10 },
      gpu: {
        available: true,
        name: 'NVIDIA A800',
        utilization: 75,
        memory_used: 40960,
        memory_total: 81920,
        temperature: 65,
        processes: [],
      },
      timestamp: 1718448000,
    }
    const result = normalizeMetricsSnapshot(data)
    expect(result).not.toBeNull()
    expect(result!.gpu).toBeDefined()
    expect(result!.gpu!.name).toBe('NVIDIA A800')
    expect(result!.gpu!.utilization).toBe(75)
    expect(result!.gpu!.temperature).toBe(65)
  })

  it('handles partial data gracefully', () => {
    const data = { cpu_percent: 0, hostname: 'partial' }
    const result = normalizeMetricsSnapshot(data)
    expect(result).not.toBeNull()
    expect(result!.cpu.overall_percent).toBe(0)
    expect(result!.hostname).toBe('partial')
    expect(result!.memory.total).toBe(0)
    expect(result!.disk.partitions).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// normalizeDockerContainers
// ---------------------------------------------------------------------------
describe('normalizeDockerContainers', () => {
  it('normalizes an array of containers', () => {
    const data = [
      { name: 'web', state: 'running', image: 'nginx', status: 'Up 2 hours' },
      { name: 'db', state: 'exited', image: 'postgres', status: 'Exited (0) 1h ago' },
    ]
    const result = normalizeDockerContainers(data)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({ name: 'web', state: 'running', image: 'nginx', status: 'Up 2 hours' })
    expect(result[1]).toEqual({ name: 'db', state: 'exited', image: 'postgres', status: 'Exited (0) 1h ago' })
  })

  it('returns empty array for a plain object without containers key', () => {
    // A single container object without a `containers` wrapper is treated as a record
    // with no `containers` property, so it yields []
    const data = { name: 'redis', state: 'running', image: 'redis:7', status: 'Up 5 min' }
    const result = normalizeDockerContainers(data)
    expect(result).toEqual([])
  })

  it('unwraps { containers: [...] } wrapper', () => {
    const data = {
      containers: [
        { name: 'api', state: 'running', image: 'api:v1', status: 'Up' },
      ],
    }
    const result = normalizeDockerContainers(data)
    expect(result).toHaveLength(1)
    expect(result[0].name).toBe('api')
  })

  it('returns empty array for null', () => {
    expect(normalizeDockerContainers(null)).toEqual([])
  })

  it('returns empty array for undefined', () => {
    expect(normalizeDockerContainers(undefined)).toEqual([])
  })

  it('falls back to PascalCase field names', () => {
    const data = [
      { Names: 'c1', State: 'running', Image: 'img', Status: 'Up' },
    ]
    const result = normalizeDockerContainers(data)
    expect(result[0]).toEqual({ name: 'c1', state: 'running', image: 'img', status: 'Up' })
  })
})

// ---------------------------------------------------------------------------
// normalizeTopProcesses
// ---------------------------------------------------------------------------
describe('normalizeTopProcesses', () => {
  it('normalizes valid process data', () => {
    const data = [
      { pid: 1234, name: 'python', user: 'root', cpu_percent: 45.2, mem_rss_mb: 512, cmdline: '/usr/bin/python3' },
    ]
    const result = normalizeTopProcesses(data)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      pid: 1234,
      name: 'python',
      user: 'root',
      cpu_percent: 45.2,
      mem_rss_mb: 512,
      cmdline: '/usr/bin/python3',
    })
  })

  it('returns empty array for null', () => {
    expect(normalizeTopProcesses(null)).toEqual([])
  })

  it('returns empty array for undefined', () => {
    expect(normalizeTopProcesses(undefined)).toEqual([])
  })

  it('handles partial process data with defaults', () => {
    const data = [{ pid: 99 }]
    const result = normalizeTopProcesses(data)
    expect(result).toHaveLength(1)
    expect(result[0].pid).toBe(99)
    expect(result[0].name).toBe('unknown')
    expect(result[0].user).toBe('')
    expect(result[0].cpu_percent).toBe(0)
    expect(result[0].mem_rss_mb).toBe(0)
    expect(result[0].cmdline).toBe('')
  })

  it('falls back to username/cmd aliases', () => {
    const data = [{ pid: 1, username: 'admin', cmd: '/bin/bash' }]
    const result = normalizeTopProcesses(data)
    expect(result[0].user).toBe('admin')
    expect(result[0].cmdline).toBe('/bin/bash')
  })
})

// ---------------------------------------------------------------------------
// normalizeGpuProcesses
// ---------------------------------------------------------------------------
describe('normalizeGpuProcesses', () => {
  it('normalizes valid GPU process data', () => {
    const data = [
      { pid: 100, name: 'python', gpu_memory_usage: 1024 },
    ]
    const result = normalizeGpuProcesses(data)
    expect(result).toHaveLength(1)
    expect(result[0].pid).toBe(100)
    expect(result[0].name).toBe('python')
    // gpu_memory_usage is multiplied by MB (1024*1024) when numeric
    expect(result[0].gpu_memory_usage).toBe(1024 * 1024 * 1024)
  })

  it('preserves string gpu_memory_usage as-is', () => {
    const data = [
      { pid: 200, name: 'train', gpu_memory_usage: '2048 MiB' },
    ]
    const result = normalizeGpuProcesses(data)
    expect(result[0].gpu_memory_usage).toBe('2048 MiB')
  })

  it('returns empty array for null', () => {
    expect(normalizeGpuProcesses(null)).toEqual([])
  })

  it('returns empty array for undefined', () => {
    expect(normalizeGpuProcesses(undefined)).toEqual([])
  })

  it('uses gpu_mem_mb as fallback for gpu_memory_usage', () => {
    const data = [
      { pid: 300, name: 'jupyter', gpu_mem_mb: 512 },
    ]
    const result = normalizeGpuProcesses(data)
    expect(result[0].gpu_memory_usage).toBe(512 * 1024 * 1024)
  })

  it('defaults name to "unknown" when missing', () => {
    const data = [{ pid: 1 }]
    const result = normalizeGpuProcesses(data)
    expect(result[0].name).toBe('unknown')
  })
})

// ---------------------------------------------------------------------------
// normalizeAlertData
// ---------------------------------------------------------------------------
describe('normalizeAlertData', () => {
  it('returns null for null input', () => {
    expect(normalizeAlertData(null)).toBeNull()
  })

  it('returns null for empty object', () => {
    expect(normalizeAlertData({})).toBeNull()
  })

  it('normalizes a valid alert with all fields', () => {
    const data = {
      id: 'alert-1',
      level: 'critical',
      title: 'High CPU',
      message: 'CPU is at 95%',
      timestamp: '2025-06-15T12:00:00Z',
    }
    const result = normalizeAlertData(data)
    expect(result).not.toBeNull()
    expect(result!.id).toBe('alert-1')
    expect(result!.level).toBe('critical')
    expect(result!.title).toBe('High CPU')
    expect(result!.message).toBe('CPU is at 95%')
    expect(result!.timestamp).toBe('2025-06-15T12:00:00.000Z')
  })

  it('maps unknown level to "info"', () => {
    const data = { level: 'debug', title: 'Test' }
    const result = normalizeAlertData(data)
    expect(result!.level).toBe('info')
  })

  it('falls back to severity field for level', () => {
    const data = { severity: 'warning', title: 'Swap' }
    const result = normalizeAlertData(data)
    expect(result!.level).toBe('warning')
  })

  it('falls back to rule_name for title', () => {
    const data = { level: 'info', rule_name: 'Swap Alert' }
    const result = normalizeAlertData(data)
    expect(result!.title).toBe('Swap Alert')
  })
})
