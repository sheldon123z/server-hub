/**
 * FileActions — 工具栏：新建文件夹 / 上传 / 搜索 / 下载 / 刷新
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import client from '@/api/client'
import { cn } from '@/lib/utils'
import type { FileEntry } from './types'

interface FileActionsProps {
  currentPath: string
  selectedEntry: FileEntry | null
  onRefresh: () => void
  onShowUpload: () => void
  onShowSearch: () => void
  uploadActive: boolean
  searchActive: boolean
}

export function FileActions({
  currentPath,
  selectedEntry,
  onRefresh,
  onShowUpload,
  onShowSearch,
  uploadActive,
  searchActive,
}: FileActionsProps) {
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [folderName, setFolderName] = useState('')

  const mkdir = useMutation({
    mutationFn: (name: string) =>
      client.post('/api/files/action', {
        action: 'mkdir',
        path: (currentPath.endsWith('/') ? currentPath : currentPath + '/') + name,
      }),
    onSuccess: () => {
      toast.success('文件夹已创建')
      qc.invalidateQueries({ queryKey: ['files', 'list', currentPath] })
      setShowModal(false)
      setFolderName('')
      onRefresh()
    },
    onError: () => toast.error('创建失败'),
  })

  const openModal = () => {
    setFolderName('')
    setShowModal(true)
  }

  return (
    <div className="flex items-center gap-1 shrink-0">
      <button
        className="flex items-center gap-1.5 px-2.5 py-1 text-[12px] text-text2 hover:text-text hover:bg-card rounded transition-colors"
        onClick={openModal}
        title="新建文件夹"
      >
        <i className="ti ti-folder-plus" />
        <span className="hidden sm:inline">新建</span>
      </button>

      <button
        className={cn(
          'flex items-center gap-1.5 px-2.5 py-1 text-[12px] rounded transition-colors',
          uploadActive ? 'bg-accent-dim text-accent' : 'text-text2 hover:text-text hover:bg-card',
        )}
        onClick={onShowUpload}
        title="上传文件"
      >
        <i className="ti ti-upload" />
        <span className="hidden sm:inline">上传</span>
      </button>

      <button
        className={cn(
          'flex items-center gap-1.5 px-2.5 py-1 text-[12px] rounded transition-colors',
          searchActive ? 'bg-accent-dim text-accent' : 'text-text2 hover:text-text hover:bg-card',
        )}
        onClick={onShowSearch}
        title="搜索文件"
      >
        <i className="ti ti-search" />
        <span className="hidden sm:inline">搜索</span>
      </button>

      {selectedEntry?.type === 'file' && (
        <a
          href={`/api/files/download?path=${encodeURIComponent(selectedEntry.path)}`}
          download={selectedEntry.name}
          className="flex items-center gap-1.5 px-2.5 py-1 text-[12px] text-text2 hover:text-text hover:bg-card rounded transition-colors"
          title="下载选中文件"
        >
          <i className="ti ti-download" />
          <span className="hidden sm:inline">下载</span>
        </a>
      )}

      <button
        className="p-1.5 text-text3 hover:text-text hover:bg-card rounded transition-colors"
        onClick={onRefresh}
        title="刷新"
      >
        <i className="ti ti-refresh" />
      </button>

      {/* New folder modal */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-bg2 border border-border rounded-lg p-6 w-80 flex flex-col gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-semibold text-text">新建文件夹</h3>
            <p className="text-[11px] text-text3 -mt-2 truncate">位置: {currentPath}</p>
            <input
              className="w-full bg-bg border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent transition-colors"
              placeholder="文件夹名称"
              value={folderName}
              onChange={(e) => setFolderName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && folderName.trim()) mkdir.mutate(folderName.trim())
                if (e.key === 'Escape') setShowModal(false)
              }}
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button
                className="px-3 py-1.5 text-sm bg-card text-text2 rounded hover:text-text transition-colors"
                onClick={() => setShowModal(false)}
              >
                取消
              </button>
              <button
                className="px-3 py-1.5 text-sm bg-accent text-bg font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
                onClick={() => folderName.trim() && mkdir.mutate(folderName.trim())}
                disabled={!folderName.trim() || mkdir.isPending}
              >
                {mkdir.isPending ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
