/**
 * FileList — 文件列表视图，含图标/名称/大小/修改时间，支持排序
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn, formatBytes, formatDate } from '@/lib/utils'
import type { FileEntry, FileListResponse } from './types'

interface FileListProps {
  currentPath: string
  sortBy: 'name' | 'size' | 'mtime'
  sortAsc: boolean
  selectedPath: string | null
  onSelect: (entry: FileEntry) => void
  onSortChange: (col: 'name' | 'size' | 'mtime') => void
}

function normalizeResponse(data: unknown): FileListResponse {
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    const entries = Array.isArray(d.entries) ? (d.entries as FileEntry[]) : []
    return {
      path: typeof d.path === 'string' ? d.path : '',
      entries,
      total_files:
        typeof d.total_files === 'number'
          ? d.total_files
          : entries.filter((e) => e.type === 'file').length,
      total_dirs:
        typeof d.total_dirs === 'number'
          ? d.total_dirs
          : entries.filter((e) => e.type === 'directory').length,
    }
  }
  return { path: '', entries: [], total_files: 0, total_dirs: 0 }
}

function getIcon(entry: FileEntry): string {
  if (entry.type === 'directory') return 'ti-folder text-yellow'
  const ext = entry.name.split('.').pop()?.toLowerCase() ?? ''
  if (['py'].includes(ext)) return 'ti-brand-python text-accent'
  if (['js', 'jsx', 'ts', 'tsx'].includes(ext)) return 'ti-file-code text-accent'
  if (['sh', 'bash', 'zsh'].includes(ext)) return 'ti-terminal-2 text-green'
  if (['md', 'mdx'].includes(ext)) return 'ti-markdown text-text2'
  if (['txt'].includes(ext)) return 'ti-file-text text-text3'
  if (['json', 'yaml', 'yml', 'toml'].includes(ext)) return 'ti-file-settings text-orange-400'
  if (['log', 'out', 'err'].includes(ext)) return 'ti-file-description text-text3'
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'].includes(ext))
    return 'ti-photo text-purple-400'
  if (['zip', 'tar', 'gz', 'bz2', 'xz'].includes(ext)) return 'ti-file-zip text-text2'
  if (['pdf'].includes(ext)) return 'ti-file-type-pdf text-red'
  return 'ti-file text-text3'
}

export function FileList({
  currentPath,
  sortBy,
  sortAsc,
  selectedPath,
  onSelect,
  onSortChange,
}: FileListProps) {
  const { data: raw, isLoading, isError } = useQuery({
    queryKey: ['files', 'list', currentPath],
    queryFn: () =>
      client.get('/api/files/list', { params: { path: currentPath, sort: 'name' } }).then((r) => r.data),
  })

  const response = useMemo(() => normalizeResponse(raw), [raw])

  const sorted = useMemo(() => {
    const dirs = response.entries.filter((e) => e.type === 'directory')
    const files = response.entries.filter((e) => e.type === 'file')

    const cmp = (a: FileEntry, b: FileEntry): number => {
      let v = 0
      if (sortBy === 'name') v = a.name.localeCompare(b.name)
      else if (sortBy === 'size') v = a.size - b.size
      else v = a.mtime.localeCompare(b.mtime)
      return sortAsc ? v : -v
    }

    return [...dirs.sort(cmp), ...files.sort(cmp)]
  }, [response.entries, sortBy, sortAsc])

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-text3 text-sm">
        <i className="ti ti-loader-2 animate-spin mr-2" />
        加载中...
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex-1 flex items-center justify-center text-red text-sm">
        <i className="ti ti-alert-circle mr-2" />
        加载失败，请检查路径权限
      </div>
    )
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Column header */}
      <div className="shrink-0 flex items-center border-b border-border bg-bg2">
        <SortBtn
          label="名称"
          col="name"
          active={sortBy}
          asc={sortAsc}
          onChange={onSortChange}
          className="flex-1 px-3 py-2"
        />
        <SortBtn
          label="大小"
          col="size"
          active={sortBy}
          asc={sortAsc}
          onChange={onSortChange}
          className="w-24 px-3 py-2 justify-end"
        />
        <SortBtn
          label="修改时间"
          col="mtime"
          active={sortBy}
          asc={sortAsc}
          onChange={onSortChange}
          className="w-40 px-3 py-2"
        />
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 ? (
          <div className="flex items-center justify-center h-full text-text3 text-sm">
            目录为空
          </div>
        ) : (
          sorted.map((entry) => (
            <button
              key={entry.path}
              className={cn(
                'flex items-center w-full text-left px-3 py-1.5 text-[13px] border-b border-border/40 transition-colors',
                selectedPath === entry.path
                  ? 'bg-accent-dim text-accent'
                  : 'text-text2 hover:bg-card hover:text-text',
              )}
              onClick={() => onSelect(entry)}
              onDoubleClick={() => entry.type === 'directory' && onSelect(entry)}
            >
              <i className={cn('ti shrink-0 mr-2 text-base', getIcon(entry))} />
              <span className="flex-1 truncate">{entry.name}</span>
              <span className="w-24 text-right text-[11px] text-text3 shrink-0">
                {entry.type === 'directory' ? '—' : formatBytes(entry.size)}
              </span>
              <span className="w-40 text-[11px] text-text3 shrink-0 pl-3">
                {entry.mtime ? formatDate(entry.mtime) : '—'}
              </span>
            </button>
          ))
        )}
      </div>

      {/* Footer counts */}
      <div className="shrink-0 border-t border-border bg-bg2 px-3 py-1 flex gap-4 text-[11px] text-text3">
        <span>{response.total_files} 文件</span>
        <span>{response.total_dirs} 目录</span>
      </div>
    </div>
  )
}

function SortBtn({
  label,
  col,
  active,
  asc,
  onChange,
  className,
}: {
  label: string
  col: 'name' | 'size' | 'mtime'
  active: 'name' | 'size' | 'mtime'
  asc: boolean
  onChange: (c: 'name' | 'size' | 'mtime') => void
  className?: string
}) {
  const isActive = active === col
  return (
    <button
      className={cn(
        'flex items-center gap-1 text-[11px] font-medium hover:text-text transition-colors',
        isActive ? 'text-text' : 'text-text3',
        className,
      )}
      onClick={() => onChange(col)}
    >
      {label}
      {isActive && (
        <i className={cn('ti text-[10px]', asc ? 'ti-sort-ascending' : 'ti-sort-descending')} />
      )}
    </button>
  )
}
