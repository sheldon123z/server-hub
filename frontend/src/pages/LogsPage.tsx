import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import DOMPurify from 'dompurify'
import client from '@/api/client'
import { cn, ensureArray, ensureRecord, formatBytes, formatDate, toNumber, toString } from '@/lib/utils'
import { useServerStore } from '@/stores/serverStore'

/** 日志文件信息 */
interface LogFile {
  /** 文件完整路径 */
  path: string
  /** 文件名 */
  name: string
  /** 文件大小 (字节) */
  size: number
  /** 最后修改时间 */
  modified: string
}

/** 日志级别过滤器 */
type LogLevel = 'ALL' | 'ERROR' | 'WARN' | 'INFO'

/** 将 API 返回的日志文件列表统一规范化 */
function normalizeLogFiles(value: unknown): { files: LogFile[]; count: number } {
  const record = ensureRecord(value)
  const files = ensureArray<Record<string, unknown>>(record.files).map((item) => ({
    path: toString(item.path),
    name: toString(item.name),
    size: toNumber(item.size ?? item.size_bytes),
    modified: toString(item.modified),
  }))
  return { files, count: toNumber(record.count, files.length) }
}

/** 将 API 返回的日志搜索结果统一规范化 */
function normalizeSearchResults(value: unknown): { path: string; pattern: string; results: string; count: number } {
  const record = ensureRecord(value)
  const results = ensureArray<Record<string, unknown>>(record.results)
    .map((item) => {
      const lineNumber = toNumber(item.line_number)
      const content = toString(item.content)
      return lineNumber > 0 ? `${lineNumber}: ${content}` : content
    })
    .join('\n')

  return {
    path: toString(record.path),
    pattern: toString(record.pattern),
    results,
    count: toNumber(record.count, results ? results.split('\n').length : 0),
  }
}

/** Highlight a single log line based on level */
function highlightLine(line: string): string {
  const escaped = line
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  if (/\bERROR\b/i.test(line)) {
    return `<span class="text-red">${escaped}</span>`
  }
  if (/\bWARN(ING)?\b/i.test(line)) {
    return `<span class="text-yellow">${escaped}</span>`
  }
  return escaped
}

/** Filter lines by level */
function filterLines(content: string, level: LogLevel): string {
  if (level === 'ALL') return content
  return content
    .split('\n')
    .filter((line) => {
      if (level === 'ERROR') return /\bERROR\b/i.test(line)
      if (level === 'WARN') return /\bWARN(ING)?\b/i.test(line)
      if (level === 'INFO') return /\bINFO\b/i.test(line)
      return true
    })
    .join('\n')
}

/**
 * 日志查看页面
 * 提供日志文件浏览、内容查看 (Tail)、关键字搜索、级别过滤和 SSE 实时追踪
 * API 前缀: /api/logs
 */
