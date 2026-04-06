/**
 * FileSearch — 搜索面板：路径搜索（文件名）| 内容搜索（grep 正则）
 * 顶部 Tab 切换两种模式
 */

import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn } from '@/lib/utils'
import { FileGrepSearch } from './FileGrepSearch'
import type { FileEntry, SearchResponse } from './types'

type SearchMode = 'path' | 'grep'

interface FileSearchProps {
  currentPath: string
  onNavigate: (path: string) => void
  onSelect: (entry: FileEntry) => void
  onClose: () => void
}

function normalizeSearchResponse(data: unknown): SearchResponse {
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    const results = Array.isArray(d.results) ? (d.results as FileEntry[]) : []
    return {
      path: typeof d.path === 'string' ? d.path : '',
      query: typeof d.query === 'string' ? d.query : '',
      results,
      total: typeof d.total === 'number' ? d.total : results.length,
    }
  }
  return { path: '', query: '', results: [], total: 0 }
}

function PathSearch({ currentPath, onNavigate, onSelect, onClose }: FileSearchProps) {
  const [query, setQuery] = useState('')
  const [committed, setCommitted] = useState('')

  const { data: raw, isLoading, isFetching } = useQuery({
    queryKey: ['files', 'search', currentPath, committed],
    queryFn: () =>
      client
        .get('/api/files/search', { params: { path: currentPath, query: committed } })
        .then((r) => r.data),
    enabled: committed.length >= 2,
  })

  const response = normalizeSearchResponse(raw)

  const doSearch = useCallback(() => {
    const q = query.trim()
    if (q.length >= 2) setCommitted(q)
  }, [query])

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Search input */}
      <div className="shrink-0 flex items-center gap-2 px-3 py-2.5 border-b border-border bg-bg2">
        <i className="ti ti-search text-text3 shrink-0" />
        <input
          type="text"
          className="flex-1 bg-transparent text-sm text-text outline-none placeholder:text-text3"
          placeholder="搜索文件名（至少 2 个字符）..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && doSearch()}
          autoFocus
        />
        {(isLoading || isFetching) && (
          <i className="ti ti-loader-2 animate-spin text-text3 shrink-0" />
        )}
        <button
          className="px-3 py-1 text-[12px] bg-accent text-bg font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity shrink-0"
          onClick={doSearch}
          disabled={query.trim().length < 2}
        >
          搜索
        </button>
        <button className="text-text3 hover:text-text transition-colors shrink-0" onClick={onClose}>
          <i className="ti ti-x" />
        </button>
      </div>

      {/* Scope info */}
      <div className="shrink-0 px-3 py-1.5 text-[11px] text-text3 border-b border-border bg-bg2">
        搜索范围:{' '}
        <span className="font-mono">{currentPath}</span>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {!committed ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-text3">
            <i className="ti ti-search text-3xl" />
            <p className="text-sm">输入关键词后按 Enter 或点击搜索</p>
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full text-text3 text-sm">
            <i className="ti ti-loader-2 animate-spin mr-2" />
            搜索中...
          </div>
        ) : response.results.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-text3">
            <i className="ti ti-mood-empty text-3xl" />
            <p className="text-sm">未找到匹配的文件</p>
          </div>
        ) : (
          <>
            <div className="px-3 py-2 text-[11px] text-text3 border-b border-border">
              找到 {response.total} 个结果，关键词:{' '}
              <span className="text-text">&ldquo;{committed}&rdquo;</span>
            </div>
            {response.results.map((result) => {
              const dir =
                result.path.substring(0, result.path.lastIndexOf('/')) || '/'
              return (
                <button
                  key={result.path}
                  className="flex items-center gap-2 w-full px-3 py-2.5 text-left hover:bg-card transition-colors border-b border-border/40"
                  onClick={() => {
                    if (result.type === 'directory') {
                      onNavigate(result.path)
                    } else {
                      onNavigate(dir)
                      onSelect({
                        name: result.name,
                        path: result.path,
                        type: result.type,
                        size: result.size,
                        mtime: result.mtime,
                      })
                    }
                    onClose()
                  }}
                >
                  <i
                    className={cn(
                      'ti text-base shrink-0',
                      result.type === 'directory'
                        ? 'ti-folder text-yellow'
                        : 'ti-file text-text3',
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-text truncate">{result.name}</div>
                    <div className="text-[11px] text-text3 truncate font-mono">{dir}</div>
                  </div>
                  <i className="ti ti-chevron-right text-text3 text-[11px] shrink-0" />
                </button>
              )
            })}
          </>
        )}
      </div>
    </div>
  )
}

export function FileSearch({ currentPath, onNavigate, onSelect, onClose }: FileSearchProps) {
  const [mode, setMode] = useState<SearchMode>('path')

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Mode tabs */}
      <div className="shrink-0 flex items-center border-b border-border bg-bg2 px-3 pt-2 gap-1">
        <button
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 text-[12px] rounded-t transition-colors border-b-2 -mb-px',
            mode === 'path'
              ? 'text-accent border-accent bg-card/50'
              : 'text-text3 border-transparent hover:text-text',
          )}
          onClick={() => setMode('path')}
        >
          <i className="ti ti-file-search" />
          路径搜索
        </button>
        <button
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 text-[12px] rounded-t transition-colors border-b-2 -mb-px',
            mode === 'grep'
              ? 'text-accent border-accent bg-card/50'
              : 'text-text3 border-transparent hover:text-text',
          )}
          onClick={() => setMode('grep')}
        >
          <i className="ti ti-regex" />
          内容搜索
        </button>
        <div className="flex-1" />
        <button
          className="pb-2 text-text3 hover:text-text transition-colors"
          onClick={onClose}
          title="关闭搜索"
        >
          <i className="ti ti-x text-sm" />
        </button>
      </div>

      {/* Panel content — render both, toggle visibility to preserve state */}
      {mode === 'path' ? (
        <PathSearch
          currentPath={currentPath}
          onNavigate={onNavigate}
          onSelect={onSelect}
          onClose={onClose}
        />
      ) : (
        <FileGrepSearch
          currentPath={currentPath}
          onNavigate={onNavigate}
          onSelect={onSelect}
          onClose={onClose}
        />
      )}
    </div>
  )
}
