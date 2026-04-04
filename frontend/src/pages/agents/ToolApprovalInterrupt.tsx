/**
 * ToolApprovalInterrupt — 3-way approval component (approve / reject / edit)
 * adapted from deep-agents-ui for the ServerHub project.
 *
 * Approval endpoint: POST /api/agents/approvals/${approvalId}
 *   Approve:          { action: 'approve' }
 *   Reject:           { action: 'reject', reason: '...' }
 *   Edit then approve:{ action: 'approve', edited_args: { ... } }
 */

import { useState } from 'react'
import { AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'
import client from '@/api/client'
import { useChatStore } from '@/stores/chatStore'

/* ── Types ──────────────────────────────────────────────── */

interface ToolAction {
  name: string
  args: Record<string, unknown>
}

export interface ToolApprovalInterruptProps {
  approvalId: string
  description?: string
  actions?: ToolAction[]
  onResolved: () => void
}

type Mode = 'default' | 'reject' | 'edit'

/* ── Component ──────────────────────────────────────────── */

export function ToolApprovalInterrupt({
  approvalId,
  description,
  actions = [],
  onResolved,
}: ToolApprovalInterruptProps) {
  const [mode, setMode] = useState<Mode>('default')
  const [loading, setLoading] = useState(false)
  const [rejectReason, setRejectReason] = useState('')

  // Per-action edited argument text (JSON string)
  const [editedArgs, setEditedArgs] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    actions.forEach((a) => {
      init[a.name] = JSON.stringify(a.args, null, 2)
    })
    return init
  })

  const pushMsg = useChatStore((s) => s.pushMsg)

  /* ── Helpers ──────────────────────────────────────────── */

  async function sendApproval(body: Record<string, unknown>) {
    setLoading(true)
    try {
      await client.post(`/api/agents/approvals/${approvalId}`, body)
      const resultLabel =
        body.action === 'approve' ? '✅ 已批准操作' : '❌ 已拒绝操作'
      pushMsg({ role: 'assistant', content: resultLabel })
      onResolved()
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? '操作失败，请重试'
      toast.error(detail)
    } finally {
      setLoading(false)
    }
  }

  function handleApprove() {
    void sendApproval({ action: 'approve' })
  }

  function handleRejectConfirm() {
    void sendApproval({ action: 'reject', reason: rejectReason || undefined })
  }

  function handleSaveAndApprove() {
    // Merge all edited args back into a flat object keyed by action name
    const merged: Record<string, unknown> = {}
    let parseError = false

    for (const [name, text] of Object.entries(editedArgs)) {
      try {
        merged[name] = JSON.parse(text)
      } catch {
        toast.error(`"${name}" 的参数不是合法 JSON`)
        parseError = true
        break
      }
    }

    if (!parseError) {
      void sendApproval({ action: 'approve', edited_args: merged })
    }
  }

  /* ── Shared button base ───────────────────────────────── */

  const btnBase = 'rounded px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50'

  /* ── Render ───────────────────────────────────────────── */

  return (
    <div className={cn('rounded-lg border border-border bg-bg2/60 p-4 max-w-[90%]')}>
      {/* Header */}
      <div className="mb-3 flex items-center gap-1.5">
        <AlertCircle size={14} className="text-yellow flex-shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wide text-yellow">
          需要审批
        </span>
      </div>

      {/* Description */}
      {description && (
        <p className="mb-3 text-sm text-text2 whitespace-pre-wrap leading-relaxed">
          {description}
        </p>
      )}

      {/* Actions list */}
      {actions.length > 0 && (
        <div className="mb-4 space-y-2">
          {actions.map((action, i) => (
            <div key={i}>
              <div className="mb-1 font-mono text-sm font-medium text-text">
                {action.name}
              </div>
              <pre
                className={cn(
                  'rounded border border-border bg-bg/50 p-2',
                  'font-mono text-xs text-text2 whitespace-pre-wrap break-all',
                  'max-h-48 overflow-y-auto',
                )}
              >
                {JSON.stringify(action.args, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}

      {/* ── Default mode ───────────────────────────────── */}
      {mode === 'default' && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMode('reject')}
            disabled={loading}
            className={cn(
              btnBase,
              'bg-red/20 text-red border border-red/30 hover:bg-red/30',
            )}
          >
            拒绝
          </button>
          <button
            onClick={() => setMode('edit')}
            disabled={loading}
            className={cn(
              btnBase,
              'bg-bg2 text-text2 border border-border hover:bg-bg2/80',
            )}
          >
            编辑
          </button>
          <button
            onClick={handleApprove}
            disabled={loading}
            className={cn(
              btnBase,
              'bg-green/20 text-green border border-green/30 hover:bg-green/30',
            )}
          >
            {loading ? '处理中…' : '批准'}
          </button>
        </div>
      )}

      {/* ── Reject mode ────────────────────────────────── */}
      {mode === 'reject' && (
        <div className="space-y-3">
          <label className="block text-xs text-text2">拒绝原因（可选）</label>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={3}
            placeholder="请输入拒绝原因…"
            className={cn(
              'w-full rounded border border-border bg-bg px-3 py-2',
              'text-sm text-text font-mono',
              'focus:border-accent focus:outline-none resize-none',
            )}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMode('default')}
              disabled={loading}
              className={cn(
                btnBase,
                'bg-bg2 text-text2 border border-border hover:bg-bg2/80',
              )}
            >
              取消
            </button>
            <button
              onClick={handleRejectConfirm}
              disabled={loading}
              className={cn(
                btnBase,
                'bg-red/20 text-red border border-red/30 hover:bg-red/30',
              )}
            >
              {loading ? '处理中…' : '确认拒绝'}
            </button>
          </div>
        </div>
      )}

      {/* ── Edit mode ──────────────────────────────────── */}
      {mode === 'edit' && (
        <div className="space-y-3">
          {actions.length === 0 ? (
            <p className="text-xs text-text3">（没有可编辑的参数）</p>
          ) : (
            actions.map((action, i) => (
              <div key={i}>
                <label className="mb-1 block font-mono text-xs font-medium text-text">
                  {action.name}
                </label>
                <textarea
                  value={editedArgs[action.name] ?? '{}'}
                  onChange={(e) =>
                    setEditedArgs((prev) => ({
                      ...prev,
                      [action.name]: e.target.value,
                    }))
                  }
                  rows={6}
                  spellCheck={false}
                  className={cn(
                    'w-full rounded border border-border bg-bg px-3 py-2',
                    'text-sm text-text font-mono',
                    'focus:border-accent focus:outline-none resize-y',
                  )}
                />
              </div>
            ))
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMode('default')}
              disabled={loading}
              className={cn(
                btnBase,
                'bg-bg2 text-text2 border border-border hover:bg-bg2/80',
              )}
            >
              取消
            </button>
            <button
              onClick={handleSaveAndApprove}
              disabled={loading}
              className={cn(
                btnBase,
                'bg-green/20 text-green border border-green/30 hover:bg-green/30',
              )}
            >
              {loading ? '处理中…' : '保存并批准'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
