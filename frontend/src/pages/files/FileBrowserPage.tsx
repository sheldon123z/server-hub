/**
 * FileBrowserPage — Web 文件管理器主页面
 * 布局: 左侧目录树 (250px) + 右侧文件列表/预览/编辑器/上传/搜索
 */

import { useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { FileTree } from './FileTree'
import { FileList } from './FileList'
import { FilePreview } from './FilePreview'
import { FileEditor } from './FileEditor'
import { FileUpload } from './FileUpload'
import { FileSearch } from './FileSearch'
import { FileActions } from './FileActions'
import type { FileEntry } from './types'

type PanelMode = 'list' | 'preview' | 'edit' | 'upload' | 'search'

const DEFAULT_PATH = '/home'

export default function FileBrowserPage() {
  const qc = useQueryClient()
  const [currentPath, setCurrentPath] = useState(DEFAULT_PATH)
  const [selectedEntry, setSelectedEntry] = useState<FileEntry | null>(null)
  const [panelMode, setPanelMode] = useState<PanelMode>('list')
  const [sortBy, setSortBy] = useState<'name' | 'size' | 'mtime'>('name')
  const [sortAsc, setSortAsc] = useState(true)

  const navigate = useCallback((path: string) => {
    setCurrentPath(path)
    setSelectedEntry(null)
    setPanelMode('list')
  }, [])

  const selectEntry = useCallback(
    (entry: FileEntry) => {
      if (entry.type === 'directory') {
        navigate(entry.path)
      } else {
        setSelectedEntry(entry)
        setPanelMode('preview')
      }
    },
    [navigate],
  )

  const refresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['files', 'list', currentPath] })
  }, [qc, currentPath])

  const handleSortChange = useCallback(
    (col: 'name' | 'size' | 'mtime') => {
      if (col === sortBy) setSortAsc((a) => !a)
      else {
        setSortBy(col)
        setSortAsc(true)
      }
    },
    [sortBy],
  )

  // Breadcrumb segments
  const parts = currentPath.split('/').filter(Boolean)

  return (
    <div className="flex flex-col -m-5" style={{ height: 'calc(100vh - 56px)' }}>
      {/* ── Top toolbar ────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border bg-bg2 px-4 py-2 flex items-center gap-2 min-w-0">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-0.5 text-sm flex-1 min-w-0 overflow-hidden">
          <button
            className="text-text2 hover:text-accent transition-colors px-1 shrink-0"
            onClick={() => navigate('/')}
          >
            /
          </button>
          {parts.map((seg, i) => {
            const path = '/' + parts.slice(0, i + 1).join('/')
            const isLast = i === parts.length - 1
            return (
              <span key={path} className="flex items-center gap-0.5 min-w-0">
                <span className="text-text3 shrink-0">/</span>
                {isLast ? (
                  <span className="text-text font-medium px-1 truncate max-w-[160px]">{seg}</span>
                ) : (
                  <button
                    className="text-text2 hover:text-accent transition-colors px-1 truncate max-w-[120px]"
                    onClick={() => navigate(path)}
                  >
                    {seg}
                  </button>
                )}
              </span>
            )
          })}
        </nav>

        {/* Action buttons */}
        <FileActions
          currentPath={currentPath}
          selectedEntry={selectedEntry}
          onRefresh={refresh}
          onShowUpload={() =>
            setPanelMode((m) => (m === 'upload' ? 'list' : 'upload'))
          }
          onShowSearch={() =>
            setPanelMode((m) => (m === 'search' ? 'list' : 'search'))
          }
          uploadActive={panelMode === 'upload'}
          searchActive={panelMode === 'search'}
        />
      </div>

      {/* ── Main body ──────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* Left: directory tree */}
        <div className="shrink-0 w-[250px] border-r border-border overflow-y-auto bg-bg2">
          <FileTree currentPath={currentPath} onNavigate={navigate} />
        </div>

        {/* Right: content area */}
        <div className="flex flex-1 min-w-0">
          {panelMode === 'upload' ? (
            <FileUpload
              currentPath={currentPath}
              onDone={() => {
                refresh()
                setPanelMode('list')
              }}
              onCancel={() => setPanelMode('list')}
            />
          ) : panelMode === 'search' ? (
            <FileSearch
              currentPath={currentPath}
              onNavigate={navigate}
              onSelect={(entry) => {
                setSelectedEntry(entry)
                setPanelMode('preview')
              }}
              onClose={() => setPanelMode('list')}
            />
          ) : panelMode === 'edit' && selectedEntry ? (
            <FileEditor
              path={selectedEntry.path}
              onClose={() => setPanelMode(selectedEntry ? 'preview' : 'list')}
              onSaved={() => setPanelMode('preview')}
            />
          ) : (
            /* List + optional preview side-by-side */
            <div className="flex flex-1 min-w-0">
              <div
                className={
                  selectedEntry && panelMode === 'preview'
                    ? 'w-[300px] shrink-0 flex flex-col border-r border-border'
                    : 'flex flex-col flex-1'
                }
              >
                <FileList
                  currentPath={currentPath}
                  sortBy={sortBy}
                  sortAsc={sortAsc}
                  selectedPath={selectedEntry?.path ?? null}
                  onSelect={selectEntry}
                  onSortChange={handleSortChange}
                />
              </div>

              {selectedEntry && panelMode === 'preview' && (
                <div className="flex-1 min-w-0 flex flex-col">
                  <FilePreview
                    entry={selectedEntry}
                    onEdit={() => setPanelMode('edit')}
                    onClose={() => {
                      setSelectedEntry(null)
                      setPanelMode('list')
                    }}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Status bar ─────────────────────────────────────── */}
      <div className="shrink-0 border-t border-border bg-bg2 px-4 py-1 flex items-center gap-4 text-[11px] text-text3">
        <span className="font-mono truncate flex-1">{currentPath}</span>
        {selectedEntry && (
          <>
            <span className="text-border">│</span>
            <span className="shrink-0">已选: {selectedEntry.name}</span>
          </>
        )}
      </div>
    </div>
  )
}
