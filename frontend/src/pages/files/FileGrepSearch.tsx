/**
 * FileGrepSearch — 文件内容 grep 搜索（正则模式）
 * 展示匹配的文件路径、行号和行内容，点击结果跳转并预览该文件
 */

import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { cn } from '@/lib/utils'
import type { FileEntry, GrepResponse, GrepResult } from './types'

interface FileGrepSearchProps {
  currentPath: string
  onNavigate: (path: string) => void
  onSelect: (entry: FileEntry) => void
  onClose: () => void
}

function normalizeGrepResponse(data: unknown): GrepResponse {
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    const results = Array.isArray(d.results) ? (d.results as GrepResult[]) : []
    return {
      path: typeof d.path === 'string' ? d.path : '',
      pattern: typeof d.pattern === 'string' ? d.pattern : '',
      results,
      total: typeof d.total === 'number' ? d.total : results.length,
    }
  }
  return { path: '', pattern: '', results: [], total: 0 }
}

/** Group grep results by file path */
function groupByFile(results: GrepResult[]): Map<string, GrepResult[]> {
  const map = new Map<string, GrepResult[]>()
  for (const r of results) {
    const existing = map.get(r.file)
    if (existing) {
      existing.push(r)
    } else {
      map.set(r.file, [r])
    }
  }
  return map
}

