/**
 * FileUpload — 拖拽上传区域，支持多文件 + 进度条
 */

import { useState, useCallback, useRef } from 'react'
import client from '@/api/client'
import { cn, formatBytes } from '@/lib/utils'

interface UploadItem {
  file: File
  progress: number
  status: 'pending' | 'uploading' | 'done' | 'error'
  error?: string
}

interface FileUploadProps {
  currentPath: string
  onDone: () => void
  onCancel: () => void
}

export function FileUpload({ currentPath, onDone, onCancel }: FileUploadProps) {
  const [items, setItems] = useState<UploadItem[]>([])
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = useCallback((newFiles: File[]) => {
    setItems((prev) => [
      ...prev,
      ...newFiles.map<UploadItem>((f) => ({ file: f, progress: 0, status: 'pending' })),
    ])
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      addFiles(Array.from(e.dataTransfer.files))
    },
    [addFiles],
  )

  const uploadAll = async () => {
    const pendingIndexes = items.reduce<number[]>(
      (acc, item, i) => (item.status === 'pending' ? [...acc, i] : acc),
      [],
    )
    if (pendingIndexes.length === 0) return
    setUploading(true)

    for (const i of pendingIndexes) {
      setItems((prev) =>
        prev.map((it, idx) => (idx === i ? { ...it, status: 'uploading', progress: 0 } : it)),
      )
      try {
        const formData = new FormData()
        formData.append('file', items[i].file)
        formData.append('path', currentPath)

        await client.post('/api/files/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (evt) => {
            const pct = evt.total ? Math.round((evt.loaded / evt.total) * 100) : 0
            setItems((prev) =>
              prev.map((it, idx) => (idx === i ? { ...it, progress: pct } : it)),
            )
          },
        })

        setItems((prev) =>
          prev.map((it, idx) => (idx === i ? { ...it, status: 'done', progress: 100 } : it)),
        )
      } catch {
        setItems((prev) =>
          prev.map((it, idx) => (idx === i ? { ...it, status: 'error', error: '上传失败' } : it)),
        )
      }
    }

    setUploading(false)
  }

  const allDone = items.length > 0 && items.every((it) => it.status === 'done' || it.status === 'error')
  const pendingCount = items.filter((it) => it.status === 'pending').length

  return (
    <div className="flex flex-col flex-1 p-6 gap-4 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-text">上传文件</h2>
          <p className="text-[11px] text-text3 mt-0.5 truncate">目标目录: {currentPath}</p>
        </div>
        <button className="text-text3 hover:text-text transition-colors" onClick={onCancel}>
          <i className="ti ti-x" />
        </button>
      </div>

      {/* Drop zone */}
      <div
        className={cn(
          'border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center gap-3 transition-colors cursor-pointer shrink-0',
          dragging ? 'border-accent bg-accent/5' : 'border-border hover:border-text3',
        )}
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onClick={() => inputRef.current?.click()}
      >
        <i
          className={cn(
            'ti ti-cloud-upload text-5xl transition-colors',
            dragging ? 'text-accent' : 'text-text3',
          )}
        />
        <p className="text-sm text-text2">
          {dragging ? '松开即可上传' : '拖拽文件到此处，或点击选择'}
        </p>
        <p className="text-[11px] text-text3">单文件最大 100MB</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => addFiles(Array.from(e.target.files ?? []))}
        />
      </div>

      {/* File list */}
      {items.length > 0 && (
        <div className="flex flex-col gap-2 max-h-64 overflow-y-auto">
          {items.map((it, i) => (
            <div key={i} className="flex items-center gap-3 px-3 py-2 bg-card rounded-lg text-sm">
              <i
                className={cn(
                  'ti text-lg shrink-0',
                  it.status === 'done'
                    ? 'ti-circle-check text-green'
                    : it.status === 'error'
                    ? 'ti-alert-circle text-red'
                    : it.status === 'uploading'
                    ? 'ti-loader-2 animate-spin text-accent'
                    : 'ti-file text-text3',
                )}
              />
              <span className="flex-1 truncate text-text2">{it.file.name}</span>
              <span className="text-[11px] text-text3 shrink-0">{formatBytes(it.file.size)}</span>
              {it.status === 'uploading' && (
                <div className="w-20 h-1.5 bg-bg rounded-full overflow-hidden shrink-0">
                  <div
                    className="h-full bg-accent transition-all duration-300"
                    style={{ width: `${it.progress}%` }}
                  />
                </div>
              )}
              {it.error && <span className="text-[11px] text-red shrink-0">{it.error}</span>}
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      {items.length > 0 && (
        <div className="flex gap-3 shrink-0">
          {!allDone ? (
            <button
              className="px-4 py-1.5 bg-accent text-bg text-sm font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
              onClick={uploadAll}
              disabled={uploading || pendingCount === 0}
            >
              {uploading ? '上传中...' : `上传 ${pendingCount} 个文件`}
            </button>
          ) : (
            <button
              className="px-4 py-1.5 bg-green/20 text-green text-sm font-medium rounded"
              onClick={onDone}
            >
              <i className="ti ti-check mr-1" />
              完成
            </button>
          )}
          {!uploading && (
            <button
              className="px-4 py-1.5 bg-card text-text2 text-sm rounded hover:text-text transition-colors"
              onClick={() => setItems([])}
            >
              清空
            </button>
          )}
        </div>
      )}
    </div>
  )
}
