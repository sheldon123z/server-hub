/**
 * AgentsPage - AI OpsAgent full-page interface with 3-column layout.
 * Sidebar | Chat (always visible) | Right panel (patrol/admin/terminal)
 */

import { useState, useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'
import { ConversationSidebar } from './ConversationSidebar'
import { ChatPanel } from './ChatPanel'
import { PatrolPanel } from './PatrolPanel'
import { AdminPanel } from './AdminPanel'
import { TerminalPanel } from './TerminalPanel'
import { SafetyToggle } from './SafetyToggle'

type RightTab = 'patrol' | 'admin'

export default function AgentsPage() {
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const { safetyMode, setSafetyMode } = useChatStore()
  const [tab, setTab] = useState<RightTab>(() => {
    const saved = localStorage.getItem('agents-tab')
    return (saved === 'patrol' || saved === 'admin') ? saved : 'patrol'
  })
  const [showTerminal, setShowTerminal] = useState(false)

  // Persist tab selection to localStorage
  useEffect(() => {
    localStorage.setItem('agents-tab', tab)
  }, [tab])

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
      <div
        className="flex-1 min-h-0"
        style={{
          display: 'grid',
          gridTemplateColumns: isAdmin ? '180px 1fr 1fr' : '180px 1fr',
        }}
      >
        {/* Left: conversation sidebar */}
        <div className="border-r border-border overflow-y-auto bg-bg">
          <ConversationSidebar />
        </div>

        {/* Center: chat panel (always visible) */}
        <div className="flex flex-col min-w-0 border-r border-border">
          <ChatPanel />
        </div>

        {/* Right: context panel (admin only) */}
        {isAdmin && (
          <div className="flex flex-col min-w-0 overflow-hidden">
            {showTerminal ? (
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