export function FileGrepSearch({ currentPath, onNavigate, onSelect, onClose }: FileGrepSearchProps) {
  const [pattern, setPattern] = useState('')
  const [committed, setCommitted] = useState('')
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set())

  const { data: raw, isLoading, isFetching, isError, error } = useQuery({
    queryKey: ['files', 'grep', currentPath, committed],
    queryFn: () =>
      client
        .get('/api/files/grep', { params: { path: currentPath, pattern: committed } })
        .then((r) => r.data),
    enabled: committed.length >= 1,
    retry: false,
  })

  const response = normalizeGrepResponse(raw)
  const grouped = groupByFile(response.results)
  const fileCount = grouped.size

  const doSearch = useCallback(() => {
    const p = pattern.trim()
    if (p.length >= 1) {
      setCommitted(p)
      // Auto-expand all files on new search
      setExpandedFiles(new Set())
    }
  }, [pattern])

  const toggleFile = useCallback((filePath: string) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev)
      if (next.has(filePath)) {
        next.delete(filePath)
      } else {
        next.add(filePath)
      }
      return next
    })
  }, [])

  const handleSelectLine = useCallback(
    (filePath: string) => {
      const fileName = filePath.split('/').pop() ?? filePath
      const dir = filePath.substring(0, filePath.lastIndexOf('/')) || '/'
      onNavigate(dir)
      onSelect({
        name: fileName,
        path: filePath,
        type: 'file',
        size: 0,
        mtime: '',
      })
      onClose()
    },
    [onNavigate, onSelect, onClose],
  )

  // Extract error message from axios error
  const errorMessage = (() => {
    if (!isError || !error) return null
    const e = error as { response?: { data?: { detail?: string } }; message?: string }
    return e?.response?.data?.detail ?? e?.message ?? '搜索失败'
  })()

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Search bar */}
      <div className="shrink-0 flex items-center gap-2 px-3 py-2.5 border-b border-border bg-bg2">
        <i className="ti ti-regex text-text3 shrink-0" />
        <input
          type="text"
          className="flex-1 bg-transparent text-sm text-text outline-none placeholder:text-text3 font-mono"
          placeholder="正则表达式（如: TODO|FIXME 或 def \w+）..."
          value={pattern}
          onChange={(e) => setPattern(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && doSearch()}
          autoFocus
        />
        {(isLoading || isFetching) && (
          <i className="ti ti-loader-2 animate-spin text-text3 shrink-0" />
        )}
        <button
          className="px-3 py-1 text-[12px] bg-accent text-bg font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity shrink-0"
          onClick={doSearch}
          disabled={pattern.trim().length < 1}
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
        <span className="ml-2 text-text3/60">· 支持正则表达式 · 忽略大小写 · 跳过隐藏目录</span>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {!committed ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-text3">
            <i className="ti ti-file-search text-3xl" />
            <p className="text-sm">输入正则表达式后按 Enter 搜索文件内容</p>
            <p className="text-[11px] text-text3/70">例如: error|warn、def \w+、TODO</p>
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full text-text3 text-sm">
            <i className="ti ti-loader-2 animate-spin mr-2" />
            搜索中...
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-red text-sm">
            <i className="ti ti-alert-circle text-2xl" />
            <p>{errorMessage}</p>
          </div>
        ) : response.results.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-text3">
            <i className="ti ti-mood-empty text-3xl" />
            <p className="text-sm">未找到匹配内容</p>
            <p className="text-[11px] font-mono text-text3/70">{committed}</p>
          </div>
        ) : (
          <>
            {/* Summary bar */}
            <div className="px-3 py-2 text-[11px] text-text3 border-b border-border flex items-center gap-3">
              <span>
                找到 <span className="text-text font-medium">{response.total}</span> 处匹配，共{' '}
                <span className="text-text font-medium">{fileCount}</span> 个文件
              </span>
              <span className="text-text3/40">|</span>
              <span>
                模式:{' '}
                <span className="font-mono text-accent">&ldquo;{committed}&rdquo;</span>
              </span>
              <button
                className="ml-auto text-[11px] text-text3 hover:text-text transition-colors"
                onClick={() => {
                  if (expandedFiles.size === fileCount) {
                    setExpandedFiles(new Set())
                  } else {
                    setExpandedFiles(new Set(grouped.keys()))
                  }
                }}
              >
                {expandedFiles.size === fileCount ? '全部折叠' : '全部展开'}
              </button>
            </div>

            {/* File groups */}
            {Array.from(grouped.entries()).map(([filePath, lines]) => {
              const fileName = filePath.split('/').pop() ?? filePath
              const dir = filePath.substring(0, filePath.lastIndexOf('/')) || '/'
              const isExpanded = expandedFiles.has(filePath)

              return (
                <div key={filePath} className="border-b border-border/40">
                  {/* File header row */}
                  <div className="flex items-center gap-2 px-3 py-2 bg-bg2/60 hover:bg-card transition-colors">
                    <button
                      className="flex items-center gap-2 flex-1 min-w-0 text-left"
                      onClick={() => toggleFile(filePath)}
                    >
                      <i
                        className={cn(
                          'ti text-[11px] text-text3 shrink-0 transition-transform',
                          isExpanded ? 'ti-chevron-down' : 'ti-chevron-right',
                        )}
                      />
                      <i className="ti ti-file-code text-accent/70 text-base shrink-0" />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm text-text font-medium truncate block">{fileName}</span>
                        <span className="text-[10px] text-text3 font-mono truncate block">{dir}</span>
                      </div>
                      <span className="shrink-0 text-[11px] text-text3 bg-card px-1.5 py-0.5 rounded">
                        {lines.length} 处
                      </span>
                    </button>
                    <button
                      className="shrink-0 p-1 text-text3 hover:text-accent transition-colors"
                      title="打开文件"
                      onClick={() => handleSelectLine(filePath)}
                    >
                      <i className="ti ti-external-link text-[13px]" />
                    </button>
                  </div>

                  {/* Match lines */}
                  {isExpanded && (
                    <div className="bg-bg">
                      {lines.map((line, idx) => (
                        <button
                          key={idx}
                          className="flex items-start gap-2 w-full px-3 py-1.5 text-left hover:bg-card/60 transition-colors group"
                          onClick={() => handleSelectLine(filePath)}
                          title={`第 ${line.line_no} 行`}
                        >
                          <span className="shrink-0 text-[11px] text-text3/60 font-mono w-10 text-right pt-px select-none">
                            {line.line_no}
                          </span>
                          <span className="flex-1 text-[12px] font-mono text-text2 break-all leading-relaxed whitespace-pre-wrap">
                            <HighlightMatch text={line.content} pattern={committed} />
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </>
        )}
      </div>
    </div>
  )
}

/** Highlight matching portions of a line */
function HighlightMatch({ text, pattern }: { text: string; pattern: string }) {
  try {
    const regex = new RegExp(`(${pattern})`, 'gi')
    const parts = text.split(regex)
    return (
      <>
        {parts.map((part, i) => {
          const isMatch = i % 2 === 1
          return isMatch ? (
            <mark key={i} className="bg-yellow/30 text-yellow rounded-[2px] px-0.5">
              {part}
            </mark>
          ) : (
            <span key={i}>{part}</span>
          )
        })}
      </>
    )
  } catch {
    return <>{text}</>
  }
}
