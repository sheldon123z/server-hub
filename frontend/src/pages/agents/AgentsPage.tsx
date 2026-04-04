/**
 * AgentsPage - AI OpsAgent full-page interface with 3-column layout.
 * Sidebar | Chat (always visible) | Right panel (patrol/admin/terminal)
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'
import { useArtifactStore } from '@/stores/artifactStore'
import { ConversationSidebar } from './ConversationSidebar'
import { ChatPanel } from './ChatPanel'
import { PatrolPanel } from './PatrolPanel'
import { AdminPanel } from './AdminPanel'
import { ArtifactsPanel } from './ArtifactsPanel'
import { TerminalPanel } from './TerminalPanel'
import { SafetyToggle } from './SafetyToggle'

type RightTab = 'patrol' | 'admin'

const STORAGE_KEY = 'agents-sidebar-width'
const DEFAULT_SIDEBAR = 200
const MIN_SIDEBAR = 140
const MAX_SIDEBAR = 360

export default function AgentsPage() {
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const { safetyMode, setSafetyMode } = useChatStore()
  const [tab, setTab] = useState<RightTab>(() => {
    const saved = localStorage.getItem('agents-tab')
    return (saved === 'patrol' || saved === 'admin') ? saved : 'patrol'
  })
  const artifactCount = useArtifactStore((s) => s.artifacts.length)
  const artifactIsOpen = useArtifactStore((s) => s.isOpen)
  const autoOpenUsed = useArtifactStore((s) => s._autoOpenUsed)
  const [showTerminal, setShowTerminal] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? Math.max(MIN_SIDEBAR, Math.min(MAX_SIDEBAR, Number(saved))) : DEFAULT_SIDEBAR
  })
  const dragging = useRef(false)

  useEffect(() => {
    localStorage.setItem('agents-tab', tab)
  }, [tab])

  // 首次产出 artifact 时自动打开查看器（仅触发一次）
  useEffect(() => {
    if (artifactCount > 0 && !autoOpenUsed) {
      const latest = useArtifactStore.getState().artifacts.at(-1)
      if (latest) {
        useArtifactStore.getState().select(latest.filePath)
      }
      useArtifactStore.getState().markAutoOpenUsed()
    }
  }, [artifactCount, autoOpenUsed])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    const startX = e.clientX
    const startW = sidebarWidth

    function onMove(ev: MouseEvent) {
      if (!dragging.current) return
      const newW = Math.max(MIN_SIDEBAR, Math.min(MAX_SIDEBAR, startW + ev.clientX - startX))
      setSidebarWidth(newW)
    }
    function onUp() {
      dragging.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      setSidebarWidth((w) => {
        localStorage.setItem(STORAGE_KEY, String(w))
        return w
      })
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [sidebarWidth])

  return (
    <div className="-m-5 flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Top bar: conversation title + controls */}
      <div className="flex items-center justify-between px-4 h-[42px] border-b border-border bg-bg2 shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green" />
          <span className="text-sm font-medium text-text">OpsAgent</span>
        </div>
        <div className="flex items-center gap-3">
          {isAdmin && (
            <SafetyToggle value={safetyMode} onChange={setSafetyMode} />
          )}
          {isAdmin && (
            <button
              className={`p-1.5 rounded text-xs transition-colors ${
                showTerminal
                  ? 'bg-accent-dim text-accent'
                  : 'text-text3 hover:text-text hover:bg-card'
              }`}
              title="终端"
              onClick={() => setShowTerminal((v) => !v)}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </button>
          )}
          {isAdmin && artifactCount > 0 && (
            <button
              className={`relative p-1.5 rounded text-xs transition-colors ${
                artifactIsOpen
                  ? 'bg-accent-dim text-accent'
                  : 'text-text3 hover:text-text hover:bg-card'
              }`}
              title="查看 Artifact 文件"
              onClick={() => useArtifactStore.getState().setOpen(true)}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 rounded-full bg-accent text-[10px] font-bold text-[#0f172a] flex items-center justify-center px-1">
                {artifactCount}
              </span>
            </button>
          )}
          {isAdmin && (
            <div className="flex items-center bg-bg rounded border border-border text-xs">
              <button
                className={`px-2.5 py-1 rounded-l transition-colors ${
                  tab === 'patrol' ? 'bg-accent-dim text-accent' : 'text-text3 hover:text-text'
                }`}
                onClick={() => { setTab('patrol'); setShowTerminal(false) }}
              >
                巡检
              </button>
              <button
                className={`px-2.5 py-1 rounded-r transition-colors ${
                  tab === 'admin' ? 'bg-accent-dim text-accent' : 'text-text3 hover:text-text'
                }`}
                onClick={() => { setTab('admin'); setShowTerminal(false) }}
              >
                管理
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 3-column body */}
      <div className="flex flex-1 min-h-0">
        {/* Left: conversation sidebar (resizable) */}
        <div className="shrink-0 overflow-y-auto bg-bg" style={{ width: sidebarWidth }}>
          <ConversationSidebar />
        </div>

        {/* Drag handle */}
        <div
          className="shrink-0 w-1 cursor-col-resize bg-border hover:bg-accent/50 transition-colors"
          onMouseDown={handleMouseDown}
        />

        {/* Center: chat panel */}
        <div className="flex flex-col flex-1 min-w-0 border-r border-border">
          <ChatPanel />
        </div>

        {/* Right: context panel (admin only) */}
        {isAdmin && (
          <div className="flex flex-col min-w-0 overflow-hidden" style={{ flex: '0 0 40%' }}>
            {artifactIsOpen ? (
              <ArtifactsPanel />
            ) : showTerminal ? (
              <TerminalPanel />
            ) : tab === 'patrol' ? (
              <PatrolPanel />
            ) : (
              <AdminPanel />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
