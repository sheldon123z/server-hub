/**
 * DataTable — sortable, filterable, searchable, paginated table
 * for rendering structured data inside agent messages.
 */

import { useState, useMemo } from 'react'
import { ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ColumnSchema {
  key: string
  label: string
  type?: 'text' | 'number' | 'status' | 'action' | 'timestamp'
  align?: 'left' | 'center' | 'right'
  render?: 'default' | 'badge' | 'progress' | 'link'
}

interface TableComponent {
  id: string
  type: 'table'
  title?: string
  schema: ColumnSchema[]
  data: Array<Record<string, unknown>>
  features?: {
    sortable?: boolean
    filterable?: boolean
    searchable?: boolean
    paginated?: boolean
    pageSize?: number
  }
}

interface DataTableProps {
  component: TableComponent
}

/* ── Status badge ──────────────────────────────── */

function StatusBadge({ value }: { value: string }) {
  const lower = value.toLowerCase()
  let colorClass = 'bg-bg3 text-text3 border-border'
  if (['running', 'active', 'online', 'healthy', 'up'].includes(lower)) {
    colorClass = 'bg-green/20 text-green border-green/30'
  } else if (['stopped', 'inactive', 'offline', 'error', 'down', 'failed'].includes(lower)) {
    colorClass = 'bg-red/10 text-red border-red/30'
  } else if (['pending', 'warning', 'restarting', 'paused'].includes(lower)) {
    colorClass = 'bg-yellow/20 text-yellow border-yellow/30'
  }

  return (
    <span className={cn('inline-block rounded px-1.5 py-0.5 text-xs border', colorClass)}>
      {value}
    </span>
  )
}

/* ── Cell renderer ─────────────────────────────── */

function CellValue({
  column,
  value,
}: {
  column: ColumnSchema
  value: unknown
}) {
  const str = value == null ? '-' : String(value)

  if (column.type === 'status') {
    return <StatusBadge value={str} />
  }

  if (column.render === 'badge') {
    return (
      <span className="inline-block rounded bg-accent/10 text-accent border border-accent/30 px-1.5 py-0.5 text-xs">
        {str}
      </span>
    )
  }

  if (column.type === 'number') {
    const num = typeof value === 'number' ? value : parseFloat(str)
    if (Number.isFinite(num)) {
      return <span className="font-mono tabular-nums">{num.toLocaleString()}</span>
    }
  }

  if (column.type === 'timestamp') {
    try {
      const d = new Date(str)
      if (!isNaN(d.getTime())) {
        return <span className="text-text2 text-xs">{d.toLocaleString('zh-CN', { hour12: false })}</span>
      }
    } catch { /* fall through */ }
  }

  return <span>{str}</span>
}

/* ── Main component ────────────────────────────── */

export function DataTable({ component }: DataTableProps) {
  const { title, schema, data, features } = component

  const pageSize = features?.pageSize ?? 10
  const [sortColumn, setSortColumn] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [filterColumn, setFilterColumn] = useState<string | null>(null)
  const [filterValue, setFilterValue] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [page, setPage] = useState(0)

  /* Sort toggle */
  const handleSort = (key: string) => {
    if (!features?.sortable) return
    if (sortColumn === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortColumn(key)
      setSortDir('asc')
    }
  }

  /* Derived data */
  const processed = useMemo(() => {
    let rows = [...data]

    // Search
    if (searchTerm && features?.searchable) {
      const lower = searchTerm.toLowerCase()
      rows = rows.filter((row) =>
        schema.some((col) => String(row[col.key] ?? '').toLowerCase().includes(lower)),
      )
    }

    // Filter
    if (filterColumn && filterValue) {
      rows = rows.filter((row) =>
        String(row[filterColumn] ?? '').toLowerCase().includes(filterValue.toLowerCase()),
      )
    }

    // Sort
    if (sortColumn) {
      rows.sort((a, b) => {
        const va = a[sortColumn] ?? ''
        const vb = b[sortColumn] ?? ''
        const cmp = String(va).localeCompare(String(vb), undefined, { numeric: true })
        return sortDir === 'asc' ? cmp : -cmp
      })
    }

    return rows
  }, [data, schema, searchTerm, filterColumn, filterValue, sortColumn, sortDir, features?.searchable])

  /* Pagination */
  const totalPages = features?.paginated ? Math.max(1, Math.ceil(processed.length / pageSize)) : 1
  const paginatedRows = features?.paginated
    ? processed.slice(page * pageSize, (page + 1) * pageSize)
    : processed

  return (
    <div className="border border-border bg-card rounded-lg overflow-hidden">
      {/* Header area */}
      {(title || features?.searchable || features?.filterable) && (
        <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-border bg-bg2">
          {title && <span className="text-sm font-medium text-text mr-auto">{title}</span>}
          {features?.searchable && (
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text3" />
              <input
                type="text"
                placeholder="搜索..."
                value={searchTerm}
                onChange={(e) => { setSearchTerm(e.target.value); setPage(0) }}
                className={cn(
                  'pl-7 pr-2 py-1 text-xs rounded border border-border bg-bg text-text',
                  'focus:outline-none focus:border-accent w-40',
                )}
              />
            </div>
          )}
          {features?.filterable && (
            <div className="flex items-center gap-1">
              <select
                value={filterColumn ?? ''}
                onChange={(e) => { setFilterColumn(e.target.value || null); setFilterValue(''); setPage(0) }}
                className="text-xs rounded border border-border bg-bg text-text px-1.5 py-1 focus:outline-none focus:border-accent"
              >
                <option value="">筛选列...</option>
                {schema.map((col) => (
                  <option key={col.key} value={col.key}>{col.label}</option>
                ))}
              </select>
              {filterColumn && (
                <input
                  type="text"
                  placeholder="筛选值..."
                  value={filterValue}
                  onChange={(e) => { setFilterValue(e.target.value); setPage(0) }}
                  className="text-xs rounded border border-border bg-bg text-text px-2 py-1 w-28 focus:outline-none focus:border-accent"
                />
              )}
            </div>
          )}
          <span className="text-xs text-text3">{processed.length} 条</span>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-bg2/50">
              {schema.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className={cn(
                    'px-3 py-2 text-xs font-medium text-text2',
                    col.align === 'center' ? 'text-center' : col.align === 'right' ? 'text-right' : 'text-left',
                    features?.sortable && 'cursor-pointer select-none hover:text-text',
                  )}
                >
                  <span className="inline-flex items-center gap-0.5">
                    {col.label}
                    {sortColumn === col.key && (
                      sortDir === 'asc'
                        ? <ChevronUp className="w-3 h-3" />
                        : <ChevronDown className="w-3 h-3" />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.length === 0 ? (
              <tr>
                <td colSpan={schema.length} className="px-3 py-6 text-center text-text3 text-xs">
                  暂无数据
                </td>
              </tr>
            ) : (
              paginatedRows.map((row, ri) => (
                <tr
                  key={ri}
                  className="border-b border-border last:border-b-0 hover:bg-bg2/30 transition-colors"
                >
                  {schema.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        'px-3 py-2 text-text2',
                        col.align === 'center' ? 'text-center' : col.align === 'right' ? 'text-right' : 'text-left',
                      )}
                    >
                      <CellValue column={col} value={row[col.key]} />
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {features?.paginated && totalPages > 1 && (
        <div className="flex items-center justify-between px-3 py-2 border-t border-border bg-bg2/30">
          <span className="text-xs text-text3">
            第 {page + 1} / {totalPages} 页
          </span>
          <div className="flex items-center gap-1">
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="p-1 rounded hover:bg-bg3 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4 text-text2" />
            </button>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              className="p-1 rounded hover:bg-bg3 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4 text-text2" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