export default function LogsPage() {
  const serverId = useServerStore((s) => s.selectedServerId)
  const [selectedFile, setSelectedFile] = useState<string>('')
  const [lines, setLines] = useState(100)
  const [searchPattern, setSearchPattern] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const [levelFilter, setLevelFilter] = useState<LogLevel>('ALL')

  // SSE streaming state
  const [streaming, setStreaming] = useState(false)
  const [sseConnected, setSseConnected] = useState(false)
  const [streamContent, setStreamContent] = useState('')
  const eventSourceRef = useRef<EventSource | null>(null)
  const logContainerRef = useRef<HTMLDivElement>(null)

  const { data: filesData, isLoading: filesLoading } = useQuery<{
    files: LogFile[]
    count: number
  }>({
    queryKey: ['log-files', serverId],
    queryFn: () => client.get('/api/logs/files', { params: { server_id: serverId } }).then((r) => normalizeLogFiles(r.data)),
  })

  const { data: tailData, isLoading: tailLoading } = useQuery<{
    path: string
    lines: number
    content: string
  }>({
    queryKey: ['log-tail', selectedFile, lines, serverId],
    queryFn: () =>
      client.get('/api/logs/tail', { params: { path: selectedFile, lines, server_id: serverId } }).then((r) => r.data),
    enabled: !!selectedFile && !streaming,
  })

  const { data: searchData, isLoading: searchLoading } = useQuery<{
    path: string
    pattern: string
    results: string
    count: number
  }>({
    queryKey: ['log-search', selectedFile, activeSearch, serverId],
    queryFn: () =>
      client
        .get('/api/logs/search', { params: { path: selectedFile, q: activeSearch, server_id: serverId } })
        .then((r) => normalizeSearchResults(r.data)),
    enabled: !!selectedFile && !!activeSearch && !streaming,
  })

  const files = ensureArray<LogFile>(filesData?.files)

  // Auto-scroll while streaming
  useEffect(() => {
    if (streaming && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [streamContent, streaming])

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close()
    }
  }, [])

  const startStreaming = useCallback(() => {
    if (!selectedFile) return

    // Close existing connection
    eventSourceRef.current?.close()

    setStreaming(true)
    setStreamContent(tailData?.content ?? '')
    setSseConnected(false)

    const es = new EventSource(`/api/logs/stream?path=${encodeURIComponent(selectedFile)}&server_id=${encodeURIComponent(serverId)}`)
    eventSourceRef.current = es

    es.onopen = () => {
      setSseConnected(true)
    }

    es.onmessage = (event) => {
      setStreamContent((prev) => prev + (prev ? '\n' : '') + event.data)
    }

    es.onerror = () => {
      setSseConnected(false)
      // EventSource will auto-reconnect, but if closed we stop
      if (es.readyState === EventSource.CLOSED) {
        setStreaming(false)
      }
    }
  }, [selectedFile, tailData?.content, serverId])

  const stopStreaming = useCallback(() => {
    eventSourceRef.current?.close()
    eventSourceRef.current = null
    setStreaming(false)
    setSseConnected(false)
  }, [])

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setActiveSearch(searchPattern)
  }

  const rawContent = streaming
    ? streamContent
    : activeSearch && searchData
      ? searchData.results
      : tailData?.content

  const displayContent = rawContent ? filterLines(rawContent, levelFilter) : ''

  // XSS 防护：先由受控代码转义并添加高亮 span，再用 DOMPurify 白名单放行
  // 这样只有一层转义，且 DOMPurify 保证最终 HTML 安全
  const sanitizedContent = displayContent
    ? displayContent
        .split('\n')
        .map((line) => DOMPurify.sanitize(highlightLine(line), { ALLOWED_TAGS: ['span'], ALLOWED_ATTR: ['class'] }))
        .join('\n')
    : ''

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">日志查看</h2>
        {filesData && (
          <div className="bg-card border border-border rounded-lg px-4 py-2 flex items-center gap-2">
            <span className="text-text3 text-xs uppercase">日志文件数</span>
            <span className="text-lg font-bold text-accent">{filesData.count}</span>
          </div>
        )}
      </div>

      <div className="flex gap-4 h-[calc(100vh-14rem)]">
        {/* 左侧文件列表 */}
        <div className="w-64 shrink-0 bg-card border border-border rounded-lg overflow-hidden flex flex-col">
          <div className="px-3 py-2.5 border-b border-border text-xs text-text3 font-medium">
            日志文件 {filesData && `(${filesData.count})`}
          </div>
          <div className="overflow-y-auto flex-1">
            {filesLoading ? (
              <p className="px-3 py-4 text-sm text-text3">加载中...</p>
            ) : files.length === 0 ? (
              <p className="px-3 py-4 text-sm text-text3">暂无日志文件</p>
            ) : (
              files.map((f) => (
                <button
                  key={f.path}
                  onClick={() => {
                    if (streaming) stopStreaming()
                    setSelectedFile(f.path)
                    setActiveSearch('')
                    setSearchPattern('')
                  }}
                  className={cn(
                    'w-full text-left px-3 py-2 border-b border-border/50 hover:bg-bg2/50 transition-colors',
                    selectedFile === f.path && 'bg-accent-dim'
                  )}
                >
                  <div className="text-sm text-text truncate">{f.name}</div>
                  <div className="text-xs text-text3 mt-0.5 flex justify-between">
                    <span>{formatBytes(f.size)}</span>
                    <span>{formatDate(f.modified)}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* 右侧内容区 */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 工具栏 */}
          <div className="flex items-center gap-3 mb-3">
            <select
              value={lines}
              onChange={(e) => setLines(Number(e.target.value))}
              disabled={streaming}
              className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none disabled:opacity-50"
            >
              <option value={50}>50 行</option>
              <option value={100}>100 行</option>
              <option value={200}>200 行</option>
            </select>

            {/* Level filter */}
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value as LogLevel)}
              className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none"
            >
              <option value="ALL">ALL</option>
              <option value="ERROR">ERROR</option>
              <option value="WARN">WARN</option>
              <option value="INFO">INFO</option>
            </select>

            <form onSubmit={handleSearch} className="flex gap-2 flex-1">
              <input
                type="text"
                placeholder="搜索模式..."
                value={searchPattern}
                onChange={(e) => setSearchPattern(e.target.value)}
                disabled={!selectedFile || streaming}
                className="flex-1 bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!selectedFile || !searchPattern || streaming}
                className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
              >
                搜索
              </button>
              {activeSearch && (
                <button
                  type="button"
                  onClick={() => {
                    setActiveSearch('')
                    setSearchPattern('')
                  }}
                  className="px-3 py-1.5 rounded-md text-sm border border-border text-text2 hover:bg-bg2"
                >
                  清除
                </button>
              )}
            </form>

            {/* 实时追踪 toggle */}
            <button
              onClick={streaming ? stopStreaming : startStreaming}
              disabled={!selectedFile}
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors shrink-0 disabled:opacity-50',
                streaming
                  ? 'bg-red/20 text-red border border-red/30 hover:bg-red/30'
                  : 'bg-green/20 text-green border border-green/30 hover:bg-green/30'
              )}
            >
              {/* Connection status dot */}
              {streaming && (
                <span
                  className={cn(
                    'w-2 h-2 rounded-full shrink-0',
                    sseConnected ? 'bg-green animate-pulse' : 'bg-red'
                  )}
                />
              )}
              {streaming ? '停止追踪' : '实时追踪'}
            </button>
          </div>

          {activeSearch && searchData && !streaming && (
            <div className="text-xs text-text3 mb-2">
              搜索 &quot;{searchData.pattern}&quot; 匹配 {searchData.count} 处
            </div>
          )}

          {/* 日志内容 */}
          <div
            ref={logContainerRef}
            className="flex-1 bg-[#0d1117] border border-border rounded-lg overflow-auto"
          >
            {!selectedFile ? (
              <div className="flex items-center justify-center h-full text-text3 text-sm">
                请从左侧选择日志文件
              </div>
            ) : (tailLoading || searchLoading) && !streaming ? (
              <div className="flex items-center justify-center h-full text-text3 text-sm">
                加载中...
              </div>
            ) : (
              <pre
                className="p-4 text-xs text-text2 font-mono whitespace-pre-wrap break-all leading-relaxed"
                dangerouslySetInnerHTML={{ __html: sanitizedContent || '(空)' }}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
