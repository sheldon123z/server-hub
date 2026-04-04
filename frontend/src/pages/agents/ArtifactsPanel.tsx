/**
 * ArtifactsPanel — 右栏 Artifacts 文件面板，展示 Agent 产出的文件制品。
 * 上半: 文件列表  下半: 文件详情查看器
 */

import { useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, Copy, Download, X, FolderOpen, Eye, Code2 } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import toast from 'react-hot-toast'
import DOMPurify from 'dompurify'
import { useArtifactStore } from '@/stores/artifactStore'
import { useChatStore } from '@/stores/chatStore'
import { getLanguage, getFileName, isMarkdown, isImage, isSVG, isHTML } from '@/lib/file-utils'
import { MarkdownContent } from './MarkdownContent'
import { cn } from '@/lib/utils'
import api from '@/api/client'

// ---------------------------------------------------------------------------
// SafeSvgViewer — DOMPurify 安全渲染 SVG（保留 CSS 动画/渐变/滤镜）
// ---------------------------------------------------------------------------

const SVG_PURIFY_CONFIG = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ADD_TAGS: ['use'],
  ADD_ATTR: ['xlink:href', 'clip-path', 'fill-rule', 'viewBox', 'xmlns', 'xmlns:xlink'],
  FORBID_TAGS: ['script', 'foreignObject'],
  FORBID_ATTR: ['onload', 'onerror', 'onclick', 'onmouseover'],
}

function SafeSvgViewer({ content, className }: { content: string; className?: string }) {
  const clean = DOMPurify.sanitize(content, SVG_PURIFY_CONFIG)
  return (
    <div
      className={cn('flex items-center justify-center p-4 [&_svg]:max-w-full [&_svg]:max-h-[60vh]', className)}
      dangerouslySetInnerHTML={{ __html: clean }}
    />
  )
}

// ---------------------------------------------------------------------------
// FileDetail — 选中文件的查看器
// ---------------------------------------------------------------------------

function FileDetail({ filePath, inlineContent }: { filePath: string; inlineContent?: string }) {
  const deselect = useArtifactStore((s) => s.deselect)
  const fileName = getFileName(filePath)
  const language = getLanguage(filePath)

  // HTTP fetch (仅当 SSE 没有内联内容时)
  const { data: fetchedData, isLoading } = useQuery({
    queryKey: ['artifact-content', filePath],
    queryFn: async () => {
      const res = await api.get('/api/agents/artifacts/file', { params: { path: filePath } })
      return res.data as { content: string; language: string; size: number }
    },
    enabled: !inlineContent,
    staleTime: 5 * 60 * 1000,
  })

  const content = inlineContent ?? fetchedData?.content ?? ''
  const showSVG = isSVG(filePath)
  const showMarkdown = isMarkdown(filePath)
  const showImage = isImage(filePath)
  const showHTML = isHTML(filePath)

  const handleCopy = useCallback(() => {
    navigator.clipboard
      .writeText(content)
      .then(() => toast.success('已复制'))
      .catch(() => toast.error('复制失败'))
  }, [content])

  const downloadUrl = `/api/agents/artifacts/download?path=${encodeURIComponent(filePath)}`

  return (
    <div className="flex flex-col min-h-0 flex-1">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={14} className="shrink-0 text-text2" />
          <span className="text-xs font-medium text-text truncate" title={filePath}>
            {fileName}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {!showImage && (
            <button
              onClick={handleCopy}
              className="rounded p-1 text-text3 transition-colors hover:bg-bg2 hover:text-text"
              title="复制"
            >
              <Copy size={13} />
            </button>
          )}
          <a
            href={downloadUrl}
            className="rounded p-1 text-text3 transition-colors hover:bg-bg2 hover:text-text"
            title="下载"
          >
            <Download size={13} />
          </a>
          <button
            onClick={deselect}
            className="rounded p-1 text-text3 transition-colors hover:bg-bg2 hover:text-text"
            title="关闭"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto min-h-0">
        {isLoading && !inlineContent ? (
          <div className="flex items-center justify-center h-32 text-sm text-text3">加载中...</div>
        ) : !content && !showImage && !showSVG ? (
          <div className="flex items-center justify-center h-32 text-sm text-text3">文件为空</div>
        ) : showSVG && content ? (
          <SafeSvgViewer content={content} />
        ) : showImage ? (
          <div className="flex items-center justify-center p-4">
            <img
              src={downloadUrl}
              alt={fileName}
              className="max-w-full max-h-[60vh] rounded border border-border"
            />
          </div>
        ) : showHTML ? (
          <iframe
            title={fileName}
            srcDoc={content}
            sandbox=""
            className="w-full h-full min-h-[300px] border-0"
          />
        ) : showMarkdown ? (
          <div className="p-4">
            <MarkdownContent content={content} />
          </div>
        ) : (
          <SyntaxHighlighter
            language={language}
            style={oneDark}
            showLineNumbers
            wrapLines
            customStyle={{
              margin: 0,
              borderRadius: 0,
              fontSize: '0.8em',
              background: 'transparent',
              padding: '0.75rem',
            }}
          >
            {content}
          </SyntaxHighlighter>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ArtifactsPanel — 主面板
// ---------------------------------------------------------------------------

export function ArtifactsPanel() {
  const artifacts = useArtifactStore((s) => s.artifacts)
  const selectedPath = useArtifactStore((s) => s.selectedPath)
  const select = useArtifactStore((s) => s.select)

  const selectedArtifact = useMemo(
    () => artifacts.find((a) => a.filePath === selectedPath),
    [artifacts, selectedPath],
  )

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text3 gap-3 p-8">
        <FolderOpen size={32} className="opacity-40" />
        <p className="text-sm text-center">Agent 产出的文件将在此处展示</p>
        <p className="text-xs text-center opacity-60">
          当 Agent 使用 write_file 或 edit_file 创建文件时，文件会自动出现在这里
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* 文件列表 */}
      <div className={cn(
        'shrink-0 overflow-y-auto border-b border-border',
        selectedPath ? 'max-h-[35%]' : 'flex-1',
      )}>
        <div className="px-3 py-2 text-xs font-medium text-text3 border-b border-border sticky top-0 bg-bg2">
          文件 ({artifacts.length})
        </div>
        <div className="divide-y divide-border/50">
          {artifacts.map((item) => {
            const isSelected = item.filePath === selectedPath
            return (
              <button
                key={item.filePath}
                className={cn(
                  'w-full flex items-center gap-2 px-3 py-2 text-left transition-colors',
                  isSelected ? 'bg-accent-dim' : 'hover:bg-bg2',
                )}
                onClick={() => select(item.filePath)}
              >
                <FileText size={14} className={cn('shrink-0', isSelected ? 'text-accent' : 'text-text3')} />
                <div className="min-w-0 flex-1">
                  <div className={cn('text-xs truncate', isSelected ? 'text-accent font-medium' : 'text-text')}>
                    {getFileName(item.filePath)}
                  </div>
                  <div className="text-[10px] text-text3 truncate">{item.filePath}</div>
                </div>
                <span className={cn(
                  'shrink-0 text-[10px] px-1.5 py-0.5 rounded',
                  item.action === 'write_file' ? 'bg-green/10 text-green' : 'bg-yellow/10 text-yellow',
                )}>
                  {item.action === 'write_file' ? '新建' : '编辑'}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* 文件详情 */}
      {selectedPath && selectedArtifact && (
        <FileDetail
          filePath={selectedPath}
          inlineContent={selectedArtifact.content}
        />
      )}
    </div>
  )
}
