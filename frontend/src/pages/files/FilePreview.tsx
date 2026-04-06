/**
 * FilePreview — 文件预览面板：代码高亮 / Markdown / 图片 / 日志自动滚底
 * 文件详情面板展示权限、所有者、修改时间等元信息（via /api/files/stat）
 */

import { useRef, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash'
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python'
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript'
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript'
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json'
import yaml from 'react-syntax-highlighter/dist/esm/languages/prism/yaml'
import sql from 'react-syntax-highlighter/dist/esm/languages/prism/sql'
import css from 'react-syntax-highlighter/dist/esm/languages/prism/css'
import docker from 'react-syntax-highlighter/dist/esm/languages/prism/docker'
import nginx from 'react-syntax-highlighter/dist/esm/languages/prism/nginx'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import client from '@/api/client'
import { formatBytes } from '@/lib/utils'
import { getLanguage, isMarkdown, isImage } from '@/lib/file-utils'
import type { FileEntry, ReadResponse, FileStat } from './types'

SyntaxHighlighter.registerLanguage('bash', bash)
SyntaxHighlighter.registerLanguage('shell', bash)
SyntaxHighlighter.registerLanguage('sh', bash)
SyntaxHighlighter.registerLanguage('python', python)
SyntaxHighlighter.registerLanguage('javascript', javascript)
SyntaxHighlighter.registerLanguage('js', javascript)
SyntaxHighlighter.registerLanguage('typescript', typescript)
SyntaxHighlighter.registerLanguage('ts', typescript)
SyntaxHighlighter.registerLanguage('json', json)
SyntaxHighlighter.registerLanguage('yaml', yaml)
SyntaxHighlighter.registerLanguage('yml', yaml)
SyntaxHighlighter.registerLanguage('sql', sql)
SyntaxHighlighter.registerLanguage('css', css)
SyntaxHighlighter.registerLanguage('dockerfile', docker)
SyntaxHighlighter.registerLanguage('nginx', nginx)

const MAX_PREVIEW_SIZE = 5 * 1024 * 1024
const LOG_EXTS = new Set(['log', 'out', 'err'])

interface FilePreviewProps {
  entry: FileEntry
  onEdit: () => void
  onClose: () => void
}

export function FilePreview({ entry, onEdit, onClose }: FilePreviewProps) {
  const logRef = useRef<HTMLPreElement>(null)
  const [showStat, setShowStat] = useState(false)
  const ext = entry.name.split('.').pop()?.toLowerCase() ?? ''
  const isLog = LOG_EXTS.has(ext)
  const image = isImage(entry.name)
  const markdown = isMarkdown(entry.name)
  const tooLarge = entry.size > MAX_PREVIEW_SIZE

  const { data, isLoading, isError } = useQuery({
    queryKey: ['files', 'read', entry.path],
    queryFn: () =>
      client
        .get<ReadResponse>('/api/files/read', { params: { path: entry.path } })
        .then((r) => r.data),
    enabled: !image && !tooLarge,
  })

  const { data: statData, isLoading: statLoading } = useQuery({
    queryKey: ['files', 'stat', entry.path],
    queryFn: () =>
      client
        .get<FileStat>('/api/files/stat', { params: { path: entry.path } })
        .then((r) => r.data),
    enabled: showStat,
    staleTime: 30_000,
  })

  // Auto-scroll to bottom for log files
  useEffect(() => {
    if (isLog && logRef.current && data) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [isLog, data])

  const language = getLanguage(entry.name)

  return (
    <div className="flex flex-col h-full min-h-0 border-l border-border">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b border-border bg-bg2">
        <div className="flex items-center gap-2 min-w-0">
          <i className="ti ti-file text-text3 shrink-0" />
          <span className="text-sm font-medium text-text truncate">{entry.name}</span>
          <span className="text-[11px] text-text3 shrink-0">{formatBytes(entry.size)}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {!image && !tooLarge && (
            <button
              className="flex items-center gap-1 px-2 py-1 text-[12px] bg-card text-text2 hover:text-text rounded transition-colors"
              onClick={onEdit}
            >
              <i className="ti ti-edit" />
              编辑
            </button>
          )}
          <a
            href={`/api/files/download?path=${encodeURIComponent(entry.path)}`}
            download={entry.name}
            className="flex items-center gap-1 px-2 py-1 text-[12px] bg-card text-text2 hover:text-text rounded transition-colors"
          >
            <i className="ti ti-download" />
            下载
          </a>
          <button
            className={`flex items-center gap-1 px-2 py-1 text-[12px] rounded transition-colors ${
              showStat ? 'bg-accent-dim text-accent' : 'bg-card text-text2 hover:text-text'
            }`}
            onClick={() => setShowStat((v) => !v)}
            title="文件详情"
          >
            <i className="ti ti-info-circle" />
            详情
          </button>
          <button
            className="p-1.5 text-text3 hover:text-text rounded transition-colors"
            onClick={onClose}
          >
            <i className="ti ti-x" />
          </button>
        </div>
      </div>

      {/* Stat panel */}
      {showStat && (
        <div className="shrink-0 border-b border-border bg-bg2 px-3 py-2">
          {statLoading ? (
            <div className="flex items-center gap-2 text-[11px] text-text3">
              <i className="ti ti-loader-2 animate-spin" />
              加载详情中...
            </div>
          ) : statData ? (
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px]">
              <StatRow label="权限" value={`${statData.permissions} (${statData.octal_permissions})`} mono />
              <StatRow label="所有者" value={`${statData.owner} : ${statData.group}`} mono />
              <StatRow label="大小" value={formatBytes(statData.size)} />
              <StatRow label="修改时间" value={new Date(statData.mtime * 1000).toLocaleString()} />
              <StatRow label="创建时间" value={new Date(statData.ctime * 1000).toLocaleString()} />
              {statData.is_symlink && statData.symlink_target && (
                <StatRow label="符号链接" value={`→ ${statData.symlink_target}`} mono />
              )}
            </div>
          ) : null}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto min-h-0 bg-bg">
        {tooLarge ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-text3">
            <i className="ti ti-file-off text-3xl" />
            <p className="text-sm">文件过大（{formatBytes(entry.size)}），超过 5MB 预览上限</p>
            <a
              href={`/api/files/download?path=${encodeURIComponent(entry.path)}`}
              download={entry.name}
              className="text-accent text-sm hover:underline"
            >
              直接下载
            </a>
          </div>
        ) : image ? (
          <div className="flex items-center justify-center h-full p-6 bg-[repeating-conic-gradient(#1e293b_0%_25%,transparent_0%_50%)_0_0/20px_20px]">
            <img
              src={`/api/files/download?path=${encodeURIComponent(entry.path)}`}
              alt={entry.name}
              className="max-w-full max-h-full object-contain shadow-lg"
            />
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full text-text3 text-sm">
            <i className="ti ti-loader-2 animate-spin mr-2" />
            加载中...
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center h-full text-red text-sm">
            <i className="ti ti-alert-circle mr-2" />
            加载失败（可能是二进制文件或权限不足）
          </div>
        ) : markdown ? (
          <div className="prose prose-invert prose-sm max-w-none p-5 text-text2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data?.content ?? ''}</ReactMarkdown>
          </div>
        ) : isLog ? (
          <pre
            ref={logRef}
            className="h-full overflow-auto p-4 text-[12px] font-mono text-text2 leading-relaxed whitespace-pre-wrap break-all"
          >
            {data?.content ?? ''}
          </pre>
        ) : (
          <SyntaxHighlighter
            language={language}
            style={oneDark}
            customStyle={{
              margin: 0,
              minHeight: '100%',
              borderRadius: 0,
              fontSize: '12px',
              lineHeight: '1.6',
            }}
            showLineNumbers
            wrapLongLines={false}
          >
            {data?.content ?? ''}
          </SyntaxHighlighter>
        )}
      </div>
    </div>
  )
}

function StatRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-text3 shrink-0 w-16">{label}</span>
      <span className={`text-text2 truncate ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}
