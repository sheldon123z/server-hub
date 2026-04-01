import { describe, it, expect } from 'vitest'
import {
  cn,
  formatBytes,
  formatPercent,
  ensureArray,
  ensureRecord,
  getErrorMessage,
  toNumber,
  toString,
  barColor,
  formatDate,
} from '@/lib/utils'

// ---------------------------------------------------------------------------
// cn
// ---------------------------------------------------------------------------
describe('cn', () => {
  it('merges multiple class strings', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1')
  })

  it('deduplicates conflicting tailwind classes', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })

  it('handles conditional values (false / undefined / null)', () => {
    expect(cn('base', false && 'hidden', undefined, null)).toBe('base')
  })

  it('returns empty string when no classes provided', () => {
    expect(cn()).toBe('')
  })
})

// ---------------------------------------------------------------------------
// formatBytes
// ---------------------------------------------------------------------------
describe('formatBytes', () => {
  it('returns "0 B" for 0', () => {
    expect(formatBytes(0)).toBe('0 B')
  })

  it('formats bytes', () => {
    expect(formatBytes(512)).toBe('512.0 B')
  })

  it('formats kilobytes', () => {
    expect(formatBytes(1024)).toBe('1.0 KB')
  })

  it('formats megabytes', () => {
    expect(formatBytes(1048576)).toBe('1.0 MB')
  })

  it('formats gigabytes', () => {
    expect(formatBytes(1073741824)).toBe('1.0 GB')
  })

  it('formats terabytes', () => {
    expect(formatBytes(1099511627776)).toBe('1.0 TB')
  })

  it('returns "0 B" for negative values', () => {
    expect(formatBytes(-100)).toBe('0 B')
  })

  it('returns "0 B" for NaN', () => {
    expect(formatBytes(NaN)).toBe('0 B')
  })

  it('returns "0 B" for Infinity', () => {
    expect(formatBytes(Infinity)).toBe('0 B')
  })
})

// ---------------------------------------------------------------------------
// formatPercent
// ---------------------------------------------------------------------------
describe('formatPercent', () => {
  it('formats 0', () => {
    expect(formatPercent(0)).toBe('0%')
  })

  it('rounds fractional values', () => {
    expect(formatPercent(50.123)).toBe('50%')
  })

  it('formats 100', () => {
    expect(formatPercent(100)).toBe('100%')
  })

  it('rounds 99.9', () => {
    expect(formatPercent(99.9)).toBe('100%')
  })

  it('handles negative values', () => {
    expect(formatPercent(-5.6)).toBe('-6%')
  })
})

