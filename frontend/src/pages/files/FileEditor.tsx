/**
 * FileEditor — 基于 textarea 的代码编辑器，Ctrl+S 保存，Tab 插入缩进
 */

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import client from '@/api/client'
import type { ReadResponse } from './types'

interface FileEditorProps {
  path: string
  onClose: () => void
  onSaved: () => void
}

export function FileEditor({ path, onClose, onSaved }: FileEditorProps) {
  const qc = useQueryClient()
  const [content, setContent] = useState('')
  const filename = path.split('/').pop() ?? path

  const { data, isLoading } = useQuery({
    queryKey: ['files', 'read', path],
    queryFn: () =>
      client.get<ReadResponse>('/api/files/read', { params: { path } }).then((r) => r.data),
  })

  useEffect(() => {
    if (data?.content !== undefined) {
      setContent(data.content)
    }
  }, [data?.content])

  const save = useMutation({
    mutationFn: () => client.put('/api/files/write', { path, content }),
    onSuccess: () => {
      toast.success('已保存')
      qc.invalidateQueries({ queryKey: ['files', 'read', path] })
      onSaved()
    },
    onError: () => toast.error('保存失败'),
  })

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl+S / Cmd+S 保存
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault()
      if (!save.isPending) save.mutate()
      return
    }
    // Tab → 两个空格
    if (e.key === 'Tab') {
      e.preventDefault()
      const el = e.currentTarget
      const start = el.selectionStart
      const end = el.selectionEnd
      const next = content.substring(0, start) + '  ' + content.substring(end)
      setContent(next)
      requestAnimationFrame(() => {
        el.selectionStart = el.selectionEnd = start + 2
      })
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b border-border bg-bg2">
        <div className="flex items-center gap-2 min-w-0">
          <i className="ti ti-edit text-accent shrink-0" />
          <span className="text-sm font-medium text-text truncate">{filename}</span>
          <span className="text-[11px] text-text3">编辑中</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] text-text3 hidden sm:block">Ctrl+S 保存</span>
          <button
            className="flex items-center gap-1 px-3 py-1 text-[12px] bg-accent text-bg font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
            onClick={() => save.mutate()}
            disabled={save.isPending || isLoading}
          >
            {save.isPending ? (
              <i className="ti ti-loader-2 animate-spin" />
            ) : (
              <i className="ti ti-device-floppy" />
            )}
            保存
          </button>
          <button
            className="px-2 py-1 text-[12px] bg-card text-text2 hover:text-text rounded transition-colors disabled:opacity-50"
            onClick={onClose}
            disabled={save.isPending}
          >
            取消
          </button>
        </div>
      </div>

      {/* Editor area */}
      <div className="flex-1 min-h-0">
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-text3 text-sm">
            <i className="ti ti-loader-2 animate-spin mr-2" />
            加载中...
          </div>
        ) : (
          <textarea
            className="w-full h-full resize-none bg-bg text-text font-mono text-[13px] p-4 outline-none leading-relaxed border-none"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
          />
        )}
      </div>
    </div>
  )
}
