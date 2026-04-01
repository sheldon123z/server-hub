import { describe, it, expect } from 'vitest'
import type { MetricsData } from '@/hooks/useWebSocket'
import type { CardId } from '@/pages/dashboard/types'
import {
  statusColor,
  statusHex,
  formatUptime,
  formatRate,
  getCardValue,
  getCardSub,
  getCardPercent,
  getSparklineData,
} from '@/pages/dashboard/utils'

// ---------------------------------------------------------------------------
// Helper: build a complete MetricsData object
// ---------------------------------------------------------------------------
function makeMetrics(overrides: Partial<MetricsData> = {}): MetricsData {
  return {
    cpu: { overall_percent: 45.2, count: 8 },
    memory: { total: 64 * 1024 ** 3, used: 32 * 1024 ** 3, available: 32 * 1024 ** 3, percent: 50 },
    swap: { total: 8 * 1024 ** 3, used: 1 * 1024 ** 3, percent: 12.5 },
    disk: {
      partitions: [
        { mountpoint: '/', total: 500 * 1024 ** 3, used: 250 * 1024 ** 3, percent: 50 },
        { mountpoint: '/mnt/data', total: 1000 * 1024 ** 3, used: 600 * 1024 ** 3, percent: 60 },
      ],
    },
    network: { bytes_sent: 1024 * 1024 * 100, bytes_recv: 1024 * 1024 * 200 },
    load: { '1min': 2.5, '5min': 2.0, '15min': 1.8 },
    gpu: {
      name: 'NVIDIA A800',
      utilization: 75,
      memory_used: 40 * 1024 ** 3,
      memory_total: 80 * 1024 ** 3,
      temperature: 65,
    },
    uptime: 86400 + 7200 + 1800, // 1d 2h 30m
    hostname: 'test-server',
    timestamp: new Date().toISOString(),
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// statusColor
// ---------------------------------------------------------------------------
describe('statusColor', () => {
  it('returns green for < 30', () => {
    expect(statusColor(0)).toBe('text-green')
    expect(statusColor(29)).toBe('text-green')
  })

  it('returns accent for 30-59', () => {
    expect(statusColor(30)).toBe('text-accent')
    expect(statusColor(59)).toBe('text-accent')
  })

  it('returns yellow for 60-84', () => {
    expect(statusColor(60)).toBe('text-yellow')
    expect(statusColor(84)).toBe('text-yellow')
  })

  it('returns red for >= 85', () => {
    expect(statusColor(85)).toBe('text-red')
    expect(statusColor(100)).toBe('text-red')
  })

  it('returns red for values > 100', () => {
    expect(statusColor(200)).toBe('text-red')
  })

  it('returns green for negative values', () => {
    expect(statusColor(-5)).toBe('text-green')
  })
})

// ---------------------------------------------------------------------------
// statusHex
// ---------------------------------------------------------------------------
describe('statusHex', () => {
  it('returns green hex for < 30', () => {
    expect(statusHex(0)).toBe('#4ade80')
    expect(statusHex(29)).toBe('#4ade80')
  })

  it('returns accent/blue hex for 30-59', () => {
    expect(statusHex(30)).toBe('#38bdf8')
    expect(statusHex(59)).toBe('#38bdf8')
  })

  it('returns yellow hex for 60-84', () => {
    expect(statusHex(60)).toBe('#fbbf24')
    expect(statusHex(84)).toBe('#fbbf24')
  })

  it('returns red hex for >= 85', () => {
    expect(statusHex(85)).toBe('#f87171')
    expect(statusHex(100)).toBe('#f87171')
  })

  it('returns red hex for values > 100', () => {
    expect(statusHex(150)).toBe('#f87171')
  })

  it('returns green hex for negative values', () => {
    expect(statusHex(-1)).toBe('#4ade80')
  })
})

// ---------------------------------------------------------------------------
// formatUptime
// ---------------------------------------------------------------------------
describe('formatUptime', () => {
  it('returns "0m" for 0 seconds', () => {
    expect(formatUptime(0)).toBe('0m')
  })

  it('returns "0m" for 59 seconds (< 1 minute rounds down)', () => {
    expect(formatUptime(59)).toBe('0m')
  })

  it('returns "1h 0m" for 3600 seconds (1 hour)', () => {
    expect(formatUptime(3600)).toBe('1h 0m')
  })

  it('returns "1d 0h 0m" for 86400 seconds (1 day)', () => {
    expect(formatUptime(86400)).toBe('1d 0h 0m')
  })

  it('formats 1d 2h 30m correctly', () => {
    const seconds = 86400 + 7200 + 1800
    expect(formatUptime(seconds)).toBe('1d 2h 30m')
  })

  it('formats 2h 15m correctly (no days)', () => {
    const seconds = 7200 + 900
    expect(formatUptime(seconds)).toBe('2h 15m')
  })

  it('formats 45m correctly (only minutes)', () => {
    expect(formatUptime(2700)).toBe('45m')
  })

  it('formats multi-day uptime', () => {
    const seconds = 5 * 86400 + 3 * 3600 + 45 * 60
    expect(formatUptime(seconds)).toBe('5d 3h 45m')
  })
})

// ---------------------------------------------------------------------------
// formatRate
// ---------------------------------------------------------------------------
describe('formatRate', () => {
  it('computes positive rate correctly', () => {
    // 1000 bytes increase over 1000ms = 1000 B/s
    const result = formatRate(2000, 1000, 1000)
    expect(result).toContain('B/s')
    expect(result).not.toBe('0 B/s')
  })

  it('returns 0 rate when curr == prev', () => {
    expect(formatRate(1000, 1000, 1000)).toBe('0 B/s')
  })

  it('clamps negative rate to 0', () => {
    expect(formatRate(500, 1000, 1000)).toBe('0 B/s')
  })

  it('returns "0 B/s" for zero interval', () => {
    expect(formatRate(2000, 1000, 0)).toBe('0 B/s')
  })

  it('returns "0 B/s" for negative interval', () => {
    expect(formatRate(2000, 1000, -100)).toBe('0 B/s')
  })

  it('formats larger rates with appropriate units', () => {
    // 10 MB increase over 1 second
    const result = formatRate(10 * 1024 * 1024, 0, 1000)
    expect(result).toContain('MB/s')
  })
})

// ---------------------------------------------------------------------------
// getCardValue
// ---------------------------------------------------------------------------
describe('getCardValue', () => {
  const m = makeMetrics()

  it('returns "--" for null metrics', () => {
    expect(getCardValue('cpu', null, null)).toBe('--')
  })

  it('returns hostname for "host" card', () => {
    expect(getCardValue('host', m, null)).toBe('test-server')
  })

  it('returns formatted CPU percent', () => {
    expect(getCardValue('cpu', m, null)).toBe('45%')
  })

  it('returns formatted memory percent', () => {
    expect(getCardValue('memory', m, null)).toBe('50%')
  })

  it('returns formatted swap percent', () => {
    expect(getCardValue('swap', m, null)).toBe('13%')
  })

  it('returns formatted disk percent for root partition', () => {
    expect(getCardValue('disk', m, null)).toBe('50%')
  })

  it('returns formatted network bytes_recv', () => {
    const val = getCardValue('network', m, null)
    expect(val).toContain('MB')
  })

  it('returns "--" for diskio (no data)', () => {
    expect(getCardValue('diskio', m, null)).toBe('--')
  })

  it('returns docker count when provided', () => {
    expect(getCardValue('docker', m, 5)).toBe('5 容器')
  })

  it('returns "--" for docker when count is null', () => {
    expect(getCardValue('docker', m, null)).toBe('--')
  })

  it('returns GPU utilization percent', () => {
    expect(getCardValue('gpu', m, null)).toBe('75%')
  })

  it('returns "N/A" for gpu when no gpu data', () => {
    const noGpu = makeMetrics({ gpu: undefined })
    expect(getCardValue('gpu', noGpu, null)).toBe('N/A')
  })

  it('returns "N/A" for swap when total is 0', () => {
    const noSwap = makeMetrics({ swap: { total: 0, used: 0, percent: 0 } })
    expect(getCardValue('swap', noSwap, null)).toBe('N/A')
  })
})

// ---------------------------------------------------------------------------
// getCardSub
// ---------------------------------------------------------------------------
describe('getCardSub', () => {
  const m = makeMetrics()

  it('returns empty string for null metrics', () => {
    expect(getCardSub('cpu', null)).toBe('')
  })

  it('returns uptime string for host', () => {
    const sub = getCardSub('host', m)
    expect(sub).toContain('运行')
    expect(sub).toContain('1d')
  })

  it('returns cpu count and load for cpu', () => {
    const sub = getCardSub('cpu', m)
    expect(sub).toContain('8 核')
    expect(sub).toContain('2.5')
  })

  it('returns memory used/total for memory', () => {
    const sub = getCardSub('memory', m)
    expect(sub).toContain('GB')
  })

  it('returns swap used/total when swap is enabled', () => {
    const sub = getCardSub('swap', m)
    expect(sub).toContain('GB')
  })

  it('returns "未启用" when swap total is 0', () => {
    const noSwap = makeMetrics({ swap: { total: 0, used: 0, percent: 0 } })
    expect(getCardSub('swap', noSwap)).toBe('未启用')
  })

  it('returns disk used/total for root partition', () => {
    const sub = getCardSub('disk', m)
    expect(sub).toContain('GB')
  })

  it('returns sent bytes for network', () => {
    const sub = getCardSub('network', m)
    expect(sub).toContain('发')
  })

  it('returns "暂无数据" for diskio', () => {
    expect(getCardSub('diskio', m)).toBe('暂无数据')
  })

  it('returns empty string for docker', () => {
    expect(getCardSub('docker', m)).toBe('')
  })

  it('returns GPU temp and VRAM', () => {
    const sub = getCardSub('gpu', m)
    expect(sub).toContain('65')
    expect(sub).toContain('VRAM')
  })

  it('returns "未检测到" when no gpu', () => {
    const noGpu = makeMetrics({ gpu: undefined })
    expect(getCardSub('gpu', noGpu)).toBe('未检测到')
  })
})

// ---------------------------------------------------------------------------
// getCardPercent
// ---------------------------------------------------------------------------
describe('getCardPercent', () => {
  const m = makeMetrics()

  it('returns 0 for null metrics', () => {
    expect(getCardPercent('cpu', null)).toBe(0)
  })

  it('returns cpu overall_percent', () => {
    expect(getCardPercent('cpu', m)).toBe(45.2)
  })

  it('returns memory percent', () => {
    expect(getCardPercent('memory', m)).toBe(50)
  })

  it('returns swap percent', () => {
    expect(getCardPercent('swap', m)).toBe(12.5)
  })

  it('returns root disk partition percent', () => {
    expect(getCardPercent('disk', m)).toBe(50)
  })

  it('returns gpu utilization', () => {
    expect(getCardPercent('gpu', m)).toBe(75)
  })

  it('returns -1 for non-percent card ids', () => {
    const nonPercentIds: CardId[] = ['host', 'network', 'diskio', 'docker']
    for (const id of nonPercentIds) {
      expect(getCardPercent(id, m)).toBe(-1)
    }
  })

  it('returns 0 for gpu when no gpu data', () => {
    const noGpu = makeMetrics({ gpu: undefined })
    expect(getCardPercent('gpu', noGpu)).toBe(0)
  })

  it('returns 0 for disk when no partitions', () => {
    const noDisk = makeMetrics({ disk: { partitions: [] } })
    expect(getCardPercent('disk', noDisk)).toBe(0)
  })

  it('falls back to first partition when no root mountpoint', () => {
    const noRoot = makeMetrics({
      disk: {
        partitions: [
          { mountpoint: '/mnt/data', total: 1000, used: 600, percent: 60 },
        ],
      },
    })
    expect(getCardPercent('disk', noRoot)).toBe(60)
  })
})

// ---------------------------------------------------------------------------
// getSparklineData
// ---------------------------------------------------------------------------
describe('getSparklineData', () => {
  const m = makeMetrics()
  const history: MetricsData[] = [m, m, m]

  it('returns empty array for empty history', () => {
    expect(getSparklineData('cpu', [])).toEqual([])
  })

  it('extracts cpu values from history', () => {
    const result = getSparklineData('cpu', history)
    expect(result).toEqual([45.2, 45.2, 45.2])
  })

  it('extracts memory values from history', () => {
    const result = getSparklineData('memory', history)
    expect(result).toEqual([50, 50, 50])
  })

  it('extracts swap values from history', () => {
    const result = getSparklineData('swap', history)
    expect(result).toEqual([12.5, 12.5, 12.5])
  })

  it('extracts gpu values from history', () => {
    const result = getSparklineData('gpu', history)
    expect(result).toEqual([75, 75, 75])
  })

  it('extracts disk root partition values from history', () => {
    const result = getSparklineData('disk', history)
    expect(result).toEqual([50, 50, 50])
  })

  it('computes host load-based values from history', () => {
    // load 1min = 2.5, cpu count = 8 -> 2.5/8 * 100 = 31.25
    const result = getSparklineData('host', history)
    expect(result).toEqual([31.25, 31.25, 31.25])
  })

  it('computes network rate-based values from history', () => {
    // bytes_recv = 200 MB -> min(100, 200MB/100MB * 100) = 100 (clamped)
    const result = getSparklineData('network', history)
    expect(result).toEqual([100, 100, 100])
  })

  it('returns 0 for unknown card ids', () => {
    const result = getSparklineData('diskio', history)
    expect(result).toEqual([0, 0, 0])
  })

  it('handles mixed history with varying values', () => {
    const h: MetricsData[] = [
      makeMetrics({ cpu: { overall_percent: 10, count: 4 } }),
      makeMetrics({ cpu: { overall_percent: 50, count: 4 } }),
      makeMetrics({ cpu: { overall_percent: 90, count: 4 } }),
    ]
    const result = getSparklineData('cpu', h)
    expect(result).toEqual([10, 50, 90])
  })

  it('handles history entries with missing optional fields gracefully', () => {
    const partial: MetricsData[] = [
      makeMetrics({ gpu: undefined }),
      makeMetrics({ gpu: { name: 'GPU', utilization: 30, memory_used: 0, memory_total: 0, temperature: 40 } }),
    ]
    // gpu card: undefined -> 0, defined -> 30
    const result = getSparklineData('gpu', partial)
    expect(result).toEqual([0, 30])
  })

  it('returns 0 for disk sparkline when no partitions', () => {
    const noDisk = makeMetrics({ disk: { partitions: [] } })
    const result = getSparklineData('disk', [noDisk])
    expect(result).toEqual([0])
  })
})