// ---------------------------------------------------------------------------
// ensureArray
// ---------------------------------------------------------------------------
describe('ensureArray', () => {
  it('returns array directly when value is an array', () => {
    expect(ensureArray([1, 2, 3])).toEqual([1, 2, 3])
  })

  it('unwraps { items: [...] } wrapper', () => {
    expect(ensureArray({ items: ['a', 'b'] })).toEqual(['a', 'b'])
  })

  it('unwraps { data: [...] } wrapper', () => {
    expect(ensureArray({ data: [10, 20] })).toEqual([10, 20])
  })

  it('returns empty array for null', () => {
    expect(ensureArray(null)).toEqual([])
  })

  it('returns empty array for undefined', () => {
    expect(ensureArray(undefined)).toEqual([])
  })

  it('returns empty array for a plain string', () => {
    expect(ensureArray('hello')).toEqual([])
  })

  it('returns empty array for a number', () => {
    expect(ensureArray(42)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// ensureRecord
// ---------------------------------------------------------------------------
describe('ensureRecord', () => {
  it('returns object when value is a plain object', () => {
    expect(ensureRecord({ foo: 'bar' })).toEqual({ foo: 'bar' })
  })

  it('returns empty object for null', () => {
    expect(ensureRecord(null)).toEqual({})
  })

  it('returns empty object for an array', () => {
    expect(ensureRecord([1, 2, 3])).toEqual({})
  })

  it('returns empty object for a string', () => {
    expect(ensureRecord('hello')).toEqual({})
  })

  it('returns empty object for a number', () => {
    expect(ensureRecord(42)).toEqual({})
  })

  it('returns empty object for undefined', () => {
    expect(ensureRecord(undefined)).toEqual({})
  })
})

// ---------------------------------------------------------------------------
// getErrorMessage
// ---------------------------------------------------------------------------
describe('getErrorMessage', () => {
  it('extracts message from Error instance', () => {
    expect(getErrorMessage(new Error('boom'), 'fallback')).toBe('boom')
  })

  it('extracts response.data.detail from Axios-like error', () => {
    const err = { response: { data: { detail: 'Unauthorized' } } }
    expect(getErrorMessage(err, 'fallback')).toBe('Unauthorized')
  })

  it('returns message property when response.data.detail is absent', () => {
    expect(getErrorMessage({ message: 'network fail' }, 'fallback')).toBe('network fail')
  })

  it('returns fallback for null', () => {
    expect(getErrorMessage(null, 'fallback')).toBe('fallback')
  })

  it('returns fallback for undefined', () => {
    expect(getErrorMessage(undefined, 'fallback')).toBe('fallback')
  })

  it('returns fallback for a string (no message property)', () => {
    expect(getErrorMessage('raw string', 'fallback')).toBe('fallback')
  })

  it('prioritizes response.data.detail over message', () => {
    const err = { response: { data: { detail: 'detail msg' } }, message: 'msg' }
    expect(getErrorMessage(err, 'fallback')).toBe('detail msg')
  })
})

// ---------------------------------------------------------------------------
// toNumber
// ---------------------------------------------------------------------------
describe('toNumber', () => {
  it('returns number directly', () => {
    expect(toNumber(42)).toBe(42)
  })

  it('parses numeric string', () => {
    expect(toNumber('3.14')).toBe(3.14)
  })

  it('returns fallback for non-numeric string', () => {
    expect(toNumber('abc', -1)).toBe(-1)
  })

  it('returns default fallback 0 for null', () => {
    expect(toNumber(null)).toBe(0)
  })

  it('returns NaN-like values as fallback', () => {
    expect(toNumber(NaN, 99)).toBe(99)
  })
})

// ---------------------------------------------------------------------------
// toString
// ---------------------------------------------------------------------------
describe('toString', () => {
  it('returns string directly', () => {
    expect(toString('hello')).toBe('hello')
  })

  it('returns fallback for number', () => {
    expect(toString(123, 'fb')).toBe('fb')
  })

  it('returns default fallback empty string for null', () => {
    expect(toString(null)).toBe('')
  })
})

// ---------------------------------------------------------------------------
// barColor
// ---------------------------------------------------------------------------
describe('barColor', () => {
  it('returns red for 85 and above', () => {
    expect(barColor(85)).toBe('var(--color-red)')
    expect(barColor(100)).toBe('var(--color-red)')
  })

  it('returns yellow for 60-84', () => {
    expect(barColor(60)).toBe('var(--color-yellow)')
    expect(barColor(84)).toBe('var(--color-yellow)')
  })

  it('returns green for below 60', () => {
    expect(barColor(0)).toBe('var(--color-green)')
    expect(barColor(59)).toBe('var(--color-green)')
  })
})

// ---------------------------------------------------------------------------
// formatDate
// ---------------------------------------------------------------------------
describe('formatDate', () => {
  it('returns dash for empty string', () => {
    expect(formatDate('')).toBe('-')
  })

  it('formats a valid ISO date string', () => {
    const result = formatDate('2025-01-15T10:30:00Z')
    // Should contain the date parts (locale-dependent, just verify non-empty and not '-')
    expect(result).not.toBe('-')
    expect(result.length).toBeGreaterThan(0)
  })
})
